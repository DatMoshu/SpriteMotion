"""Crossing surfaces, bounded contact and hidden-face independence of holdout."""
import importlib.util
from pathlib import Path
import numpy as np

spec = importlib.util.spec_from_file_location('body_occlusion', Path(__file__).resolve().parents[2] / 'tools/uo-content/occlusion.py')
occlusion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(occlusion)


def test_side_identity_and_twist_aliases():
    assert occlusion.region('forearm_twist.L') == 'forearm.L'
    assert occlusion.region('forearm.R') != occlusion.region('forearm.L')
    assert occlusion.region('finger_index.R') == 'hand.R'


def test_full_body_depth_and_contact_limit():
    # Visible, torso occlusion, own-surface penetration, own far side,
    # opposite arm, uncovered background, exact tolerance boundary.
    body = np.array([2., 2., 2., 2., 2., np.inf, 2.])
    item = np.array([1.9, 2.3, 2.015, 2.3, 2.015, 2.3, 2.02])
    own_body = np.array([2., np.inf, 2., 2., np.inf, np.inf, 2.])
    own_item = item.copy()
    assert occlusion.blocked_pixels(body, item, .01, [(own_body, own_item)], .02).tolist() == [False, True, False, True, True, False, False]


def test_rear_garment_cannot_exempt_front_item():
    body, item = np.array([2.]), np.array([2.015])
    assert occlusion.blocked_pixels(body, item, .01, [(body, np.array([2.1]))], .2)[0]


def test_strict_body_mode_and_unknown_contact():
    body, item = np.array([2., np.inf]), np.array([2.015, np.inf])
    assert occlusion.blocked_pixels(body, item, .01).tolist() == [True, False]


def test_zero_margin_retains_fractional_contact_tolerance():
    body, item = np.array([2.]), np.array([2.015])
    assert not occlusion.blocked_pixels(body, item, 0, [(body, item)], .02)[0]


def test_render_masks_color_without_drawing_body_and_none_is_unchanged():
    from types import SimpleNamespace
    holdout = occlusion.BodyHoldout.__new__(occlusion.BodyHoldout)
    holdout.body = object()  # Pristine proxy, not the fitting body from env.
    item = SimpleNamespace(hide_render=False)
    holdout.items = [(item, np.array(['forearm.L']))]
    holdout.body_regions = np.array(['chest'])
    original = np.ones((1, 2, 4))
    original[..., :3] = [.8, .4, .1]
    def raster(objects, mask=None):
        if objects[0] is holdout.body:
            return np.array([[True, True]]), np.array([[2., 2.]])
        assert objects[0] is item
        return np.array([[True, True]]), np.array([[2.3, 1.9]])
    env = {'raster': raster, 'body': object()}
    holdout.configure('clothing', {'enabled': True, 'inward': .02})
    result, coverage = holdout.render(env, original, .01)
    assert not result[0, 0].any()
    np.testing.assert_array_equal(result[0, 1], original[0, 1])
    assert original[0, 0, 3] == 1
    assert coverage.all()
    holdout.configure('none', {})
    result, _ = holdout.render(env, original, .01)
    np.testing.assert_array_equal(result, original)
