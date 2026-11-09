"""Build monthly static data bundles for GitHub Pages deployment."""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from sqlalchemy import text
from .db import ROOT, engine


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
        countries = [dict(r) for r in conn.execute(text('SELECT iso3,name,status,quality,grid_cells,coverage,note FROM countries')).mappings()]
        normals = defaultdict(dict)
        for r in conn.execute(text('SELECT iso3,mmdd,temp_c FROM normals')).mappings():
            normals[r['iso3']][r['mmdd']] = round(r['temp_c'], 4)
        months = defaultdict(lambda: defaultdict(dict))
        for r in conn.execute(text('SELECT iso3,day,temp_c,provisional FROM daily ORDER BY day,iso3')).mappings():
            day = str(r['day'])
            months[day[:7]][r['iso3']][day[-2:]] = [round(r['temp_c'],4),bool(r['provisional'])]
    meta = {'first_date':str(dates[0]),'latest_date':str(dates[1]),'countries_with_data':dates[2],
            'mode':mode, 'source':'Ilustratīvi ģenerēti dati' if mode == 'demo' else 'Copernicus ERA5-Land 2 m temperature; mean of 24 UTC hourly values',
            'baseline':'1991–2020'}
    (args.output / 'meta.json').write_text(json.dumps(meta,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    (args.output / 'countries.json').write_text(json.dumps(countries,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    (args.output / 'normals.json').write_text(json.dumps(normals,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    for month, data in months.items():
        (args.output / f'{month}.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    print(f'Exported {len(months)} months to {args.output}')


if __name__ == '__main__':
    main()
