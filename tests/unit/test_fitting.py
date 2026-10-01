import math

import numpy as np
import pytest

from spritemotion.fitting.camera import AffineOrthographicCamera, direction_rotations, yaw_between
from spritemotion.fitting.rig import quat_from_rotvec, quat_to_matrix, quat_to_rotvec
from spritemotion.fitting.solver import least_squares
from spritemotion.jsonio import read_json
from spritemotion.rendering.ortho import blender_camera_params

from conftest import UO

UO_CAMERAS = ["ground-grid.json", "character-depth-0447.json"]


def test_quaternion_round_trip():
    rng = np.random.default_rng(1)
    for _ in range(50):
        v = rng.uniform(-3, 3, 3)
        if np.linalg.norm(v) > math.pi:
            continue
        assert np.allclose(quat_to_rotvec(quat_from_rotvec(v)), v, atol=1e-9)
        m = quat_to_matrix(quat_from_rotvec(v))
        assert np.allclose(m @ m.T, np.eye(3), atol=1e-12)


def test_direction_rotation_turns_forward_onto_facing():
    rotations = direction_rotations([{"id": 0, "facing": [1, 1]}, {"id": 1, "facing": [0, 1]}], (0.0, -1.0))
    forward = np.array([0.0, -1.0, 0.0])
    assert np.allclose(rotations[0] @ forward, np.array([1, 1, 0]) / math.sqrt(2))
    assert np.allclose(rotations[1] @ forward, [0, 1, 0])
    assert yaw_between((1, 0), (0, 1)) == pytest.approx(math.pi / 2)


@pytest.mark.parametrize("name", UO_CAMERAS)
def test_blender_camera_params_reproduce_projection(name):
    """Rebuild the orthographic projection from the Blender parameters and compare (no Blender needed)."""
    data = read_json(UO / "profiles" / "cameras" / name)
    camera = AffineOrthographicCamera.from_dict(data, [128, 192])
    p = blender_camera_params(camera, 256, 256)
    rot = np.array(p["rotation"])
    right, up = rot[:, 0], rot[:, 1]
    width_units = p["ortho_scale"]
    height_units = width_units * 256 * p["pixel_aspect_y"] / (256 * p["pixel_aspect_x"])
    points = np.random.default_rng(3).uniform(-2, 2, (20, 3))
    rel = points - np.array(p["location"])
    px = (rel @ right / width_units + 0.5) * 256 - 0.5
    py = (0.5 - rel @ up / height_units) * 256 - 0.5
    assert np.allclose(np.column_stack([px, py]), camera.project(points), atol=1e-6)


def test_blender_camera_rejects_skewed_projection():
    camera = AffineOrthographicCamera(np.array([[22, 22, 0], [22, -10, -31]]), np.array([128, 192]))
    with pytest.raises(ValueError):
        blender_camera_params(camera, 256, 256)


def test_least_squares_respects_bounds():
    result = least_squares(lambda x: np.array([x[0] - 3.0, 2 * (x[1] + 1.0)]), np.zeros(2),
                           lower=np.array([-10, -0.5]), upper=np.array([10, 10]))
    assert result.x == pytest.approx([3.0, -0.5], abs=1e-4)
