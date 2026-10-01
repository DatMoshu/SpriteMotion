"""Source/render comparisons, silhouettes, contact sheets and render-camera setup.

The drawing helpers (sheets) need Pillow and load on first use, so Blender's
Python can import rendering.ortho and rendering.compare.render_path without it.
"""
from .compare import FrameMetrics, compare_dataset, compare_frame, render_path, silhouette_iou
from .ortho import blender_camera_params

__all__ = ["FrameMetrics", "blender_camera_params", "compare_dataset", "compare_frame", "contact_sheet",
           "difference_image", "draw_pose", "render_path", "silhouette_iou"]


def __getattr__(name):
    if name in ("contact_sheet", "difference_image", "draw_pose"):
        from . import sheets
        return getattr(sheets, name)
    raise AttributeError(name)
