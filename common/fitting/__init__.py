"""2D projection, rig kinematics and 3D pose fitting utilities."""
from .camera import AffineOrthographicCamera, direction_rotations, rotation_z, yaw_between
from .fit import FitSettings, FrameFit, PoseFitter, ViewTarget, matrix_to_quat
from .mapping import RigMapping
from .rig import Bone, Rig, basis_matrix, quat_from_rotvec, quat_multiply, quat_to_matrix, quat_to_rotvec
from .solver import SolveResult, least_squares

__all__ = ["AffineOrthographicCamera", "Bone", "FitSettings", "FrameFit", "PoseFitter", "Rig", "RigMapping",
           "SolveResult", "ViewTarget", "basis_matrix", "direction_rotations", "least_squares", "matrix_to_quat",
           "quat_from_rotvec", "quat_multiply", "quat_to_matrix", "quat_to_rotvec", "rotation_z", "yaw_between"]
