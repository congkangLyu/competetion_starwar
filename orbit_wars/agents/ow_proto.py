"""
OW-Proto agent, ported from the "1000+ Public Score Agent" notebook.

The strategy is a high-production-core expansion heuristic:

* score targets by distance, production, enemy ownership, ETA, and cost
* predict orbiting target positions before firing
* remember fleets already en route so targets are not overfilled
* reinforce planets that are predicted to lose an incoming fight
* coordinate multi-source attacks when one planet cannot afford the target

Compared with the original notebook, the global mutable lists are instance
state and are cleared by ``reset()``, so a single Agent can safely play many
games in one Python process.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from orbit_wars.agents.base import Agent
from orbit_wars.core.geometry import (
    SUN_R,
    SUN_X,
    SUN_Y,
    angle_to,
    dist,
    fleet_speed,
    is_orbiting,
    orbital_position,
)
from orbit_wars.core.state import Fleet, GameState, Move, Planet


@dataclass
class OwProtoConfig:
    """Tunable parameters for :class:`OwProtoAgent`."""

    min_ships_mine_attack: int = 5
    min_ships_target_coop_attack: int = 20
    coop_planet_cap: int = 8
    lookahead_ticks: int = 60
    wait_turns: int = 2

    formula_dist: float = 100.0
    formula_prod_mult: float = 15.0
    formula_enemy_bonus_mult: float = 10.0
    formula_total_ships_percent: float = 0.7
    formula_eta_mult: float = 2.0

    skip_comets: bool = True


@dataclass
class _FleetPlan:
    mine_id: int
    target_id: int
    angle: float
    ships: int
    arrive_tick: int


@dataclass
class _ReinforcementPlan:
    mine_id: int
    target_id: int
    angle: float
    ships: int
    arrive_tick: int


class OwProtoAgent(Agent):
    """High-production expansion baseline adapted from the public notebook."""

    name = "ow_proto"

    def __init__(self, config: OwProtoConfig | None = None) -> None:
        super().__init__()
        self.config = config or OwProtoConfig()
        self.fleet_trajectories: list[_FleetPlan] = []
        self.reinforcement_trajectories: list[_ReinforcementPlan] = []

    def reset(self) -> None:
        super().reset()
        self.fleet_trajectories.clear()
        self.reinforcement_trajectories.clear()

    def act(self, state: GameState) -> list[Move]:
        if state.step < self.config.wait_turns:
            return []
        if not state.my_planets or not state.non_my_planets:
            return []

        self._update_fleet_trajectories(state.fleets)
        self._update_reinforcement_trajectories()

        moves: list[Move] = []
        exhausted_planet_ids: set[int] = set()
        under_attack = self._planets_under_attack(state)

        self._add_reinforcements(state, under_attack, exhausted_planet_ids, moves)
        self._add_attacks(state, under_attack, exhausted_planet_ids, moves)
        return moves

    # ── Scoring and aiming ───────────────────────────────────────────
    def _target_score(self, src: Planet, tgt: Planet) -> float:
        d = dist(src.x, src.y, tgt.x, tgt.y)
        min_ships = tgt.ships + 1
        speed = fleet_speed(max(1, min_ships))
        eta = d / speed if speed > 0 else 0.0

        enemy_produced = 0.0
        enemy_bonus = 0.0
        if tgt.owner != -1:
            enemy_produced = eta * tgt.production
            enemy_bonus = float(tgt.production)

        total_ships = min_ships + enemy_produced
        s = self.config
        return (
            (s.formula_dist - d)
            + (s.formula_prod_mult * tgt.production)
            + (s.formula_enemy_bonus_mult * enemy_bonus)
            - (s.formula_total_ships_percent * total_ships)
            - (s.formula_eta_mult * eta)
        )

    def _is_moving_planet(self, state: GameState, planet_id: int) -> bool:
        if state.is_comet(planet_id):
            return True
        initial = state.initial_planet_by_id.get(planet_id)
        return bool(initial and is_orbiting(initial.x, initial.y, initial.radius))

    def _planet_position_at(
        self,
        state: GameState,
        planet: Planet,
        ticks_ahead: int,
    ) -> tuple[float, float]:
        ticks_ahead = max(0, int(ticks_ahead))
        if state.is_comet(planet.id):
            for group in state.comet_groups:
                for idx, pid in enumerate(group.planet_ids):
                    if pid != planet.id or idx >= len(group.paths):
                        continue
                    path = group.paths[idx]
                    path_idx = group.path_index + ticks_ahead
                    if 0 <= path_idx < len(path):
                        return path[path_idx]
                    return (planet.x, planet.y)

        initial = state.initial_planet_by_id.get(planet.id)
        if initial and is_orbiting(initial.x, initial.y, initial.radius):
            return orbital_position(
                initial.x,
                initial.y,
                state.angular_velocity,
                state.step + ticks_ahead,
            )
        return (planet.x, planet.y)

    def _find_angle_to_planet(
        self,
        state: GameState,
        src: Planet,
        tgt: Planet,
        ships: int,
    ) -> tuple[float | None, int | None]:
        speed = fleet_speed(max(1, ships))
        if self._is_moving_planet(state, tgt.id):
            for tick in range(1, self.config.lookahead_ticks + 1):
                tx, ty = self._planet_position_at(state, tgt, tick)
                travel_dist = speed * tick
                target_dist = max(0.0, dist(src.x, src.y, tx, ty) - src.radius)
                if abs(travel_dist - target_dist) > tgt.radius:
                    continue
                angle = angle_to(src.x, src.y, tx, ty)
                if self._sun_collision(src.x, src.y, angle, speed, tick):
                    return None, None
                return angle, tick
            return None, None

        angle = angle_to(src.x, src.y, tgt.x, tgt.y)
        d = dist(src.x, src.y, tgt.x, tgt.y)
        arrive_tick = max(1, int(math.floor(d / speed)))
        if self._sun_collision(src.x, src.y, angle, speed, arrive_tick):
            return None, None
        return angle, arrive_tick

    def _predict_total_ships(
        self,
        state: GameState,
        src: Planet,
        tgt: Planet,
        base_ships: int,
        available_ships: int,
    ) -> tuple[int | None, float | None, int | None]:
        total_ships = int(base_ships)
        for _ in range(5):
            angle, arrive_tick = self._find_angle_to_planet(
                state, src, tgt, total_ships
            )
            if angle is None or arrive_tick is None:
                return None, None, None

            new_total = int(base_ships)
            if tgt.owner != -1:
                new_total += int(arrive_tick * tgt.production)
            if new_total > available_ships:
                return None, None, None
            if new_total == total_ships:
                break
            total_ships = new_total
        return total_ships, angle, arrive_tick

    # ── Threats and reinforcements ───────────────────────────────────
    def _planets_under_attack(
        self, state: GameState
    ) -> dict[int, dict[str, object]]:
        under_attack: dict[int, dict[str, object]] = {}
        seen: set[tuple[int, int]] = set()

        for fleet in state.enemy_fleets:
            speed = fleet_speed(max(1, fleet.ships))
            prev_x, prev_y = fleet.x, fleet.y
            for tick in range(1, self.config.lookahead_ticks + 1):
                next_x = fleet.x + math.cos(fleet.angle) * speed * tick
                next_y = fleet.y + math.sin(fleet.angle) * speed * tick
                for planet in state.my_planets:
                    px, py = self._planet_position_at(state, planet, tick)
                    if not self._collides(
                        prev_x, prev_y, next_x, next_y, px, py, planet.radius
                    ):
                        continue
                    key = (planet.id, fleet.id)
                    if key in seen:
                        continue
                    row = under_attack.setdefault(
                        planet.id, {"planet": planet, "fleets": []}
                    )
                    row["fleets"].append({"fleet": fleet, "arrive_tick": tick})
                    seen.add(key)
                prev_x, prev_y = next_x, next_y
        return under_attack

    def _reinforcement_plans(
        self,
        state: GameState,
        under_attack: dict[int, dict[str, object]],
    ) -> dict[int, dict[str, int]]:
        plans: dict[int, dict[str, int]] = {}
        for planet in state.my_planets:
            if planet.id not in under_attack:
                continue
            attacking_fleets = sorted(
                under_attack[planet.id]["fleets"],
                key=lambda row: row["arrive_tick"],
            )
            incoming_reinforcements = sorted(
                [
                    r
                    for r in self.reinforcement_trajectories
                    if r.target_id == planet.id
                ],
                key=lambda r: r.arrive_tick,
            )

            available = planet.ships
            previous_tick = 0
            reinforcement_idx = 0
            for attack in attacking_fleets:
                arrive_tick = int(attack["arrive_tick"])
                fleet = attack["fleet"]
                available += (arrive_tick - previous_tick) * planet.production
                while (
                    reinforcement_idx < len(incoming_reinforcements)
                    and incoming_reinforcements[reinforcement_idx].arrive_tick
                    <= arrive_tick
                ):
                    available += incoming_reinforcements[reinforcement_idx].ships
                    reinforcement_idx += 1

                available -= fleet.ships
                previous_tick = arrive_tick
                if available < 0:
                    plans[planet.id] = {
                        "ships_needed": max(
                            self.config.min_ships_mine_attack, abs(int(available))
                        ),
                        "needed_by_tick": arrive_tick,
                    }
                    break
        return plans

    def _add_reinforcements(
        self,
        state: GameState,
        under_attack: dict[int, dict[str, object]],
        exhausted_planet_ids: set[int],
        moves: list[Move],
    ) -> None:
        plans = self._reinforcement_plans(state, under_attack)
        for target_id, plan in plans.items():
            if any(r.target_id == target_id and r.arrive_tick >= 0
                   for r in self.reinforcement_trajectories):
                continue
            target = state.planet_by_id.get(target_id)
            if target is None:
                continue

            for src in self._closest_planets_to_target(state.my_planets, target):
                if src.id == target.id or src.id in exhausted_planet_ids:
                    continue
                available = self._safe_available_ships(src, under_attack)
                reserved = sum(
                    r.ships
                    for r in self.reinforcement_trajectories
                    if r.mine_id == src.id
                )
                available = max(0, available - reserved)
                ships = max(self.config.min_ships_mine_attack, plan["ships_needed"])
                if available < ships:
                    continue
                angle, arrive_tick = self._find_angle_to_planet(
                    state, src, target, ships
                )
                if (
                    angle is None
                    or arrive_tick is None
                    or arrive_tick > plan["needed_by_tick"]
                ):
                    continue

                move = Move(src.id, angle, ships)
                moves.append(move)
                exhausted_planet_ids.add(src.id)
                self.reinforcement_trajectories.append(
                    _ReinforcementPlan(src.id, target.id, angle, ships, arrive_tick)
                )
                self.log(
                    move,
                    reason="reinforce",
                    target_id=target.id,
                    arrive_tick=arrive_tick,
                    ships_needed=plan["ships_needed"],
                )
                break

    # ── Attacks ──────────────────────────────────────────────────────
    def _add_attacks(
        self,
        state: GameState,
        under_attack: dict[int, dict[str, object]],
        exhausted_planet_ids: set[int],
        moves: list[Move],
    ) -> None:
        for src in sorted(state.my_planets, key=lambda p: p.ships, reverse=True):
            if (
                src.id in exhausted_planet_ids
                or src.ships < self.config.min_ships_mine_attack
            ):
                continue

            candidates = self._candidate_targets(state, src)
            for tgt, score in candidates[:3]:
                available = self._safe_available_ships(src, under_attack)
                if available < self.config.min_ships_mine_attack:
                    continue

                en_route = sum(
                    f.ships for f in self.fleet_trajectories
                    if f.target_id == tgt.id
                )
                needed_now = tgt.ships + 1
                if tgt.owner != -1:
                    needed_now += 3 * tgt.production

                if len(state.my_planets) < len(state.planets) * 0.75:
                    if en_route >= needed_now:
                        continue

                base_ships = max(
                    self.config.min_ships_mine_attack,
                    int(needed_now - en_route),
                )
                if available >= base_ships:
                    self._try_single_attack(
                        state,
                        src,
                        tgt,
                        available,
                        base_ships,
                        score,
                        exhausted_planet_ids,
                        moves,
                    )
                    if src.id in exhausted_planet_ids:
                        break
                elif (
                    len(state.my_planets) > 1
                    and tgt.ships >= self.config.min_ships_target_coop_attack
                ):
                    self._try_coop_attack(
                        state,
                        src,
                        tgt,
                        available,
                        base_ships,
                        score,
                        under_attack,
                        exhausted_planet_ids,
                        moves,
                    )
                    if src.id in exhausted_planet_ids:
                        break

    def _try_single_attack(
        self,
        state: GameState,
        src: Planet,
        tgt: Planet,
        available: int,
        base_ships: int,
        score: float,
        exhausted_planet_ids: set[int],
        moves: list[Move],
    ) -> None:
        total_ships, angle, arrive_tick = self._predict_total_ships(
            state, src, tgt, base_ships, available
        )
        if total_ships is None or angle is None or arrive_tick is None:
            return
        move = Move(src.id, angle, total_ships)
        moves.append(move)
        exhausted_planet_ids.add(src.id)
        self.fleet_trajectories.append(
            _FleetPlan(src.id, tgt.id, angle, total_ships, arrive_tick)
        )
        self.log(
            move,
            reason="attack",
            score=score,
            target_id=tgt.id,
            target_owner=tgt.owner,
            target_production=tgt.production,
            arrive_tick=arrive_tick,
        )

    def _try_coop_attack(
        self,
        state: GameState,
        src: Planet,
        tgt: Planet,
        available: int,
        base_ships: int,
        score: float,
        under_attack: dict[int, dict[str, object]],
        exhausted_planet_ids: set[int],
        moves: list[Move],
    ) -> None:
        attacking = [(src, available)]
        accumulated = available
        for helper in self._closest_planets_to_target(state.my_planets, tgt):
            if helper.id == src.id or helper.id in exhausted_planet_ids:
                continue
            helper_available = self._safe_available_ships(helper, under_attack)
            if helper_available < self.config.min_ships_mine_attack:
                continue
            attacking.append((helper, helper_available))
            accumulated += helper_available
            if len(attacking) > self.config.coop_planet_cap:
                break
            if accumulated < base_ships:
                continue

            remainder, planned = self._plan_coop_attack(
                state, attacking, tgt, base_ships
            )
            if remainder > 0:
                continue
            for planet, angle, ships, arrive_tick in planned:
                move = Move(planet.id, angle, ships)
                moves.append(move)
                exhausted_planet_ids.add(planet.id)
                self.fleet_trajectories.append(
                    _FleetPlan(planet.id, tgt.id, angle, ships, arrive_tick)
                )
                self.log(
                    move,
                    reason="coop_attack",
                    score=score,
                    target_id=tgt.id,
                    target_owner=tgt.owner,
                    target_production=tgt.production,
                    arrive_tick=arrive_tick,
                )
            return

    def _plan_coop_attack(
        self,
        state: GameState,
        attacking_planets: list[tuple[Planet, int]],
        tgt: Planet,
        base_ships: int,
    ) -> tuple[int, list[tuple[Planet, float, int, int]]]:
        remainder = base_ships
        planned: list[tuple[Planet, float, int, int]] = []
        for planet, available in attacking_planets:
            ships = min(available, remainder)
            if ships > 0:
                ships = min(available, max(ships, self.config.min_ships_mine_attack))
            if ships <= 0:
                continue
            angle, arrive_tick = self._find_angle_to_planet(state, planet, tgt, ships)
            remainder -= ships
            if angle is None or arrive_tick is None:
                continue
            planned.append((planet, angle, ships, arrive_tick))
        return remainder, planned

    # ── Small utilities ──────────────────────────────────────────────
    def _candidate_targets(
        self, state: GameState, src: Planet
    ) -> list[tuple[Planet, float]]:
        targets: list[tuple[Planet, float]] = []
        for tgt in state.non_my_planets:
            if self.config.skip_comets and state.is_comet(tgt.id):
                continue
            targets.append((tgt, self._target_score(src, tgt)))
        return sorted(targets, key=lambda row: row[1], reverse=True)

    def _closest_planets_to_target(
        self, planets: list[Planet], target: Planet
    ) -> list[Planet]:
        return sorted(planets, key=lambda p: dist(p.x, p.y, target.x, target.y))

    def _safe_available_ships(
        self,
        planet: Planet,
        under_attack: dict[int, dict[str, object]],
    ) -> int:
        available = planet.ships
        if planet.id in under_attack:
            available -= sum(
                row["fleet"].ships for row in under_attack[planet.id]["fleets"]
            )
        return max(0, int(available))

    def _update_fleet_trajectories(self, fleets: list[Fleet]) -> None:
        for plan in self.fleet_trajectories[:]:
            found = any(
                f.from_planet_id == plan.mine_id
                and abs(f.angle - plan.angle) < 1e-6
                for f in fleets
            )
            if found:
                plan.arrive_tick = max(0, plan.arrive_tick - 1)
            else:
                self.fleet_trajectories.remove(plan)

    def _update_reinforcement_trajectories(self) -> None:
        for plan in self.reinforcement_trajectories[:]:
            plan.arrive_tick -= 1
            if plan.arrive_tick <= 0:
                self.reinforcement_trajectories.remove(plan)

    def _sun_collision(
        self,
        start_x: float,
        start_y: float,
        angle: float,
        speed: float,
        ticks: int,
    ) -> bool:
        prev_x, prev_y = start_x, start_y
        for tick in range(1, min(max(1, ticks), self.config.lookahead_ticks) + 1):
            x = start_x + math.cos(angle) * speed * tick
            y = start_y + math.sin(angle) * speed * tick
            if self._collides(prev_x, prev_y, x, y, SUN_X, SUN_Y, SUN_R):
                return True
            prev_x, prev_y = x, y
        return False

    @staticmethod
    def _collides(
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        cx: float,
        cy: float,
        radius: float,
    ) -> bool:
        vec_x = x2 - x1
        vec_y = y2 - y1
        vec_len_sq = vec_x * vec_x + vec_y * vec_y
        if vec_len_sq == 0.0:
            return dist(x1, y1, cx, cy) <= radius

        to_cx = cx - x1
        to_cy = cy - y1
        closest = (to_cx * vec_x + to_cy * vec_y) / vec_len_sq
        closest = max(0.0, min(1.0, closest))
        closest_x = x1 + closest * vec_x
        closest_y = y1 + closest * vec_y
        return dist(closest_x, closest_y, cx, cy) <= radius
