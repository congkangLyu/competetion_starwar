"""Smoke test for orbit_wars.eval.tournament.

We rely on the same fake kaggle env that smoke_test_eval.py uses (no
network for pip in this sandbox). The fake env produces deterministic
rewards keyed on (seed, agent identities), so the tournament results
are reproducible and we can assert exact match counts, Elo deltas, and
leaderboard ordering.
"""

from __future__ import annotations

import csv
import json
import math
import sys
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ─── Fake kaggle_environments (re-uses the trick from smoke_test_eval) ───
class _FakeEnv:
    def __init__(self, configuration):
        self.configuration = configuration
        self._seed = int(configuration.get("seed", 0))
        self.steps: list = []

    def run(self, agents):
        # Reward signal blends seed + agent hash so swapping positions and
        # changing opponents both flip outcomes deterministically.
        # Importantly, the relative *strength* of an agent should show
        # through across many seeds: we encode that by adding a per-agent
        # bonus drawn from a small lookup.
        STRENGTH = {
            ALPHA: 30.0,
            BETA: 15.0,
            GAMMA: 0.0,
            "random": -10.0,
            "reaction": -5.0,
        }
        def strength(spec: str) -> float:
            for k, v in STRENGTH.items():
                if k in spec:
                    return v
            return 0.0
        # Base score + noise + strength
        s = self._seed
        noise0 = ((s * 7) % 17) - 8
        noise1 = ((s * 13) % 17) - 8
        r0 = strength(agents[0]) + noise0
        r1 = strength(agents[1]) + noise1
        self.steps = [
            None,
            [
                SimpleNamespace(reward=r0, status="DONE"),
                SimpleNamespace(reward=r1, status="DONE"),
            ],
        ]


def _install_fake_kaggle() -> None:
    fake = ModuleType("kaggle_environments")
    def _make(env_name, configuration=None, debug=False):
        return _FakeEnv(configuration or {})
    fake.make = _make
    sys.modules["kaggle_environments"] = fake


_install_fake_kaggle()


# Dummy agent files: resolve_agent_spec requires the path to exist,
# even though the fake env never executes them. Place them at known
# names whose substring shows up in the FakeEnv strength table.
import tempfile
_TMP = Path(tempfile.mkdtemp(prefix='ow_tourn_test_'))
for _name in ['alpha', 'beta', 'gamma']:
    (_TMP / f'{_name}.py').write_text('def agent(obs):\n    return []\n')
ALPHA = str(_TMP / 'alpha.py')
BETA  = str(_TMP / 'beta.py')
GAMMA = str(_TMP / 'gamma.py')
AGENTS3 = [ALPHA, BETA, GAMMA]


from orbit_wars.eval.tournament import (   # noqa: E402
    Tournament,
    compute_elo,
    expected_score,
    run_tournament,
)
from orbit_wars.eval.runner import MatchResult   # noqa: E402


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


# ─── Elo arithmetic ──────────────────────────────────────────────────────
def test_expected_score_known_values() -> None:
    print("test_expected_score_known_values")
    # Equal ratings -> 0.5 each
    check("equal ratings = 0.5", abs(expected_score(1500, 1500) - 0.5) < 1e-9)
    # 400-point gap -> 10x odds, ~0.909 for stronger
    check("400 gap = ~0.909",   abs(expected_score(1900, 1500) - 10/11) < 1e-9)
    check("200 gap = ~0.760",   abs(expected_score(1700, 1500) - 0.7597469) < 1e-5)


def test_compute_elo_one_win() -> None:
    print("test_compute_elo_one_win")
    # One game: equal-rated 'a' beats 'b'. Sa=1, Ea=0.5, delta = 32*0.5 = 16
    r = MatchResult(seed=1, agent_a="a", agent_b="b", agent_a_position=0,
                    reward_a=1.0, reward_b=0.0, n_turns=1, elapsed_seconds=0.0)
    elo = compute_elo([r], ["a", "b"], initial=1500.0, k_factor=32.0)
    check("a gains 16",  abs(elo["a"] - 1516.0) < 1e-9)
    check("b loses 16",  abs(elo["b"] - 1484.0) < 1e-9)
    check("zero-sum",    abs((elo["a"] + elo["b"]) - 3000.0) < 1e-9)


def test_compute_elo_draw() -> None:
    print("test_compute_elo_draw")
    r = MatchResult(seed=1, agent_a="a", agent_b="b", agent_a_position=0,
                    reward_a=0.0, reward_b=0.0, n_turns=1, elapsed_seconds=0.0)
    elo = compute_elo([r], ["a", "b"], initial=1500.0, k_factor=32.0)
    # Equal rated draw -> no change
    check("a unchanged on equal draw", abs(elo["a"] - 1500.0) < 1e-9)
    check("b unchanged on equal draw", abs(elo["b"] - 1500.0) < 1e-9)


# ─── Tournament structure ────────────────────────────────────────────────
def test_pair_count_and_match_count() -> None:
    """3 agents -> 3 unique pairs * n games each = 3n total matches."""
    _install_fake_kaggle()
    print("test_pair_count_and_match_count")
    t = run_tournament(
        agents=AGENTS3,
        n_games_per_pair=4,
        base_seed=1, parallel=1,
    )
    check("agent list preserved", t.agents == AGENTS3)
    check("3 pairs of results", len(t.pairings) == 3)
    check("4 matches per pair",
          all(len(rs) == 4 for rs in t.pairings.values()))
    check("12 total matches", len(t.results) == 12)


