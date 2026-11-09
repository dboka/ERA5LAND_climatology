"""Explicitly illustrative fixture; never presented as observed ERA5-Land data."""
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import text
from .db import ROOT, engine, init_schema


def hash_unit(value: str) -> float:
    return int(hashlib.blake2b(value.encode(), digest_size=4).hexdigest(), 16) / 0xffffffff


def latitude(geometry: dict) -> float:
    def points(coords):
        if coords and isinstance(coords[0], (int, float)):
            yield coords
        else:
            for item in coords:
                yield from points(item)
    pts = list(points(geometry['coordinates']))
    return (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2


def normal_temp(lat: float, ordinal: int, bias: float) -> float:
    seasonal = 13 * math.sin(math.radians(min(abs(lat), 75)))
    phase = 2 * math.pi * (ordinal - 80) / 365.2425
    return 28 - abs(lat) * .49 + bias + seasonal * math.sin(phase) * (1 if lat >= 0 else -1)


def seed_demo() -> None:
    init_schema()
    with engine.connect() as conn:
        if conn.execute(text('SELECT COUNT(*) FROM daily')).scalar():
            with engine.begin() as write:
                write.execute(text("INSERT INTO dataset_info (id,mode) VALUES (1,'demo') ON CONFLICT(id) DO UPDATE SET mode='demo'"))
            return
    boundaries = json.loads((ROOT / 'public' / 'countries.geojson').read_text(encoding='utf-8'))
    countries = []
    for feature in boundaries['features']:
        props = feature['properties']
        iso3 = props['iso3']
        if iso3 == '-99':
            continue
        lat = latitude(feature['geometry'])
        bias = (hash_unit(iso3) - .5) * 6
        quality = 'proxy' if iso3 in {'MCO', 'VAT', 'SMR'} else 'limited' if iso3 in {'MLT', 'SGP', 'BHR', 'LIE', 'NRU', 'TUV'} else 'grid'
        countries.append((iso3, props['name'], props['status'], lat, bias, quality))
    end = datetime.now(timezone.utc).date() - timedelta(days=6)
    start = date(2020, 1, 1)
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM normals'))
        conn.execute(text('DELETE FROM countries'))
        conn.execute(text('DELETE FROM daily'))
        conn.execute(text('INSERT INTO countries (iso3,name,status,quality,grid_cells,coverage,note) VALUES (:iso3,:name,:status,:quality,:cells,:coverage,:note)'), [
            {'iso3': iso, 'name': name, 'status':status, 'quality': q, 'cells': 0 if q == 'proxy' else 3 if q == 'limited' else 100,
             'coverage': 0 if q == 'proxy' else .75 if q == 'limited' else .99,
             'note': 'Ilustratīva reģionāla aproksimācija' if q == 'proxy' else 'Ilustratīvi dati'}
            for iso, name, status, _, _, q in countries])
        normals = []
        for iso, _, _, lat, bias, _ in countries:
            for offset in range(366):
                d = date(2020, 1, 1) + timedelta(days=offset)
                normals.append({'iso3': iso, 'mmdd': d.strftime('%m-%d'), 'temp': normal_temp(lat, d.timetuple().tm_yday, bias)})
        conn.execute(text('INSERT INTO normals (iso3,mmdd,temp_c) VALUES (:iso3,:mmdd,:temp)'), normals)
        batch = []
        current = start
        while current <= end:
            doy = date(2020, current.month, current.day).timetuple().tm_yday
            for iso, _, _, lat, bias, _ in countries:
                baseline = normal_temp(lat, doy, bias)
                phase = hash_unit(iso) * 2 * math.pi
                anomaly = .65 + .23 * (current.year - 2020) + 1.15 * math.sin(doy / 38 + phase) + .68 * math.sin(doy / 113 - phase) + (hash_unit(f'{iso}:{current.isoformat()}') - .5) * .8
                batch.append({'iso3': iso, 'day': current.isoformat(), 'mmdd': current.strftime('%m-%d'), 'temp': baseline + anomaly, 'provisional': current > end - timedelta(days=25)})
            if len(batch) >= 10000:
                conn.execute(text('INSERT INTO daily (iso3,day,mmdd,temp_c,provisional) VALUES (:iso3,:day,:mmdd,:temp,:provisional)'), batch)
                batch = []
            current += timedelta(days=1)
        if batch:
            conn.execute(text('INSERT INTO daily (iso3,day,mmdd,temp_c,provisional) VALUES (:iso3,:day,:mmdd,:temp,:provisional)'), batch)
        conn.execute(text("INSERT INTO dataset_info (id,mode) VALUES (1,'demo') ON CONFLICT(id) DO UPDATE SET mode='demo'"))
