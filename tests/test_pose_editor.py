"""Edits accepted for Blender export must be bounded and tied to the exact asset."""
import importlib.util
import os
import tempfile
import unittest
from unittest import mock
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

class FindBlender(unittest.TestCase):
    def make(self,root,*names):
        for name in names:
            exe=Path(root)/'tools/blender-runtime'/name/'blender.exe';exe.parent.mkdir(parents=True);exe.touch()
    def test_env_wins(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d,'blender-5.2.2-windows-x64')
            self.assertEqual(module.find_blender(d,{'SPRITEMOTION_BLENDER':'custom.exe'}),'custom.exe')
    def test_newest_runtime_beats_path_and_program_files(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d,'blender-5.2.2-windows-x64','blender-5.10.0-windows-x64','blender-4.2.1-windows-x64')
            with mock.patch.object(module.shutil,'which',return_value='path-blender.exe'):
                found=module.find_blender(d,{'ProgramFiles':d})
            self.assertIn('blender-5.10.0',found)
    def test_path_used_without_runtime(self):
        with tempfile.TemporaryDirectory() as d,mock.patch.object(module.shutil,'which',return_value='path-blender.exe'):
            self.assertEqual(module.find_blender(d,{}),'path-blender.exe')
    def test_program_files_version_sorted_numerically(self):
        with tempfile.TemporaryDirectory() as d,mock.patch.object(module.shutil,'which',return_value=None):
            for v in ('Blender 4.2','Blender 10.0'):
                exe=Path(d)/'Blender Foundation'/v/'blender.exe';exe.parent.mkdir(parents=True);exe.touch()
            self.assertIn('Blender 10.0',module.find_blender(Path(d)/'none',{'ProgramFiles':d}))
    def test_missing_raises(self):
        with tempfile.TemporaryDirectory() as d,mock.patch.object(module.shutil,'which',return_value=None):
            with self.assertRaises(RuntimeError):module.find_blender(d,{'ProgramFiles':d})

class PrivateWrite(unittest.TestCase):
    def test_content_written_and_private_mode_requested(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'edits.json';module.write_private(target,'{}')
            self.assertEqual(target.read_text(),'{}')
            if os.name!='nt':self.assertEqual(target.stat().st_mode&0o777,0o600)

if __name__=='__main__':unittest.main()
