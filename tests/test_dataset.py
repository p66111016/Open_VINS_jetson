"""Sensor timeline correctness and refusal of ambiguous historical data."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from mono_openvins_tools.dataset import integer, prepare, load_normalized, events, audit


class HistoricalDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = 1782089908520829
        self.config = dict(image_dir=str(self.root), image_timestamps_csv=str(self.root/'frames_source.csv'),
                           image_time_column='unix_utc+8', imu_csv=str(self.root/'imu_source.csv'),
                           imu_instance=0, dataset_confirmed=True, timebase_reviewed=True,
                           imu_units_axes_reviewed=True)
        self.write_sources()

    def write_sources(self, duplicate=False, nonfinite=False, gap=False):
        for name in ('frame_a.png','frame_b.png'):
            (self.root/name).touch()
        with (self.root/'frames_source.csv').open('w') as f:
            w=csv.writer(f)
            w.writerow(['Label','unix_utc+8','X'])
            # Deliberately include irrelevant EO position; normalization must ignore it.
            w.writerows([['frame_a.png',self.base+10000,999999],['frame_b.png',self.base+30000,-999999]])
        with (self.root/'imu_source.csv').open('w') as f:
            w=csv.writer(f)
            w.writerow(['TimeUS','I','GyrX','GyrY','GyrZ','AccX','AccY','AccZ','unix_us'])
            for i in range(5):
                t=self.base+i*10000
                if duplicate and i==2:
                    t=self.base+10000
                boot=i*10000+(100000 if gap and i>=2 else 0)
                w.writerow([f'{boot}.0','0.0','nan' if nonfinite else 0.01,0.02,0.03,0,0,-9.81,t])

    def test_exact_integer_timestamp_precision(self):
        self.assertEqual(integer('1782089908520829001'),1782089908520829001)
        self.assertEqual(integer('504889796.0'),504889796)
        with self.assertRaises(ValueError):
            integer('1.5')

    def test_round_trip_preserves_sensor_intervals_and_full_imu(self):
        out=self.root/'normalized'
        prepare(self.config,out)
        _,frames,imu=load_normalized(out)
        self.assertEqual(len(frames),2)
        self.assertEqual(len(imu),5)
        self.assertEqual(frames[1][0]-frames[0][0],20000000)
        self.assertEqual(imu[-1][0]-imu[0][0],40000000)
        self.assertEqual(imu[0][1],(0.01,0.02,0.03,0.0,0.0,-9.81))
        self.assertNotIn('999999',(out/'imu.csv').read_text())

    def test_imu_before_image_at_same_time_and_tail_present(self):
        out=self.root/'normalized'
        prepare(self.config,out)
        _,frames,imu=load_normalized(out)
        merged=list(events(frames,imu))
        same=[kind for t,kind,_ in merged if t==frames[0][0]]
        self.assertEqual(same,[0,1])
        self.assertGreater(imu[-1][0],frames[-1][0])

    def test_duplicate_imu_time_refused_without_deleting_samples(self):
        self.write_sources(duplicate=True)
        with self.assertRaisesRegex(ValueError,'strictly increasing'):
            prepare(self.config,self.root/'normalized')
        self.assertFalse((self.root/'normalized').exists())

    def test_unreviewed_clock_refused(self):
        self.config['timebase_reviewed']=False
        with self.assertRaisesRegex(ValueError,'clock relationship'):
            prepare(self.config,self.root/'normalized')

    def test_exploratory_mode_preserves_unreviewed_status(self):
        self.config['timebase_reviewed']=False
        out=self.root/'normalized'
        manifest=prepare(self.config,out,exploratory=True)
        self.assertFalse(manifest['reviewed'])
        with self.assertRaisesRegex(ValueError,'not reviewed'):
            load_normalized(out)
        _,frames,imu=load_normalized(out,exploratory=True)
        self.assertEqual(len(frames),2)
        self.assertEqual(len(imu),5)

    def test_exploratory_mode_still_refuses_broken_timestamps(self):
        self.write_sources(duplicate=True)
        with self.assertRaisesRegex(ValueError,'strictly increasing'):
            prepare(self.config,self.root/'normalized',exploratory=True)

    def test_nonfinite_measurements_refused(self):
        self.write_sources(nonfinite=True)
        with self.assertRaisesRegex(ValueError,'nonfinite'):
            prepare(self.config,self.root/'normalized')

    def test_in_window_gap_refused(self):
        self.write_sources(gap=True)
        self.assertTrue(audit(self.config)['imu_gaps_over_50ms'][0]['overlaps_image_window'])
        with self.assertRaisesRegex(ValueError,'gap over 50 ms'):
            prepare(self.config,self.root/'normalized')

    def test_normalized_dataset_cannot_be_overwritten(self):
        out=self.root/'normalized'
        prepare(self.config,out)
        with self.assertRaisesRegex(ValueError,'overwrite'):
            prepare(self.config,out)

    def test_missing_image_refused(self):
        (self.root/'frame_b.png').unlink()
        with self.assertRaisesRegex(ValueError,'missing'):
            prepare(self.config,self.root/'normalized')


if __name__=='__main__':
    unittest.main()
