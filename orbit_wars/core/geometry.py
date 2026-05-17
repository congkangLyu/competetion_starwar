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

from __future__ import annotations

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
