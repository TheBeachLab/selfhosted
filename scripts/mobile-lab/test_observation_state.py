import unittest
from datetime import datetime, timezone, timedelta
from observation_state import ObservationState, finite_float, gml_fields

class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.state=ObservationState()
        self.now=datetime(2026,9,12,tzinfo=timezone.utc)
    def test_retained_replay_cannot_create_live_sample(self):
        self.state.receive('car','imu_pitch_deg','-31',retained=True,now=self.now)
        self.assertEqual(self.state.snapshots(self.now),[])
    def test_measurement_timestamp_is_not_flush_time(self):
        self.state.receive('car','imu_pitch_deg','8',now=self.now)
        row=self.state.snapshots(self.now+timedelta(seconds=60))[0]
        self.assertEqual(row[3],self.now)
    def test_new_cabin_sample_cannot_refresh_old_attitude(self):
        self.state.receive('car','imu_pitch_deg','8',now=self.now)
        later=self.now+timedelta(seconds=301)
        self.state.receive('car','temperature_c','24',now=later)
        row=self.state.snapshots(later)[0]
        self.assertNotIn('imu_pitch_deg',row[1])
        self.assertNotIn('imu_pitch_deg',row[2])
    def test_all_expired_values_stop_writes(self):
        self.state.receive('car','temperature_c','24',now=self.now)
        self.assertEqual(self.state.snapshots(self.now+timedelta(seconds=301)),[])
    def test_nonfinite_values_never_reach_database(self):
        for v in ['NaN','Infinity','',None,True]: self.assertIsNone(finite_float(v))
        self.assertEqual(finite_float('0'),0)

class AdapterTests(unittest.TestCase):
    def test_privacy_rounding_and_no_raw_payload(self):
        row=gml_fields('gml/nav','{"lat":41.234567,"lon":1.798765,"secret":"never store"}')
        self.assertEqual(row['gps_lat'],41.23)
        self.assertEqual(row['gps_lon'],1.8)
        self.assertNotIn('secret',row)
    def test_outbox_nav_cannot_become_fresh(self):
        self.assertEqual(gml_fields('gml/nav','{"ts":"2020-01-01T00:00:00Z","pitch_deg":8}'),{})

if __name__=='__main__': unittest.main()
