"""One-time country aggregation of monthly ERA5-Land daily NetCDF archives."""
import argparse
import calendar
import hashlib
import json
import tempfile
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import xarray as xr
from pyproj import Geod
from scipy.spatial import cKDTree
from shapely import box, contains, intersects, intersection
from shapely.geometry import shape
from sqlalchemy import text

from backend.db import ROOT, engine, init_schema
from backend.etl.download import DATASET, months

GEOD = Geod(ellps='WGS84')
GRID_STEP = .1
MAX_PROXY_KM = 100


def cell_area(geom) -> float:
    if geom.is_empty:
        return 0.
    return abs(GEOD.geometry_area_perimeter(geom)[0])


def extract_dataset(archive: Path, folder: Path):
    if not zipfile.is_zipfile(archive):
        return xr.open_dataset(archive)
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith('.nc')]
        if len(names) != 1:
            raise ValueError(f'{archive}: expected one NetCDF for 2m temperature, found {names}')
        target = folder / Path(names[0]).name
        with zf.open(names[0]) as src, target.open('wb') as out:
            import shutil
            shutil.copyfileobj(src, out)
        return xr.open_dataset(target)


def normalize(ds):
    var = 't2m' if 't2m' in ds.data_vars else '2m_temperature' if '2m_temperature' in ds.data_vars else next(iter(ds.data_vars))
    da = ds[var]
    lat_name = 'latitude' if 'latitude' in da.coords else 'lat'
    lon_name = 'longitude' if 'longitude' in da.coords else 'lon'
    time_name = 'valid_time' if 'valid_time' in da.coords else 'time'
    if da[lon_name].max() > 180:
        da = da.assign_coords({lon_name: ((da[lon_name] + 180) % 360) - 180}).sortby(lon_name)
    da = da.transpose(time_name, lat_name, lon_name)
    units = da.attrs.get('units', 'K')
    if units not in ('K', 'kelvin'):
        raise ValueError(f'Unexpected temperature units: {units}')
    return da, time_name, lat_name, lon_name


def build_weights(lats: np.ndarray, lons: np.ndarray, valid: np.ndarray, boundaries: Path):
    """Exact polygon intersection for boundary cells; centre cells use full geodesic area."""
    frame = gpd.read_file(boundaries)
    if frame.crs and frame.crs.to_epsg() != 4326:
        frame = frame.to_crs(4326)
    lon_mesh, lat_mesh = np.meshgrid(lons, lats)
    land_coords = np.column_stack((lon_mesh[valid].ravel(), lat_mesh[valid].ravel()))
    tree = cKDTree(land_coords)
    valid_flat = np.flatnonzero(valid.ravel())
    result = {}
    for _, row in frame.iterrows():
        iso = row['iso3']
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        minx, miny, maxx, maxy = geom.bounds
        ys = np.flatnonzero((lats >= miny - GRID_STEP) & (lats <= maxy + GRID_STEP))
        xs = np.flatnonzero((lons >= minx - GRID_STEP) & (lons <= maxx + GRID_STEP))
        indexes, weights = [], []
        if len(ys) and len(xs):
            for y in ys:
                row_xs = xs[valid[y, xs]]
                if not len(row_xs):
                    continue
                cells = box(lons[row_xs]-GRID_STEP/2, lats[y]-GRID_STEP/2,
                            lons[row_xs]+GRID_STEP/2, lats[y]+GRID_STEP/2)
                full = contains(geom, cells)
                touched = intersects(geom, cells)
                whole_area = cell_area(cells[0])
                for j in np.flatnonzero(touched):
                    x = row_xs[j]
                    area = whole_area if full[j] else cell_area(intersection(cells[j], geom))
                    if area > 0:
                        indexes.append(int(y * len(lons) + x))
                        weights.append(area)
        country_area = cell_area(geom)
        covered = sum(weights)
        quality = 'grid' if len(indexes) >= 5 and covered / max(country_area, 1) >= .6 else 'limited' if indexes else 'unavailable'
        proxy = None
        centre = geom.representative_point()
        nominal_cell_area = cell_area(box(centre.x-GRID_STEP/2, centre.y-GRID_STEP/2,
                                         centre.x+GRID_STEP/2, centre.y+GRID_STEP/2))
        if indexes and country_area < nominal_cell_area * .25:
            quality = 'proxy'
            proxy = 'Regional approximation: country occupies less than 25% of one ERA5-Land grid cell'
        if not indexes:
            dist_deg, nearest = tree.query([centre.x, centre.y])
            candidate_index = int(valid_flat[nearest])
            candidate_y, candidate_x = divmod(candidate_index, len(lons))
            _, _, metres = GEOD.inv(centre.x, centre.y, lons[candidate_x], lats[candidate_y])
            if metres <= MAX_PROXY_KM * 1000:
                indexes, weights, quality, proxy = [candidate_index], [1.], 'proxy', f'Regional approximation: nearest land grid cell {metres/1000:.1f} km away'
        result[iso] = {'name': row['name'], 'status':row.get('status','member'), 'geometry': geom, 'indexes': np.asarray(indexes, dtype=np.int64),
                       'weights': np.asarray(weights, dtype=np.float64), 'quality': quality,
                       'coverage': min(1., covered / max(country_area, 1)), 'proxy': proxy}
        print(f'{iso}: {len(indexes)} cells, {quality}, {result[iso]["coverage"]:.0%} coverage', flush=True)
    return result


