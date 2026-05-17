"""
Orbit Wars submission -- preset: blitz

AUTO-GENERATED FILE -- DO NOT EDIT BY HAND.
Source: configs/blitz.yaml + orbit_wars/ package
Built:  2026-05-13T05:32:45Z
Commit: unknown

Distance-weighted greedy attack with a mild production-rate preference.
Slight bias toward enemy targets over neutrals. No defense pass.
Wins 72.2% of a 10-strategy round-robin in the EDA notebook.
"""
from __future__ import annotations

# ====================================================================
# inlined from orbit_wars/core/geometry.py
# ====================================================================
"""
Orbit Wars - Geometry and physics primitives.

Pure functions and constants describing the board, the sun, fleet speed,
sun-avoidance, and orbital motion. No imports of agent code, no state.

These are the building blocks that *every* agent and *every* analysis tool
should be using -- duplicating them in agent files (as the current
``main.py`` / ``agents/blitz.py`` do) is exactly what this module is here
to eliminate.

Conventions
-----------
* Board origin is the top-left, x grows right, y grows down.
* Angles are in radians, ``0`` = +x (right), ``pi/2`` = +y (down), matching
  ``math.atan2(dy, dx)``.
* Distances are in board units (the board is 100 x 100).
"""


import math

# ── Board constants ──────────────────────────────────────────────────────
BOARD_SIZE: float = 100.0
SUN_X: float = 50.0
SUN_Y: float = 50.0
SUN_R: float = 10.0
CENTER: tuple[float, float] = (SUN_X, SUN_Y)

# ── Fleet physics ────────────────────────────────────────────────────────
MIN_SPEED: float = 1.0
MAX_SPEED: float = 6.0
SPEED_REFERENCE_SHIPS: int = 1000  # fleet size at which max speed is reached

# ── Useful derived constants ─────────────────────────────────────────────
MAX_DIAG: float = math.hypot(BOARD_SIZE, BOARD_SIZE)  # ~141.42, max distance
ROTATION_RADIUS_LIMIT: float = 50.0  # orbital_r + planet_r < this => rotates


# ── Distance / angle ─────────────────────────────────────────────────────
def dist(x1: float, y1: float, x2: float, y2: float) -> float:
    """Euclidean distance between two points."""
    return math.hypot(x1 - x2, y1 - y2)


def angle_to(x1: float, y1: float, x2: float, y2: float) -> float:
    """Angle (radians) of the vector from (x1, y1) -> (x2, y2)."""
    return math.atan2(y2 - y1, x2 - x1)


# ── Fleet speed ──────────────────────────────────────────────────────────
def fleet_speed(ships: int, max_speed: float = MAX_SPEED) -> float:
    """Fleet speed as a function of fleet size.

    ``speed = 1 + (max - 1) * (log(ships) / log(1000)) ^ 1.5``,
    clamped to ``[1, max_speed]``.

    * 1 ship   -> 1.0 units/turn
    * ~500     -> ~5.0
    * 1000+    -> max_speed
    """
    if ships <= 1:
        return MIN_SPEED
    ratio = math.log(ships) / math.log(SPEED_REFERENCE_SHIPS)
    s = MIN_SPEED + (max_speed - MIN_SPEED) * (ratio ** 1.5)
    # log can exceed 1 if ships > 1000, so clamp explicitly
    return min(s, max_speed)


# ── Sun collision (continuous segment test) ──────────────────────────────
def seg_hits_sun(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    margin: float = 2.0,
) -> bool:
    """True iff the line segment (x1, y1) -> (x2, y2) passes within
    ``SUN_R + margin`` of the sun.

    Solved via segment / circle intersection: find the parameter ``t`` along
    the segment where distance to the sun equals ``SUN_R + margin`` and test
    whether either solution lies in [0, 1].
    """
    dx, dy = x2 - x1, y2 - y1
    fx, fy = x1 - SUN_X, y1 - SUN_Y
    a = dx * dx + dy * dy
    if a == 0.0:
        # zero-length segment: check the endpoint against the sun
        return (fx * fx + fy * fy) <= (SUN_R + margin) ** 2
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - (SUN_R + margin) ** 2
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return False
    sq = math.sqrt(disc)
    t1 = (-b - sq) / (2.0 * a)
    t2 = (-b + sq) / (2.0 * a)
    return (0.0 <= t1 <= 1.0) or (0.0 <= t2 <= 1.0)


