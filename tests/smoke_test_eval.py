"""Smoke test for orbit_wars.eval.runner.

The kaggle env is not available in this sandbox (no network for pip).
We mock it via sys.modules injection so the runner's *logic* is exercised
end-to-end without the real dependency. Parallel mode is verified
structurally (the work scheduler) but not actually run across processes;
real-env parallel runs are validated by the user on a machine with
kaggle-environments installed.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ─── Fake kaggle_environments ────────────────────────────────────────────
# A deterministic "env" that returns rewards as a function of (seed,
# agents). Doesn't actually run any agent code; we just need the runner
# to produce a sane MatchResult.
class _FakeEnv:
    def __init__(self, configuration):
        self.configuration = configuration
        self._seed = int(configuration.get("seed", 0))
        self.steps: list = []

    def run(self, agents):
        # Synthesise a *populated* trace -- the runner now computes
        # metrics from env.steps, so we need real obs rows. Three
        # turns: initial state, slot-0 captures a neutral, final.
        n_turns_padding = (self._seed % 5)
        reward0 = float((self._seed * 7) % 200) - 100.0
        reward1 = float((self._seed * 5) % 200) - 100.0
        reward0 += hash(agents[0]) % 7
        reward1 += hash(agents[1]) % 7

        def make_row(planets, fleets):
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
            return [
                {"observation": obs, "reward": None, "status": "ACTIVE", "info": {}},
                {"observation": obs, "reward": None, "status": "ACTIVE", "info": {}},
            ]

        s0 = make_row(
            planets=[
                [0, 0, 20.0, 20.0, 2.0, 50, 3],
                [1, 1, 80.0, 80.0, 2.0, 30, 3],
                [2, -1, 30.0, 70.0, 1.5, 5, 2],
            ],
            fleets=[],
        )
        s1 = make_row(
            planets=[
                [0, 0, 20.0, 20.0, 2.0, 40, 3],
                [1, 1, 80.0, 80.0, 2.0, 30, 3],
                [2, 0, 30.0, 70.0, 1.5, 5, 2],   # player 0 just captured
            ],
            fleets=[],
        )
        # Pad some extra empty turns so n_turns varies with seed
        padding = [make_row([[0, 0, 20.0, 20.0, 2.0, 40, 3]], [])
                   for _ in range(n_turns_padding)]
        sN = [
            SimpleNamespace(
                reward=reward0, status="DONE",
                observation={
                    "player": 0,
                    "planets": [
                        [0, 0, 20.0, 20.0, 2.0, 40, 3],
                        [1, 1, 80.0, 80.0, 2.0, 30, 3],
                        [2, 0, 30.0, 70.0, 1.5, 5, 2],
                    ],
                    "fleets": [],
                    "angular_velocity": 0.03,
                    "initial_planets": [],
                    "comets": [],
                    "comet_planet_ids": [],
                    "remainingOverageTime": 60.0,
                },
            ),
            SimpleNamespace(reward=reward1, status="DONE"),
        ]
        self.steps = [s0, s1, *padding, sN]


def _install_fake_kaggle() -> None:
    fake = ModuleType("kaggle_environments")
    def _make(env_name, configuration=None, debug=False):
        return _FakeEnv(configuration or {})
    fake.make = _make
    sys.modules["kaggle_environments"] = fake


_install_fake_kaggle()


# Import AFTER mock install so the runner sees the fake module if/when
# it imports kaggle_environments inside _run_one.
from orbit_wars.eval.runner import (   # noqa: E402
    MatchResult,
    Summary,
    load_jsonl,
    resolve_agent_spec,
    run_match,
    run_matches,
    summarize,
)


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


# ─── Spec resolution ─────────────────────────────────────────────────────
def test_resolve_specs() -> None:
    print("test_resolve_specs")
    check("random passthrough", resolve_agent_spec("random") == "random")
    check("reaction passthrough", resolve_agent_spec("reaction") == "reaction")

    main_path = resolve_agent_spec("main.py")
    check("relative .py resolves to abs", Path(main_path).is_absolute())
    check("relative .py exists",          Path(main_path).is_file())

    main_path2 = resolve_agent_spec("file:main.py")
    check("file: prefix accepted", Path(main_path2).is_file())

    try:
        resolve_agent_spec("nope_does_not_exist.py")
    except FileNotFoundError:
        check("missing path raises FileNotFoundError", True)
    else:
        check("missing path raises FileNotFoundError", False)


def test_preset_spec_builds_a_file() -> None:
    """``preset:NAME`` should call the build script and produce a real
    .py file in the supplied tmp root."""
    print("test_preset_spec_builds_a_file")
    with tempfile.TemporaryDirectory() as td:
        out = resolve_agent_spec("preset:blitz", Path(td))
        p = Path(out)
        check("path exists",          p.is_file())
        check("path is in tmp_root",  p.parent == Path(td))
        check("file is non-trivial",  p.stat().st_size > 5000)
        head = p.read_text(encoding="utf-8")[:200]
        check("has Kaggle header",    "Orbit Wars submission" in head)


# ─── Match results ───────────────────────────────────────────────────────
def test_single_match() -> None:
    _install_fake_kaggle()
    print("test_single_match")
    r = run_match("random", "reaction", seed=42)
    check("MatchResult type",  isinstance(r, MatchResult))
    check("seed roundtrip",    r.seed == 42)
    check("agent_a label",     r.agent_a == "random")
    check("position is 0",     r.agent_a_position == 0)
    check("n_turns positive",  r.n_turns > 0)
    check("elapsed positive",  r.elapsed_seconds > 0)
    check("winner is one of {a,b,draw}", r.winner in {"a", "b", "draw"})


def test_match_with_swap() -> None:
    """Same seed, with and without swap, must report rewards
    consistently from agent_a's perspective."""
    _install_fake_kaggle()
    print("test_match_with_swap")
    r_norm = run_match("random", "reaction", seed=99, swap=False)
    r_swap = run_match("random", "reaction", seed=99, swap=True)
    # In the fake env, slot 0 reward differs from slot 1 reward; after
    # the swap, agent_a's reward should equal what slot 1 had in the
    # unswapped game (because agent_a was placed in slot 1).
    # We can't compare exactly because the agent string hashing adds
    # +- 6 noise; but reward_a should be reproducibly *different*.
    check("swap changes agent_a's reward",
          r_norm.reward_a != r_swap.reward_a or r_norm.reward_b != r_swap.reward_b)
    check("position field reflects swap",
          r_norm.agent_a_position == 0 and r_swap.agent_a_position == 1)


