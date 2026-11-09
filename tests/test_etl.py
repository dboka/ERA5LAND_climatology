"""Small integration check for weighted cells, leap-day normals and country-day storage."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
import xarray as xr
from sqlalchemy import create_engine, text
from backend.etl.ingest import build_weights

ROOT = Path(__file__).resolve().parents[1]


def archive(folder: Path, year: int, values: list[float], plain=False):
    name = folder / f'era5_land_t2m_daily_{year}-02.{"nc" if plain else "zip"}'
    nc = folder / 't2m.nc'
    days = [f'{year}-02-28', f'{year}-02-29'] if year % 4 == 0 else [f'{year}-02-28']
    array = np.stack([np.full((2, 2), v + 273.15) for v in values])
    da = xr.DataArray(array, dims=['valid_time', 'latitude', 'longitude'],
                      coords={'valid_time':np.array(days,dtype='datetime64[ns]'),
                              'latitude':[0.1, 0.0], 'longitude':[0.0,0.1]},attrs={'units':'K'})
    if plain:
        xr.Dataset({'t2m':da}).to_netcdf(name)
    else:
        xr.Dataset({'t2m':da}).to_netcdf(nc)
        with zipfile.ZipFile(name,'w') as zf:
            zf.write(nc,'t2m.nc')
        nc.unlink()


class ETLTest(unittest.TestCase):
    def test_sub_grid_country_is_marked_as_regional_proxy(self):
        with tempfile.TemporaryDirectory() as folder_str:
            path = Path(folder_str) / 'tiny.geojson'
            tiny = {'type':'FeatureCollection','features':[{'type':'Feature',
              'properties':{'iso3':'TNY','name':'Tiny state'},
              'geometry':{'type':'Polygon','coordinates':[[[-.005,-.005],[.005,-.005],[.005,.005],[-.005,.005],[-.005,-.005]]]}}]}
            path.write_text(json.dumps(tiny),encoding='utf8')
            result = build_weights(np.array([0.]),np.array([0.]),np.ones((1,1),dtype=bool),path)['TNY']
            self.assertEqual(result['quality'],'proxy')
            self.assertEqual(len(result['indexes']),1)
            self.assertIn('25%',result['proxy'])

    def test_leap_day_and_weighted_country(self):
        with tempfile.TemporaryDirectory() as folder_str:
            folder=Path(folder_str)
            boundaries={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'iso3':'TST','name':'Testland'},
              'geometry':{'type':'Polygon','coordinates':[[[-.04,-.04],[.14,-.04],[.14,.14],[-.04,.14],[-.04,-.04]]]}}]}
            path=folder/'boundaries.geojson';path.write_text(json.dumps(boundaries),encoding='utf8')
            archive(folder,1992,[10.,12.]);archive(folder,2020,[20.,22.]);archive(folder,2024,[23.,25.])
            database=folder/'test.sqlite'
            env=os.environ.copy();env['DATABASE_URL']=f'sqlite:///{database.as_posix()}';env['CLIMATE_DEMO']='0'
            rejected=subprocess.run([sys.executable,'-m','backend.etl.ingest','--raw',str(folder),'--boundaries',str(path)],
                                    cwd=ROOT,env=env,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn('Incomplete 1991',rejected.stdout+rejected.stderr)
            initial=subprocess.run([sys.executable,'-m','backend.etl.ingest','--raw',str(folder),'--boundaries',str(path),'--allow-partial-baseline'],
                                   cwd=ROOT,env=env,capture_output=True,text=True)
            self.assertEqual(initial.returncode,0,initial.stdout+'\n'+initial.stderr)
            archive(folder,2025,[24.],plain=True)
            updated=subprocess.run([sys.executable,'-m','backend.etl.ingest','--raw',str(folder),'--boundaries',str(path),'--update','--allow-partial-baseline'],
                                   cwd=ROOT,env=env,capture_output=True,text=True)
            self.assertEqual(updated.returncode,0,updated.stdout+'\n'+updated.stderr)
            engine=create_engine(env['DATABASE_URL'])
            with engine.connect() as conn:
                normal=conn.execute(text("SELECT temp_c FROM normals WHERE iso3='TST' AND mmdd='02-29'")).scalar_one()
                actual=conn.execute(text("SELECT temp_c FROM daily WHERE iso3='TST' AND day='2020-02-29'")).scalar_one()
                days=conn.execute(text("SELECT COUNT(*) FROM daily WHERE iso3='TST'")).scalar_one()
                history=conn.execute(text("SELECT COUNT(*) FROM baseline_daily WHERE iso3='TST'")).scalar_one()
                feb28=conn.execute(text("SELECT temp_c FROM normals WHERE iso3='TST' AND mmdd='02-28'")).scalar_one()
                mode=conn.execute(text('SELECT mode FROM dataset_info WHERE id=1')).scalar_one()
            engine.dispose()
            self.assertAlmostEqual(normal,17.)
            self.assertAlmostEqual(feb28,15.)
            self.assertAlmostEqual(actual,22.)
            self.assertEqual(days,5)
            self.assertEqual(history,4)
            self.assertEqual(mode,'pilot')


if __name__=='__main__':
    unittest.main()
