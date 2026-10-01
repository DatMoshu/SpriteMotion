import unittest
import numpy as np
from PIL import Image
from build_mario import mustache

class MarioTests(unittest.TestCase):
    def test_mustache_clips_to_head_and_hides_on_back(self):
        labels=np.zeros((256,256),np.uint8);labels[100:111,122:133]=1
        design=Image.new('RGBA',(40,15),'black')
        front=np.array(mustache(design,labels,0))
        self.assertTrue((front[:,:,3]>0).any())
        self.assertFalse(np.any((front[:,:,3]>0)&(labels!=1)))
        self.assertIsNone(mustache(design,labels,4).getbbox())

    def test_missing_head_does_not_invent_face(self):
        self.assertIsNone(mustache(Image.new('RGBA',(20,10),'black'),np.zeros((256,256),np.uint8),0).getbbox())

if __name__=='__main__':unittest.main()
