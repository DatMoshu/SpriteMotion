import unittest
import numpy as np
from PIL import Image
from build_plate_armor import crop_asset,fit_helmet

class PlateArmorTests(unittest.TestCase):
    def test_empty_helmet_stays_empty(self):
        self.assertIsNone(fit_helmet(Image.new('RGBA',(256,256)),Image.new('RGBA',(20,20),'gold')).getbbox())

    def test_helmet_tracks_source_bounds(self):
        a=np.zeros((256,256,4),np.uint8);a[100:112,120:130]=[150,150,150,255]
        result=fit_helmet(Image.fromarray(a),Image.new('RGBA',(20,20),'gold'))
        self.assertEqual(result.getbbox(),(119,99,131,112))

    def test_low_alpha_border_does_not_change_registration(self):
        a=np.zeros((20,20,4),np.uint8);a[:]=[0,100,0,20];a[5:15,5:15]=[50,100,10,254]
        self.assertEqual(crop_asset(Image.fromarray(a)).size,(10,10))

if __name__=='__main__':unittest.main()
