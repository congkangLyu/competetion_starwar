"""Smoke test for orbit_wars.analysis (replay loader + SVG/HTML viz)."""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orbit_wars.agents.base import Decision
from orbit_wars.analysis import (
    PLAYER_COLORS,
    extract_states,
    load_kaggle_replay,
    render_frame_svg,
    render_replay_html,
)
from orbit_wars.core.state import GameState, Move


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


# ─── Helpers ─────────────────────────────────────────────────────────────
def make_step(planets, fleets, ang_vel=0.03, comet_ids=()):
    obs = {
        "player": 0,
        "planets": planets,
        "fleets": fleets,
        "angular_velocity": ang_vel,
        "initial_planets": planets,
        "comets": [],
        "comet_planet_ids": list(comet_ids),
        "remainingOverageTime": 60.0,
    }
    return [
        {"observation": obs, "reward": None, "status": "ACTIVE", "info": {}},
        {"observation": obs, "reward": None, "status": "ACTIVE", "info": {}},
    ]


def sample_state(step: int = 0) -> GameState:
    obs = {
        "player": 0,
        "planets": [
            [0, 0, 20.0, 20.0, 2.0, 50, 3],
            [1, 1, 80.0, 80.0, 2.0, 30, 3],
            [2, -1, 30.0, 70.0, 1.5, 5, 2],
        ],
        "fleets": [
            [10, 0, 25.0, 25.0, 0.785, 0, 5],   # 45-degree
        ],
        "angular_velocity": 0.03,
        "initial_planets": [
            [0, 0, 20.0, 20.0, 2.0, 50, 3],
            [1, 1, 80.0, 80.0, 2.0, 30, 3],
            [2, -1, 30.0, 70.0, 1.5, 5, 2],
        ],
        "comets": [],
        "comet_planet_ids": [],
        "remainingOverageTime": 60.0,
    }
    return GameState.from_obs(obs, step=step)


# ─── Replay loader ───────────────────────────────────────────────────────
def test_load_kaggle_replay_dict_shape() -> None:
    print("test_load_kaggle_replay_dict_shape")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "replay.json"
        p.write_text(json.dumps({"steps": [make_step([[0,0,20,20,2,5,1]], [])]}))
        steps = load_kaggle_replay(p)
        check("returns list", isinstance(steps, list))
        check("right length",  len(steps) == 1)


def test_load_kaggle_replay_list_shape() -> None:
    print("test_load_kaggle_replay_list_shape")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "replay.json"
        p.write_text(json.dumps([make_step([[0,0,20,20,2,5,1]], [])]))
        steps = load_kaggle_replay(p)
        check("top-level list accepted", isinstance(steps, list) and len(steps) == 1)


def test_extract_states_walks_trace() -> None:
    print("test_extract_states_walks_trace")
    steps = [
        make_step([[0, 0, 20, 20, 2, 50, 3]], []),
        None,
        make_step([[0, 0, 20, 20, 2, 53, 3]], []),
        [],
        make_step([[0, 1, 20, 20, 2, 0, 3]], []),
    ]
    states = extract_states(steps, player=0)
    check("skips empty/None turns",   len(states) == 3)
    check("step numbers preserved",   [s.step for s in states] == [0, 2, 4])
    check("player patched correctly", all(s.player == 0 for s in states))
    # The mid-trace state should still have planet 0 as mine
    check("planet visible mid-game",  states[1].planet_by_id[0].ships == 53)


def test_extract_states_namespace_rows() -> None:
    """Some kaggle builds wrap rows as namespaces. extract_states should accept either."""
    print("test_extract_states_namespace_rows")
    obs = {
        "player": 0,
        "planets": [[0, 0, 20, 20, 2, 5, 1]],
        "fleets": [],
        "angular_velocity": 0.03,
        "initial_planets": [[0, 0, 20, 20, 2, 5, 1]],
        "comets": [],
        "comet_planet_ids": [],
        "remainingOverageTime": 60.0,
    }
    step = [SimpleNamespace(observation=obs), SimpleNamespace(observation=obs)]
    states = extract_states([step], player=0)
    check("namespace step parses", len(states) == 1 and states[0].my_total_ships == 5)


