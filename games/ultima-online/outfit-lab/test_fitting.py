import unittest
import numpy as np
from PIL import Image
from build import canvas, fit_texture, fit_lightsaber, occlude

class FittingTests(unittest.TestCase):
    def test_ground_origin(self):
        im=Image.new('RGBA',(8,12),'red')
        self.assertEqual(canvas({'image':im,'center':[3,5]}).getbbox(),(125,175,133,187))

    def test_no_alpha_growth_or_limb_bridge(self):
        arr=np.zeros((256,256,4),np.uint8)
        arr[100:130,110:115]=[150,150,150,255]
        arr[100:130,125:130]=[150,150,150,255]
        fitted=np.array(fit_texture(Image.fromarray(arr),Image.new('RGBA',(20,40),'teal')))
        np.testing.assert_array_equal(fitted[:,:,3],arr[:,:,3])
        self.assertFalse(np.array_equal(fitted[:,:,:3],arr[:,:,:3]))

    def test_occlusion_removes_only_selected_regions(self):
        im=Image.new('RGBA',(256,256),'gold');labels=np.zeros((256,256),np.uint8)
        labels[10:20,10:20]=5;labels[25:30,25:30]=3
        clipped=np.array(occlude(im,labels,[5]))
        self.assertTrue(np.all(clipped[labels==5,3]==0))
        self.assertTrue(np.all(clipped[labels!=5,3]==255))

    def test_empty_frame_stays_empty(self):
        im=Image.new('RGBA',(256,256))
        self.assertIsNone(fit_texture(im,Image.new('RGBA',(10,10),'red')).getbbox())

    def test_saber_grip_faces_hand_and_blade_reaches_tip(self):
        src=Image.new('RGBA',(256,256))
        pixels=np.array(src);pixels[100,80:111]=[190,190,190,255]
        design=Image.new('RGBA',(100,10),'red')
        patch=np.array(design);patch[:,:20]=[0,255,0,255]
        labels=np.zeros((256,256),np.uint8);labels[100,111]=5
        result=np.array(fit_lightsaber(Image.fromarray(pixels),Image.fromarray(patch),labels))
        self.assertGreater(result[100,109,1],result[100,109,0])
        self.assertGreater(result[100,82,0],result[100,82,1])

    def test_empty_saber_does_not_invent_blade(self):
        result=fit_lightsaber(Image.new('RGBA',(256,256)),Image.new('RGBA',(100,10),'red'),np.zeros((256,256),np.uint8))
        self.assertIsNone(result.getbbox())

if __name__=='__main__':unittest.main()