def load_or_build_weights(lats, lons, valid, boundaries):
    digest = hashlib.sha256(b'country-quality-v3' + lats.tobytes() + lons.tobytes() + valid.tobytes() + boundaries.read_bytes()).hexdigest()
    target = ROOT / 'data' / f'weights-{digest[:20]}.npz'
    if target.exists():
        with np.load(target, allow_pickle=False) as archive:
            metadata = json.loads(str(archive['metadata']))
            result = {iso: {**info, 'geometry': shape(info['geometry']),
                            'indexes': archive[f'i_{iso}'], 'weights': archive[f'w_{iso}']}
                      for iso, info in metadata.items()}
        print(f'Loaded cached grid weights: {target}', flush=True)
        return result
    result = build_weights(lats, lons, valid, boundaries)
    metadata = {iso: {k: (v.__geo_interface__ if k == 'geometry' else v)
                      for k, v in info.items() if k not in ('indexes','weights')}
                for iso, info in result.items()}
    arrays = {'metadata': np.array(json.dumps(metadata))}
    for iso, info in result.items():
        arrays[f'i_{iso}'] = info['indexes']
        arrays[f'w_{iso}'] = info['weights']
    np.savez_compressed(target, **arrays)
    print(f'Saved grid weights: {target}', flush=True)
    return result


def stream_archives(first: date, last: date, completed: set[str]):
    """Retrieve one global month at a time; discard it after country aggregation."""
    import cdsapi
    client = cdsapi.Client()
    with tempfile.TemporaryDirectory() as directory:
        for year, month in months(first, last):
            key = f'{year}-{month:02d}'
            if key in completed:
                print(f'Skip completed month {key}', flush=True)
                continue
            first_day = first.day if (year,month) == (first.year,first.month) else 1
            last_day = last.day if (year,month) == (last.year,last.month) else calendar.monthrange(year,month)[1]
            request = {'variable':['2m_temperature'],'year':str(year),'month':[f'{month:02d}'],
                       'day':[f'{day:02d}' for day in range(first_day,last_day+1)],
                       'daily_statistic':'daily_mean','time_zone':'utc+00:00','frequency':'1_hourly'}
            path = Path(directory) / f'era5_land_t2m_daily_{key}.partial'
            print(f'CDS {key}: {len(request["day"])} UTC days', flush=True)
            # Keep a completed CDS job when a transient TLS/download error occurs.
            # Repeating the download is cheaper and safer than resubmitting the job.
            result = client.retrieve(DATASET, request)
            for attempt in range(1, 6):
                try:
                    result.download(str(path))
                    break
                except Exception as exc:
                    if attempt == 5:
                        raise
                    print(f'Download {key} failed ({type(exc).__name__}); retry {attempt}/4 in {attempt * 30}s', flush=True)
                    import time
                    time.sleep(attempt * 30)
            yield path
            path.unlink(missing_ok=True)


