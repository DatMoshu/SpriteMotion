"""Edits accepted for Blender export must be bounded and tied to the exact asset."""
import importlib.util
import unittest
from pathlib import Path

path=Path(__file__).resolve().parents[1]/'games/ultima-online/region-masks/pose_editor_server.py'
spec=importlib.util.spec_from_file_location('pose_editor_server',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class PoseEditsValidation(unittest.TestCase):
    def setUp(self):
        self.scene={'assetId':'test-model','clips':{'Idle':{'frames':[{}]},'Walk':{'frames':[{}]*10}}}
        self.doc={'version':1,'assetId':'test-model','edits':{'Walk:9':{'upperarm_l':[0,0,0,1]}}}
    def test_last_sample_is_valid(self):
        self.assertEqual(module.validate(self.doc,self.scene),self.doc)
    def test_wrong_asset_rejected(self):
        self.doc['assetId']='another-model'
        with self.assertRaises(ValueError):module.validate(self.doc,self.scene)
    def test_out_of_range_frame_rejected(self):
        self.doc['edits']={'Walk:10':{}}
        with self.assertRaises(ValueError):module.validate(self.doc,self.scene)
    def test_noneditable_bone_rejected(self):
        self.doc['edits']={'Idle:0':{'pelvis':[0,0,0,1]}}
        with self.assertRaises(ValueError):module.validate(self.doc,self.scene)
    def test_nonfinite_and_nonunit_quaternions_rejected(self):
        for q in ([float('nan'),0,0,1],[0,0,0,0],[False,0,0,1]):
            with self.subTest(q=q):
                self.doc['edits']['Walk:9']['upperarm_l']=q
                with self.assertRaises(ValueError):module.validate(self.doc,self.scene)

if __name__=='__main__':unittest.main()
