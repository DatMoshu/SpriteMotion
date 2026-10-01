"""Interface for generating initial joint estimates.

An estimator proposes poses for frames that have none. Its output always goes
to the estimate layer, never the correction layer, and must say how it was
produced (provenance.method / estimator) and whether it was read from the
sprite pixels (independent=True) or derived from another model (False).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..poses.annotations import AnnotationSet
from ..poses.skeleton import Skeleton
from ..sprites.dataset import Dataset


class Estimator(ABC):
    name: str = "estimator"
    independent: bool = False

    @abstractmethod
    def estimate(self, dataset: Dataset, skeleton: Skeleton, sequence: str, existing: AnnotationSet) -> AnnotationSet:
        """Return `existing` extended with estimates for frames it can handle. Never overwrite existing poses."""


_REGISTRY: dict[str, type[Estimator]] = {}


def register(cls: type[Estimator]) -> type[Estimator]:
    _REGISTRY[cls.name] = cls
    return cls


def available() -> dict[str, type[Estimator]]:
    return dict(_REGISTRY)
