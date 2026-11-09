"""Resume the historical ERA5-Land country-day build from hourly ARCO Zarr.

One UTC day is committed at a time. Completed CDS months and 2026 daily rows
are retained; the database itself is the resume checkpoint.
"""
import argparse
import calendar
import time
from datetime import date, timedelta

import aiohttp
import numpy as np
import requests
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.db import ROOT, engine, init_schema
from backend.etl.arco_2026 import country_rows, open_arco
from backend.etl.ingest import finalize_baseline, load_or_build_weights

BASELINE_START = date(1991, 1, 1)
BASELINE_END = date(2020, 12, 31)
DISPLAY_START = date(2020, 1, 1)
BACKFILL_END = date(2025, 12, 31)


def complete_days(table: str, countries: int) -> set[date]:
    if table not in ('baseline_daily', 'daily'):
        raise ValueError('Unsupported checkpoint table')
    with engine.connect() as conn:
        rows = conn.execute(text(f'''SELECT d.day FROM {table} d
            JOIN countries c ON c.iso3=d.iso3 AND c.quality != 'unavailable'
            GROUP BY d.day HAVING COUNT(*) = :countries'''), {'countries': countries})
        return {row[0] for row in rows}


def needs_day(day: date, baseline_done: set[date], daily_done: set[date]) -> bool:
    return (day <= BASELINE_END and day not in baseline_done) or (day >= DISPLAY_START and day not in daily_done)


def is_transient(exc: Exception) -> bool:
    if isinstance(exc, aiohttp.ClientResponseError):
        return exc.status == 429 or 500 <= exc.status < 600
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        return status is None or status == 429 or 500 <= status < 600
    return isinstance(exc, (aiohttp.ClientError, requests.RequestException, OperationalError,
                            ConnectionError, TimeoutError, OSError))


def store_day(day: date, rows: list[dict]) -> None:
    with engine.begin() as conn:
        if day <= BASELINE_END:
            conn.execute(text('''INSERT INTO baseline_daily (iso3,day,mmdd,temp_c)
                VALUES (:iso,:day,:mmdd,:temp)
                ON CONFLICT(iso3,day) DO UPDATE SET mmdd=excluded.mmdd,temp_c=excluded.temp_c'''), rows)
        if day >= DISPLAY_START:
            conn.execute(text('''INSERT INTO daily (iso3,day,mmdd,temp_c,provisional)
                VALUES (:iso,:day,:mmdd,:temp,:provisional)
                ON CONFLICT(iso3,day) DO UPDATE SET
                mmdd=excluded.mmdd,temp_c=excluded.temp_c,provisional=excluded.provisional'''), rows)


def checkpoint_month(day: date, baseline_done: set[date], daily_done: set[date]) -> None:
    last = calendar.monthrange(day.year, day.month)[1]
    month_days = [date(day.year, day.month, number) for number in range(1, last + 1)]
    if all(not needs_day(value, baseline_done, daily_done) for value in month_days):
        with engine.begin() as conn:
            conn.execute(text('''INSERT INTO ingested_months (month) VALUES (:month)
                ON CONFLICT(month) DO NOTHING'''), {'month': day.strftime('%Y-%m')})