def finalize_baseline(allow_partial: bool = False) -> None:
    expected_days = (date(2021, 1, 1) - date(1991, 1, 1)).days
    with engine.connect() as conn:
        available = conn.execute(text('SELECT COUNT(*) FROM baseline_daily')).scalar()
        coverage = conn.execute(text('''
          SELECT c.iso3, COUNT(b.day) AS days
          FROM countries c LEFT JOIN baseline_daily b ON b.iso3=c.iso3
          WHERE c.quality != 'unavailable'
          GROUP BY c.iso3
        ''')).all()
    if not available:
        raise SystemExit('No 1991–2020 country-day history; refusing to finalize normals')
    missing = [(iso, days) for iso, days in coverage if days != expected_days]
    if missing and not allow_partial:
        raise SystemExit(f'Incomplete 1991–2020 history ({expected_days} days required per available country): {missing[:10]}')
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM normals'))
        conn.execute(text('''INSERT INTO normals (iso3,mmdd,temp_c)
          SELECT iso3,mmdd,AVG(temp_c) FROM baseline_daily GROUP BY iso3,mmdd'''))
        mode = 'pilot' if allow_partial else 'era5_land'
        conn.execute(text('''INSERT INTO dataset_info (id,mode) VALUES (1,:mode)
          ON CONFLICT(id) DO UPDATE SET mode=excluded.mode'''), {'mode':mode})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw', type=Path, default=ROOT / 'data' / 'raw')
    parser.add_argument('--boundaries', type=Path, default=ROOT / 'public' / 'countries.geojson')
    parser.add_argument('--update', action='store_true', help='Only refresh recent daily values; preserve 1991–2020 normals')
    parser.add_argument('--stream', action='store_true', help='Initial build with monthly CDS retrieval and resumable DB checkpoints')
    parser.add_argument('--resume-raw', action='store_true', help='Ingest local monthly files into an existing streaming build without clearing it')
    parser.add_argument('--allow-partial-baseline', action='store_true', help='For isolated pilot databases only; results remain marked pilot and cannot serve as ERA5-Land')
    parser.add_argument('--from-date', type=date.fromisoformat, default=date(1991,1,1))
    parser.add_argument('--through-date', type=date.fromisoformat, default=datetime.now(timezone.utc).date()-timedelta(days=6))
    args = parser.parse_args()
    if sum((args.stream, args.update, args.resume_raw)) > 1:
        raise SystemExit('--stream, --update and --resume-raw cannot be combined')
    if args.stream and args.allow_partial_baseline:
        raise SystemExit('Streaming production build cannot use --allow-partial-baseline')
    if args.stream and (args.from_date != date(1991,1,1) or args.through_date < date(2020,12,31)):
        raise SystemExit('Streaming build requires the full 1991–2020 baseline; use --from-date 1991-01-01 and --through-date >= 2020-12-31')
    candidates = list(args.raw.glob('era5_land_t2m_daily_*.zip')) + list(args.raw.glob('era5_land_t2m_daily_*.nc')) if not args.stream else []
    by_month = {}
    for candidate in candidates:
        key = candidate.stem[-7:]
        if key not in by_month or candidate.stat().st_mtime > by_month[key].stat().st_mtime:
            by_month[key] = candidate
    archives = [by_month[k] for k in sorted(by_month)]
    if not args.stream and not archives:
        raise SystemExit('No monthly archives found. Run backend.etl.download first, or use --stream.')
    init_schema()
    if args.stream:
        with engine.connect() as conn:
            mode = conn.execute(text('SELECT mode FROM dataset_info WHERE id=1')).scalar()
            completed = {r[0] for r in conn.execute(text('SELECT month FROM ingested_months'))}
        if mode == 'era5_land':
            raise SystemExit('Database is already complete; use --update for recent months')
        if mode != 'building':
            with engine.begin() as conn:
                for table in ('daily','baseline_daily','normals','countries','ingested_months'):
                    conn.execute(text(f'DELETE FROM {table}'))
                conn.execute(text("INSERT INTO dataset_info (id,mode) VALUES (1,'building') ON CONFLICT(id) DO UPDATE SET mode='building'"))
            completed = set()
        elif completed:
            with engine.connect() as conn:
                history_count = conn.execute(text('SELECT COUNT(*) FROM baseline_daily')).scalar()
            if not history_count:
                raise SystemExit('Previous partial build has no retained 1991–2020 history; use a fresh database for this schema')
        archives = stream_archives(args.from_date, args.through_date, completed)
    if args.resume_raw:
        with engine.connect() as conn:
            mode = conn.execute(text('SELECT mode FROM dataset_info WHERE id=1')).scalar()
            completed = {r[0] for r in conn.execute(text('SELECT month FROM ingested_months'))}
        if mode != 'building':
            raise SystemExit('--resume-raw requires an existing streaming build in mode=building')
        archives = [archive for archive in archives if archive.stem[-7:] not in completed]
        if not archives:
            raise SystemExit('No unprocessed monthly archives found')
    if args.update:
        with engine.connect() as conn:
            latest = conn.execute(text('SELECT MAX(day) FROM daily')).scalar()
            mode = conn.execute(text('SELECT mode FROM dataset_info WHERE id=1')).scalar()
        if mode != 'era5_land' and not (args.allow_partial_baseline and mode == 'pilot'):
            raise SystemExit('Update requires an ERA5-Land database; run full ingest first')
        if not latest:
            raise SystemExit('No existing country data; run full ingest first')
        latest = date.fromisoformat(str(latest))
        cutoff = date(latest.year, latest.month, 1)
        cutoff_month = (cutoff.year * 12 + cutoff.month) - 2
        archives = [a for a in archives if int(a.stem[-7:-3])*12 + int(a.stem[-2:]) >= cutoff_month]
        if any(int(a.stem[-7:-3]) <= 2020 for a in archives):
            raise SystemExit('Updating baseline years requires a full ingest')
        print(f'Updating {len(archives)} recent monthly archives', flush=True)
    weights = None
    grid_hash = None
    if not args.update and not args.stream and not args.resume_raw:
        with engine.begin() as conn:
            conn.execute(text('DELETE FROM daily'))
            conn.execute(text('DELETE FROM baseline_daily'))
            conn.execute(text('DELETE FROM normals'))
            conn.execute(text('DELETE FROM countries'))
            conn.execute(text('DELETE FROM ingested_months'))
            conn.execute(text("INSERT INTO dataset_info (id,mode) VALUES (1,'building') ON CONFLICT(id) DO UPDATE SET mode='building'"))
    for archive in archives:
        with tempfile.TemporaryDirectory() as temp_dir:
            ds = extract_dataset(archive, Path(temp_dir))
            try:
                da, time_name, lat_name, lon_name = normalize(ds)
                lats = da[lat_name].values
                lons = da[lon_name].values
                fingerprint = hashlib.sha256(lats.tobytes() + lons.tobytes()).hexdigest()
                if weights is None:
                    first = da.isel({time_name: 0}).values
                    weights = load_or_build_weights(lats, lons, np.isfinite(first), args.boundaries)
                    grid_hash = fingerprint
                    with engine.begin() as conn:
                        if engine.dialect.name == 'postgresql':
                            conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
                            conn.execute(text('ALTER TABLE countries ADD COLUMN IF NOT EXISTS geom geometry(MultiPolygon,4326)'))
                            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_countries_geom ON countries USING GIST(geom)'))
                        for iso, info in weights.items():
                            conn.execute(text('''INSERT INTO countries (iso3,name,status,quality,grid_cells,coverage,note)
                              VALUES (:iso,:name,:status,:quality,:cells,:coverage,:note) ON CONFLICT(iso3)
                              DO UPDATE SET name=excluded.name,status=excluded.status,quality=excluded.quality,
                              grid_cells=excluded.grid_cells,coverage=excluded.coverage,note=excluded.note'''),
                              {'iso':iso,'name':info['name'],'status':info.get('status','member'),'quality':info['quality'],
                               'cells':len(info['indexes']),'coverage':info['coverage'],
                               'note':info['proxy'] or ''})
                            if engine.dialect.name == 'postgresql':
                                conn.execute(text('UPDATE countries SET geom=ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom),4326)) WHERE iso3=:iso'),
                                             {'iso':iso,'geom':json.dumps(info['geometry'].__geo_interface__)})
                elif fingerprint != grid_hash:
                    raise ValueError(f'Grid changed in {archive}; rebuild country weights')
                daily_rows = []
                baseline_rows = []
                for t in range(da.sizes[time_name]):
                    stamp = np.datetime64(da[time_name].values[t], 'D')
                    day = date.fromisoformat(str(stamp))
                    values = da.isel({time_name:t}).values.ravel()
                    for iso, info in weights.items():
                        ix, w = info['indexes'], info['weights']
                        if not len(ix):
                            continue
                        measured = values[ix]
                        finite = np.isfinite(measured)
                        if not finite.any():
                            continue
                        temperature = float(np.average(measured[finite], weights=w[finite]) - 273.15)
                        mmdd = day.strftime('%m-%d')
                        if date(1991,1,1) <= day <= date(2020,12,31):
                            baseline_rows.append({'iso':iso,'day':day,'mmdd':mmdd,'temp':temperature})
                        if day >= date(2020,1,1):
                            daily_rows.append({'iso':iso,'day':day,'mmdd':mmdd,'temp':temperature,
                                               'provisional':(datetime.now(timezone.utc).date()-day).days <= 90})
                if daily_rows or baseline_rows or args.stream or args.resume_raw:
                    with engine.begin() as conn:
                        if baseline_rows:
                            conn.execute(text('''INSERT INTO baseline_daily (iso3,day,mmdd,temp_c)
                              VALUES (:iso,:day,:mmdd,:temp) ON CONFLICT(iso3,day)
                              DO UPDATE SET mmdd=excluded.mmdd,temp_c=excluded.temp_c'''),baseline_rows)
                        if daily_rows:
                            conn.execute(text('''INSERT INTO daily (iso3,day,mmdd,temp_c,provisional)
                              VALUES (:iso,:day,:mmdd,:temp,:provisional) ON CONFLICT(iso3,day)
                              DO UPDATE SET temp_c=excluded.temp_c,provisional=excluded.provisional'''),daily_rows)
                        if args.stream or args.resume_raw:
                            conn.execute(text('INSERT INTO ingested_months (month) VALUES (:month)'),
                                         {'month':archive.stem[-7:]})
                print(f'Ingested {archive.name}: {len(baseline_rows)} baseline country-days, {len(daily_rows)} display country-days',flush=True)
            finally:
                ds.close()
    if args.stream:
        with engine.connect() as conn:
            finished = {r[0] for r in conn.execute(text('SELECT month FROM ingested_months'))}
        expected = {f'{y}-{m:02d}' for y,m in months(date(1991,1,1),args.through_date)}
        if not expected.issubset(finished):
            raise SystemExit(f'Streaming build remains incomplete: {len(expected-finished)} months missing')
        finalize_baseline()
        print('Streaming build complete; 1991–2020 daily history retained and norms finalized.')
    elif args.resume_raw:
        print('Local monthly archives checkpointed; streaming build can resume at the next missing month.')
    elif not args.update:
        finalize_baseline(args.allow_partial_baseline)
        print('Finished: 1991–2020 daily history retained; normals derived from it. Feb 29 uses leap years only.')
    else:
        print('Finished daily update; baseline normals were preserved.')


if __name__ == '__main__':
    main()