# ── Orbital motion ───────────────────────────────────────────────────────
def orbital_position(
    initial_x: float,
    initial_y: float,
    angular_velocity: float,
    steps: int,
) -> tuple[float, float]:
    """Predict where an orbiting planet (or comet) will be in ``steps`` turns.

    The planet rotates around the sun at constant ``angular_velocity``
    radians per turn. Returns the (x, y) position after the rotation.

    For *static* planets (those with orbital_r + planet_r >= 50), pass
    ``angular_velocity = 0`` to get the unchanged position back.
    """
    dx, dy = initial_x - SUN_X, initial_y - SUN_Y
    r = math.hypot(dx, dy)
    if r == 0.0:
        return (SUN_X, SUN_Y)
    theta0 = math.atan2(dy, dx)
    theta = theta0 + angular_velocity * steps
    return (SUN_X + r * math.cos(theta), SUN_Y + r * math.sin(theta))


def is_orbiting(planet_x: float, planet_y: float, planet_radius: float) -> bool:
    """Return True if the planet is one of the rotating inner planets.

    Rule from the rules doc: a planet rotates iff its orbital radius plus
    its own radius is strictly less than 50.
    """
    orbital_r = dist(planet_x, planet_y, SUN_X, SUN_Y)
    return orbital_r + planet_radius < ROTATION_RADIUS_LIMIT


def in_bounds(x: float, y: float) -> bool:
    """Whether (x, y) lies inside the playing field."""
    return 0.0 <= x <= BOARD_SIZE and 0.0 <= y <= BOARD_SIZE

# ====================================================================
# inlined from orbit_wars/core/state.py
# ====================================================================
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

# ====================================================================
# inlined from orbit_wars/agents/base.py
# ====================================================================
"""
Agent base class and the kaggle adapter.

Design
------
Every Orbit Wars agent is a subclass of :class:`Agent` that implements
``act(state) -> list[Move]``. The base class provides:

* **Step counting**: the raw kaggle observation does not include the turn
  number, but our :class:`GameState` does. The base class threads the
  step counter through so each call to ``act`` sees ``state.step`` and so
  decision logs can be timestamped.
* **Decision logging**: subclasses can call :meth:`Agent.log` to record
  *why* a move was made. The runner (Step 4) and the replay analyser
  (Step 6) read these to explain agent behaviour after the fact.
* **Lifecycle hooks**: :meth:`Agent.on_game_start` /
  :meth:`Agent.on_game_end` are called automatically on the first and
  (where the runner can detect it) last turn of a game. Override them for
  per-game setup / teardown without polluting ``act``.
* **Game-isolation via reset**: ``reset()`` clears per-game state so the
  same agent instance can be reused across many games during local
  evaluation without leaking the turn counter or decision log between
  games.

The :func:`make_kaggle_agent` factory hides all of this behind the plain
``(obs) -> list[list]`` callable that ``env.run([fn, ...])`` expects.
"""


from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any



# ─────────────────────────────────────────────────────────────────────────
# Decision log entry
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class Decision:
    """One reasoning trace entry attached to one issued :class:`Move`.

    ``meta`` is intentionally free-form -- subclasses can stash any extra
    fields they care about (e.g. ``target_owner``, ``predicted_arrival``).
    """

    step: int
    move: Move
    reason: str = ""
    score: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
