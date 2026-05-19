"""
PeakingAgent -- mission-oriented baseline adapted from 1103-peaking-bot.

This agent ports the notebook strategy's main ideas into the local Agent
framework without copying the full notebook verbatim:

* a compact WorldModel with phase / strength / arrival views;
* real launch-point geometry for sun-safe shots;
* moving-target aiming for orbiting planets and comets;
* mission generation for capture, snipe, rescue, and reinforce;
* greedy execution with per-source reserves and planned commitments.

It is intentionally independent from HeuristicAgent so the simpler
baselines remain stable and easy to compare against.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from orbit_wars.agents.base import Agent
from orbit_wars.core.geometry import (
    BOARD_SIZE,
    CENTER,
    MAX_SPEED,
    ROTATION_RADIUS_LIMIT,
    SUN_R,
    SUN_X,
    SUN_Y,
    angle_to,
    dist,
    fleet_speed,
    in_bounds,
    is_orbiting,
    orbital_position,
)
from orbit_wars.core.state import GameState, Move


TOTAL_STEPS = 500


@dataclass
class PeakingConfig:
    """Tunable knobs for :class:`PeakingAgent`.

    The defaults are conservative enough to act as a robust new baseline
    rather than a heavily overfit port of the notebook.
    """

    sun_safety: float = 1.5
    launch_clearance: float = 0.1
    horizon: int = 50
    route_search_horizon: int = 30
    intercept_tolerance: int = 1
    aim_iterations: int = 2

    early_turn_limit: int = 40
    opening_turn_limit: int = 80
    late_remaining_turns: int = 60
    very_late_remaining_turns: int = 25

    reserve_floor: int = 5
    defense_buffer: int = 2
    proactive_defense_horizon: int = 18
    attack_margin_base: int = 2
    attack_margin_prod_weight: float = 1.5
    hostile_value_mult: float = 1.65
    static_value_mult: float = 1.25
    contested_neutral_mult: float = 0.75
    comet_value_mult: float = 0.7

    partial_source_min_ships: int = 6
    max_missions_per_turn: int = 8
    max_sources_per_target: int = 3
    snipe_window: int = 2
    reinforce_min_production: int = 2
    reinforce_max_travel_turns: int = 20
    reinforce_source_fraction: float = 0.55
    cost_turn_weight: float = 0.55


@dataclass(frozen=True)
class ShotOption:
    score: float
    src_id: int
    target_id: int
    angle: float
    turns: int
    needed: int
    send_cap: int
    mission: str = "capture"
    anchor_turn: int | None = None


@dataclass
class Mission:
    kind: str
    score: float
    target_id: int
    turns: int
    options: list[ShotOption] = field(default_factory=list)


def _point_to_segment_distance(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return dist(px, py, x1, y1)
    t = ((px - x1) * dx + (py - y1) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return dist(px, py, x1 + t * dx, y1 + t * dy)


class PeakingWorldModel:
    """Derived, cache-friendly view of one turn for PeakingAgent."""

    def __init__(self, state: GameState, config: PeakingConfig) -> None:
        self.state = state
        self.config = config
        self.player = state.player
        self.step = state.step
        self.planets = state.planets
        self.fleets = state.fleets
        self.planet_by_id = state.planet_by_id
        self.initial_by_id = state.initial_planet_by_id
        self.comet_ids = set(state.comet_planet_ids)
        self.comet_groups = state.comet_groups
        self.my_planets = state.my_planets
        self.enemy_planets = state.enemy_planets
        self.neutral_planets = state.neutral_planets
        self.static_neutral_planets = [
            p for p in self.neutral_planets if self.is_static(p.id)
        ]
        self.non_my_planets = state.non_my_planets
        self.remaining_steps = max(1, TOTAL_STEPS - state.step)
        self.is_early = state.step < config.early_turn_limit
        self.is_opening = state.step < config.opening_turn_limit
        self.is_late = self.remaining_steps < config.late_remaining_turns
        self.is_very_late = self.remaining_steps < config.very_late_remaining_turns

        self.owner_strength: dict[int, int] = defaultdict(int)
        self.owner_production: dict[int, int] = defaultdict(int)
        for p in self.planets:
            if p.owner >= 0:
                self.owner_strength[p.owner] += int(p.ships)
                self.owner_production[p.owner] += int(p.production)
        for f in self.fleets:
            if f.owner >= 0:
                self.owner_strength[f.owner] += int(f.ships)

        self.my_total = self.owner_strength.get(self.player, 0)
        self.enemy_total = sum(
            v for owner, v in self.owner_strength.items() if owner != self.player
        )
        self.my_prod = self.owner_production.get(self.player, 0)
        self.enemy_prod = sum(
            v for owner, v in self.owner_production.items() if owner != self.player
        )

        self.arrivals_by_planet = self._build_arrival_ledger()
        self.shot_cache: dict[tuple[int, int, int], tuple[float, int, float, float] | None] = {}
        self.reaction_cache: dict[int, tuple[int, int]] = {}

    def is_static(self, planet_id: int) -> bool:
        planet = self.planet_by_id[planet_id]
        initial = self.initial_by_id.get(planet_id)
        if initial is None:
            return True
        return not is_orbiting(initial.x, initial.y, initial.radius)

    def predict_planet_position(self, planet_id: int, turns: int) -> tuple[float, float]:
        planet = self.planet_by_id[planet_id]
        initial = self.initial_by_id.get(planet_id)
        if initial is None or not is_orbiting(initial.x, initial.y, initial.radius):
            return planet.x, planet.y
        return orbital_position(
            initial.x,
            initial.y,
            self.state.angular_velocity,
            self.step + max(0, int(turns)),
        )

    def predict_comet_position(self, planet_id: int, turns: int) -> tuple[float, float] | None:
        for group in self.comet_groups:
            if planet_id not in group.planet_ids:
                continue
            idx = group.planet_ids.index(planet_id)
            if idx >= len(group.paths):
                return None
            future_idx = group.path_index + max(0, int(turns))
            path = group.paths[idx]
            if 0 <= future_idx < len(path):
                return path[future_idx]
            return None
        return None

    def comet_life(self, planet_id: int) -> int:
        for group in self.comet_groups:
            if planet_id not in group.planet_ids:
                continue
            idx = group.planet_ids.index(planet_id)
            if idx < len(group.paths):
                return max(0, len(group.paths[idx]) - group.path_index)
        return 0

    def predict_target_position(self, target_id: int, turns: int) -> tuple[float, float] | None:
        if target_id in self.comet_ids:
            pos = self.predict_comet_position(target_id, turns)
            if pos is None:
                return None
            return pos
        return self.predict_planet_position(target_id, turns)

    def segment_hits_sun(self, x1: float, y1: float, x2: float, y2: float) -> bool:
        return (
            _point_to_segment_distance(SUN_X, SUN_Y, x1, y1, x2, y2)
            < SUN_R + self.config.sun_safety
        )

    def launch_point(self, src_id: int, angle: float) -> tuple[float, float]:
        src = self.planet_by_id[src_id]
        clearance = src.radius + self.config.launch_clearance
        return src.x + math.cos(angle) * clearance, src.y + math.sin(angle) * clearance

    def safe_angle_and_distance(
        self, src_id: int, tx: float, ty: float, target_radius: float
    ) -> tuple[float, float] | None:
        src = self.planet_by_id[src_id]
        angle = angle_to(src.x, src.y, tx, ty)
        start_x, start_y = self.launch_point(src_id, angle)
        hit_distance = max(
            0.0,
            dist(src.x, src.y, tx, ty)
            - (src.radius + self.config.launch_clearance)
            - target_radius,
        )
        end_x = start_x + math.cos(angle) * hit_distance
        end_y = start_y + math.sin(angle) * hit_distance
        if self.segment_hits_sun(start_x, start_y, end_x, end_y):
            return None
        return angle, hit_distance

    def estimate_arrival(
        self, src_id: int, target_id: int, tx: float, ty: float, ships: int
    ) -> tuple[float, int] | None:
        target = self.planet_by_id[target_id]
        safe = self.safe_angle_and_distance(src_id, tx, ty, target.radius)
        if safe is None:
            return None
        angle, distance_to_hit = safe
        turns = max(1, int(math.ceil(distance_to_hit / fleet_speed(max(1, ships)))))
        return angle, turns

    def target_can_move(self, target_id: int) -> bool:
        if target_id in self.comet_ids:
            return True
        return not self.is_static(target_id)

    def search_safe_intercept(
        self, src_id: int, target_id: int, ships: int
    ) -> tuple[float, int, float, float] | None:
        max_turns = min(self.config.horizon, self.config.route_search_horizon)
        if target_id in self.comet_ids:
            max_turns = min(max_turns, max(0, self.comet_life(target_id) - 1))
        best: tuple[tuple[int, int, int], tuple[float, int, float, float]] | None = None
        for candidate_turns in range(1, max_turns + 1):
            pos = self.predict_target_position(target_id, candidate_turns)
            if pos is None:
                continue
            est = self.estimate_arrival(src_id, target_id, pos[0], pos[1], ships)
            if est is None:
                continue
            _, turns = est
            if abs(turns - candidate_turns) > self.config.intercept_tolerance:
                continue
            actual_turns = max(turns, candidate_turns)
            actual_pos = self.predict_target_position(target_id, actual_turns)
            if actual_pos is None:
                continue
            confirm = self.estimate_arrival(
                src_id, target_id, actual_pos[0], actual_pos[1], ships
            )
            if confirm is None:
                continue
            delta = abs(confirm[1] - actual_turns)
            if delta > self.config.intercept_tolerance:
                continue
            score = (delta, confirm[1], candidate_turns)
            candidate = (confirm[0], confirm[1], actual_pos[0], actual_pos[1])
            if best is None or score < best[0]:
                best = (score, candidate)
        return None if best is None else best[1]

    def aim_with_prediction(
        self, src_id: int, target_id: int, ships: int
    ) -> tuple[float, int, float, float] | None:
        target = self.planet_by_id[target_id]
        est = self.estimate_arrival(src_id, target_id, target.x, target.y, ships)
        if est is None:
            if self.target_can_move(target_id):
                return self.search_safe_intercept(src_id, target_id, ships)
            return None

        tx, ty = target.x, target.y
        for _ in range(max(0, int(self.config.aim_iterations))):
            _, turns = est
            pos = self.predict_target_position(target_id, turns)
            if pos is None:
                return None
            next_est = self.estimate_arrival(src_id, target_id, pos[0], pos[1], ships)
            if next_est is None:
                if self.target_can_move(target_id):
                    return self.search_safe_intercept(src_id, target_id, ships)
                return None
            if (
                abs(pos[0] - tx) < 0.3
                and abs(pos[1] - ty) < 0.3
                and abs(next_est[1] - turns) <= self.config.intercept_tolerance
            ):
                return next_est[0], next_est[1], pos[0], pos[1]
            tx, ty = pos
            est = next_est

        final_est = self.estimate_arrival(src_id, target_id, tx, ty, ships)
        if final_est is None:
            return self.search_safe_intercept(src_id, target_id, ships)
        return final_est[0], final_est[1], tx, ty

    def plan_shot(
        self, src_id: int, target_id: int, ships: int
    ) -> tuple[float, int, float, float] | None:
        key = (src_id, target_id, max(1, int(ships)))
        if key not in self.shot_cache:
            self.shot_cache[key] = self.aim_with_prediction(*key)
        return self.shot_cache[key]

    def _fleet_target_planet(self, fleet) -> tuple[int, int] | None:
        dx = math.cos(fleet.angle)
        dy = math.sin(fleet.angle)
        speed = fleet_speed(fleet.ships)
        best: tuple[float, int] | None = None
        for planet in self.planets:
            if planet.id == fleet.from_planet_id:
                continue
            rel_x = planet.x - fleet.x
            rel_y = planet.y - fleet.y
            along = dx * rel_x + dy * rel_y
            if along <= 0:
                continue
            perp = abs(dx * rel_y - dy * rel_x)
            if perp > planet.radius + 0.5:
                continue
            turns = max(1, int(math.ceil(along / speed)))
            if best is None or turns < best[0]:
                best = (turns, planet.id)
        if best is None:
            return None
        return best[1], int(best[0])

    def _build_arrival_ledger(self) -> dict[int, list[tuple[int, int, int]]]:
        arrivals: dict[int, list[tuple[int, int, int]]] = {p.id: [] for p in self.planets}
        for fleet in self.fleets:
            target = self._fleet_target_planet(fleet)
            if target is None:
                continue
            target_id, eta = target
            arrivals.setdefault(target_id, []).append((eta, fleet.owner, int(fleet.ships)))
        for values in arrivals.values():
            values.sort(key=lambda item: item[0])
        return arrivals

    def projected_owner_ships(
        self,
        target_id: int,
        turn: int,
        planned: dict[int, list[tuple[int, int, int]]] | None = None,
        extra: tuple[int, int, int] | None = None,
    ) -> tuple[int, int]:
        """Approximate ownership/garrison at ``turn`` after known arrivals."""
        target = self.planet_by_id[target_id]
        owner = target.owner
        ships = int(target.ships)
        events = list(self.arrivals_by_planet.get(target_id, []))
        if planned:
            events.extend(planned.get(target_id, []))
        if extra is not None:
            events.append(extra)
        by_turn: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for eta, fleet_owner, fleet_ships in events:
            if 0 < eta <= turn and fleet_ships > 0:
                by_turn[int(math.ceil(eta))][fleet_owner] += int(fleet_ships)
        for t in range(1, max(1, turn) + 1):
            if owner >= 0:
                ships += int(target.production)
            if t not in by_turn:
                continue
            for fleet_owner, fleet_ships in by_turn[t].items():
                if fleet_owner == owner:
                    ships += fleet_ships
                elif fleet_ships > ships:
                    owner = fleet_owner
                    ships = fleet_ships - ships
                else:
                    ships -= fleet_ships
        return owner, max(0, ships)

    def min_ships_to_own_at(
        self,
        target_id: int,
        turn: int,
        planned: dict[int, list[tuple[int, int, int]]] | None = None,
    ) -> int:
        owner, ships = self.projected_owner_ships(target_id, turn, planned=planned)
        if owner == self.player:
            return 1
        target = self.planet_by_id[target_id]
        margin = self.config.attack_margin_base + int(
            target.production * self.config.attack_margin_prod_weight
        )
        if target.owner not in (-1, self.player):
            margin += 2
        if self.is_very_late:
            margin = max(1, margin - 2)
        return max(1, ships + margin)

    def source_inventory_left(self, source_id: int, spent: dict[int, int]) -> int:
        return max(0, int(self.planet_by_id[source_id].ships) - spent.get(source_id, 0))

    def nearest_sources(self, target_id: int, sources: list, limit: int) -> list:
        target = self.planet_by_id[target_id]
        return sorted(
            sources,
            key=lambda src: (dist(src.x, src.y, target.x, target.y), -src.ships, src.id),
        )[:limit]

    def reaction_times(self, target_id: int) -> tuple[int, int]:
        if target_id in self.reaction_cache:
            return self.reaction_cache[target_id]
        target = self.planet_by_id[target_id]

        def best_time(sources: list) -> int:
            best = 10**9
            for src in self.nearest_sources(target_id, sources, self.config.max_sources_per_target):
                ships = max(1, min(int(src.ships), int(target.ships) + 10))
                aim = self.plan_shot(src.id, target_id, ships)
                if aim is not None:
                    best = min(best, aim[1])
            return best

        my_t = best_time(self.my_planets)
        enemy_sources = [p for p in self.planets if p.owner >= 0 and p.owner != self.player]
        enemy_t = best_time(enemy_sources)
        self.reaction_cache[target_id] = (my_t, enemy_t)
        return my_t, enemy_t


def _target_value(target, turns: int, mission: str, world: PeakingWorldModel) -> float:
    cfg = world.config
    if target.id in world.comet_ids:
        life = world.comet_life(target.id)
        profit_turns = max(0, min(world.remaining_steps - turns, life - turns))
        if profit_turns <= 0:
            return -1.0
    else:
        profit_turns = max(1, world.remaining_steps - turns)

    value = target.production * profit_turns
    nearest_friend = min(
        (dist(target.x, target.y, p.x, p.y) for p in world.my_planets),
        default=BOARD_SIZE,
    )
    nearest_enemy = min(
        (dist(target.x, target.y, p.x, p.y) for p in world.enemy_planets),
        default=BOARD_SIZE,
    )
    value += max(0.0, BOARD_SIZE - nearest_friend) * 0.06
    value += max(0.0, BOARD_SIZE - nearest_enemy) * 0.03

    if world.is_static(target.id):
        value *= cfg.static_value_mult
    elif world.is_opening and target.owner == -1:
        value *= 0.9

    if target.owner not in (-1, world.player):
        value *= cfg.hostile_value_mult
        if world.is_late:
            value *= 1.2
    else:
        my_t, enemy_t = world.reaction_times(target.id)
        if abs(my_t - enemy_t) <= 2:
            value *= cfg.contested_neutral_mult
        elif my_t + 2 < enemy_t:
            value *= 1.15
        if world.is_early:
            value *= 1.15

    if target.id in world.comet_ids:
        value *= cfg.comet_value_mult * (1.0 + min(1.0, world.comet_life(target.id) / 20.0) * 0.5)

    if mission == "snipe":
        value *= 1.12
    elif mission in ("rescue", "reinforce"):
        value *= 1.25
    return value


def _build_policy(world: PeakingWorldModel) -> tuple[dict[int, int], dict[int, int]]:
    cfg = world.config
    reserve: dict[int, int] = {}
    attack_budget: dict[int, int] = {}
    for planet in world.my_planets:
        incoming = 0
        earliest = 10**9
        for eta, owner, ships in world.arrivals_by_planet.get(planet.id, []):
            if owner == world.player or eta > cfg.proactive_defense_horizon:
                continue
            incoming += ships
            earliest = min(earliest, eta)
        future_local = int(planet.ships)
        if earliest < 10**9:
            future_local += int(planet.production * earliest)
        needed = max(cfg.reserve_floor, incoming - future_local + cfg.defense_buffer)
        reserve[planet.id] = min(int(planet.ships), max(0, needed))
        attack_budget[planet.id] = max(0, int(planet.ships) - reserve[planet.id])
    return reserve, attack_budget


def _build_capture_missions(
    world: PeakingWorldModel,
    attack_budget: dict[int, int],
    planned: dict[int, list[tuple[int, int, int]]],
) -> list[Mission]:
    cfg = world.config
    missions: list[Mission] = []
    for src in world.my_planets:
        source_cap = attack_budget.get(src.id, 0)
        if source_cap < cfg.partial_source_min_ships:
            continue
        for target in world.non_my_planets:
            if target.id == src.id:
                continue
            rough_send = min(source_cap, max(1, int(target.ships) + cfg.attack_margin_base + 2))
            rough = world.plan_shot(src.id, target.id, rough_send)
            if rough is None:
                continue
            _, rough_turns, _, _ = rough
            if target.id in world.comet_ids and rough_turns >= max(1, world.comet_life(target.id)):
                continue
            needed = world.min_ships_to_own_at(target.id, rough_turns, planned=planned)
            if needed > source_cap:
                continue
            send = min(source_cap, max(needed, rough_send))
            aim = world.plan_shot(src.id, target.id, send)
            if aim is None:
                continue
            angle, turns, _, _ = aim
            needed = world.min_ships_to_own_at(target.id, turns, planned=planned)
            if needed > source_cap:
                continue
            send = min(source_cap, max(send, needed))
            value = _target_value(target, turns, "capture", world)
            if value <= 0:
                continue
            score = value / (send + turns * cfg.cost_turn_weight + 1.0)
            option = ShotOption(
                score=score,
                src_id=src.id,
                target_id=target.id,
                angle=angle,
                turns=turns,
                needed=needed,
                send_cap=send,
                mission="capture",
            )
            missions.append(Mission("single", score, target.id, turns, [option]))
    return missions


def _build_snipe_missions(
    world: PeakingWorldModel,
    attack_budget: dict[int, int],
    planned: dict[int, list[tuple[int, int, int]]],
) -> list[Mission]:
    cfg = world.config
    missions: list[Mission] = []
    for target in world.neutral_planets:
        enemy_etas = sorted(
            {
                eta
                for eta, owner, ships in world.arrivals_by_planet.get(target.id, [])
                if owner not in (-1, world.player) and ships > 0
            }
        )
        if not enemy_etas:
            continue
        enemy_eta = enemy_etas[0]
        for src in world.nearest_sources(target.id, world.my_planets, cfg.max_sources_per_target):
            source_cap = attack_budget.get(src.id, 0)
            if source_cap < cfg.partial_source_min_ships:
                continue
            base_need = world.min_ships_to_own_at(target.id, enemy_eta, planned=planned)
            if base_need > source_cap:
                continue
            aim = world.plan_shot(src.id, target.id, base_need)
            if aim is None:
                continue
            angle, turns, _, _ = aim
            if abs(turns - enemy_eta) > cfg.snipe_window:
                continue
            need = world.min_ships_to_own_at(target.id, max(turns, enemy_eta), planned=planned)
            if need > source_cap:
                continue
            value = _target_value(target, max(turns, enemy_eta), "snipe", world)
            score = value / (need + turns * cfg.cost_turn_weight + 1.0)
            option = ShotOption(
                score=score,
                src_id=src.id,
                target_id=target.id,
                angle=angle,
                turns=turns,
                needed=need,
                send_cap=need,
                mission="snipe",
                anchor_turn=enemy_eta,
            )
            missions.append(Mission("snipe", score, target.id, max(turns, enemy_eta), [option]))
    return missions


def _build_defense_missions(
    world: PeakingWorldModel,
    attack_budget: dict[int, int],
    planned: dict[int, list[tuple[int, int, int]]],
) -> list[Mission]:
    cfg = world.config
    missions: list[Mission] = []
    for target in world.my_planets:
        for eta, owner, ships in world.arrivals_by_planet.get(target.id, []):
            if owner == world.player or eta > cfg.proactive_defense_horizon:
                continue
            projected_owner, projected_ships = world.projected_owner_ships(
                target.id, eta, planned=planned
            )
            if projected_owner == world.player and projected_ships >= cfg.defense_buffer:
                continue
            need = max(1, ships - projected_ships + cfg.defense_buffer)
            for src in world.nearest_sources(target.id, [p for p in world.my_planets if p.id != target.id], cfg.max_sources_per_target):
                cap = min(
                    attack_budget.get(src.id, 0),
                    int(src.ships * cfg.reinforce_source_fraction),
                )
                if cap < need or cap < cfg.partial_source_min_ships:
                    continue
                aim = world.plan_shot(src.id, target.id, need)
                if aim is None:
                    continue
                angle, turns, _, _ = aim
                if turns > eta:
                    continue
                saved_turns = max(1, world.remaining_steps - eta)
                value = target.production * saved_turns + ships
                score = value / (need + turns * 0.35 + 1.0)
                option = ShotOption(
                    score=score,
                    src_id=src.id,
                    target_id=target.id,
                    angle=angle,
                    turns=turns,
                    needed=need,
                    send_cap=need,
                    mission="rescue",
                    anchor_turn=eta,
                )
                missions.append(Mission("rescue", score, target.id, eta, [option]))
    return missions


def _build_reinforce_missions(
    world: PeakingWorldModel,
    attack_budget: dict[int, int],
) -> list[Mission]:
    cfg = world.config
    if world.remaining_steps < cfg.horizon:
        return []
    missions: list[Mission] = []
    valuable = [
        p for p in world.my_planets
        if p.production >= cfg.reinforce_min_production and p.ships < cfg.reserve_floor * 2
    ]
    for target in valuable:
        for src in world.nearest_sources(target.id, [p for p in world.my_planets if p.id != target.id], cfg.max_sources_per_target):
            cap = min(
                attack_budget.get(src.id, 0),
                int(src.ships * cfg.reinforce_source_fraction),
            )
            if cap < cfg.partial_source_min_ships:
                continue
            send = min(cap, cfg.reserve_floor * 2 - int(target.ships) + cfg.defense_buffer)
            if send <= 0:
                continue
            aim = world.plan_shot(src.id, target.id, send)
            if aim is None:
                continue
            angle, turns, _, _ = aim
            if turns > cfg.reinforce_max_travel_turns:
                continue
            value = _target_value(target, turns, "reinforce", world)
            score = value / (send + turns * 0.35 + 1.0)
            option = ShotOption(
                score=score,
                src_id=src.id,
                target_id=target.id,
                angle=angle,
                turns=turns,
                needed=send,
                send_cap=send,
                mission="reinforce",
            )
            missions.append(Mission("reinforce", score, target.id, turns, [option]))
    return missions


def _plan_moves(world: PeakingWorldModel) -> list[Move]:
    cfg = world.config
    if not world.my_planets:
        return []
    reserve, attack_budget = _build_policy(world)
    planned: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    spent: dict[int, int] = defaultdict(int)

    missions: list[Mission] = []
    missions.extend(_build_defense_missions(world, attack_budget, planned))
    missions.extend(_build_reinforce_missions(world, attack_budget))
    missions.extend(_build_capture_missions(world, attack_budget, planned))
    missions.extend(_build_snipe_missions(world, attack_budget, planned))
    missions.sort(key=lambda mission: (-mission.score, mission.turns, mission.target_id))

    moves: list[Move] = []
    for mission in missions:
        if len(moves) >= cfg.max_missions_per_turn:
            break
        if not mission.options:
            continue
        option = mission.options[0]
        src = world.planet_by_id.get(option.src_id)
        target = world.planet_by_id.get(option.target_id)
        if src is None or target is None:
            continue
        left_total = world.source_inventory_left(src.id, spent)
        left_budget = max(0, attack_budget.get(src.id, 0) - spent.get(src.id, 0))
        left = min(left_total, left_budget)
        send = min(left, option.send_cap)
        if send < option.needed or send <= 0:
            continue
        # Re-aim using the final send size because speed depends on ships.
        aim = world.plan_shot(src.id, target.id, send)
        if aim is None:
            continue
        angle, turns, _, _ = aim
        if target.owner != world.player:
            needed = world.min_ships_to_own_at(target.id, turns, planned=planned)
            if send < needed:
                continue
        if send > src.ships:
            continue
        move = Move(src.id, angle, send)
        moves.append(move)
        spent[src.id] = spent.get(src.id, 0) + send
        planned[target.id].append((turns, world.player, send))
    return moves


class PeakingAgent(Agent):
    """Mission-oriented strategy inspired by the 1103 peaking bot."""

    name = "peaking"

    def __init__(self, config: PeakingConfig | None = None) -> None:
        super().__init__()
        self.config = config or PeakingConfig()

    def act(self, state: GameState) -> list[Move]:
        world = PeakingWorldModel(state, self.config)
        moves = _plan_moves(world)
        for move in moves:
            self.log(
                move,
                reason="mission",
                source_ships=state.planet_by_id.get(move.from_planet_id).ships
                if move.from_planet_id in state.planet_by_id else None,
            )
        return moves
