"""Build monthly static data bundles for GitHub Pages deployment."""
import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from sqlalchemy import text
from .db import ROOT, engine


BASELINE_FIRST = date(1991, 1, 1)
DISPLAY_FIRST = date(2020, 1, 1)


def first_export_date(conn, table: str, countries: int) -> str:
    """Require a complete pre-2020 archive before exposing baseline years."""
    if table not in ('baseline_daily', 'precipitation_baseline_daily'):
        raise ValueError('Unsupported baseline table')
    first, last, country_count, rows = conn.execute(text(f'''
        SELECT MIN(day), MAX(day), COUNT(DISTINCT iso3), COUNT(*) FROM {table}
        WHERE day < :display_first
    '''), {'display_first': DISPLAY_FIRST}).one()
    expected = (DISPLAY_FIRST - BASELINE_FIRST).days * countries
    if (str(first) != str(BASELINE_FIRST) or str(last) != '2019-12-31'
            or country_count != countries or rows != expected):
        raise SystemExit(f'Incomplete {table} archive; refusing historical export')
    return str(first)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'public' / 'data')
    parser.add_argument('--allow-demo', action='store_true')
    args = parser.parse_args()
    from .app import DEMO
    if DEMO and not args.allow_demo:
        raise SystemExit('Refusing to export illustrative data without --allow-demo')
    args.output.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:
        mode = conn.execute(text('SELECT mode FROM dataset_info WHERE id=1')).scalar()
        if mode != 'era5_land' and not (mode == 'demo' and args.allow_demo):
            raise SystemExit(f'Refusing static export from database mode {mode!r}')
        dates = conn.execute(text('SELECT MIN(day),MAX(day),COUNT(DISTINCT iso3) FROM daily')).one()
        if not dates[0]:
            raise SystemExit('No daily data to export')
        first_date = first_export_date(conn, 'baseline_daily', dates[2]) if mode == 'era5_land' else str(dates[0])
        countries = [dict(r) for r in conn.execute(text('SELECT iso3,name,status,quality,grid_cells,coverage,note FROM countries')).mappings()]
        normals = defaultdict(dict)
        for r in conn.execute(text('SELECT iso3,mmdd,temp_c FROM normals')).mappings():
            normals[r['iso3']][r['mmdd']] = round(r['temp_c'], 4)
        months = defaultdict(lambda: defaultdict(dict))
        if mode == 'era5_land':
            for r in conn.execution_options(yield_per=5000).execute(text('''SELECT iso3,day,temp_c FROM baseline_daily
                WHERE day < :display_first ORDER BY day,iso3'''), {'display_first': DISPLAY_FIRST}).mappings():
                day = str(r['day'])
                months[day[:7]][r['iso3']][day[-2:]] = [round(r['temp_c'], 4), False]
        for r in conn.execution_options(yield_per=5000).execute(text('SELECT iso3,day,temp_c,provisional FROM daily ORDER BY day,iso3')).mappings():
            day = str(r['day'])
            months[day[:7]][r['iso3']][day[-2:]] = [round(r['temp_c'],4),bool(r['provisional'])]
    meta = {'first_date':first_date,'latest_date':str(dates[1]),'countries_with_data':dates[2],
            'mode':mode, 'source':'Ilustratīvi ģenerēti dati' if mode == 'demo' else 'Copernicus ERA5-Land 2 m temperature; mean of 24 UTC hourly values',
            'baseline':'1991–2020'}
    (args.output / 'meta.json').write_text(json.dumps(meta,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    (args.output / 'countries.json').write_text(json.dumps(countries,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    (args.output / 'normals.json').write_text(json.dumps(normals,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    for month, data in months.items():
        (args.output / f'{month}.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    print(f'Exported {len(months)} months to {args.output}')
    del months

    if mode == 'era5_land':
        precipitation_output = args.output / 'precipitation'
        precipitation_output.mkdir(parents=True, exist_ok=True)
        with engine.connect() as conn:
            dates = conn.execute(text('SELECT MIN(day),MAX(day),COUNT(DISTINCT iso3) FROM precipitation_daily')).one()
            norm_count = conn.execute(text('SELECT COUNT(*) FROM precipitation_normals')).scalar()
            if not dates[0] or norm_count != 188 * 366:
                raise SystemExit('Precipitation archive or normals are incomplete; refusing static export')
            precipitation_first = first_export_date(conn, 'precipitation_baseline_daily', dates[2])
            precipitation_normals = defaultdict(dict)
            for row in conn.execute(text('SELECT iso3,mmdd,precip_mm FROM precipitation_normals')).mappings():
                precipitation_normals[row['iso3']][row['mmdd']] = round(row['precip_mm'], 5)
            precipitation_months = defaultdict(lambda: defaultdict(dict))
            for row in conn.execution_options(yield_per=5000).execute(text('''SELECT iso3,day,precip_mm FROM precipitation_baseline_daily
                WHERE day < :display_first ORDER BY day,iso3'''), {'display_first': DISPLAY_FIRST}).mappings():
                day = str(row['day'])
                precipitation_months[day[:7]][row['iso3']][day[-2:]] = [round(row['precip_mm'], 5), False]
            for row in conn.execution_options(yield_per=5000).execute(text('SELECT iso3,day,precip_mm FROM precipitation_daily ORDER BY day,iso3')).mappings():
                day = str(row['day'])
                provisional = (datetime.now(timezone.utc).date() - date.fromisoformat(day)).days <= 90
                precipitation_months[day[:7]][row['iso3']][day[-2:]] = [round(row['precip_mm'], 5), provisional]
        precipitation_meta = {'first_date': precipitation_first, 'latest_date': str(dates[1]),
                              'countries_with_data': dates[2], 'mode': mode,
                              'source': 'Copernicus ERA5-Land total precipitation; sum of 24 UTC hourly values',
                              'baseline': '1991–2020'}
        (precipitation_output / 'meta.json').write_text(
            json.dumps(precipitation_meta, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
        (precipitation_output / 'normals.json').write_text(
            json.dumps(precipitation_normals, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
        for month, data in precipitation_months.items():
            (precipitation_output / f'{month}.json').write_text(
                json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
        print(f'Exported {len(precipitation_months)} precipitation months to {precipitation_output}')


if __name__ == '__main__':
    main()