# ─── SVG renderer ────────────────────────────────────────────────────────
def test_render_frame_svg_basic() -> None:
    print("test_render_frame_svg_basic")
    svg = render_frame_svg(sample_state())
    check("starts with <svg",        svg.startswith("<svg"))
    check("ends with </svg>",        svg.rstrip().endswith("</svg>"))
    check("contains sun coords",     'cx="50.0" cy="50.0"' in svg or 'cx="50" cy="50"' in svg)
    check("paints player 0 colour",  PLAYER_COLORS[0] in svg)
    check("paints player 1 colour",  PLAYER_COLORS[1] in svg)
    check("paints neutral colour",   PLAYER_COLORS[-1] in svg)
    check("renders ship count text", ">50<" in svg)
    check("turn label present",      "t=0" in svg)


def test_render_frame_svg_with_decisions() -> None:
    print("test_render_frame_svg_with_decisions")
    state = sample_state()
    decisions = [
        Decision(step=0, move=Move(0, math.radians(45), 10), reason="attack",
                 meta={"target_id": 1}),
    ]
    svg = render_frame_svg(state, decisions_at_step=decisions)
    # The overlay is drawn as a dashed line; check that the dashed attribute is present
    check("dashed decision overlay rendered", "stroke-dasharray=" in svg)
    # And the highlight color
    check("overlay uses highlight colour", "#fef08a" in svg)


def test_render_frame_svg_marks_comets() -> None:
    print("test_render_frame_svg_marks_comets")
    obs = {
        "player": 0,
        "planets": [
            [0, 0, 20, 20, 2, 5, 1],
            [9, -1, 90, 50, 1, 4, 1],
        ],
        "fleets": [],
        "angular_velocity": 0.03,
        "initial_planets": [],
        "comets": [],
        "comet_planet_ids": [9],
        "remainingOverageTime": 60.0,
    }
    state = GameState.from_obs(obs, step=120)
    svg = render_frame_svg(state)
    check("comet rendered with dashed stroke", "stroke-dasharray=\"0.4 0.4\"" in svg)


def test_render_frame_svg_show_orbits() -> None:
    print("test_render_frame_svg_show_orbits")
    obs = {
        "player": 0,
        "planets": [
            [0, 0, 20, 20, 2, 5, 1],
            [1, -1, 80, 80, 2, 5, 1],
        ],
        "fleets": [],
        "angular_velocity": 0.03,
        "initial_planets": [
            [0, 0, 20, 20, 2, 5, 1],
            [1, -1, 80, 80, 2, 5, 1],
        ],
        "comets": [],
        "comet_planet_ids": [],
        "remainingOverageTime": 60.0,
    }
    state = GameState.from_obs(obs, step=0)
    svg = render_frame_svg(state, show_orbits=True)
    check("orbit guide rendered", "#94a3b8" in svg)


# ─── HTML renderer ───────────────────────────────────────────────────────
def test_render_replay_html_shape() -> None:
    print("test_render_replay_html_shape")
    states = [sample_state(step=i) for i in range(5)]
    html = render_replay_html(states, title="Test replay")
    check("is HTML5 doctype",        html.startswith("<!doctype html>"))
    check("title set",               "<title>Test replay</title>" in html)
    check("has range slider",        '<input type="range"' in html)
    check("has play button",         "play" in html)
    # Frames are embedded as a JS array literal; pull the literal out and
    # verify it has 5 entries.
    m = re.search(r"var F=(\[.*?\]);", html, flags=re.DOTALL)
    check("frames embedded",         m is not None)
    arr = json.loads(m.group(1))
    check("right number of frames",  len(arr) == 5)
    check("each frame is SVG",       all(s.startswith("<svg") for s in arr))


def test_render_replay_html_with_decisions() -> None:
    print("test_render_replay_html_with_decisions")
    states = [sample_state(step=i) for i in range(3)]
    decisions_by_step = {
        1: [Decision(step=1, move=Move(0, 0.785, 10), reason="attack")]
    }
    html = render_replay_html(states, decisions_by_step=decisions_by_step)
    # The overlay highlight colour should now appear at least once
    check("decision colour appears", "#fef08a" in html)


