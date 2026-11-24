import unittest
import datetime
from src.core.utils.date_utils import get_vn_now, to_vn_iso, format_vn_datetime, VN_TZ


class TestDateUtils(unittest.TestCase):
    def test_get_vn_now_timezone(self):
        now_vn = get_vn_now()
        self.assertEqual(now_vn.tzinfo, VN_TZ)
        self.assertEqual(now_vn.utcoffset().total_seconds(), 7 * 3600)

    def test_to_vn_iso_naive_and_aware(self):
        # Naive datetime
        dt_naive = datetime.datetime(2026, 11, 7, 2, 46, 0)
        iso_res = to_vn_iso(dt_naive)
        self.assertTrue(iso_res.startswith("2026-11-07T09:46:00+07:00"))

        # String ISO without offset
        iso_str = "2026-11-07T02:46:00"
        iso_res2 = to_vn_iso(iso_str)
        self.assertTrue(iso_res2.startswith("2026-11-07T09:46:00+07:00"))

        # String ISO with Z
        iso_str_z = "2026-11-07T02:46:00Z"
        iso_res3 = to_vn_iso(iso_str_z)
        self.assertTrue(iso_res3.startswith("2026-11-07T09:46:00+07:00"))

    def test_to_vn_display(self):
        iso_str = "2026-11-07T02:46:00Z"
        display = format_vn_datetime(iso_str, "%H:%M %d-%m")
        self.assertEqual(display, "09:46 07-11")


if __name__ == "__main__":
    unittest.main()
