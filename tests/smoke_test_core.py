"""Smoke test for orbit_wars.core.

Run from the project root:
    python tests/smoke_test_core.py

Not a real pytest suite yet -- this only verifies that imports work and
the dataclasses parse a representative observation correctly. A proper
pytest suite will be added in a later step.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace

# Make the project root importable when running this script directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orbit_wars import (  # noqa: E402
    GameState,
    Move,
    SUN_X,
    SUN_Y,
    fleet_speed,
    seg_hits_sun,
    orbital_position,
    is_orbiting,
    angle_to,
    dist,
)


# ----- Sample observations -----------------------------------------------
def sample_obs() -> dict:
    """A small fabricated observation -- one of each kind of planet."""
    return {
        "player": 0,
        "planets": [
            [0, 0, 25.0, 25.0, 2.0, 10, 3],   # mine
            [1, 1, 75.0, 75.0, 2.0, 15, 4],   # enemy
            [2, -1, 50.0, 20.0, 1.5, 5, 2],   # neutral, near sun
            [3, -1, 90.0, 50.0, 1.0, 7, 1],   # neutral, a comet
        ],
        "fleets": [
            [100, 0, 30.0, 30.0, 0.5, 0, 5],   # my fleet
            [101, 1, 70.0, 70.0, 3.0, 1, 8],   # enemy fleet
        ],
        "angular_velocity": 0.03,
        "initial_planets": [
            [0, 0, 25.0, 25.0, 2.0, 10, 3],
            [1, 1, 75.0, 75.0, 2.0, 15, 4],
            [2, -1, 50.0, 20.0, 1.5, 5, 2],
            [3, -1, 90.0, 50.0, 1.0, 7, 1],
        ],
        "comets": [
            {
                "planet_ids": [3],
                "paths": [[(90.0, 50.0), (85.0, 50.0), (80.0, 50.0)]],
                "path_index": 0,
            },
        ],
        "comet_planet_ids": [3],
        "remainingOverageTime": 60.0,
    }


def check(label: str, cond: bool) -> None:
    """Print OK / FAIL line, then raise AssertionError on failure.

    Using AssertionError (instead of SystemExit) makes the smoke tests
    pytest-compatible: pytest collects each ``test_*`` function and
    captures the assertion's label as the failure message, while
    ``python tests/smoke_test_X.py`` still exits non-zero with a
    traceback that points at the failing case."""
    if cond:
        print(f"  [OK ] {label}")
    else:
        print(f"  [FAIL] {label}")
        raise AssertionError(label)


# ----- Tests -------------------------------------------------------------
def test_parse_dict_obs() -> None:
    print("test_parse_dict_obs")
    gs = GameState.from_obs(sample_obs(), step=5)
    check("player parsed", gs.player == 0)
    check("planet count", len(gs.planets) == 4)
    check("fleet count", len(gs.fleets) == 2)
    check("step passed through", gs.step == 5)
    check("comet_planet_ids", gs.comet_planet_ids == frozenset({3}))
    check("comet group parsed", len(gs.comet_groups) == 1)
    check("comet group path_index", gs.comet_groups[0].path_index == 0)


def test_parse_namespace_obs() -> None:
    print("test_parse_namespace_obs")
    obs = sample_obs()
    gs = GameState.from_obs(SimpleNamespace(**obs))
    check("namespace parses", gs.player == 0 and len(gs.planets) == 4)


def test_derived_views() -> None:
    print("test_derived_views")
    gs = GameState.from_obs(sample_obs())
    check("my_planets", [p.id for p in gs.my_planets] == [0])
    check("enemy_planets", [p.id for p in gs.enemy_planets] == [1])
    check("neutral_planets", sorted(p.id for p in gs.neutral_planets) == [2, 3])
    check("non_my_planets", sorted(p.id for p in gs.non_my_planets) == [1, 2, 3])
    check("planet_by_id lookup", gs.planet_by_id[2].ships == 5)
    check("my_fleets", [f.id for f in gs.my_fleets] == [100])
    check("enemy_fleets", [f.id for f in gs.enemy_fleets] == [101])
    check("is_comet on 3", gs.is_comet(3))
    check("is_comet on 0 false", not gs.is_comet(0))


def test_totals() -> None:
    print("test_totals")
    gs = GameState.from_obs(sample_obs())
    # me: planet 0 (10 ships) + fleet 100 (5) = 15
    check("my_total_ships", gs.my_total_ships == 15)
    totals = gs.total_ships_by_owner
    check("totals owner 0", totals[0] == 15)
    check("totals owner 1", totals[1] == 23)   # planet 1 (15) + fleet 101 (8)
    check("neutrals excluded", -1 not in totals)


def test_fleet_speed_curve() -> None:
    print("test_fleet_speed_curve")
    speeds = [fleet_speed(n) for n in [1, 10, 100, 500, 1000, 5000]]
    check("monotonic", speeds == sorted(speeds))
    check("1 ship -> 1.0", abs(speeds[0] - 1.0) < 1e-9)
    check("1000 ships -> ~6.0", abs(speeds[4] - 6.0) < 1e-9)
    check("clamped above 1000", abs(speeds[5] - 6.0) < 1e-9)


def test_seg_hits_sun() -> None:
    print("test_seg_hits_sun")
    check("horizontal through center hits", seg_hits_sun(0, 50, 100, 50))
    check("near miss above sun", not seg_hits_sun(0, 30, 100, 30))   # 20 above
    check("vertical through center hits", seg_hits_sun(50, 0, 50, 100))
    check("offscreen segment doesn't hit", not seg_hits_sun(0, 0, 10, 10))
    # tangent + margin should hit (sun_r=10, margin=2 -> avoid within 12)
    check("tangent-plus-margin hits", seg_hits_sun(0, 39, 100, 39))


def test_orbital_position() -> None:
    print("test_orbital_position")
    # 0 steps -> unchanged
    x, y = orbital_position(25.0, 50.0, 0.05, 0)
    check("0 steps unchanged", abs(x - 25.0) < 1e-9 and abs(y - 50.0) < 1e-9)
    # Half revolution: (25, 50) is on a r=25 circle centered at sun;
    # rotating by exactly pi must land on (75, 50).
    x2, y2 = orbital_position(25.0, 50.0, math.pi, 1)
    check("half revolution lands opposite", dist(x2, y2, 75.0, 50.0) < 1e-9)
    # Full revolution with omega that evenly divides 2pi -- must return exactly.
    x3, y3 = orbital_position(25.0, 50.0, 2 * math.pi / 100, 100)
    check("full revolution returns to start", dist(x3, y3, 25.0, 50.0) < 1e-9)
    # Quarter turn from (25, 50) at omega = pi/2 rad/step for 1 step.
    # In screen coords (y down) the game's angle convention is clockwise,
    # so starting at 9-o'clock (left of sun) we land at 12-o'clock (above
    # sun on screen, i.e. y < SUN_Y).
    x4, y4 = orbital_position(25.0, 50.0, math.pi / 2, 1)
    check("quarter turn lands at (50, 25)",
          abs(x4 - 50.0) < 1e-9 and abs(y4 - 25.0) < 1e-9)


def test_is_orbiting() -> None:
    print("test_is_orbiting")
    # planet at (25, 50): orbital_r = 25, radius 2 -> 27 < 50 -> orbits
    check("inner planet orbits", is_orbiting(25.0, 50.0, 2.0))
    # planet at (90, 50): orbital_r = 40, radius 2 -> 42 < 50 -> orbits
    check("borderline planet orbits", is_orbiting(90.0, 50.0, 2.0))
    # planet at (95, 50): orbital_r = 45, radius 6 -> 51 >= 50 -> static
    check("outer planet static", not is_orbiting(95.0, 50.0, 6.0))


def test_geometry_helpers() -> None:
    print("test_geometry_helpers")
    check("dist", abs(dist(0, 0, 3, 4) - 5.0) < 1e-9)
    check("angle_to right", abs(angle_to(0, 0, 1, 0) - 0.0) < 1e-9)
    check("angle_to down", abs(angle_to(0, 0, 0, 1) - math.pi / 2) < 1e-9)


def test_move_serialization() -> None:
    print("test_move_serialization")
    m = Move(from_planet_id=4, angle=1.234, ships=17)
    check("to_list", m.to_list() == [4, 1.234, 17])


# ----- Runner ------------------------------------------------------------
def main() -> None:
    test_parse_dict_obs()
    test_parse_namespace_obs()
    test_derived_views()
    test_totals()
    test_fleet_speed_curve()
    test_seg_hits_sun()
    test_orbital_position()
    test_is_orbiting()
    test_geometry_helpers()
    test_move_serialization()
    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    main()
