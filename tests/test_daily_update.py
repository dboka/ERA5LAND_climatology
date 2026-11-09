"""Checks for the daily updater's UTC completeness gate."""
import unittest
from datetime import date

import numpy as np

from backend.etl.arco_daily_update import latest_complete_day


class DailyUpdateTest(unittest.TestCase):
    def test_partial_final_day_is_excluded(self):
        self.assertEqual(latest_complete_day(np.datetime64('2026-11-04T22:00:00'),
                                             date(2026, 11, 9)), date(2026, 11, 3))

    def test_complete_day_is_included(self):
        self.assertEqual(latest_complete_day(np.datetime64('2026-11-04T23:00:00'),
                                             date(2026, 11, 9)), date(2026, 11, 4))

    def test_current_utc_day_and_year_boundary(self):
        self.assertEqual(latest_complete_day(np.datetime64('2027-01-01T23:00:00'),
                                             date(2027, 1, 1)), date(2026, 12, 31))


if __name__ == '__main__':
    unittest.main()
