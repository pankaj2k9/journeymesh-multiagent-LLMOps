"""LangGraph orchestration for JourneyMesh.

The workflow is exposed lazily so that ``app.graph.state`` - which the agents
and the evaluation rules import - can be loaded without pulling in the graph
itself.
"""

from __future__ import annotations

from typing import Any

from app.graph.state import TravelState, new_state

__all__ = ["TravelState", "new_state", "TravelWorkflow", "get_workflow"]

_LAZY = {
    "TravelWorkflow": ("app.graph.travel_graph", "TravelWorkflow"),
    "get_workflow": ("app.graph.travel_graph", "get_workflow"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module 'app.graph' has no attribute '{name}'")
    from importlib import import_module

    return getattr(import_module(target[0]), target[1])
