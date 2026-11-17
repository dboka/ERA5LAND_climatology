"""Resume ERA5-Land ARCO precipitation import into the existing PostGIS database.

The source contains de-accumulated hourly total precipitation in metres. A UTC
day is the sum of its 24 hours, converted to millimetres and area averaged by
the same country grid weights used for temperature. Each day is committed in
one transaction; the two destination tables are the resume checkpoints.
"""
import argparse
import time
from datetime import date, timedelta

import cdsapi
import numpy as np
import requests
import xarray as xr
from sqlalchemy import text

from backend.db import ROOT, engine, init_schema
from backend.etl.arco_2026 import read_hour
from backend.etl.arco_backfill import is_transient
from backend.etl.ingest import load_or_build_weights

URL = ('https://arco.datastores.ecmwf.int/cadl-arco-time-009/arco/'
       'reanalysis_era5_land/sfc-pressure-precipitation/timeChunked.zarr')
FIRST = date(1991, 1, 1)
BASELINE_LAST = date(2020, 12, 31)
DISPLAY_FIRST = date(2020, 1, 1)
LAST = date(2026, 11, 3)
LOCK_ID = 17052902


def open_precipitation():
    key = cdsapi.Client(quiet=True).key
    if not key:
        raise RuntimeError('CDS API key is required for ARCO access')
    headers = {'Authorization': f'Bearer {key}'}
    probe = requests.get(URL + '/.zmetadata', headers=headers, timeout=30)
    if probe.status_code in (401, 403):
        raise RuntimeError('ARCO access denied: check CDS site policies and dataset licence')
    probe.raise_for_status()
    return xr.open_zarr(URL, consolidated=True, chunks=None,
                        storage_options={'headers': headers})


def completed_days(table: str, countries: int) -> set[date]:
    if table not in ('precipitation_baseline_daily', 'precipitation_daily'):
        raise ValueError('Unsupported checkpoint table')
    with engine.connect() as conn:
        return {row[0] for row in conn.execute(text(f'''
            SELECT day FROM {table} GROUP BY day HAVING COUNT(*) = :countries'''),
            {'countries': countries})}


def needs_day(day: date, baseline_done: set[date], display_done: set[date]) -> bool:
    return ((day <= BASELINE_LAST and day not in baseline_done)
            or (day >= DISPLAY_FIRST and day not in display_done))


def country_rows(day: date, da, weights: dict) -> list[dict]:
    start = np.datetime64(day.isoformat() + 'T00:00:00', 'h')
    expected = start + np.arange(24).astype('timedelta64[h]')
    day_data = da.sel(time=slice(expected[0], expected[-1]))
    actual = day_data.time.values.astype('datetime64[h]')
    if not np.array_equal(actual, expected):
        raise ValueError(f'{day}: expected 24 complete UTC hours, got {len(actual)}')

    shape = (da.sizes['latitude'], da.sizes['longitude'])
    totals = np.zeros(shape, dtype=np.float32)
    counts = np.zeros(shape, dtype=np.uint8)
    for hour in range(24):
        values = read_hour(day_data, hour)
        valid = np.isfinite(values)
        # Tiny negative values can occur from forecast de-accumulation rounding.
        if np.any(values[valid] < -1e-6):
            raise ValueError(f'{day} hour {hour}: materially negative precipitation')
        np.maximum(values, 0, out=values)
        totals[valid] += values[valid]
        counts[valid] += 1
    flat_totals = totals.ravel()
    flat_counts = counts.ravel()

    rows = []
    for iso, info in weights.items():
        indexes, areas = info['indexes'], info['weights']
        if not len(indexes):
            continue
        complete = flat_counts[indexes] == 24
        if not complete.any():
            continue
        mm = float(np.average(flat_totals[indexes[complete]],
                              weights=areas[complete]) * 1000)
        rows.append({'iso': iso, 'day': day, 'mmdd': day.strftime('%m-%d'),
                     'precip': mm})
    return rows


def store_day(day: date, rows: list[dict]) -> None:
    with engine.begin() as conn:
        if day <= BASELINE_LAST:
            conn.execute(text('''INSERT INTO precipitation_baseline_daily
                (iso3,day,mmdd,precip_mm) VALUES (:iso,:day,:mmdd,:precip)
                ON CONFLICT(iso3,day) DO UPDATE SET
                mmdd=excluded.mmdd,precip_mm=excluded.precip_mm'''), rows)
        if day >= DISPLAY_FIRST:
            conn.execute(text('''INSERT INTO precipitation_daily
                (iso3,day,mmdd,precip_mm) VALUES (:iso,:day,:mmdd,:precip)
                ON CONFLICT(iso3,day) DO UPDATE SET
                mmdd=excluded.mmdd,precip_mm=excluded.precip_mm'''), rows)