def test_render_replay_html_with_player_names() -> None:
    print("test_render_replay_html_with_player_names")
    states = [sample_state(step=i) for i in range(2)]
    html = render_replay_html(
        states,
        title="Named replay",
        player_names={0: "ow_proto", 1: "blitz"},
    )
    check("player 0 name rendered", "ow_proto" in html)
    check("player 1 name rendered", "blitz" in html)
    check("player ids rendered", "P0" in html and "P1" in html)
    check("legend swatches rendered", "class=\"swatch\"" in html)


# ─── CLI end-to-end ──────────────────────────────────────────────────────
def test_cli_end_to_end() -> None:
    """Drive tools/viz.py as a subprocess: synthetic replay JSON in,
    HTML out. Asserts the file is a non-trivial standalone document."""
    print("test_cli_end_to_end")
    steps = [
        make_step([[0, 0, 20, 20, 2, 50, 3], [1, 1, 80, 80, 2, 30, 3]], []),
        make_step([[0, 0, 20, 20, 2, 53, 3], [1, 1, 80, 80, 2, 30, 3]], []),
        make_step([[0, 0, 20, 20, 2, 56, 3], [1, 1, 80, 80, 2, 30, 3]], []),
    ]
    with tempfile.TemporaryDirectory() as td:
        replay = Path(td) / "replay.json"
        out_html = Path(td) / "out.html"
        replay.write_text(json.dumps({"steps": steps}), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "tools/viz.py",
                str(replay),
                "-o",
                str(out_html),
                "--names",
                "alpha,beta",
            ],
            cwd=ROOT, capture_output=True, text=True,
        )
        check("CLI exits cleanly", result.returncode == 0)
        check("HTML file created", out_html.is_file())
        txt = out_html.read_text(encoding="utf-8")
        check("HTML is non-trivial",   len(txt) > 1000)
        check("contains 3 SVG frames", txt.count("<svg") == 3)
        check("CLI player names rendered", "alpha" in txt and "beta" in txt)


def test_replay_cli_end_to_end() -> None:
    """Drive legacy tools/replay.py too; Makefile's replay target uses it."""
    print("test_replay_cli_end_to_end")
    steps = [
        make_step([[0, 0, 20, 20, 2, 50, 3], [1, 1, 80, 80, 2, 30, 3]], []),
        make_step([[0, 0, 20, 20, 2, 53, 3], [1, 1, 80, 80, 2, 30, 3]], []),
    ]
    with tempfile.TemporaryDirectory() as td:
        replay = Path(td) / "replay.json"
        out_html = Path(td) / "out.html"
        replay.write_text(json.dumps({"steps": steps}), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "tools/replay.py",
                str(replay),
                "-o",
                str(out_html),
                "--show-orbits",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        check("replay CLI exits cleanly", result.returncode == 0)
        check("replay HTML file created", out_html.is_file())
        txt = out_html.read_text(encoding="utf-8")
        check("replay HTML is non-trivial", len(txt) > 1000)
        check("replay contains 2 SVG frames", txt.count("<svg") == 2)


def test_cli_empty_replay_fails_clearly() -> None:
    print("test_cli_empty_replay_fails_clearly")
    with tempfile.TemporaryDirectory() as td:
        replay = Path(td) / "empty.json"
        out_html = Path(td) / "out.html"
        replay.write_text(json.dumps({"steps": []}), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "tools/viz.py", str(replay), "-o", str(out_html)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        check("empty replay exits non-zero", result.returncode != 0)
        check("empty replay error is clear", "no usable frames" in result.stderr)
        check("empty replay wrote no HTML", not out_html.exists())


# ─── Runner ──────────────────────────────────────────────────────────────
def main() -> None:
    test_load_kaggle_replay_dict_shape()
    test_load_kaggle_replay_list_shape()
    test_extract_states_walks_trace()
    test_extract_states_namespace_rows()
    test_render_frame_svg_basic()
    test_render_frame_svg_with_decisions()
    test_render_frame_svg_marks_comets()
    test_render_frame_svg_show_orbits()
    test_render_replay_html_shape()
    test_render_replay_html_with_decisions()
    test_render_replay_html_with_player_names()
    test_cli_end_to_end()
    test_replay_cli_end_to_end()
    test_cli_empty_replay_fails_clearly()
    print("\nAll viz smoke tests passed.")


if __name__ == "__main__":
    main()
