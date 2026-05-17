"""Orbit Wars agent toolkit.

A library for building, evaluating, and analyzing Orbit Wars agents.

Layout:
    orbit_wars.core      -- parsed game state + physics/geometry primitives
    orbit_wars.agents    -- agent implementations (added in a later step)
    orbit_wars.eval      -- evaluation harness (added in a later step)
    orbit_wars.analysis  -- replay parsing + visualization (added later)

The top-level package re-exports the most commonly used symbols so that
agents and tools can do:

    from orbit_wars import GameState, Planet, Fleet, fleet_speed, seg_hits_sun
"""

from orbit_wars.core.state import (
    GameState,
    Planet,
    Fleet,
    CometGroup,
    Move,
)
from orbit_wars.core.geometry import (
    BOARD_SIZE,
    SUN_X,
    SUN_Y,
    SUN_R,
    CENTER,
    MAX_SPEED,
    MAX_DIAG,
    ROTATION_RADIUS_LIMIT,
    dist,
    angle_to,
    fleet_speed,
    seg_hits_sun,
    orbital_position,
    is_orbiting,
    in_bounds,
)

__all__ = [
    # data
    "GameState",
    "Planet",
    "Fleet",
    "CometGroup",
    "Move",
    # constants
    "BOARD_SIZE",
    "SUN_X",
    "SUN_Y",
    "SUN_R",
    "CENTER",
    "MAX_SPEED",
    "MAX_DIAG",
    "ROTATION_RADIUS_LIMIT",
    # geometry / physics
    "dist",
    "angle_to",
    "fleet_speed",
    "seg_hits_sun",
    "orbital_position",
    "is_orbiting",
    "in_bounds",
]
