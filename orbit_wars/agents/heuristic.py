"""
HeuristicAgent -- the parametric scoring agent (blitz preset by default).

Strategy
--------
For each owned planet, score every viable target with a weighted sum of
features and launch at the highest-scoring target the source can afford:

    score = -dist_weight    * (dist / MAX_DIAG)
          +  prod_weight    * (production / 5)
          -  weak_weight    * (min(ships, 500) / 500)
          +  neutral_bonus  * I[neutral]
          +  enemy_bonus    * I[enemy_player]

The ship cost for each attack is solved iteratively (production during
transit is taken into account, see :meth:`HeuristicAgent._capture_cost`).
Surplus ships flow toward the nearest friendly planet ("consolidate").
Optional defensive pass diverts ships home when an incoming enemy fleet
is detected.

This is a 1:1 port of the original ``agents/blitz.py`` on top of the new
:class:`Agent` abstraction:

* Strategy parameters live in :class:`HeuristicConfig` instead of a
  module-level ``STRATEGY`` dict, so swapping presets means instantiating
  with a different config (and, eventually in Step 3, loading the config
  from YAML).
* Step counting comes from :attr:`GameState.step` instead of a closure
  variable -- :meth:`Agent.reset` correctly clears it between games.
* Every move flows through :meth:`Agent.log` with structured fields so
  replays can show *why* each launch happened.

Presets
-------
* :meth:`HeuristicAgent.blitz` returns the default-config agent that won
  the 10-strategy round-robin in the EDA notebook with 72.2% winrate.
* :meth:`HeuristicAgent.with_defense` returns the same scoring policy
  with the defensive reinforcement pass enabled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from orbit_wars.core.geometry import (
    MAX_DIAG,
    angle_to,
    dist,
    fleet_speed,
    seg_hits_sun,
)
from orbit_wars.core.state import GameState, Move
from orbit_wars.agents.base import Agent

if TYPE_CHECKING:
    from orbit_wars.core.state import Planet


# ─────────────────────────────────────────────────────────────────────────
# Strategy parameters
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class HeuristicConfig:
    """All tunable parameters for :class:`HeuristicAgent` in one place.

    The defaults reproduce the ``blitz`` preset from the original
    ``agents/blitz.py`` (the 72.2% winrate baseline)."""

    # ── Scoring weights ──
    dist_weight:   float = 3.0   # strong preference for nearby planets
    prod_weight:   float = 0.5   # mild bonus for high-production targets
    weak_weight:   float = 0.0   # penalty for heavily garrisoned targets
    neutral_bonus: float = 0.0   # additive bonus when target is neutral
    enemy_bonus:   float = 1.0   # additive bonus when target is enemy

    # ── Attack sizing ──
    attack_buffer: float = 1.0   # multiplier on the iterative capture cost
    min_ships:     int   = 1     # don't launch from sources below this

    # ── Defensive reinforcement ──
    use_defense:   bool  = False
    defense_reserve: int = 5     # never leave a source below this in defense

    # ── Pacing ──
    wait_turns:    int   = 2     # skip the first N turns (let home build up)

    # ── Consolidation (surplus ships -> nearest friendly) ──
    consolidate_threshold: int = 15  # only consolidate if availability > this
    consolidate_fraction:  float = 0.5  # send this fraction of availability

    # ── Normalisers (kept on the config so they can be tuned, too) ──
    max_ships_norm: float = 500.0


# ─────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────
class HeuristicAgent(Agent):
    """Parametric heuristic agent. See module docstring."""

    name = "heuristic"

    def __init__(self, config: HeuristicConfig | None = None) -> None:
        super().__init__()
        self.config = config or HeuristicConfig()

    # ── Preset constructors ─────────────────────────────────────────
    @classmethod
    def blitz(cls) -> "HeuristicAgent":
        """The 72.2% winrate preset from the EDA notebook -- our baseline."""
        return cls(HeuristicConfig())

    @classmethod
    def with_defense(cls) -> "HeuristicAgent":
        """Blitz scoring + defensive reinforcement enabled."""
        return cls(HeuristicConfig(use_defense=True))

    # ── Main entry point ─────────────────────────────────────────────
    def act(self, state: GameState) -> list[Move]:
        s = self.config

        # Skip the first few turns -- the home planet is too sparse to act on
        if state.step < s.wait_turns:
            return []
        if not state.my_planets:
            return []

        # Per-turn ship budget; both defense and attack passes draw from it
        availability: dict[int, int] = {p.id: p.ships for p in state.my_planets}
        moves: list[Move] = []

        if s.use_defense:
            moves.extend(self._defense_pass(state, availability))

        if not state.non_my_planets:
            return moves

        moves.extend(self._attack_pass(state, availability))
        return moves

    # ────────────────────────────────────────────────────────────────
    # Internal helpers
    # ────────────────────────────────────────────────────────────────
    def _capture_cost(self, sx: float, sy: float, tgt: "Planet") -> int:
        """Iteratively solve ``needed = garrison + production * (dist / speed(needed)) + 1``.

        Larger fleets travel faster, so the fixed point converges quickly
        (8 iterations is more than enough)."""
        d = dist(sx, sy, tgt.x, tgt.y)
        ships = tgt.ships + 1
        for _ in range(8):
            turns = d / fleet_speed(ships)
            ships = int(tgt.ships + tgt.production * turns) + 1
        return ships

    def _detect_threats(self, state: GameState) -> dict[int, tuple[int, float]]:
        """Cone-test every enemy fleet against every owned planet.

        Returns ``{planet_id: (total_incoming_ships, min_arrival_turns)}``.
        A fleet is "threatening" a planet iff the planet sits in front of
        the fleet's heading and within ``planet.radius + 3`` of its line."""
        threats: dict[int, list] = {}
        for f in state.enemy_fleets:
            fdx, fdy = math.cos(f.angle), math.sin(f.angle)
            for p in state.my_planets:
                tdx, tdy = p.x - f.x, p.y - f.y
                dot = fdx * tdx + fdy * tdy
                if dot <= 0:
                    continue
                if abs(fdx * tdy - fdy * tdx) > p.radius + 3:
                    continue
                turns = dot / fleet_speed(f.ships)
                if p.id not in threats:
                    threats[p.id] = [0, float("inf")]
                threats[p.id][0] += f.ships
                if turns < threats[p.id][1]:
                    threats[p.id][1] = turns
        return {pid: (v[0], v[1]) for pid, v in threats.items()}

    def _defense_pass(
        self, state: GameState, availability: dict[int, int]
    ) -> list[Move]:
        """Top up planets under threat from the nearest healthy friend."""
        s = self.config
        moves: list[Move] = []
        threats = self._detect_threats(state)

        # Process the most-urgent threats first
        for pid, (incoming, turns) in sorted(threats.items(), key=lambda kv: kv[1][1]):
            target_planet = state.planet_by_id.get(pid)
            if target_planet is None:
                continue
            deficit = (
                incoming
                - (target_planet.ships + int(target_planet.production * turns))
                + 1
            )
            if deficit <= 0:
                continue

            helpers = sorted(
                (p for p in state.my_planets
                 if p.id != pid and availability[p.id] > 10),
                key=lambda p: dist(p.x, p.y, target_planet.x, target_planet.y),
            )
            for h in helpers:
                if deficit <= 0:
                    break
                if seg_hits_sun(h.x, h.y, target_planet.x, target_planet.y):
                    continue
                send = min(availability[h.id] - s.defense_reserve, deficit)
                if send <= 0:
                    continue
                move = Move(
                    from_planet_id=h.id,
                    angle=angle_to(h.x, h.y, target_planet.x, target_planet.y),
                    ships=send,
                )
                moves.append(move)
                self.log(
                    move,
                    reason="defend",
                    target_id=pid,
                    incoming=incoming,
                    eta_turns=turns,
                    deficit=deficit,
                )
                availability[h.id] -= send
                deficit -= send
        return moves

    def _score_target(self, src: "Planet", tgt: "Planet", state: GameState) -> float:
        s = self.config
        d = dist(src.x, src.y, tgt.x, tgt.y)
        is_neutral = float(tgt.owner == -1)
        is_enemy = float(tgt.owner >= 0 and tgt.owner != state.player)
        return (
            -s.dist_weight    * (d / MAX_DIAG)
            + s.prod_weight   * (tgt.production / 5.0)
            - s.weak_weight   * (min(tgt.ships, s.max_ships_norm) / s.max_ships_norm)
            + s.neutral_bonus * is_neutral
            + s.enemy_bonus   * is_enemy
        )

    def _attack_pass(
        self, state: GameState, availability: dict[int, int]
    ) -> list[Move]:
        """Richest planet first, pick best-scored unique target it can afford."""
        s = self.config
        moves: list[Move] = []
        targeted: set[int] = set()

        for src in sorted(state.my_planets, key=lambda p: -availability[p.id]):
            if availability[src.id] < s.min_ships:
                continue

            # Score every legal target
            scored: list[tuple["Planet", float]] = []
            for tgt in state.non_my_planets:
                if tgt.id in targeted:
                    continue
                if seg_hits_sun(src.x, src.y, tgt.x, tgt.y):
                    continue
                scored.append((tgt, self._score_target(src, tgt, state)))

            if not scored:
                moves.extend(self._consolidate(state, src, availability))
                continue

            tgt, best = max(scored, key=lambda x: x[1])
            needed = int(self._capture_cost(src.x, src.y, tgt) * s.attack_buffer)
            if availability[src.id] >= needed > 0:
                move = Move(
                    from_planet_id=src.id,
                    angle=angle_to(src.x, src.y, tgt.x, tgt.y),
                    ships=needed,
                )
                moves.append(move)
                self.log(
                    move,
                    reason="attack",
                    score=best,
                    target_id=tgt.id,
                    target_owner=tgt.owner,
                    target_ships=tgt.ships,
                    ships_sent=needed,
                )
                availability[src.id] -= needed
                targeted.add(tgt.id)
            else:
                # Can't afford the best target -- consolidate instead
                moves.extend(self._consolidate(state, src, availability))
        return moves

    def _consolidate(
        self, state: GameState, src: "Planet", availability: dict[int, int]
    ) -> list[Move]:
        """Spill surplus ships toward the nearest friendly planet."""
        s = self.config
        if availability[src.id] <= s.consolidate_threshold:
            return []
        friends = [p for p in state.my_planets if p.id != src.id]
        if not friends:
            return []
        dst = min(friends, key=lambda p: dist(p.x, p.y, src.x, src.y))
        if seg_hits_sun(src.x, src.y, dst.x, dst.y):
            return []
        send = int(availability[src.id] * s.consolidate_fraction)
        if send <= 0:
            return []
        move = Move(
            from_planet_id=src.id,
            angle=angle_to(src.x, src.y, dst.x, dst.y),
            ships=send,
        )
        self.log(
            move,
            reason="consolidate",
            target_id=dst.id,
            ships_sent=send,
        )
        availability[src.id] -= send
        return [move]
