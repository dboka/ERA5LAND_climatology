import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from shapely.geometry import Point, shape
from backend.etl.ingest import build_weights

ROOT = Path(__file__).resolve().parents[1]


class CountryCatalogTest(unittest.TestCase):
    def test_un_scope_and_spain_islands(self):
        geo = json.loads((ROOT/'public'/'countries.geojson').read_text(encoding='utf8'))
        catalog = json.loads((ROOT/'backend'/'country_catalog.json').read_text(encoding='utf8'))
        features = geo['features']
        codes = {f['properties']['iso3'] for f in features}
        self.assertEqual(len(features), 195)
        self.assertEqual(len(codes), 195)
        self.assertEqual(codes,{c['iso3'] for c in catalog['countries']})
        self.assertEqual(sum(f['properties']['status']=='member' for f in features),193)
        self.assertEqual({f['properties']['iso3'] for f in features if f['properties']['status']=='observer'}, {'VAT','PSE'})
        self.assertTrue(codes.isdisjoint({'ATA','ABW','KOS','TWN','CYN','SOL','PSX','SDS'}))
        spain = shape(next(f['geometry'] for f in features if f['properties']['iso3']=='ESP'))
        self.assertTrue(spain.contains(Point(-16.56,28.29)))  # Tenerife, Canary Islands
        self.assertTrue(spain.contains(Point(2.65,39.70)))     # Mallorca, Balearic Islands

    def test_spain_weights_cover_mainland_and_islands(self):
        geo = json.loads((ROOT/'public'/'countries.geojson').read_text(encoding='utf8'))
        spain = next(f for f in geo['features'] if f['properties']['iso3']=='ESP')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'spain.geojson'
            path.write_text(json.dumps({'type':'FeatureCollection','features':[spain]}),encoding='utf8')
            lats = np.array([40.4,39.7,28.3])
            lons = np.array([-16.56,-3.0,2.65])
            weights = build_weights(lats,lons,np.ones((3,3),dtype=bool),path)['ESP']
        self.assertIn(1,weights['indexes'])  # mainland
        self.assertIn(5,weights['indexes'])  # Mallorca
        self.assertIn(6,weights['indexes'])  # Tenerife


if __name__ == '__main__':
    unittest.main()
