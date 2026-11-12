"""Regression checks for rounded EO timestamps and exact filename recovery."""
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('timestamp_join', Path(__file__).resolve().parents[1]/'scripts/join_image_timestamps.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TimestampJoinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.eo, self.sidecar = self.root/'eo.csv', self.root/'sidecar.csv'
        with self.eo.open('w') as f:
            w=csv.writer(f)
            w.writerow(['Label','unix_us','X'])
            w.writerows([['a.png','1.78209E+15','99'],['b.png','1.78209E+15','100'],['c.png','','101']])
        for name in ('a.png','b.png','c.png'):
            (self.root/name).touch()
        self.write_sidecar()

    def write_sidecar(self, duplicate=False):
        with self.sidecar.open('w') as f:
            w=csv.writer(f)
            w.writerow(['Label','unix_utc+8','gyr_x'])
            w.writerows([['a.png','1782089908520829','0.1'],
                         ['a.png' if duplicate else 'b.png','1782089908622483','0.2']])

    def test_exact_join_recovers_full_precision_without_eo_position(self):
        out=self.root/'result.csv'
        before=self.eo.read_bytes()
        report=module.join(self.eo,self.sidecar,self.root,out)
        self.assertEqual(report['eo_valid_time_unique_count'],1)
        self.assertEqual(report['eo_invalid_time_rows'],1)
        self.assertEqual(report['excluded_labels'],['c.png'])
        with out.open() as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(rows[0],{'Label':'a.png','unix_us':'1782089908520829'})
        self.assertEqual(rows[1]['unix_us'],'1782089908622483')
        self.assertEqual(self.eo.read_bytes(),before)

    def test_ambiguous_label_refused(self):
        self.write_sidecar(duplicate=True)
        with self.assertRaisesRegex(ValueError,'Duplicate sidecar label'):
            module.join(self.eo,self.sidecar,self.root,self.root/'result.csv')

    def test_existing_output_not_overwritten(self):
        out=self.root/'result.csv'
        out.write_text('keep')
        with self.assertRaises(FileExistsError):
            module.join(self.eo,self.sidecar,self.root,out)
        self.assertEqual(out.read_text(),'keep')
