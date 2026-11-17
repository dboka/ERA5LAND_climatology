import os
from datetime import date
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .db import engine, init_schema
from .demo import seed_demo

DEMO = os.getenv('CLIMATE_DEMO', '0') == '1'
Metric = Literal['temperature', 'precipitation']


def metric_config(metric: Metric):
    if metric == 'precipitation':
        if DEMO:
            raise HTTPException(503, 'Ilustratīvajā režīmā nokrišņu dati nav pieejami')
        return ('precipitation_daily', 'precipitation_normals', 'precip_mm', 'SUM',
                "MAX(CASE WHEN d.day >= CURRENT_DATE - INTERVAL '90 days' THEN 1 ELSE 0 END)")
    return 'daily', 'normals', 'temp_c', 'AVG', 'MAX(CASE WHEN d.provisional THEN 1 ELSE 0 END)'


def anomaly_value(actual: float, normal: float, metric: Metric) -> float:
    if metric == 'precipitation':
        return round((actual / normal - 1) * 100, 2) if normal > 0 else 0.0
    return round(actual - normal, 3)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if DEMO:
        seed_demo()
    else:
        init_schema()
        with engine.connect() as conn:
            mode = conn.execute(text('SELECT mode FROM dataset_info WHERE id=1')).scalar()
            has_data = conn.execute(text('SELECT COUNT(*) FROM daily')).scalar()
        if mode == 'demo' or (has_data and mode != 'era5_land'):
            raise RuntimeError('Database provenance is missing or illustrative; refusing to label it ERA5-Land')
    yield


app = FastAPI(title='Climate Atlas API', version='0.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'], allow_methods=['GET'], allow_headers=['*'])


def bounds(start: date, end: date, metric: Metric = 'temperature'):
    if start > end:
        raise HTTPException(422, 'Sākuma datums ir pēc beigu datuma')
    if start < date(2020, 1, 1):
        raise HTTPException(422, 'Pieejamais periods sākas 2020-01-01')
    table = metric_config(metric)[0]
    with engine.connect() as conn:
        latest = conn.execute(text(f'SELECT MAX(day) FROM {table}')).scalar()
    if latest is None:
        raise HTTPException(503, 'Dienas dati vēl nav sagatavoti')
    if isinstance(latest, str):
        latest = date.fromisoformat(latest)
    if end > latest:
        raise HTTPException(422, f'Jaunākais pieejamais datums ir {latest}')


@app.get('/api/meta')
def meta(metric: Metric = 'temperature'):
    table = metric_config(metric)[0]
    with engine.connect() as conn:
        row = conn.execute(text(f'SELECT MIN(day), MAX(day), COUNT(DISTINCT iso3) FROM {table}')).one()
        mode = conn.execute(text('SELECT mode FROM dataset_info WHERE id=1')).scalar() or 'era5_land'
    return {'first_date': str(row[0]) if row[0] else None, 'latest_date': str(row[1]) if row[1] else None,
            'countries_with_data': row[2], 'mode': mode,
            'source': ('Copernicus ERA5-Land total precipitation; sum of 24 UTC hourly values'
                       if metric == 'precipitation' else
                       'Ilustratīvi ģenerēti dati' if mode == 'demo' else
                       'Copernicus ERA5-Land 2 m temperature; mean of 24 UTC hourly values'),
            'baseline': '1991–2020'}


@app.get('/api/anomalies')
def anomalies(start: date = Query(...), end: date = Query(...), metric: Metric = 'temperature'):
    bounds(start, end, metric)
    table, norm_table, column, aggregate, provisional = metric_config(metric)
    with engine.connect() as conn:
        rows = conn.execute(text(f'''
          SELECT c.iso3, c.name, c.status, c.quality, c.grid_cells, c.coverage, c.note,
                 {aggregate}(d.{column}) actual, {aggregate}(n.{column}) normal, COUNT(*) days,
                 {provisional} provisional
          FROM {table} d JOIN {norm_table} n ON n.iso3=d.iso3 AND n.mmdd=d.mmdd
          JOIN countries c ON c.iso3=d.iso3
          WHERE d.day BETWEEN :start AND :end
          GROUP BY c.iso3,c.name,c.status,c.quality,c.grid_cells,c.coverage,c.note
          ORDER BY c.iso3
        '''), {'start': start, 'end': end}).mappings().all()
    return {'start': start, 'end': end, 'mode': 'demo' if DEMO else 'era5_land', 'countries': [
        {**dict(r), 'anomaly': anomaly_value(r['actual'], r['normal'], metric),
         'actual': round(r['actual'], 3), 'normal': round(r['normal'], 3),
         'provisional': bool(r['provisional'])} for r in rows]}


@app.get('/api/countries/{iso3}/series')
def series(iso3: str, start: date = Query(...), end: date = Query(...), metric: Metric = 'temperature'):
    bounds(start, end, metric)
    table, norm_table, column, aggregate, _ = metric_config(metric)
    iso3 = iso3.upper()
    with engine.connect() as conn:
        if not conn.execute(text('SELECT 1 FROM countries WHERE iso3=:iso3'), {'iso3': iso3}).scalar():
            raise HTTPException(404, 'Valsts nav atrasta')
        grouping = 'day' if (end - start).days <= 45 else 'month'
        bucket = 'd.day' if grouping == 'day' else "SUBSTR(CAST(d.day AS TEXT),1,7)"
        rows = conn.execute(text(f'''
          SELECT {bucket} bucket, {aggregate}(d.{column}) actual, {aggregate}(n.{column}) normal,
                 COUNT(*) days FROM {table} d JOIN {norm_table} n ON n.iso3=d.iso3 AND n.mmdd=d.mmdd
          WHERE d.iso3=:iso3 AND d.day BETWEEN :start AND :end GROUP BY {bucket} ORDER BY bucket
        '''), {'iso3': iso3, 'start': start, 'end': end}).mappings().all()
    return {'iso3': iso3, 'grouping': grouping, 'points': [{'date': str(r['bucket']),
            'actual': round(r['actual'], 2), 'normal': round(r['normal'], 2),
            'anomaly': anomaly_value(r['actual'], r['normal'], metric), 'days': r['days']} for r in rows]}