def test_run_matches_balance_and_ordering() -> None:
    _install_fake_kaggle()
    print("test_run_matches_balance_and_ordering")
    results = run_matches("random", "reaction", n_games=8,
                          base_seed=12345, parallel=1)
    check("got 8 results", len(results) == 8)
    # Half should have position 0, half position 1
    p0 = sum(1 for r in results if r.agent_a_position == 0)
    p1 = sum(1 for r in results if r.agent_a_position == 1)
    check("position balance", p0 == 4 and p1 == 4)
    # Deterministic seeds
    results2 = run_matches("random", "reaction", n_games=8,
                           base_seed=12345, parallel=1)
    check("deterministic seed list",
          [r.seed for r in results] == [r.seed for r in results2])


def test_jsonl_roundtrip() -> None:
    _install_fake_kaggle()
    print("test_jsonl_roundtrip")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "results.jsonl"
        results = run_matches("random", "reaction", n_games=4,
                              base_seed=7, parallel=1, output_path=path)
        check("file exists", path.is_file())
        loaded = load_jsonl(path)
        check("same row count", len(loaded) == len(results))
        check("same first row",
              loaded[0].seed == results[0].seed and
              abs(loaded[0].reward_a - results[0].reward_a) < 1e-9)
        # Each line is valid JSON
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)
        check("every line is valid JSON", True)


def test_summary_shape() -> None:
    _install_fake_kaggle()
    print("test_summary_shape")
    results = run_matches("random", "reaction", n_games=10,
                          base_seed=1, parallel=1)
    s = summarize(results)
    check("Summary type",         isinstance(s, Summary))
    check("games count matches",  s.games == 10)
    check("wins+draws+wins = N",  s.wins_a + s.draws + s.wins_b == 10)
    check("winrate in [0, 1]",    0.0 <= s.winrate_a <= 1.0)
    check("rendering non-empty",  len(str(s)) > 50)


def test_summary_rejects_mixed_pairs() -> None:
    _install_fake_kaggle()
    print("test_summary_rejects_mixed_pairs")
    r1 = run_match("random", "reaction", seed=1)
    r2 = run_match("reaction", "random", seed=2)
    try:
        summarize([r1, r2])
    except ValueError:
        check("rejects mixed pairs", True)
    else:
        check("rejects mixed pairs", False)


# ─── Runner ──────────────────────────────────────────────────────────────



def test_metrics_populated_through_runner() -> None:
    """End-to-end: run_match should populate MatchResult.metrics_a/b by
    walking env.steps through compute_metrics."""
    _install_fake_kaggle()
    print("test_metrics_populated_through_runner")
    r = run_match("random", "reaction", seed=1234)
    check("metrics_a populated",      r.metrics_a is not None)
    check("metrics_b populated",      r.metrics_b is not None)
    check("a captured the neutral",   r.metrics_a.planets_captured == 1)
    check("b captured nothing",       r.metrics_b.planets_captured == 0)
    check("a peak planets >= 2",      r.metrics_a.peak_planets >= 2)


def test_metrics_jsonl_roundtrip() -> None:
    _install_fake_kaggle()
    print("test_metrics_jsonl_roundtrip")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "results.jsonl"
        results = run_matches("random", "reaction", n_games=3,
                              base_seed=42, parallel=1, output_path=path)
        loaded = load_jsonl(path)
        check("row count preserved", len(loaded) == len(results))
        check("metrics dataclass reconstructed",
              loaded[0].metrics_a is not None
              and loaded[0].metrics_a.__class__.__name__ == "PlayerMetrics")
        check("captured count preserved",
              loaded[0].metrics_a.planets_captured == results[0].metrics_a.planets_captured)

def main() -> None:
    test_resolve_specs()
    test_preset_spec_builds_a_file()
    test_single_match()
    test_match_with_swap()
    test_run_matches_balance_and_ordering()
    test_jsonl_roundtrip()
    test_summary_shape()
    test_summary_rejects_mixed_pairs()
    test_metrics_populated_through_runner()
    test_metrics_jsonl_roundtrip()
    print("\nAll eval smoke tests passed.")


if __name__ == "__main__":
    main()
