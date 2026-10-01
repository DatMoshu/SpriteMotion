"""Focused algorithm checks; run with python -m unittest discover -s ... ."""
import unittest
import numpy as np
import fit_armature as F


class ArmatureTests(unittest.TestCase):
    def setUp(self):
        self.prior={n:np.array([110.,130.+i]) for i,n in enumerate(F.NAMES)}
        for c in F.CHAINS:
            x=110. if c['name'].endswith('A') else 140.
            for k,n in enumerate(c['joints']):self.prior[n]=np.array([x,140.+10*k])

    def test_empty_masks_do_not_invent_joint_motion(self):
        fit,status,metrics=F.fit_pose(np.zeros((256,256),np.uint8),self.prior)
        self.assertEqual(metrics,[])
        self.assertTrue(all(s=='inferred' for s in status.values()))
        for n in F.NAMES:np.testing.assert_allclose(fit[n],self.prior[n],atol=.001)

    def test_merged_limb_pixels_are_never_shared_by_chains(self):
        labels=np.zeros((256,256),np.uint8)
        labels[145:150,108:143]=4
        split=F.split_regions(labels,self.prior,'arm')
        self.assertFalse((split['A'][0]&split['B'][0]).any())
        self.assertTrue(split['A'][0][147,110])
        self.assertTrue(split['B'][0][147,140])
        self.assertFalse(split['A'][0][147,125])
        self.assertFalse(split['B'][0][147,125])

    def test_far_away_mask_does_not_drag_a_hidden_arm(self):
        labels=np.zeros((256,256),np.uint8)
        labels[200:210,200:210]=4
        split=F.split_regions(labels,self.prior,'arm')
        self.assertFalse(any(m.any() for side in split.values() for m in side))


if __name__=='__main__':unittest.main()
