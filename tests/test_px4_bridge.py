import json
from pathlib import Path
import unittest
import numpy as np
from mono_openvins_tools.px4_bridge import convert,rotation,quaternion_wxyz

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.c=json.loads((Path(__file__).resolve().parents[1]/'config/px4_bridge.json').read_text())
        self.cov=np.eye(6)*.1
    def call(self,**kwargs):
        args=dict(position=[1,2,3],q_xyzw=[0,0,0,1],velocity_imu=[0,0,0],angular_imu=[1,2,3],
                  pose_cov=self.cov,twist_cov=self.cov,config=self.c,stamp_ns=1_000_000_000,now_ns=1_010_000_000)
        args.update(kwargs);return convert(**args)
    def test_up_to_down_and_wxyz(self):
        r=self.call()
        self.assertEqual(r['position'],[1,-2,-3])
        np.testing.assert_allclose(np.abs(r['q']),[0,1,0,0],atol=1e-8)
        self.assertEqual(r['pose_frame'],2)
        self.assertEqual(r['timestamp_sample'],1_000_000)
        self.assertEqual(r['velocity_frame'],0)
    def test_body_rotation_and_angular_rate(self):
        self.c['R_imu_from_body_frd']=[[0,-1,0],[1,0,0],[0,0,1]]
        r=self.call();self.assertEqual(r['angular_velocity'],[2,-1,3])
        np.testing.assert_allclose(rotation(np.array(r['q'])[[1,2,3,0]]),np.diag([1,-1,-1])@np.array(self.c['R_imu_from_body_frd']),atol=1e-8)
    def test_stale_future_and_invalid_covariance(self):
        for opts in (dict(now_ns=2_000_000_000),dict(now_ns=1),dict(pose_cov=np.zeros((6,6))),dict(q_xyzw=[0,0,0,0])):
            with self.assertRaises(ValueError):self.call(**opts)
    def test_rotation_reflection_refused(self):
        self.c['R_imu_from_body_frd']=np.diag([1,1,-1]).tolist()
        with self.assertRaises(ValueError):self.call()
