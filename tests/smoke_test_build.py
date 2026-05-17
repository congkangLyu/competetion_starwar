"""Smoke test for tools/build_submission.py.

For each preset:
  1. Build it via tools/build_submission.py to a tmp file.
  2. Import the built file. Verify it exposes agent(obs) -> list.
  3. Run several turns on a sample obs. Verify shape.

Plus the critical parity test:
  - Build blitz preset and compare its outputs (move-by-move, across
    several distinct observations and turn counts) against the
    hand-maintained `main.py` (which is currently the source-of-truth
    blitz submission). They MUST be byte-equivalent: if they aren't,
    the build script silently regressed our actual Kaggle submission.
"""

from __future__ import annotations

import importlib.util
import math
import subprocess
import sys
import tempfile
from collections import namedtuple
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _install_kaggle_stub() -> None:
    if "kaggle_environments.envs.orbit_wars.orbit_wars" in sys.modules:
        return
    fake = ModuleType("kaggle_environments.envs.orbit_wars.orbit_wars")
    fake.Planet = namedtuple("Planet", "id owner x y radius ships production")
    fake.Fleet = namedtuple("Fleet", "id owner x y angle from_planet_id ships")
    fake.CENTER = (50.0, 50.0)
    fake.ROTATION_RADIUS_LIMIT = 50.0
    for name in (
        "kaggle_environments",
        "kaggle_environments.envs",
        "kaggle_environments.envs.orbit_wars",
    ):
        sys.modules.setdefault(name, ModuleType(name))
    sys.modules["kaggle_environments.envs.orbit_wars.orbit_wars"] = fake


_install_kaggle_stub()


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


# ──────────────────────────────────────────────────────────────────────────
# Sample observations -- distinct shapes to exercise different code paths
# ──────────────────────────────────────────────────────────────────────────
def obs_two_planets(player: int = 0) -> dict:
    return {
        "player": player,
        "planets": [
            [0, 0, 20.0, 20.0, 2.0, 100, 3],
            [1, 1, 80.0, 80.0, 2.0, 50, 4],
            [2, -1, 30.0, 70.0, 1.5, 10, 2],
            [3, -1, 70.0, 30.0, 1.5, 8, 2],
        ],
        "fleets": [
            [99, 1, 30.0, 30.0, math.atan2(-10, -10), 1, 15],
        ],
        "angular_velocity": 0.03,
        "initial_planets": [
            [0, 0, 20.0, 20.0, 2.0, 100, 3],
            [1, 1, 80.0, 80.0, 2.0, 50, 4],
            [2, -1, 30.0, 70.0, 1.5, 10, 2],
            [3, -1, 70.0, 30.0, 1.5, 8, 2],
        ],
        "comets": [],
        "comet_planet_ids": [],
        "remainingOverageTime": 60.0,
    }


