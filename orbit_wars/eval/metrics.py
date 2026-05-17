"""
Derived per-player metrics from a kaggle env step trace.

Why this exists
---------------
``MatchResult.reward_a`` only tells you who won and by how much. To
*understand* why an agent won or lost we want richer signals:

* how many planets did each side capture or lose?
* how many fleets did each side launch?
* how many ships did each side waste on the sun?
* how fast did the score gap open up?

Everything in this module is computed from ``env.steps`` alone -- the
public per-turn trace that the kaggle env exposes after ``env.run()``.
That means metrics are **observer-side**: they work for any agent
(builtin, file, preset) and don't require any agent-side instrumentation.

This module is also kaggle-free: it never imports ``kaggle_environments``,
only walks a list-of-lists structure produced by it. Unit-testable in
isolation with a hand-crafted trace.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from orbit_wars.core.geometry import fleet_speed, seg_hits_sun
from orbit_wars.core.state import GameState


@dataclass
class PlayerMetrics:
    """Per-player aggregate signals derived from a finished game."""

    final_score: int             # ships on owned planets + own fleets at end
    planets_captured: int        # owner flips INTO this player
    planets_lost: int            # owner flips OUT of this player
    fleets_launched: int         # new fleets we owned, across the game
    fleets_lost_to_sun: int      # owned fleets that vanished while crossing sun
    ships_lost_to_sun: int       # sum of ships in those fleets
    peak_planets: int            # max planets owned at any point
    survived_turns: int          # turns we owned >= 1 planet or fleet


def _read_observation(step_entry: Any) -> Any:
    """Pull the observation dict out of one step row.

    The kaggle env hands back rows that may be dicts, SimpleNamespaces,
    or kaggle's own ``Struct`` type. ``observation`` is what we need;
    other fields (action/reward/status) are not consulted here.
    """
    if step_entry is None:
        return None
    if isinstance(step_entry, dict):
        return step_entry.get("observation")
    return getattr(step_entry, "observation", None)


def _patch_player(obs: Any, player: int) -> Any:
    """Return a copy of ``obs`` with ``player=<player>``.

    ``env.steps`` records each row from a single agent's perspective.
    To compute *the other* player's metrics we copy the observation and
    rewrite the player id so :meth:`GameState.from_obs` derives the
    correct ``my_planets`` / ``my_fleets`` slices.
    """
    if isinstance(obs, dict):
        new = dict(obs)
        new["player"] = player
        return new
    # namespace-like
    import copy
    new = copy.copy(obs)
    try:
        new.player = player
    except Exception:
        pass
    return new



def _project_to_board_edge(x: float, y: float, angle: float) -> tuple[float, float]:
    """Where does a straight trajectory from (x, y) along ``angle`` leave the
    [0, BOARD_SIZE]^2 playing field? Returns the exit point.

    Used by :func:`compute_metrics` to test whether a vanished fleet's
    extended trajectory would pass through the sun.
    """
    from orbit_wars.core.geometry import BOARD_SIZE
    dx = math.cos(angle)
    dy = math.sin(angle)
    ts: list[float] = []
    if dx > 1e-12:
        ts.append((BOARD_SIZE - x) / dx)
    elif dx < -1e-12:
        ts.append(-x / dx)
    if dy > 1e-12:
        ts.append((BOARD_SIZE - y) / dy)
    elif dy < -1e-12:
        ts.append(-y / dy)
    positive = [t for t in ts if t > 0]
    if not positive:
        return x, y
    t = min(positive)
    return x + dx * t, y + dy * t


def _planet_blocks_before_sun(fleet, gs: GameState, ex: float, ey: float) -> bool:
    """True iff some planet sits closer than the sun on the fleet's
    extended trajectory. Used to suppress sun-death false positives when
    a fleet was actually killed in planetary combat first."""
    from orbit_wars.core.geometry import SUN_X, SUN_Y, dist
    # Approximate "distance to sun along trajectory" as straight-line
    # distance from fleet to sun centre; same approximation for planets.
    d_sun = dist(fleet.x, fleet.y, SUN_X, SUN_Y)
    fdx = math.cos(fleet.angle)
    fdy = math.sin(fleet.angle)
    for p in gs.planets:
        # Drop the fleet's source planet -- it's just been launched from
        # it, so it can't kill the fleet immediately.
        if p.id == fleet.from_planet_id:
            continue
        # planet must be in front of the fleet (positive dot product)
        to_px, to_py = p.x - fleet.x, p.y - fleet.y
        dot = fdx * to_px + fdy * to_py
        if dot <= 0:
            continue
        # perpendicular distance from planet centre to trajectory line
        perp = abs(fdx * to_py - fdy * to_px)
        if perp > p.radius + 0.5:
            continue
        d_planet = dist(fleet.x, fleet.y, p.x, p.y)
        if d_planet < d_sun:
            return True
    return False


def compute_metrics(steps: list, player: int) -> PlayerMetrics:
    """Walk an ``env.steps`` trace and compute :class:`PlayerMetrics` for one side.

    Robust to missing observations, missing fields, and partial traces.
    """
    captured = 0
    lost = 0
    fleets_launched = 0
    fleets_to_sun = 0
    ships_to_sun = 0
    peak_planets = 0
    survived_turns = 0

    prev_planet_owners: dict[int, int] | None = None
    prev_fleet_ids: set[int] = set()
    # snapshot of the previous turn's fleets so we can replay their final
    # one-turn flight when they disappear
    prev_fleets_by_id: dict[int, Any] = {}

    last_state: GameState | None = None

    for step in steps:
        if not step:
            continue
        # ``step`` is a list of per-agent rows; take whichever has an obs.
        obs = None
        for row in step:
            obs = _read_observation(row)
            if obs is not None:
                break
        if obs is None:
            continue

        obs = _patch_player(obs, player)
        try:
            gs = GameState.from_obs(obs)
        except Exception:
            continue
        last_state = gs

        # ── planets: detect ownership flips ──────────────────────────
        cur_planet_owners = {p.id: p.owner for p in gs.planets}
        if prev_planet_owners is not None:
            for pid, owner in cur_planet_owners.items():
                prev = prev_planet_owners.get(pid)
                if prev is None:
                    continue
                if prev == player and owner != player:
                    lost += 1
                if prev != player and owner == player:
                    captured += 1
        prev_planet_owners = cur_planet_owners

        # ── fleets: detect launches and sun-deaths ───────────────────
        cur_fleet_ids = {f.id for f in gs.fleets}
        cur_fleets_by_id = {f.id: f for f in gs.fleets}

        for fid in cur_fleet_ids - prev_fleet_ids:
            f = cur_fleets_by_id[fid]
            if f.owner == player:
                fleets_launched += 1

        for fid in prev_fleet_ids - cur_fleet_ids:
            f = prev_fleets_by_id.get(fid)
            if f is None or f.owner != player:
                continue
            # The fleet vanished between turns. Decide if the cause was
            # the sun by extending its trajectory line to the board edge
            # and checking whether that segment crosses the sun *and*
            # is closer to the fleet's last position than any planet it
            # could have hit. This is observer-side and approximate; it
            # will misattribute a fleet that simultaneously hit a planet
            # while passing through the sun's shadow, which is rare.
            ex, ey = _project_to_board_edge(f.x, f.y, f.angle)
            if not seg_hits_sun(f.x, f.y, ex, ey, margin=0.0):
                continue
            # If a planet sits along the trajectory and is closer than
            # the sun, attribute the death to the planet instead.
            if _planet_blocks_before_sun(f, gs, ex, ey):
                continue
            fleets_to_sun += 1
            ships_to_sun += f.ships

        prev_fleet_ids = cur_fleet_ids
        prev_fleets_by_id = cur_fleets_by_id

        # ── presence / score ────────────────────────────────────────
        own_planets = len(gs.my_planets)
        peak_planets = max(peak_planets, own_planets)
        if own_planets > 0 or len(gs.my_fleets) > 0:
            survived_turns += 1

    final_score = last_state.my_total_ships if last_state is not None else 0

    return PlayerMetrics(
        final_score=int(final_score),
        planets_captured=captured,
        planets_lost=lost,
        fleets_launched=fleets_launched,
        fleets_lost_to_sun=fleets_to_sun,
        ships_lost_to_sun=ships_to_sun,
        peak_planets=peak_planets,
        survived_turns=survived_turns,
    )