# Agent base class
# ─────────────────────────────────────────────────────────────────────────
class Agent(ABC):
    """Abstract base class for all Orbit Wars agents.

    Subclasses must implement :meth:`act`. Subclasses *may* override
    :meth:`on_game_start` / :meth:`on_game_end` for setup or teardown.

    Subclasses should call :meth:`log` for every move they issue, so the
    decision log stays in sync with the moves returned.
    """

    #: Human-readable name. Override per subclass; used in eval output.
    name: str = "agent"

    def __init__(self) -> None:
        self._step: int = 0
        self._decisions: list[Decision] = []
        self._game_started: bool = False

    # ── Lifecycle ────────────────────────────────────────────────────
    def on_game_start(self, state: GameState) -> None:
        """Called once, on the first turn of a new game."""

    @abstractmethod
    def act(self, state: GameState) -> list[Move]:
        """Decide what to do this turn. Return the list of launches."""

    def on_game_end(self, state: GameState, reward: int) -> None:
        """Called by the runner after the final turn. May not fire if the
        agent is invoked through the bare kaggle adapter (kaggle does not
        give us a clean end-of-game callback)."""

    # ── Decision logging ─────────────────────────────────────────────
    def log(
        self,
        move: Move,
        *,
        reason: str = "",
        score: float | None = None,
        **meta: Any,
    ) -> None:
        """Record a decision. Call from inside :meth:`act` when issuing a move."""
        self._decisions.append(
            Decision(step=self._step, move=move, reason=reason, score=score, meta=dict(meta))
        )

    @property
    def decisions(self) -> list[Decision]:
        """All decisions logged so far (across the current game)."""
        return list(self._decisions)

    # ── Runner-facing internals ──────────────────────────────────────
    def _run_turn(self, state: GameState) -> list[Move]:
        """Internal: drive one turn. Used by the kaggle adapter and the
        evaluation runner; subclasses should *not* call this themselves."""
        if not self._game_started:
            self._game_started = True
            self.on_game_start(state)
        self._step = state.step
        return self.act(state)

    def reset(self) -> None:
        """Clear per-game state. The runner calls this between games."""
        self._step = 0
        self._decisions.clear()
        self._game_started = False


# ─────────────────────────────────────────────────────────────────────────
# Kaggle adapter
# ─────────────────────────────────────────────────────────────────────────
def make_kaggle_agent(agent_cls: type[Agent], **kwargs: Any):
    """Adapt an Agent class into a callable that ``kaggle_environments``
    can consume directly:

    >>> env = kaggle_environments.make("orbit_wars")
    >>> env.run([make_kaggle_agent(SniperAgent), "random"])

    The returned function tracks the turn number internally (kaggle does
    not include it in the observation), parses the raw obs into a
    :class:`GameState`, and serialises moves back to list-of-lists. The
    underlying Agent instance is attached to the function as
    ``fn.agent_instance`` so callers can read its decision log afterwards.
    """
    instance = agent_cls(**kwargs)
    step_counter = [0]

    def kaggle_fn(obs):
        state = GameState.from_obs(obs, step=step_counter[0])
        moves = instance._run_turn(state)
        step_counter[0] += 1
        return [m.to_list() for m in moves]

    kaggle_fn.agent_instance = instance  # type: ignore[attr-defined]
    kaggle_fn.__name__ = f"kaggle_{agent_cls.__name__}"
    return kaggle_fn

# ====================================================================
# inlined from orbit_wars/agents/heuristic.py
# ====================================================================
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


import math
from dataclasses import dataclass
from typing import TYPE_CHECKING




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

# ====================================================================
# Kaggle entrypoint
# ====================================================================
_config = HeuristicConfig(
    dist_weight=3.0,
    prod_weight=0.5,
    weak_weight=0.0,
    neutral_bonus=0.0,
    enemy_bonus=1.0,
    attack_buffer=1.0,
    min_ships=1,
    use_defense=False,
    defense_reserve=5,
    wait_turns=2,
    consolidate_threshold=15,
    consolidate_fraction=0.5,
    max_ships_norm=500.0,
)
_kaggle_agent = make_kaggle_agent(HeuristicAgent, config=_config)

def agent(obs):
    return _kaggle_agent(obs)
