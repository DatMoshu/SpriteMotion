import unittest
import numpy as np
from PIL import Image
from build_tracksuit import cloth, chain_image

class TracksuitTests(unittest.TestCase):
    def test_stripes_stay_on_limb_and_keep_native_alpha(self):
        pixels=np.zeros((256,256,4),np.uint8)
        pixels[110:140,100:130]=[160,160,160,255]
        limb=np.zeros((256,256),bool);limb[110:140,100:106]=True
        result=np.array(cloth(Image.fromarray(pixels),Image.new('RGBA',(40,40),'red'),limb))
        np.testing.assert_array_equal(result[:,:,3],pixels[:,:,3])
        white=(result[:,:,0]>200)&(result[:,:,1]>200)&(result[:,:,3]>0)
        self.assertTrue(white.any());self.assertFalse(np.any(white&~limb))
        self.assertGreater(result[120,120,0],result[120,120,1]*2)

    def test_chain_is_front_only_and_clipped_to_torso(self):
        labels=np.zeros((256,256),np.uint8);labels[120:150,115:135]=3
        design=Image.new('RGBA',(30,20),'gold')
        self.assertIsNone(chain_image(design,labels,7).getbbox())
        result=np.array(chain_image(design,labels,3))
        self.assertTrue((result[:,:,3]>0).any())
        self.assertFalse(np.any((result[:,:,3]>0)&(labels!=3)))

if __name__=='__main__':unittest.main()
