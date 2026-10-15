"""Offline calendar checks only; never contacts providers or starts a call."""
import unittest
from datetime import datetime, timezone
from server import availability, holidays


class HoursTests(unittest.TestCase):
    def check(self, iso, allowed, reason):
        result = availability(datetime.fromisoformat(iso))
        self.assertEqual((result["can_transfer"], result["reason"]), (allowed, reason))
        return result

    def test_boundaries_and_weekend(self):
        self.check("2026-10-15T08:59:59+02:00", False, "outside_hours")
        self.check("2026-10-15T09:00:00+02:00", True, "open")
        self.check("2026-10-15T16:59:59+02:00", True, "open")
        self.check("2026-10-15T17:00:00+02:00", False, "outside_hours")
        self.check("2026-10-17T12:00:00+02:00", False, "weekend")

    def test_easter_and_munich_specific_days(self):
        for day in ("2026-04-03", "2026-04-06", "2026-05-14", "2026-05-25", "2026-06-04", "2027-03-26", "2028-08-15"):
            self.check(day + "T12:00:00+02:00", False, "public_holiday")
        self.check("2028-08-08T12:00:00+02:00", True, "open")
        self.check("2026-12-24T12:00:00+01:00", True, "open")
        self.assertEqual(len(holidays(2026)), 13)

    def test_dst_and_year_rollover(self):
        self.check("2026-03-30T07:00:00+00:00", True, "open")
        self.check("2026-10-26T07:59:00+00:00", False, "outside_hours")
        result = self.check("2026-10-23T17:00:00+02:00", False, "outside_hours")
        self.assertEqual(result["next_open"], "2026-10-26T09:00:00+01:00")
        result = self.check("2026-12-31T17:00:00+01:00", False, "outside_hours")
        self.assertEqual(result["next_open"], "2027-01-04T09:00:00+01:00")
        with self.assertRaises(ValueError):
            availability(datetime(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
