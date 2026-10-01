"""A small bounded Levenberg-Marquardt least-squares solver (numpy only).

Blender's bundled Python ships numpy but not scipy, so fitting code in this
package avoids scipy. Problems here are small (tens of parameters, hundreds of
residuals); forward-difference Jacobians are adequate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass
class SolveResult:
    x: np.ndarray
    cost: float
    initial_cost: float
    iterations: int
    evaluations: int
    converged: bool


def least_squares(residual: Callable[[np.ndarray], np.ndarray], x0: np.ndarray, lower: np.ndarray | None = None,
                  upper: np.ndarray | None = None, max_iterations: int = 60, step: float = 1e-4,
                  tolerance: float = 1e-6) -> SolveResult:
    x = np.asarray(x0, dtype=float).copy()
    lower = np.full_like(x, -np.inf) if lower is None else np.asarray(lower, dtype=float)
    upper = np.full_like(x, np.inf) if upper is None else np.asarray(upper, dtype=float)
    x = np.clip(x, lower, upper)
    r = residual(x)
    cost = float(r @ r)
    initial = cost
    damping = 1e-2
    evaluations = 1
    converged = False
    iteration = 0
    for iteration in range(1, max_iterations + 1):
        jacobian = np.empty((r.size, x.size))
        for i in range(x.size):
            h = step if x[i] + step <= upper[i] else -step
            probe = x.copy()
            probe[i] += h
            jacobian[:, i] = (residual(probe) - r) / h
        evaluations += x.size
        gradient = jacobian.T @ r
        normal = jacobian.T @ jacobian
        improved = False
        for _ in range(10):
            try:
                delta = np.linalg.solve(normal + damping * np.diag(np.diag(normal) + 1e-9), -gradient)
            except np.linalg.LinAlgError:
                damping *= 10
                continue
            candidate = np.clip(x + delta, lower, upper)
            r_new = residual(candidate)
            evaluations += 1
            new_cost = float(r_new @ r_new)
            if new_cost < cost:
                shrink = cost - new_cost
                x, r, cost = candidate, r_new, new_cost
                damping = max(damping / 3, 1e-9)
                improved = True
                if shrink < tolerance * max(cost, 1e-12) or np.linalg.norm(delta) < tolerance:
                    converged = True
                break
            damping *= 4
        if not improved:
            converged = True
            break
        if converged:
            break
    return SolveResult(x, cost, initial, iteration, evaluations, converged)