def obs_dense() -> dict:
    """A more populated mid-game obs with multiple my planets and fleets."""
    return {
        "player": 0,
        "planets": [
            [0, 0, 15.0, 15.0, 2.0, 80, 3],
            [1, 0, 25.0, 65.0, 1.8, 40, 2],
            [2, 1, 85.0, 85.0, 2.5, 120, 4],
            [3, 1, 75.0, 35.0, 1.8, 25, 2],
            [4, -1, 50.0, 90.0, 1.5, 6, 1],
            [5, -1, 90.0, 50.0, 1.5, 9, 2],
            [6, -1, 35.0, 35.0, 1.2, 4, 1],
        ],
        "fleets": [
            [100, 0, 16.0, 18.0, 0.3, 0, 5],
            [101, 1, 70.0, 80.0, math.pi, 2, 18],
            [102, 1, 80.0, 40.0, math.atan2(-20, -60), 3, 8],
        ],
        "angular_velocity": 0.04,
        "initial_planets": [
            [0, 0, 15.0, 15.0, 2.0, 80, 3],
            [1, 0, 25.0, 65.0, 1.8, 40, 2],
            [2, 1, 85.0, 85.0, 2.5, 120, 4],
            [3, 1, 75.0, 35.0, 1.8, 25, 2],
            [4, -1, 50.0, 90.0, 1.5, 6, 1],
            [5, -1, 90.0, 50.0, 1.5, 9, 2],
            [6, -1, 35.0, 35.0, 1.2, 4, 1],
        ],
        "comets": [],
        "comet_planet_ids": [],
        "remainingOverageTime": 55.0,
    }


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────
def import_built(path: Path, mod_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _moves_equal(a, b) -> bool:
    if len(a) != len(b):
        return False
    a_sorted = sorted(a)
    b_sorted = sorted(b)
    return all(
        x[0] == y[0] and abs(x[1] - y[1]) < 1e-12 and x[2] == y[2]
        for x, y in zip(a_sorted, b_sorted)
    )


def build_to_tmp(preset: str, tmp: Path) -> Path:
    out = tmp / f"{preset}.py"
    result = subprocess.run(
        [sys.executable, "tools/build_submission.py", preset, "-o", str(out), "--no-check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"build of preset '{preset}' failed")
    return out


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────
def test_build_all_presets() -> None:
    print("test_build_all_presets")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for preset in ["blitz", "sniper", "sentinel"]:
            out = build_to_tmp(preset, tmp)
            check(f"{preset}.py exists", out.is_file())
            check(f"{preset}.py non-empty", out.stat().st_size > 1000)
            mod = import_built(out, f"built_{preset}")
            check(f"{preset} exposes agent()", callable(getattr(mod, "agent", None)))
            result = mod.agent(obs_two_planets())
            check(f"{preset} agent() returns list", isinstance(result, list))


def test_built_header_carries_metadata() -> None:
    print("test_built_header_carries_metadata")
    with tempfile.TemporaryDirectory() as td:
        out = build_to_tmp("blitz", Path(td))
        text = out.read_text(encoding="utf-8")
        check("header mentions preset", "preset: blitz" in text)
        check("header mentions AUTO-GENERATED", "AUTO-GENERATED" in text)
        check("header has Built timestamp", "Built:" in text)
        check("header has Commit", "Commit:" in text)
        check("inlines geometry.py", "inlined from orbit_wars/core/geometry.py" in text)
        check("inlines state.py", "inlined from orbit_wars/core/state.py" in text)
        check("inlines base.py", "inlined from orbit_wars/agents/base.py" in text)
        check("inlines heuristic.py", "inlined from orbit_wars/agents/heuristic.py" in text)
        check("has Kaggle entrypoint", "def agent(obs):" in text)
        import re as _re
        leftover = _re.findall(r"^\s*(from|import)\s+orbit_wars", text, flags=_re.MULTILINE)
        check("no leftover orbit_wars import statement", leftover == [])


def test_blitz_parity_against_handmaintained_main() -> None:
    """The new built blitz main.py must produce identical moves to the
    currently-shipped (hand-maintained) main.py across a battery of
    observations. This is the critical "we did not regress Kaggle" check."""
    print("test_blitz_parity_against_handmaintained_main")

    with tempfile.TemporaryDirectory() as td:
        new_path = build_to_tmp("blitz", Path(td))
        new_mod = import_built(new_path, "built_blitz")
        old_mod = import_built(ROOT / "main.py", "old_main")

        # Both agents are stateful (step counter inside the closure). Drive
        # them in lockstep on the same observation sequence and verify
        # each turn's moves are identical.
        observations = []
        # Warmup: 4 copies of the dense obs (covers WAIT_TURNS + a few real turns)
        for _ in range(4):
            observations.append(obs_dense())
        # Then different obs to make sure parity holds across shapes
        for player in (0, 1):
            for _ in range(3):
                observations.append(obs_two_planets(player=player))

        for i, obs in enumerate(observations):
            new_moves = new_mod.agent(obs)
            old_moves = old_mod.agent(obs)
            same = _moves_equal(new_moves, old_moves)
            if not same:
                print(f"    turn {i}: NEW={sorted(new_moves)}")
                print(f"    turn {i}: OLD={sorted(old_moves)}")
            check(f"turn {i} matches", same)


def main() -> None:
    test_build_all_presets()
    test_built_header_carries_metadata()
    test_blitz_parity_against_handmaintained_main()
    print("\nAll build smoke tests passed.")


if __name__ == "__main__":
    main()
