"""Read ERA5-Land hourly ARCO chunks and checkpoint 2026 UTC country days.

Only the existing `daily` table is written. Baseline history and normals stay intact.
"""
import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone

import cdsapi
import numpy as np
import requests
import xarray as xr
from sqlalchemy import text

from backend.db import ROOT, engine, init_schema
from backend.etl.ingest import load_or_build_weights

URL = ('https://arco.datastores.ecmwf.int/cadl-arco-time-007/arco/'
       'reanalysis_era5_land/sfc-2m-temperature/timeChunked.zarr')
CHECKPOINT = ROOT / 'data' / 'arco-2026-days.jsonl'


def open_arco():
    key = cdsapi.Client(quiet=True).key
    if not key:
        raise RuntimeError('CDS API key is required for ARCO access')
    probe = requests.get(URL + '/.zmetadata',
                         headers={'Authorization': f'Bearer {key}'}, timeout=30)
    if probe.status_code in (401, 403):
        raise RuntimeError('ARCO access denied: sign in to CDS and accept the required site policies')
    probe.raise_for_status()
    return xr.open_zarr(URL, consolidated=True, chunks=None,
                        storage_options={'headers': {'Authorization': f'Bearer {key}'}})


def read_hour(da, index: int):
    for attempt in range(5):
        try:
            return np.asarray(da.isel(time=index).values, dtype=np.float32)
        except Exception as exc:
            if getattr(exc, 'status', None) in (401, 403):
                raise RuntimeError('ARCO access denied: check CDS site policies and dataset licence') from exc
            if attempt == 4:
                raise
            delay = min(60, 5 * 2 ** attempt)
            print(f'ARCO hour read failed ({type(exc).__name__}); retry in {delay}s', flush=True)
            time.sleep(delay)


def country_rows(day: date, da, weights: dict):
    start = np.datetime64(day.isoformat() + 'T00:00:00', 'h')
    expected = start + np.arange(24).astype('timedelta64[h]')
    day_data = da.sel(time=slice(expected[0], expected[-1]))
    actual = day_data.time.values.astype('datetime64[h]')
    if not np.array_equal(actual, expected):
        raise ValueError(f'{day}: expected 24 complete UTC hours, got {len(actual)}')

    sums = np.zeros((da.sizes['latitude'], da.sizes['longitude']), dtype=np.float64)
    counts = np.zeros(sums.shape, dtype=np.uint8)
    for hour in range(24):
        values = read_hour(day_data, hour)
        valid = np.isfinite(values)
        sums[valid] += values[valid]
        counts[valid] += 1
    daily_grid = np.full(sums.shape, np.nan, dtype=np.float32)
    np.divide(sums, counts, out=daily_grid, where=counts > 0)
    flat = daily_grid.ravel()

    provisional = (datetime.now(timezone.utc).date() - day).days <= 90
    rows = []
    for iso, info in weights.items():
        ix, areas = info['indexes'], info['weights']
        if not len(ix):
            continue
        values = flat[ix]
        valid = np.isfinite(values)
        if valid.any():
            rows.append({'iso': iso, 'day': day, 'mmdd': day.strftime('%m-%d'),
                         'temp': float(np.average(values[valid], weights=areas[valid]) - 273.15),
                         'provisional': provisional})
    return rows


def completed_days():
    if not CHECKPOINT.exists():
        return set()
    return {json.loads(line)['day'] for line in CHECKPOINT.read_text(encoding='utf8').splitlines() if line.strip()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-date', type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument('--through-date', type=date.fromisoformat)
    parser.add_argument('--max-days', type=int, help='Stop after this many newly processed days')
    parser.add_argument('--validate-day', type=date.fromisoformat,
                        help='Compare one ARCO UTC day with saved CDS baseline; write nothing')
    args = parser.parse_args()
    if not args.validate_day and (args.from_date.year != 2026 or
                                  (args.through_date and args.through_date.year != 2026)):
        parser.error('This importer is limited to 2026')
    if args.max_days is not None and args.max_days < 1:
        parser.error('--max-days must be positive')

    init_schema()
    with engine.connect() as conn:
        mode = conn.execute(text('SELECT mode FROM dataset_info WHERE id=1')).scalar()
        expected_countries = conn.execute(text("SELECT COUNT(*) FROM countries WHERE quality != 'unavailable'")).scalar()
    if mode not in ('building', 'era5_land') or expected_countries < 180:
        raise SystemExit('Existing PostGIS country catalogue and streaming build are required')

    ds = open_arco()
    try:
        da = ds['t2m']
        if da.attrs.get('units') != 'K':
            raise ValueError('Unexpected ARCO temperature units')
        available_end = date.fromisoformat(str(da.time.values[-1].astype('datetime64[D]')))
        if str(da.time.values[-1]).split('T')[1][:2] != '23':
            available_end -= timedelta(days=1)
        first = args.validate_day or args.from_date
        last = args.validate_day or min(args.through_date or available_end, available_end, date(2026, 12, 31))
        if last < first:
            raise SystemExit(f'No ARCO data in requested range; latest complete UTC day is {available_end}')

        lats, lons = da.latitude.values, da.longitude.values
        first_hour = da.sel(time=first.isoformat() + 'T00:00:00').values
        weights = load_or_build_weights(lats, lons, np.isfinite(first_hour), ROOT / 'public' / 'countries.geojson')
        if len(weights) < 190:
            raise ValueError(f'Only {len(weights)} country geometries available')
        print(f'ARCO ready: {first}..{last}, {len(weights)} countries, latest UTC day {available_end}', flush=True)

        if args.validate_day:
            rows = country_rows(first, da, weights)
            with engine.connect() as conn:
                baseline = {r[0]: r[1] for r in conn.execute(
                    text('SELECT iso3,temp_c FROM baseline_daily WHERE day=:day'), {'day': first})}
            differences = [abs(r['temp'] - baseline[r['iso']]) for r in rows if r['iso'] in baseline]
            if not differences:
                raise ValueError('No matching CDS baseline rows to validate')
            print(f'Validation {first}: {len(differences)} countries; median absolute difference '
                  f'{np.median(differences):.3f} °C; max {np.max(differences):.3f} °C', flush=True)
            return

        done = completed_days()
        processed = 0
        day = first
        while day <= last:
            if day.isoformat() in done:
                print(f'Skip checkpointed ARCO day {day}', flush=True)
                day += timedelta(days=1)
                continue
            started = time.monotonic()
            rows = country_rows(day, da, weights)
            if len(rows) < expected_countries:
                raise ValueError(f'{day}: only {len(rows)} of {expected_countries} countries have ARCO data')
            with engine.begin() as conn:
                conn.execute(text('''INSERT INTO daily (iso3,day,mmdd,temp_c,provisional)
                    VALUES (:iso,:day,:mmdd,:temp,:provisional)
                    ON CONFLICT(iso3,day) DO UPDATE SET
                    mmdd=excluded.mmdd,temp_c=excluded.temp_c,provisional=excluded.provisional'''), rows)
            with CHECKPOINT.open('a', encoding='utf8') as out:
                out.write(json.dumps({'day': day.isoformat(), 'countries': len(rows), 'source': URL,
                                      'utc_hours': 24}) + '\n')
            processed += 1
            print(f'Committed ARCO {day}: {len(rows)} country days in {time.monotonic()-started:.1f}s', flush=True)
            if args.max_days and processed >= args.max_days:
                break
            day += timedelta(days=1)
    finally:
        ds.close()


if __name__ == '__main__':
    main()
