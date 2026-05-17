"""Smoke test for orbit_wars.eval.metrics.

We bypass kaggle entirely: hand-craft an env.steps trace covering
ownership flips, fleet launches, and a sun-death, and verify
``compute_metrics`` extracts the right counts.
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orbit_wars.agents import (
    Decision, decisions_to_jsonl, load_decisions_jsonl,
)
from orbit_wars.core.state import Move
from orbit_wars.eval.metrics import PlayerMetrics, compute_metrics


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


# ─── Scenario builder ────────────────────────────────────────────────────
def make_step(planets, fleets) -> list:
    """Wrap planets+fleets into a kaggle-shaped step row."""
    obs = {
        "player": 0,
        "planets": planets,
        "fleets": fleets,
        "angular_velocity": 0.03,
        "initial_planets": planets,
        "comets": [],
        "comet_planet_ids": [],
        "remainingOverageTime": 60.0,
    }
    # Each step is a list of per-agent rows; both rows share the global obs.
    return [
        {"observation": obs, "reward": None, "status": "ACTIVE", "info": {}},
        {"observation": obs, "reward": None, "status": "ACTIVE", "info": {}},
    ]


# ─── Tests ───────────────────────────────────────────────────────────────
def test_empty_trace() -> None:
    print("test_empty_trace")
    m = compute_metrics([], player=0)
    check("zeroed metrics on empty trace",
          m.final_score == 0 and m.planets_captured == 0
          and m.fleets_launched == 0 and m.peak_planets == 0)


def test_planet_capture_and_loss() -> None:
    """Two players, one captures and one loses planets across turns."""
    print("test_planet_capture_and_loss")
    # Initial: I own planet 0, enemy owns planet 1, planet 2 is neutral
    s0 = make_step(
        planets=[
            [0, 0, 20.0, 20.0, 2.0, 50, 3],
            [1, 1, 80.0, 80.0, 2.0, 30, 3],
            [2, -1, 50.0, 50.0, 1.0, 5, 1],
        ],
        fleets=[],
    )
    # Step 1: I captured planet 2; enemy still owns 1
    s1 = make_step(
        planets=[
            [0, 0, 20.0, 20.0, 2.0, 50, 3],
            [1, 1, 80.0, 80.0, 2.0, 30, 3],
            [2, 0, 50.0, 50.0, 1.0, 5, 1],
        ],
        fleets=[],
    )
    # Step 2: enemy captures planet 0 from me; I still hold planet 2
    s2 = make_step(
        planets=[
            [0, 1, 20.0, 20.0, 2.0, 10, 3],
            [1, 1, 80.0, 80.0, 2.0, 30, 3],
            [2, 0, 50.0, 50.0, 1.0, 5, 1],
        ],
        fleets=[],
    )
    m0 = compute_metrics([s0, s1, s2], player=0)
    m1 = compute_metrics([s0, s1, s2], player=1)
    check("player 0 captured 1 planet",  m0.planets_captured == 1)
    check("player 0 lost 1 planet",      m0.planets_lost == 1)
    check("player 1 captured 1 planet",  m1.planets_captured == 1)
    check("player 1 lost 0 planets",     m1.planets_lost == 0)
    check("peak planets correct (p0)",   m0.peak_planets == 2)


def test_fleet_launch_and_sun_death() -> None:
    """A fleet appears (launch), then disappears with a path crossing the sun."""
    print("test_fleet_launch_and_sun_death")
    # Step 0: I own one planet, no fleets
    s0 = make_step(
        planets=[
            [0, 0, 20.0, 50.0, 2.0, 100, 3],
            [9, 1, 80.0, 50.0, 2.0, 50, 3],
        ],
        fleets=[],
    )
    # Step 1: I launch fleet 5 from planet 0 (20, 50) aimed at (80, 50)
    #         path crosses the sun at (50, 50)
    s1 = make_step(
        planets=[
            [0, 0, 20.0, 50.0, 2.0, 95, 3],
            [9, 1, 80.0, 50.0, 2.0, 50, 3],
        ],
        fleets=[
            # angle 0 = +x, fleet aimed directly across the sun
            [5, 0, 22.0, 50.0, 0.0, 0, 5],
        ],
    )
    # Step 2: fleet 5 has vanished (sun ate it)
    s2 = make_step(
        planets=[
            [0, 0, 20.0, 50.0, 2.0, 95, 3],
            [9, 1, 80.0, 50.0, 2.0, 50, 3],
        ],
        fleets=[],
    )
    m = compute_metrics([s0, s1, s2], player=0)
    check("fleet launch counted",          m.fleets_launched == 1)
    check("sun-death fleet counted",       m.fleets_lost_to_sun == 1)
    check("sun-death ships counted",       m.ships_lost_to_sun == 5)


def test_final_score_uses_last_state() -> None:
    print("test_final_score_uses_last_state")
    s0 = make_step(
        planets=[
            [0, 0, 20.0, 20.0, 2.0, 10, 3],
            [1, 1, 80.0, 80.0, 2.0, 5, 3],
        ],
        fleets=[],
    )
    s1 = make_step(
        planets=[
            [0, 0, 20.0, 20.0, 2.0, 200, 3],   # produced ships
            [1, 1, 80.0, 80.0, 2.0, 5, 3],
        ],
        fleets=[
            [7, 0, 25.0, 22.0, 0.1, 0, 50],     # my fleet
        ],
    )
    m = compute_metrics([s0, s1], player=0)
    check("final_score = own planet + own fleet", m.final_score == 250)
    check("survived all turns", m.survived_turns == 2)


def test_robust_to_missing_observation() -> None:
    print("test_robust_to_missing_observation")
    bad = [[{}, {}], [None]]
    m = compute_metrics(bad, player=0)
    check("returns zeroed metrics, no crash",
          isinstance(m, PlayerMetrics) and m.final_score == 0)


def test_namespace_observation_also_supported() -> None:
    """Some kaggle env builds wrap rows as namespace objects rather than
    dicts. compute_metrics should handle both."""
    print("test_namespace_observation_also_supported")
    from types import SimpleNamespace
    obs = {
        "player": 0,
        "planets": [[0, 0, 20.0, 20.0, 2.0, 10, 1]],
        "fleets": [],
        "angular_velocity": 0.03,
        "initial_planets": [[0, 0, 20.0, 20.0, 2.0, 10, 1]],
        "comets": [],
        "comet_planet_ids": [],
        "remainingOverageTime": 60.0,
    }
    step = [SimpleNamespace(observation=obs), SimpleNamespace(observation=obs)]
    m = compute_metrics([step], player=0)
    check("parses namespace step", m.final_score == 10 and m.peak_planets == 1)


# ─── Decision JSONL roundtrip ────────────────────────────────────────────
def test_decisions_jsonl_roundtrip() -> None:
    print("test_decisions_jsonl_roundtrip")
    decisions = [
        Decision(
            step=2,
            move=Move(from_planet_id=4, angle=1.234, ships=17),
            reason="attack",
            score=0.87,
            meta={"target_id": 7, "target_owner": 1},
        ),
        Decision(
            step=2,
            move=Move(from_planet_id=4, angle=0.0, ships=5),
            reason="consolidate",
            score=None,
            meta={"target_id": 0, "ships_sent": 5},
        ),
    ]
    blob = decisions_to_jsonl(decisions)
    check("blob non-empty", "attack" in blob and "consolidate" in blob)
    check("two lines",      blob.count("\n") == 2)

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "decisions.jsonl"
        p.write_text(blob, encoding="utf-8")
        loaded = load_decisions_jsonl(p)
    check("roundtrip length",      len(loaded) == 2)
    check("first reason preserved", loaded[0].reason == "attack")
    check("first move preserved",
          loaded[0].move.from_planet_id == 4
          and abs(loaded[0].move.angle - 1.234) < 1e-12
          and loaded[0].move.ships == 17)
    check("meta preserved",         loaded[0].meta.get("target_id") == 7)
    check("score is None preserved", loaded[1].score is None)


# ─── Runner ──────────────────────────────────────────────────────────────
def main() -> None:
    test_empty_trace()
    test_planet_capture_and_loss()
    test_fleet_launch_and_sun_death()
    test_final_score_uses_last_state()
    test_robust_to_missing_observation()
    test_namespace_observation_also_supported()
    test_decisions_jsonl_roundtrip()
    print("\nAll metrics smoke tests passed.")


if __name__ == "__main__":
    main()
