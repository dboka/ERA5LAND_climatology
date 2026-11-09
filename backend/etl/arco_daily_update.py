"""Append complete ERA5-Land ARCO UTC days to the production PostGIS database.

The database is the checkpoint. Baseline history and normals are never changed.
"""
import argparse
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np
from sqlalchemy import text

from backend.db import ROOT, engine
from backend.etl.arco_2026 import country_rows, open_arco
from backend.etl.arco_backfill import is_transient, store_day
from backend.etl.ingest import load_or_build_weights

DISPLAY_START = date(2020, 1, 1)
LOCK_ID = 17052901


def latest_complete_day(last_hour, today_utc: date) -> date:
    """Exclude a partial final ARCO day and the current UTC day."""
    hour = np.datetime64(last_hour, 'h')
    day = date.fromisoformat(str(hour.astype('datetime64[D]')))
    if str(hour)[11:13] != '23':
        day -= timedelta(days=1)
    return min(day, today_utc - timedelta(days=1))


def stored_state(conn):
    mode = conn.execute(text('SELECT mode FROM dataset_info WHERE id=1')).scalar()
    if mode != 'era5_land':
        raise ValueError(f'Production ERA5-Land database required, found {mode!r}')
    codes = {row[0] for row in conn.execute(text(
        "SELECT iso3 FROM countries WHERE quality != 'unavailable'"))}
    if len(codes) != 188:
        raise ValueError(f'Expected 188 supported countries, found {len(codes)}')
    first, last, days, rows = conn.execute(text(
        'SELECT MIN(day), MAX(day), COUNT(DISTINCT day), COUNT(*) FROM daily')).one()
    if first != DISPLAY_START or last is None:
        raise ValueError('Display history has an unexpected start date')
    expected_days = (last - first).days + 1
    if days != expected_days or rows != expected_days * len(codes):
        raise ValueError('Display history has a missing day or country; repair before appending')
    normals = conn.execute(text('SELECT COUNT(*) FROM normals')).scalar()
    if normals != len(codes) * 366:
        raise ValueError(f'Expected {len(codes) * 366} calendar-day normals, found {normals}')
    return codes, last


def backoff(exc: Exception, failures: int, day: date | None):
    delay = min(1800, max(60, 30 * (2 ** min(failures, 6))))
    status = getattr(exc, 'status', None)
    if status == 429:
        retry_after = (getattr(exc, 'headers', None) or {}).get('Retry-After')
        if retry_after and retry_after.isdigit():
            delay = max(delay, int(retry_after))
    print(f'Transient {type(exc).__name__} on {day or "ARCO open"}; '
          f'attempt {failures}; retry in {delay}s: {str(exc)[:180]}', flush=True)
    time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through-date', type=date.fromisoformat,
                        help='Optional upper UTC day for a controlled run')
    parser.add_argument('--max-days', type=int, help='Append at most N days for a pilot')
    parser.add_argument('--probe', action='store_true', help='Read metadata and report pending days only')
    args = parser.parse_args()
    if args.max_days is not None and args.max_days < 1:
        parser.error('--max-days must be positive')
    if engine.dialect.name != 'postgresql':
        raise SystemExit('Set DATABASE_URL to the production PostGIS database')

    # Session-level advisory lock also protects manually launched runs.
    with engine.connect() as lock_conn:
        locked = lock_conn.execute(text('SELECT pg_try_advisory_lock(:id)'), {'id': LOCK_ID}).scalar()
        lock_conn.commit()
        if not locked:
            raise SystemExit('Another daily ARCO update is running')
        try:
            codes, latest = stored_state(lock_conn)
            lock_conn.commit()
            first = latest + timedelta(days=1)
            ds = None
            failures = 0
            while ds is None:
                try:
                    ds = open_arco()
                except Exception as exc:
                    if args.probe or not is_transient(exc):
                        raise
                    failures += 1
                    backoff(exc, failures, None)
            try:
                da = ds['t2m']
                if da.attrs.get('units') != 'K':
                    raise ValueError('Unexpected ARCO 2m temperature units')
                available = latest_complete_day(da.time.values[-1], datetime.now(timezone.utc).date())
                end = min(available, args.through_date) if args.through_date else available
                pending = max(0, (end - first).days + 1)
                print(f'PostGIS latest={latest}; ARCO latest complete UTC day={available}; '
                      f'pending={pending}', flush=True)
                if args.probe or pending == 0:
                    return

                weights = None
                processed = 0
                day = first
                failures = 0
                while day <= end and (args.max_days is None or processed < args.max_days):
                    started = time.monotonic()
                    try:
                        if ds is None:
                            ds = open_arco()
                            da = ds['t2m']
                            if da.attrs.get('units') != 'K':
                                raise ValueError('Unexpected ARCO 2m temperature units')
                        if weights is None:
                            lats, lons = da.latitude.values, da.longitude.values
                            first_hour = da.sel(time=day.isoformat() + 'T00:00:00').values
                            weights = load_or_build_weights(lats, lons, np.isfinite(first_hour),
                                                            ROOT / 'public' / 'countries.geojson')
                            if {iso for iso, info in weights.items() if info['indexes'].size} != codes:
                                raise ValueError('ARCO grid coverage differs from production country catalogue')
                        rows = country_rows(day, da, weights)
                        if {row['iso'] for row in rows} != codes:
                            raise ValueError(f'{day}: incomplete country values: {len(rows)} of {len(codes)}')
                        store_day(day, rows)
                        print(f'Committed ARCO {day}: {len(rows)} countries in '
                              f'{time.monotonic() - started:.1f}s', flush=True)
                        processed += 1
                        day += timedelta(days=1)
                        failures = 0
                    except Exception as exc:
                        if not is_transient(exc):
                            raise
                        failures += 1
                        if ds is not None:
                            ds.close()
                        ds = None
                        da = None
                        backoff(exc, failures, day)
                print(f'Daily update complete: {processed} new UTC days; latest committed '
                      f'{day - timedelta(days=1)}', flush=True)
            finally:
                if ds is not None:
                    ds.close()
        finally:
            lock_conn.execute(text('SELECT pg_advisory_unlock(:id)'), {'id': LOCK_ID})
            lock_conn.commit()


if __name__ == '__main__':
    main()
