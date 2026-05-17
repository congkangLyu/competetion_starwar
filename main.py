"""
Orbit Wars - Current submission entrypoint.

This file is what gets submitted to Kaggle. It is currently a copy of
agents/blitz.py (the parametric heuristic agent with the 'blitz' preset,
which won the 10-strategy round-robin in the EDA notebook with 72.2%).

To swap in a different agent, copy its contents over this file. Keep
main.py self-contained -- Kaggle's evaluation environment expects a
single-file submission unless you bundle a tar.gz.

Currently selected agent: blitz
"""

import math
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet, Fleet

# BEGIN_STRATEGY
STRATEGY = {
    "dist_weight":   3.0,   # strong preference for nearby planets
    "prod_weight":   0.5,   # mild production bonus
    "weak_weight":   0.0,   # no preference for lightly-defended planets
    "neutral_bonus": 0.0,   # no preference for neutrals over enemies
    "enemy_bonus":   1.0,   # prefer attacking enemy planets
    "attack_buffer": 1.0,   # send exactly the minimum needed
    "min_ships":     1,     # any garrison size can launch
    "use_defense":   False, # no defensive reinforcement
}
# END_STRATEGY


# ── Physics constants ────────────────────────────────────────────────────────
SUN_X, SUN_Y, SUN_R = 50.0, 50.0, 10.0
MAX_SPEED  = 6.0
MAX_DIAG   = 141.421
MAX_SHIPS  = 500.0
WAIT_TURNS = 2


def fleet_speed(ships):
    if ships <= 1:
        return 1.0
    return 1.0 + 5.0 * (math.log(ships) / math.log(1000)) ** 1.5


def _seg_hits_sun(x1, y1, x2, y2, margin=2.0):
    dx, dy = x2 - x1, y2 - y1
    fx, fy = x1 - SUN_X, y1 - SUN_Y
    a = dx * dx + dy * dy
    if a == 0:
        return False
    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - (SUN_R + margin) ** 2
    disc = b * b - 4 * a * c
    if disc < 0:
        return False
    sq = math.sqrt(disc)
    t1, t2 = (-b - sq) / (2 * a), (-b + sq) / (2 * a)
    return (0 <= t1 <= 1) or (0 <= t2 <= 1)


def _capture_cost(sx, sy, tgt):
    dist = math.hypot(sx - tgt.x, sy - tgt.y)
    ships = tgt.ships + 1
    for _ in range(8):
        turns = dist / fleet_speed(ships)
        ships = int(tgt.ships + tgt.production * turns) + 1
    return ships


def _detect_threats(my_planets, fleets, player):
    threats = {}
    for f in fleets:
        if f.owner == player or f.owner < 0:
            continue
        fdx, fdy = math.cos(f.angle), math.sin(f.angle)
        for p in my_planets:
            to_px, to_py = p.x - f.x, p.y - f.y
            dot = fdx * to_px + fdy * to_py
            if dot <= 0:
                continue
            if abs(fdx * to_py - fdy * to_px) > p.radius + 3:
                continue
            turns = dot / fleet_speed(f.ships)
            if p.id not in threats:
                threats[p.id] = [0, float("inf")]
            threats[p.id][0] += f.ships
            threats[p.id][1] = min(threats[p.id][1], turns)
    return {pid: tuple(v) for pid, v in threats.items()}


def make_fresh_agent():
    s = STRATEGY
    tc = [0]

    def _agent(obs):
        tc[0] += 1
        if tc[0] <= WAIT_TURNS:
            return []

        player  = obs.get("player", 0)   if isinstance(obs, dict) else obs.player
        raw_p   = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
        raw_f   = obs.get("fleets", [])  if isinstance(obs, dict) else obs.fleets
        planets = [Planet(*p) for p in raw_p]
        fleets  = [Fleet(*f)  for f in (raw_f or [])]
        my_pl   = [p for p in planets if p.owner == player]
        targets = [p for p in planets if p.owner != player]

        if not my_pl:
            return []

        avail = {p.id: p.ships for p in my_pl}
        moves = []

        if s["use_defense"]:
            pby_id = {p.id: p for p in planets}
            for pid, (inc, turns) in sorted(
                _detect_threats(my_pl, fleets, player).items(),
                key=lambda x: x[1][1],
            ):
                pl = pby_id.get(pid)
                if pl is None:
                    continue
                deficit = inc - (pl.ships + int(pl.production * turns)) + 1
                if deficit <= 0:
                    continue
                helpers = sorted(
                    [p for p in my_pl if p.id != pid and avail[p.id] > 10],
                    key=lambda p: math.hypot(p.x - pl.x, p.y - pl.y),
                )
                for h in helpers:
                    if deficit <= 0:
                        break
                    if _seg_hits_sun(h.x, h.y, pl.x, pl.y):
                        continue
                    send = min(avail[h.id] - 5, deficit)
                    if send <= 0:
                        continue
                    moves.append([h.id, math.atan2(pl.y - h.y, pl.x - h.x), send])
                    avail[h.id] -= send
                    deficit -= send

        if not targets:
            return moves

        targeted = set()
        for src in sorted(my_pl, key=lambda p: -avail[p.id]):
            if avail[src.id] < s["min_ships"]:
                continue
            scored = []
            for tgt in targets:
                if tgt.id in targeted or _seg_hits_sun(src.x, src.y, tgt.x, tgt.y):
                    continue
                dist = math.hypot(src.x - tgt.x, src.y - tgt.y)
                is_n = float(tgt.owner == -1)
                is_e = float(tgt.owner not in (-1, player) and tgt.owner >= 0)
                score = (
                    -s["dist_weight"]    * (dist / MAX_DIAG)
                    + s["prod_weight"]   * (tgt.production / 5.0)
                    - s["weak_weight"]   * (min(tgt.ships, MAX_SHIPS) / MAX_SHIPS)
                    + s["neutral_bonus"] * is_n
                    + s["enemy_bonus"]   * is_e
                )
                scored.append((tgt, score))

            if not scored:
                if avail[src.id] > 15:
                    frn = [p for p in my_pl if p.id != src.id]
                    if frn:
                        dst = min(frn, key=lambda p: math.hypot(p.x - src.x, p.y - src.y))
                        if not _seg_hits_sun(src.x, src.y, dst.x, dst.y):
                            send = avail[src.id] // 2
                            moves.append([src.id, math.atan2(dst.y - src.y, dst.x - src.x), send])
                            avail[src.id] -= send
                continue

            tgt, _ = max(scored, key=lambda x: x[1])
            needed = int(_capture_cost(src.x, src.y, tgt) * s["attack_buffer"])
            if avail[src.id] >= needed > 0:
                moves.append([src.id, math.atan2(tgt.y - src.y, tgt.x - src.x), needed])
                avail[src.id] -= needed
                targeted.add(tgt.id)
            elif avail[src.id] > 15:
                frn = [p for p in my_pl if p.id != src.id]
                if frn:
                    dst = min(frn, key=lambda p: math.hypot(p.x - src.x, p.y - src.y))
                    if not _seg_hits_sun(src.x, src.y, dst.x, dst.y):
                        send = avail[src.id] // 2
                        moves.append([src.id, math.atan2(dst.y - src.y, dst.x - src.x), send])
                        avail[src.id] -= send
        return moves

    return _agent


_agent_instance = make_fresh_agent()


def agent(obs):
    return _agent_instance(obs)
