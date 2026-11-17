"""UTC accumulation and coverage checks for ERA5-Land precipitation."""
import unittest
from datetime import date

import numpy as np
import xarray as xr

from backend.etl.arco_precipitation import country_rows


class PrecipitationTest(unittest.TestCase):
    def setUp(self):
        self.day = date(1991, 1, 1)
        self.hours = np.arange(np.datetime64('1991-01-01T00', 'h'),
                               np.datetime64('1991-01-02T00', 'h'),
                               np.timedelta64(1, 'h'))
        self.weights = {'AAA': {'indexes': np.array([0, 1]),
                                'weights': np.array([1.0, 3.0])}}

    def data(self, values):
        return xr.DataArray(values, dims=('time', 'latitude', 'longitude'),
                            coords={'time': self.hours, 'latitude': [0],
                                    'longitude': [0, 1]})

    def test_sums_24_hours_then_area_averages_in_millimetres(self):
        values = np.tile(np.array([0.001, 0.003], dtype=np.float32), (24, 1, 1))
        rows = country_rows(self.day, self.data(values), self.weights)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['precip'], 60.0, places=3)

    def test_incomplete_utc_day_is_rejected(self):
        values = np.zeros((23, 1, 2), dtype=np.float32)
        da = xr.DataArray(values, dims=('time', 'latitude', 'longitude'),
                          coords={'time': self.hours[:23], 'latitude': [0],
                                  'longitude': [0, 1]})
        with self.assertRaisesRegex(ValueError, '24 complete UTC hours'):
            country_rows(self.day, da, self.weights)

    def test_cell_missing_an_hour_is_excluded(self):
        values = np.tile(np.array([0.001, 0.003], dtype=np.float32), (24, 1, 1))
        values[5, 0, 1] = np.nan
        rows = country_rows(self.day, self.data(values), self.weights)
        self.assertAlmostEqual(rows[0]['precip'], 24.0, places=3)


if __name__ == '__main__':
    unittest.main()
