"""Shared geometry data structures."""

from collections import namedtuple

PlanformSolve = namedtuple("PlanformSolve", "chords c_root c_tip b S AR lam MAC")

__all__ = ["PlanformSolve"]
