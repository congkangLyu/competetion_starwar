"""
Orbit Wars - GameState and core data classes.

Wraps the raw observation (a dict or namespace object handed in by the
kaggle env) into typed, richer data objects with cached convenience
views. Every agent should call ``GameState.from_obs(obs)`` at the top of
its ``act()`` and then work against this object -- never against the raw
list-of-lists form.

Why this layer exists
---------------------
The raw observation has two annoying properties:

1. It can arrive as either a ``dict`` *or* a namespace-like object. Every
   existing agent has its own ``if isinstance(obs, dict)`` boilerplate.
2. Planets and fleets are stored as 7-tuples / 7-lists with positional
   semantics. Reading ``p[5]`` instead of ``p.ships`` is a constant source
   of bugs.

``GameState.from_obs`` solves both problems once. The dataclasses below
are intentionally *not* the kaggle namedtuples -- using our own keeps the
attribute set under our control and lets us extend it later (e.g. adding
an ``is_comet`` flag or a precomputed ``orbital_radius``).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Any


# ─────────────────────────────────────────────────────────────────────────
# Raw entity dataclasses
# ─────────────────────────────────────────────────────────────────────────
# These are frozen + slotted: cheap to construct, hashable, and immutable.
# Construction matches the kaggle field order: ``Planet(*raw_planet_list)``
# works exactly like the kaggle Planet namedtuple.


@dataclass(frozen=True, slots=True)
class Planet:
    """One planet (or comet) snapshot.

    Field order matches the raw observation list:
    ``[id, owner, x, y, radius, ships, production]``.
    """

    id: int
    owner: int  # -1 = neutral, 0..3 = player id
    x: float
    y: float
    radius: float
    ships: int
    production: int


@dataclass(frozen=True, slots=True)
class Fleet:
    """One fleet in flight.

    Field order matches the raw observation list:
    ``[id, owner, x, y, angle, from_planet_id, ships]``.
    """

    id: int
    owner: int
    x: float
    y: float
    angle: float
    from_planet_id: int
    ships: int


@dataclass(frozen=True, slots=True)
class CometGroup:
    """One symmetric group of four comets sharing a trajectory family.

    ``paths[i]`` is the full pre-computed trajectory for ``planet_ids[i]``,
    a sequence of (x, y) points. ``path_index`` is the index of the
    *current* position along each path.
    """

    planet_ids: tuple[int, ...]
    paths: tuple[tuple[tuple[float, float], ...], ...]
    path_index: int


@dataclass(frozen=True, slots=True)
class Move:
    """One launch order, in the format the kaggle env expects.

    Use ``.to_list()`` when returning from an agent's ``act()``.
    """

    from_planet_id: int
    angle: float
    ships: int

    def to_list(self) -> list:
        return [int(self.from_planet_id), float(self.angle), int(self.ships)]


# ─────────────────────────────────────────────────────────────────────────
# obs accessor: dict vs namespace
# ─────────────────────────────────────────────────────────────────────────
def _get(obs: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from either a dict-style or attribute-style object."""
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)


# ─────────────────────────────────────────────────────────────────────────
# GameState
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class GameState:
    """Parsed view of one turn's observation.

    Construct via :meth:`from_obs`. The ``my_*`` / ``enemy_*`` / ``planet_by_id``
    accessors are computed lazily and cached on first access.

    The ``step`` counter is *not* present in the raw observation; the
    agent runner is responsible for tracking turn count and passing it in.
    It defaults to 0 for one-off parsing (e.g. in tests).
    """

    player: int
    planets: list[Planet]
    fleets: list[Fleet]
    angular_velocity: float
    initial_planets: list[Planet]
    comet_groups: list[CometGroup]
    comet_planet_ids: frozenset[int]
    remaining_time: float
    step: int = 0

    # ─── Construction ────────────────────────────────────────────────
    @classmethod
    def from_obs(cls, obs: Any, step: int = 0) -> "GameState":
        """Parse a raw observation (dict or namespace) into a GameState."""

        planets = [Planet(*p) for p in (_get(obs, "planets") or [])]
        fleets = [Fleet(*f) for f in (_get(obs, "fleets") or [])]
        initial = [Planet(*p) for p in (_get(obs, "initial_planets") or [])]

        comet_groups: list[CometGroup] = []
        for c in (_get(obs, "comets") or []):
            pids = _get(c, "planet_ids") or []
            paths_raw = _get(c, "paths") or []
            paths = tuple(
                tuple((float(pt[0]), float(pt[1])) for pt in path)
                for path in paths_raw
            )
            comet_groups.append(
                CometGroup(
                    planet_ids=tuple(int(i) for i in pids),
                    paths=paths,
                    path_index=int(_get(c, "path_index") or 0),
                )
            )

        return cls(
            player=int(_get(obs, "player") or 0),
            planets=planets,
            fleets=fleets,
            angular_velocity=float(_get(obs, "angular_velocity") or 0.0),
            initial_planets=initial,
            comet_groups=comet_groups,
            comet_planet_ids=frozenset(
                int(i) for i in (_get(obs, "comet_planet_ids") or [])
            ),
            remaining_time=float(_get(obs, "remainingOverageTime") or 0.0),
            step=step,
        )

    # ─── Cached views over planets ───────────────────────────────────
    @cached_property
    def my_planets(self) -> list[Planet]:
        return [p for p in self.planets if p.owner == self.player]

    @cached_property
    def enemy_planets(self) -> list[Planet]:
        """Planets owned by *some* other player (excludes neutral)."""
        return [
            p for p in self.planets
            if p.owner >= 0 and p.owner != self.player
        ]

    @cached_property
    def neutral_planets(self) -> list[Planet]:
        return [p for p in self.planets if p.owner == -1]

    @cached_property
    def non_my_planets(self) -> list[Planet]:
        """All planets we don't own (enemy + neutral). Common attack pool."""
        return [p for p in self.planets if p.owner != self.player]

    @cached_property
    def planet_by_id(self) -> dict[int, Planet]:
        return {p.id: p for p in self.planets}

    @cached_property
    def initial_planet_by_id(self) -> dict[int, Planet]:
        return {p.id: p for p in self.initial_planets}

    # ─── Cached views over fleets ────────────────────────────────────
    @cached_property
    def my_fleets(self) -> list[Fleet]:
        return [f for f in self.fleets if f.owner == self.player]

    @cached_property
    def enemy_fleets(self) -> list[Fleet]:
        return [
            f for f in self.fleets
            if f.owner >= 0 and f.owner != self.player
        ]

    # ─── Score / totals ──────────────────────────────────────────────
    @cached_property
    def my_total_ships(self) -> int:
        return (
            sum(p.ships for p in self.my_planets)
            + sum(f.ships for f in self.my_fleets)
        )

    @cached_property
    def total_ships_by_owner(self) -> dict[int, int]:
        """Total ships (planets + fleets) keyed by owner id. Neutral excluded."""
        totals: dict[int, int] = {}
        for p in self.planets:
            if p.owner >= 0:
                totals[p.owner] = totals.get(p.owner, 0) + p.ships
        for f in self.fleets:
            if f.owner >= 0:
                totals[f.owner] = totals.get(f.owner, 0) + f.ships
        return totals

    # ─── Comet helpers ───────────────────────────────────────────────
    def is_comet(self, planet_id: int) -> bool:
        return planet_id in self.comet_planet_ids
