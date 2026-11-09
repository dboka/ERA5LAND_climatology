"""Freeze the 193 UN member states plus the two UN non-member observer states.

Input: Natural Earth 1:50m admin-0 countries GeoJSON. The Natural Earth TYPE
classification is reviewed against the UN membership and observer lists. Fail
closed if the resulting roster changes, rather than silently adding areas.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPROVED_ROSTER = ROOT / 'config' / 'un_country_codes.json'
REGULAR_COUNTRIES = {'USA', 'GBR', 'NZL', 'NLD', 'FRA', 'FIN', 'DNK', 'CHN', 'AUS'}
SOVEREIGNTY_EXCEPTIONS = {'KAZ', 'CUB'}
EXCLUDED_FROM_SOVEREIGN = {'CYN', 'SOL', 'TWN'}
SOURCE_TO_ISO3 = {'PSX': 'PSE', 'SDS': 'SSD'}
OBSERVERS = {'VAT', 'PSE'}


def included(properties: dict) -> bool:
    source = properties['ADM0_A3']
    category = properties['TYPE']
    return (category == 'Sovereign country' and source not in EXCLUDED_FROM_SOVEREIGN
            or category == 'Country' and source in REGULAR_COUNTRIES
            or category == 'Sovereignty' and source in SOVEREIGNTY_EXCEPTIONS
            or category == 'Disputed' and source == 'ISR'
            or category == 'Indeterminate' and source == 'PSX')


def build(source: Path, boundaries: Path, catalog: Path) -> None:
    original = json.loads(source.read_text(encoding='utf8'))
    approved = json.loads(APPROVED_ROSTER.read_text(encoding='utf8'))
    approved_members = set(approved['members'])
    approved_observers = set(approved['observers'])
    if len(approved_members) != 193 or approved_observers != OBSERVERS or approved_members & approved_observers:
        raise ValueError('Approved UN roster must contain 193 distinct members and VAT/PSE observers')
    features, roster = [], []
    for feature in original['features']:
        p = feature['properties']
        if not included(p):
            continue
        source_iso = p['ADM0_A3']
        iso3 = SOURCE_TO_ISO3.get(source_iso, source_iso)
        status = 'observer' if iso3 in OBSERVERS else 'member'
        name = 'Vatican City (Holy See)' if iso3 == 'VAT' else 'State of Palestine' if iso3 == 'PSE' else p['ADMIN']
        features.append({'type':'Feature','id':iso3,'properties':{'iso3':iso3,'name':name,'status':status},
                         'geometry':feature['geometry']})
        roster.append({'iso3':iso3,'source_iso3':source_iso,'name':name,'status':status})
    codes = [row['iso3'] for row in roster]
    if len(codes) != 195 or len(set(codes)) != 195 or sum(x['status']=='member' for x in roster) != 193:
        raise ValueError('Country roster differs from the 193 UN members + 2 observers; review Natural Earth changes')
    expected_observers = {row['iso3'] for row in roster if row['status']=='observer'}
    if expected_observers != OBSERVERS:
        raise ValueError(f'Unexpected observer states: {expected_observers}')
    selected_members = {row['iso3'] for row in roster if row['status']=='member'}
    if selected_members != approved_members:
        raise ValueError(f'Natural Earth and approved UN roster differ: missing={sorted(approved_members-selected_members)}, extra={sorted(selected_members-approved_members)}')
    # Prevent a country mean from quietly dropping Spain's major island groups.
    spain = next(x for x in features if x['properties']['iso3']=='ESP')
    polygons = spain['geometry']['coordinates'] if spain['geometry']['type']=='MultiPolygon' else [spain['geometry']['coordinates']]
    bounds = [(min(p[0] for ring in poly for p in ring),min(p[1] for ring in poly for p in ring),
               max(p[0] for ring in poly for p in ring),max(p[1] for ring in poly for p in ring)) for poly in polygons]
    if not any(-19 < b[0] < -13 and 27 < b[1] < 30 for b in bounds):
        raise ValueError('Spanish Canary Islands are missing from boundary source')
    if not any(1 < b[0] < 4 and 38 < b[1] < 41 for b in bounds):
        raise ValueError('Spanish Balearic Islands are missing from boundary source')
    boundaries.parent.mkdir(parents=True,exist_ok=True)
    catalog.parent.mkdir(parents=True,exist_ok=True)
    boundaries.write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False,separators=(',',':')),encoding='utf8')
    catalog.write_text(json.dumps({'scope':'193 UN members + 2 UN observer states','countries':sorted(roster,key=lambda r:r['iso3'])},ensure_ascii=False,indent=2),encoding='utf8')
    print(f'Wrote {len(features)} countries: 193 members, 2 observers')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ROOT/'data'/'ne_original.geojson')
    parser.add_argument('--boundaries',type=Path,default=ROOT/'public'/'countries.geojson')
    parser.add_argument('--catalog',type=Path,default=ROOT/'backend'/'country_catalog.json')
    args = parser.parse_args()
    build(args.source,args.boundaries,args.catalog)
