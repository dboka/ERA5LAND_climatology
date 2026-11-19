"""The published archive must contain every reference-period country-day."""
import calendar
import json
import unittest
from pathlib import Path


DATA = Path(__file__).resolve().parents[1] / 'public' / 'data'


class HistoricalSnapshotTest(unittest.TestCase):
    def test_all_baseline_years_are_available_for_both_metrics(self):
        for folder in (DATA, DATA / 'precipitation'):
            with self.subTest(metric=folder.name):
                meta = json.loads((folder / 'meta.json').read_text(encoding='utf8'))
                self.assertEqual(meta['first_date'], '1991-01-01')
                self.assertEqual(meta['baseline'], '1991–2020')
                normals = json.loads((folder / 'normals.json').read_text(encoding='utf8'))
                self.assertEqual(len(normals), 188)
                for country in normals.values():
                    self.assertEqual(len(country), 366)
                for year in range(1991, 2021):
                    for month in range(1, 13):
                        path = folder / f'{year}-{month:02d}.json'
                        with self.subTest(file=path.name):
                            data = json.loads(path.read_text(encoding='utf8'))
                            self.assertEqual(len(data), 188)
                            expected_days = calendar.monthrange(year, month)[1]
                            self.assertTrue(all(len(days) == expected_days for days in data.values()))


if __name__ == '__main__':
    unittest.main()
