"""
Replay loader: convert a finished game's step trace into a list of
:class:`GameState` objects.

The kaggle env produces two roughly equivalent things:

1. ``env.steps`` -- a Python list-of-lists held in memory after
   ``env.run()`` returns. Each row is one turn, each cell is one
   agent's per-turn dict with ``observation`` etc.
2. The serialised JSON dumped by ``env.toJSON()`` or downloaded with
   ``kaggle competitions replay <episode_id>``.

Both have the same shape under the hood. :func:`load_kaggle_replay`
handles the on-disk JSON; :func:`extract_states` walks either form and
emits one :class:`GameState` per turn (parsed via
:meth:`GameState.from_obs`).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from orbit_wars.core.state import GameState


def load_kaggle_replay(path: str | Path) -> list:
    """Load a kaggle replay JSON file and return the ``steps`` array.

    The on-disk format kaggle hands back from ``kaggle competitions
    replay`` is a dict with several top-level keys; we only need
    ``steps``. If that key is missing the file may have been dumped by
    ``env.toJSON()`` directly in which case the top level *is* the
    structure we want.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "steps" in raw:
        return raw["steps"]
    if isinstance(raw, list):
        return raw
    raise ValueError(f"replay JSON at {path} has unexpected shape")


def _read_observation(step_entry: Any) -> Any:
    """Pull the obs out of one per-agent row (dict OR namespace)."""
    if step_entry is None:
        return None
    if isinstance(step_entry, dict):
        return step_entry.get("observation")
    return getattr(step_entry, "observation", None)


def _patch_player(obs: Any, player: int) -> Any:
    """Return a copy of ``obs`` with ``player=<player>`` set."""
    if isinstance(obs, dict):
        new = dict(obs)
        new["player"] = player
        return new
    new = copy.copy(obs)
    try:
        new.player = player
    except Exception:
        pass
    return new


def extract_states(steps: list, player: int = 0) -> list[GameState]:
    """Walk a step trace and emit one :class:`GameState` per turn.

    Robust to missing observations: turns without obs are skipped, not
    represented as ``None`` -- the caller wants a clean sequence of
    parseable frames.
    """
    out: list[GameState] = []
    for i, step in enumerate(steps):
        if not step:
            continue
        obs = None
        for row in step:
            obs = _read_observation(row)
            if obs is not None:
                break
        if obs is None:
            continue
        try:
            gs = GameState.from_obs(_patch_player(obs, player), step=i)
        except Exception:
            continue
        out.append(gs)
    return out
