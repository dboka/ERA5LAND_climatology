"""Extract non-roster Natural Earth admin-0 areas for a noninteractive map layer.

The 195-country catalogue and the ETL boundaries remain separate and unchanged.
"""
import argparse
import json
from pathlib import Path

from build_country_catalog import included

ROOT = Path(__file__).resolve().parents[1]


def build(source: Path, output: Path) -> None:
    original = json.loads(source.read_text(encoding='utf8'))
    countries = json.loads((ROOT / 'public' / 'countries.geojson').read_text(encoding='utf8'))
    roster = {feature['properties']['iso3'] for feature in countries['features']}
    if len(roster) != 195:
        raise ValueError('The approved 195-country catalogue is required')

    territories = []
    for feature in original['features']:
        props = feature['properties']
        if included(props):
            continue
        code = props['ADM0_A3']
        if code in roster:
            raise ValueError(f'Territory overlaps the approved country roster: {code}')
        territories.append({
            'type': 'Feature',
            'properties': {'code': code, 'name': props['ADMIN'], 'source_type': props['TYPE']},
            'geometry': feature['geometry'],
        })

    codes = [feature['properties']['code'] for feature in territories]
    if 'GRL' not in codes or len(codes) != len(set(codes)):
        raise ValueError('Greenland is missing or territory codes are duplicated')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'type': 'FeatureCollection', 'features': territories},
                                 ensure_ascii=False, separators=(',', ':')), encoding='utf8')
    print(f'Wrote {len(territories)} noninteractive map areas to {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT / 'data' / 'ne_original.geojson')
    parser.add_argument('--output', type=Path, default=ROOT / 'public' / 'territories.geojson')
    args = parser.parse_args()
    build(args.source, args.output)