def test_winrate_matrix_symmetry() -> None:
    """``pw[a,b] + pw[b,a]`` should equal 1.0 within float tolerance."""
    _install_fake_kaggle()
    print("test_winrate_matrix_symmetry")
    t = run_tournament(
        agents=AGENTS3,
        n_games_per_pair=6, base_seed=42, parallel=1,
    )
    for a in t.agents:
        for b in t.agents:
            if a == b:
                continue
            wr_ab = t.pairwise_winrate.get((a, b))
            wr_ba = t.pairwise_winrate.get((b, a))
            check(f"wr({a},{b}) + wr({b},{a}) ~= 1",
                  abs((wr_ab + wr_ba) - 1.0) < 1e-9)


def test_strong_agent_wins() -> None:
    """The fake env's strength table makes alpha > beta > gamma; the
    final leaderboard should reflect that across enough games."""
    _install_fake_kaggle()
    print("test_strong_agent_wins")
    t = run_tournament(
        agents=AGENTS3,
        n_games_per_pair=20, base_seed=123, parallel=1,
    )
    order = [name for name, *_ in t.leaderboard()]
    check("alpha is top",      "alpha" in order[0])
    check("gamma is bottom",   "gamma" in order[-1])
    # alpha vs gamma should be very lopsided
    wr = t.pairwise_winrate[(ALPHA, GAMMA)]
    check("alpha sweeps gamma",  wr >= 0.9)


def test_deterministic_with_seed() -> None:
    _install_fake_kaggle()
    print("test_deterministic_with_seed")
    t1 = run_tournament(AGENTS3, n_games_per_pair=4,
                        base_seed=7, parallel=1)
    t2 = run_tournament(AGENTS3, n_games_per_pair=4,
                        base_seed=7, parallel=1)
    seeds1 = sorted(r.seed for r in t1.results)
    seeds2 = sorted(r.seed for r in t2.results)
    check("seed lists identical", seeds1 == seeds2)
    check("Elo identical",        t1.elo == t2.elo)


def test_rejects_duplicate_agents() -> None:
    _install_fake_kaggle()
    print("test_rejects_duplicate_agents")
    try:
        run_tournament([ALPHA, ALPHA], n_games_per_pair=2,
                       base_seed=0, parallel=1)
    except ValueError:
        check("duplicate specs rejected", True)
    else:
        check("duplicate specs rejected", False)


def test_too_few_agents() -> None:
    _install_fake_kaggle()
    print("test_too_few_agents")
    try:
        run_tournament([ALPHA], n_games_per_pair=2,
                       base_seed=0, parallel=1)
    except ValueError:
        check("singleton rejected", True)
    else:
        check("singleton rejected", False)


def test_leaderboard_counts() -> None:
    """Sum of (wins, draws, losses) per agent must equal that agent's
    games column, and must equal (N-1) * n_games_per_pair."""
    _install_fake_kaggle()
    print("test_leaderboard_counts")
    t = run_tournament(AGENTS3, n_games_per_pair=10,
                       base_seed=11, parallel=1)
    expected_games = (3 - 1) * 10
    for name, elo, games, wins, draws, losses in t.leaderboard():
        check(f"{name}: games == (N-1)*per_pair", games == expected_games)
        check(f"{name}: W+D+L == games", wins + draws + losses == games)


def test_output_artifacts() -> None:
    _install_fake_kaggle()
    print("test_output_artifacts")
    with tempfile.TemporaryDirectory() as td:
        t = run_tournament(AGENTS3, n_games_per_pair=4,
                           base_seed=99, parallel=1, output_dir=td)
        td = Path(td)
        check("matches.jsonl exists",    (td / "matches.jsonl").is_file())
        check("leaderboard.csv exists",  (td / "leaderboard.csv").is_file())
        check("tournament.json exists",  (td / "tournament.json").is_file())
        # Every JSONL line parses
        for line in (td / "matches.jsonl").read_text(encoding="utf-8").splitlines():
            json.loads(line)
        check("jsonl is valid",          True)
        # CSV has the right rows
        with (td / "leaderboard.csv").open() as f:
            rows = list(csv.DictReader(f))
        check("CSV has 3 rows",          len(rows) == 3)
        check("CSV has agent column",    "agent" in rows[0])
        check("CSV has elo column",      "elo" in rows[0])
        check("Elo values float-parse",
              all(float(r["elo"]) > 0 for r in rows))
        # JSON summary is loadable
        summary = json.loads((td / "tournament.json").read_text(encoding="utf-8"))
        check("JSON summary has leaderboard", "leaderboard" in summary)
        check("JSON summary has pairwise",    "pairwise_winrate" in summary)


def test_text_renderers() -> None:
    _install_fake_kaggle()
    print("test_text_renderers")
    t = run_tournament(AGENTS3, n_games_per_pair=4,
                       base_seed=33, parallel=1)
    lb = t.leaderboard_text()
    check("leaderboard mentions alpha", ALPHA in lb)
    check("leaderboard has 'elo'",      "elo" in lb)
    mat = t.winrate_matrix_text()
    check("matrix mentions all agents",
          all(a in mat for a in AGENTS3))
    check("matrix marks diagonal with --", "--" in mat)


# ─── Runner ──────────────────────────────────────────────────────────────
def main() -> None:
    test_expected_score_known_values()
    test_compute_elo_one_win()
    test_compute_elo_draw()
    test_pair_count_and_match_count()
    test_winrate_matrix_symmetry()
    test_strong_agent_wins()
    test_deterministic_with_seed()
    test_rejects_duplicate_agents()
    test_too_few_agents()
    test_leaderboard_counts()
    test_output_artifacts()
    test_text_renderers()
    print("\nAll tournament smoke tests passed.")


if __name__ == "__main__":
    main()
