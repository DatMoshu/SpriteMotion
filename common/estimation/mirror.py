"""Fill a direction from its mirrored partner.

Only valid when the dataset says the two views are mirror images (the
direction's mirror_of) - true for games that store some facings and flip
them at draw time. Chain names are preserved across the mirror by default.
"""
from __future__ import annotations

from ..poses.annotations import AnnotationSet, mirror_pose
from ..poses.skeleton import Skeleton
from ..sprites.dataset import Dataset
from .base import Estimator, register


@register
class MirrorEstimator(Estimator):
    name = "mirror"

    def __init__(self, swap_sides: bool = False):
        self.swap_sides = swap_sides

    def estimate(self, dataset: Dataset, skeleton: Skeleton, sequence: str, existing: AnnotationSet) -> AnnotationSet:
        swap = skeleton.swap_map() if self.swap_sides else None
        for direction in dataset.directions:
            partner = direction.get("mirror_of")
            if partner is None:
                continue
            for _, record in dataset.frames(sequence):
                if record["direction"] != direction["id"] or existing.get(direction["id"], record["frame"]):
                    continue
                source = existing.get(partner, record["frame"])
                if source is None:
                    continue
                existing.put(mirror_pose(source, dataset.mirror_axis_x, direction["id"], record["frame_id"],
                                         record["fingerprint"], swap))
        return existing