def verify_complete(countries: int) -> None:
    baseline_days = (BASELINE_END - BASELINE_START).days + 1
    with engine.connect() as conn:
        baseline = conn.execute(text('''SELECT iso3,COUNT(*) FROM baseline_daily
            WHERE day BETWEEN :first AND :last GROUP BY iso3'''),
            {'first': BASELINE_START, 'last': BASELINE_END}).all()
        latest = conn.execute(text('SELECT MAX(day) FROM daily')).scalar()
        daily = conn.execute(text('''SELECT iso3,COUNT(*) FROM daily
            WHERE day BETWEEN :first AND :last GROUP BY iso3'''),
            {'first': DISPLAY_START, 'last': latest}).all()
    expected_daily_days = (latest - DISPLAY_START).days + 1 if latest else 0
    if (len(baseline) != countries or any(count != baseline_days for _, count in baseline)
            or len(daily) != countries or any(count != expected_daily_days for _, count in daily)):
        raise ValueError('Historical or display country-day coverage is incomplete; normals not finalized')
    print(f'Coverage verified: {countries} countries, {baseline_days} baseline days and '
          f'{expected_daily_days} display days each', flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--through-date', type=date.fromisoformat, default=BACKFILL_END)
    parser.add_argument('--max-days', type=int, help='Process at most N missing days for a pilot')
    args = parser.parse_args()
    if args.through_date < BASELINE_START or args.through_date > BACKFILL_END:
        parser.error('--through-date must be within 1991–2025')
    if args.max_days is not None and args.max_days < 1:
        parser.error('--max-days must be positive')

    init_schema()
    with engine.connect() as conn:
        mode = conn.execute(text('SELECT mode FROM dataset_info WHERE id=1')).scalar()
        countries = conn.execute(text("SELECT COUNT(*) FROM countries WHERE quality != 'unavailable'")).scalar()
    if mode != 'building' or countries < 180:
        raise SystemExit('Existing building-mode PostGIS database with country catalogue is required')

    baseline_done = complete_days('baseline_daily', countries)
    daily_done = complete_days('daily', countries)
    day = BASELINE_START
    while day <= args.through_date and not needs_day(day, baseline_done, daily_done):
        day += timedelta(days=1)
    if day > args.through_date:
        print('All requested days already stored.', flush=True)
        if args.through_date == BACKFILL_END and args.max_days is None:
            verify_complete(countries)
            finalize_baseline()
        return
    print(f'First missing UTC day: {day}; preserved {len(baseline_done)} baseline and '
          f'{len(daily_done)} display day checkpoints', flush=True)

    ds = None
    da = None
    weights = None
    failures = 0
    processed = 0
    try:
        while day <= args.through_date:
            if not needs_day(day, baseline_done, daily_done):
                day += timedelta(days=1)
                continue
            started = time.monotonic()
            try:
                if ds is None:
                    ds = open_arco()
                    da = ds['t2m']
                    if da.attrs.get('units') != 'K':
                        raise ValueError('Unexpected ARCO 2m temperature units')
                    available = date.fromisoformat(str(da.time.values[-1].astype('datetime64[D]')))
                    if available < args.through_date:
                        raise ValueError(f'ARCO ends at {available}, before requested {args.through_date}')
                if weights is None:
                    lats, lons = da.latitude.values, da.longitude.values
                    first_hour = da.sel(time=day.isoformat() + 'T00:00:00').values
                    weights = load_or_build_weights(lats, lons, np.isfinite(first_hour),
                                                    ROOT / 'public' / 'countries.geojson')
                    if sum(bool(info['indexes'].size) for info in weights.values()) != countries:
                        raise ValueError('ARCO grid coverage differs from stored country catalogue')
                rows = country_rows(day, da, weights)
                if len(rows) != countries:
                    raise ValueError(f'{day}: {len(rows)} country values; expected {countries}')
                store_day(day, rows)
                if day <= BASELINE_END:
                    baseline_done.add(day)
                if day >= DISPLAY_START:
                    daily_done.add(day)
                if day.day == calendar.monthrange(day.year, day.month)[1]:
                    checkpoint_month(day, baseline_done, daily_done)
                failures = 0
                processed += 1
                print(f'Committed ARCO {day}: {len(rows)} countries, '
                      f'baseline={day <= BASELINE_END}, daily={day >= DISPLAY_START}, '
                      f'{time.monotonic()-started:.1f}s', flush=True)
                if args.max_days and processed >= args.max_days:
                    break
                day += timedelta(days=1)
            except Exception as exc:
                if not is_transient(exc):
                    raise
                failures += 1
                delay = min(1800, max(60, 30 * (2 ** min(failures, 6))))
                if isinstance(exc, aiohttp.ClientResponseError) and exc.status == 429:
                    retry_after = (exc.headers or {}).get('Retry-After')
                    if retry_after and retry_after.isdigit():
                        delay = max(delay, int(retry_after))
                print(f'Transient {type(exc).__name__} on {day}; attempt {failures}, '
                      f'retry after {delay}s: {str(exc)[:180]}', flush=True)
                if ds is not None:
                    ds.close()
                ds = None
                da = None
                time.sleep(delay)
    finally:
        if ds is not None:
            ds.close()

    if day >= args.through_date and args.through_date == BACKFILL_END and args.max_days is None:
        verify_complete(countries)
        finalize_baseline()
        print('ARCO historical build complete; 1991–2020 normals finalized.', flush=True)
    else:
        print(f'Paused pilot after {processed} newly committed days; normals unchanged.', flush=True)


if __name__ == '__main__':
    main()
