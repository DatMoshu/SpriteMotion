import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parent))
import pipeline
from client_import import vd_blocks,inspect_vd,stage
from equipment import encode_art,decode_art,tile_layout,tile_offset,server_source

class ContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=pipeline.BACKEND/'pipeline/uo_vd_writer.py'
        if not path.exists():raise unittest.SkipTest('Install the shared v13 backend before these integration tests.')
        spec=importlib.util.spec_from_file_location('writer',path);cls.writer=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.writer)

    def make_vd(self,path,full=True):
        image=np.zeros((256,256,4),np.uint8);image[94:103,119:129]=[190,45,90,255]
        self.writer.write_vd(path,{(a,d):[image] for a in range(35 if full else 1) for d in range(5)},anchor=(128,192))

    def test_vd_cross_decoder_origin_and_alpha(self):
        sys.path.insert(0,str(pipeline.ROOT/'games/ultima-online/extraction'))
        from uo_anim import decode_entry
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'item.vd';self.make_vd(path)
            self.assertEqual(len(inspect_vd(path)),175)
            frame=decode_entry(vd_blocks(path)[(0,0)])[0]
            self.assertEqual((frame.center_x,frame.center_y,frame.width,frame.height),(9,89,10,9))
            self.assertTrue((frame.rgba[...,3]==255).all())

    def test_truncated_vd_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'item.vd';self.make_vd(path);path.write_bytes(path.read_bytes()[:-4])
            with self.assertRaises(ValueError):vd_blocks(path)

    def test_rle_outside_bounds_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'item.vd';self.make_vd(path)
            data=bytearray(path.read_bytes());start=struct.unpack_from('<i',data,4)[0]
            offset=struct.unpack_from('<I',data,start+516)[0]
            struct.pack_into('<I',data,start+512+offset+8,0x100)
            path.write_bytes(data)
            with self.assertRaises(ValueError):vd_blocks(path)

    def test_partial_import_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.make_vd(root/'item.vd',False)
            with self.assertRaisesRegex(ValueError,'incomplete'):stage(root/'item.vd',root/'client',900,root/'out')

    def test_stage_preserves_source_and_unrelated_indices(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);client=root/'client';client.mkdir();self.make_vd(root/'item.vd')
            raw_index=struct.pack('<iii',0,4,7)+struct.pack('<iii',-1,-1,-1)*35000
            (client/'anim.idx').write_bytes(raw_index);(client/'anim.mul').write_bytes(b'KEEP')
            report=stage(root/'item.vd',client,401,root/'staged')
            self.assertTrue(report['verified']);self.assertEqual((client/'anim.idx').read_bytes(),raw_index)
            self.assertEqual((client/'anim.mul').read_bytes(),b'KEEP')
            self.assertEqual((root/'staged/anim.idx').read_bytes()[:len(raw_index)],raw_index)
            with self.assertRaisesRegex(ValueError,'occupied'):stage(root/'item.vd',root/'staged',401,root/'again')

    def test_static_art_disjoint_runs_and_empty_rows(self):
        image=np.zeros((17,19,4),np.uint8)
        image[2:6,1:5]=[255,0,0,255];image[3:15,11:17]=[0,255,0,255]
        decoded=decode_art(encode_art(Image.fromarray(image)))
        np.testing.assert_array_equal(image,decoded)

    def test_tiledata_offsets_old_and_new(self):
        for flag,land,item in [(8,30,41),(4,26,37)]:
            data=bytes(512*(4+32*land)+2048*(4+32*item))
            layout=tile_layout(data);self.assertEqual(layout[0],flag)
            self.assertEqual(tile_offset(32,layout)-tile_offset(0,layout),4+32*item)
            self.assertEqual(tile_offset(31,layout)-tile_offset(0,layout),31*item)

    def test_configuration_rejects_nonfinite_placement(self):
        for value in [float('nan'),float('inf'),-1]:
            with self.assertRaises(ValueError):pipeline.normalize({'scale':value})
        self.assertEqual(pipeline.normalize({'prompt':'gold helmet'})['color'],'#d5a63c')
        with self.assertRaises(ValueError):pipeline.normalize({'part':'typo'})

    def test_generated_server_source_escapes_name(self):
        source=server_source('Hat";\nattack',0x6000,'helm')
        self.assertIn('Name = "Hat\\";\\nattack";',source)
        self.assertIn('Layer.Helm',source)

if __name__=='__main__':unittest.main()
