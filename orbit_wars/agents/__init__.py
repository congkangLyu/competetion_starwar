"""Orbit Wars agent implementations.

All agents inherit from :class:`Agent` (defined in ``base.py``). The base
class handles step counting, decision logging, and lifecycle hooks; the
concrete agents only need to implement :meth:`Agent.act`.

To run an Agent inside ``kaggle_environments.make("orbit_wars")``, wrap it
with :func:`make_kaggle_agent` -- the adapter converts the raw observation
into a :class:`GameState` and serialises returned moves back to the
list-of-lists format the env expects.
"""

from orbit_wars.agents.base import (
    Agent,
    Decision,
    decisions_to_jsonl,
    load_decisions_jsonl,
    make_kaggle_agent,
)
from orbit_wars.agents.sniper import SniperAgent
from orbit_wars.agents.heuristic import HeuristicAgent, HeuristicConfig

__all__ = [
    "Agent",
    "Decision",
    "make_kaggle_agent",
    "decisions_to_jsonl",
    "load_decisions_jsonl",
    "SniperAgent",
    "HeuristicAgent",
    "HeuristicConfig",
]
