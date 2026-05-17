"""Replay-side analysis and visualisation.

This subpackage turns a finished game's :func:`env.steps` trace and the
decision log produced by an :class:`~orbit_wars.agents.Agent` into things
a human can look at: SVG snapshots, time-slider HTML pages, and
per-turn data structures.

Public surface:
    load_kaggle_replay(path)        -> raw steps from a kaggle replay JSON
    extract_states(steps, player)   -> list[GameState], one per turn
    render_frame_svg(state, ...)    -> SVG <svg>...</svg> snippet
    render_replay_html(states, ...) -> standalone HTML document
"""

from orbit_wars.analysis.replay import (
    extract_states,
    load_kaggle_replay,
)
from orbit_wars.analysis.viz import (
    PLAYER_COLORS,
    render_frame_svg,
    render_replay_html,
)

__all__ = [
    "PLAYER_COLORS",
    "extract_states",
    "load_kaggle_replay",
    "render_frame_svg",
    "render_replay_html",
]