def finalize_normals(countries: int) -> None:
    expected_days = (BASELINE_LAST - FIRST).days + 1
    display_days = (LAST - DISPLAY_FIRST).days + 1
    with engine.begin() as conn:
        coverage = conn.execute(text('''SELECT iso3, COUNT(*) FROM precipitation_baseline_daily
            GROUP BY iso3''')).all()
        if len(coverage) != countries or any(count != expected_days for _, count in coverage):
            raise ValueError('Precipitation baseline is incomplete; normals not finalized')
        display_coverage = conn.execute(text('''SELECT iso3, COUNT(*) FROM precipitation_daily
            GROUP BY iso3''')).all()
        if (len(display_coverage) != countries or
                any(count != display_days for _, count in display_coverage)):
            raise ValueError('Precipitation display archive is incomplete; normals not finalized')
        conn.execute(text('DELETE FROM precipitation_normals'))
        conn.execute(text('''INSERT INTO precipitation_normals (iso3,mmdd,precip_mm)
            SELECT iso3,mmdd,AVG(precip_mm) FROM precipitation_baseline_daily
            GROUP BY iso3,mmdd'''))
    print(f'Finalized precipitation normals: {countries} countries x 366 calendar days', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through-date', type=date.fromisoformat, default=LAST)
    parser.add_argument('--max-days', type=int, help='Stop after N newly imported days')
    parser.add_argument('--probe', action='store_true', help='Inspect source and checkpoints without importing data')
    args = parser.parse_args()
    if not FIRST <= args.through_date <= LAST:
        parser.error('--through-date must be in 1991-01-01..2026-11-03')
    if args.max_days is not None and args.max_days < 1:
        parser.error('--max-days must be positive')
    if engine.dialect.name != 'postgresql':
        raise SystemExit('Set DATABASE_URL to the existing PostGIS database')

    init_schema()
    with engine.connect() as lock_conn:
        if not lock_conn.execute(text('SELECT pg_try_advisory_lock(:id)'), {'id': LOCK_ID}).scalar():
            raise SystemExit('Another precipitation import is running')
        lock_conn.commit()
        try:
            mode = lock_conn.execute(text('SELECT mode FROM dataset_info WHERE id=1')).scalar()
            codes = {row[0] for row in lock_conn.execute(text(
                "SELECT iso3 FROM countries WHERE quality != 'unavailable'"))}
            lock_conn.commit()
            if mode != 'era5_land' or len(codes) != 188:
                raise ValueError(f'Expected production ERA5-Land database with 188 countries; found {mode}, {len(codes)}')
            baseline_done = completed_days('precipitation_baseline_daily', len(codes))
            display_done = completed_days('precipitation_daily', len(codes))
            ds = open_precipitation()
            try:
                da = ds['tp']
                if da.attrs.get('units') != 'm':
                    raise ValueError(f'Unexpected precipitation units: {da.attrs.get("units")!r}')
                available = da.time.values[-1].astype('datetime64[h]')
                if available < np.datetime64(args.through_date.isoformat() + 'T23', 'h'):
                    raise ValueError(f'ARCO ends at {available}, before requested {args.through_date} 23:00')
                missing = sum(needs_day(FIRST + timedelta(days=n), baseline_done, display_done)
                              for n in range((args.through_date - FIRST).days + 1))
                print(f'Precipitation source ready; complete baseline days={len(baseline_done)}, '
                      f'display days={len(display_done)}, pending UTC days={missing}', flush=True)
                if args.probe or not missing:
                    if not args.probe and not missing and args.through_date == LAST:
                        finalize_normals(len(codes))
                    return
                weights = None
                processed = 0
                day = FIRST
                failures = 0
                while day <= args.through_date:
                    if not needs_day(day, baseline_done, display_done):
                        day += timedelta(days=1)
                        continue
                    started = time.monotonic()
                    try:
                        if ds is None:
                            ds = open_precipitation()
                            da = ds['tp']
                        if weights is None:
                            first_hour = da.sel(time=day.isoformat() + 'T00:00:00').values
                            weights = load_or_build_weights(da.latitude.values, da.longitude.values,
                                                            np.isfinite(first_hour),
                                                            ROOT / 'public' / 'countries.geojson')
                            weighted_codes = {iso for iso, info in weights.items() if info['indexes'].size}
                            if weighted_codes != codes:
                                raise ValueError(f'Precipitation grid covers {len(weighted_codes)} countries, expected {len(codes)}')
                        rows = country_rows(day, da, weights)
                        if {row['iso'] for row in rows} != codes:
                            raise ValueError(f'{day}: incomplete country values: {len(rows)} of {len(codes)}')
                        store_day(day, rows)
                        if day <= BASELINE_LAST:
                            baseline_done.add(day)
                        if day >= DISPLAY_FIRST:
                            display_done.add(day)
                        processed += 1
                        failures = 0
                        print(f'Committed precipitation {day}: {len(rows)} countries, '
                              f'{time.monotonic()-started:.1f}s', flush=True)
                        if args.max_days and processed >= args.max_days:
                            break
                        day += timedelta(days=1)
                    except Exception as exc:
                        if not is_transient(exc):
                            raise
                        failures += 1
                        delay = min(1800, max(60, 30 * 2 ** min(failures, 6)))
                        print(f'Transient {type(exc).__name__} on {day}; retry in {delay}s: '
                              f'{str(exc)[:180]}', flush=True)
                        if ds is not None:
                            ds.close()
                        ds = None
                        time.sleep(delay)
                if args.max_days is None and args.through_date == LAST:
                    finalize_normals(len(codes))
                print(f'Run ended after {processed} new UTC days', flush=True)
            finally:
                if ds is not None:
                    ds.close()
        finally:
            lock_conn.execute(text('SELECT pg_advisory_unlock(:id)'), {'id': LOCK_ID})
            lock_conn.commit()


if __name__ == '__main__':
    main()
