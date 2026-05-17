"""
Orbit Wars - Nearest Planet Sniper Agent (baseline)

The original baseline shipped with the project. Captures the nearest
unowned planet when it has enough ships to guarantee the takeover.

Strategy:
  For each planet we own, find the closest planet we don't own.
  If we have more ships than the target's garrison, send exactly
  enough to capture it (garrison + 1). Otherwise, wait and accumulate.

Known weaknesses (see agents/blitz.py for fixes):
  - Ignores travel time -- target keeps producing ships during transit
  - Uses naive `garrison + 1` instead of solving for capture cost
  - Doesn't avoid the sun -- straight-line aim may pass through it
  - No coordination across source planets (multiple may target the same)
  - Ignores orbital motion of inner planets
"""

import math
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet


def agent(obs):
    moves = []
    player = obs.get("player", 0) if isinstance(obs, dict) else obs.player
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets

    planets = [Planet(*p) for p in raw_planets]
    my_planets = [p for p in planets if p.owner == player]
    targets = [p for p in planets if p.owner != player]

    if not targets:
        return moves

    for mine in my_planets:
        nearest = None
        min_dist = float("inf")
        for t in targets:
            dist = math.sqrt((mine.x - t.x) ** 2 + (mine.y - t.y) ** 2)
            if dist < min_dist:
                min_dist = dist
                nearest = t

        if nearest is None:
            continue

        ships_needed = nearest.ships + 1

        if mine.ships >= ships_needed:
            angle = math.atan2(nearest.y - mine.y, nearest.x - mine.x)
            moves.append([mine.id, angle, ships_needed])

    return moves
