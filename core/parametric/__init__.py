"""Parametric telecom geometry decision layer.

This package contains the business logic that decides how each object in a
SceneSpec should be produced. It is intentionally independent of Blender/bpy
so it can be unit-tested and reused by the orchestrator, the API layer, and
QA reporting.
"""

from core.parametric.resolver import ParametricModelResolver, resolve_scene_strategies

__all__ = ["ParametricModelResolver", "resolve_scene_strategies"]
