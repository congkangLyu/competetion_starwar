# Orbit Wars — Agent Workshop

> [中文版](README.zh-CN.md)

Research infrastructure for the Kaggle [Orbit Wars](https://www.kaggle.com/competitions/orbit-wars)
competition. The repo is structured as a small Python package
(`orbit_wars/`) plus a build toolchain that turns a YAML strategy into
the single-file `main.py` Kaggle expects.

**You write strategies (YAML or Agent subclass), the toolchain handles:**
build, smoke check, parallel evaluation, Elo tournament, replay
visualisation, and submission.

- **Game rules & physics**: see [GAME_RULES.md](GAME_RULES.md)
- **Kaggle CLI cheatsheet**: see [agents.md](agents.md)
- **Notebook references**: see `information/`

---

## At a glance

```
configs/blitz.yaml ──► build_submission ──► main.py ──► kaggle submit
                                                │
orbit_wars/agents/ ──┐                          │
orbit_wars/core/    ──┤── inlined into ─────────┘
orbit_wars/eval/    ──┤
orbit_wars/analysis/──┘   (eval/analysis stay local; never shipped)

7 smoke test suites · 237 standalone checks · 61 pytest functions
```

| Layer | What's in it | Ships to Kaggle? |
|---|---|---|
| `orbit_wars/core/` | `GameState`, `Planet`, `Fleet`, `Move`, geometry primitives | ✅ |
| `orbit_wars/agents/` | `Agent` ABC, `SniperAgent`, `HeuristicAgent` | ✅ |
| `orbit_wars/eval/` | Parallel runner, metrics, tournament, Elo | ❌ |
| `orbit_wars/analysis/` | Replay loader, SVG/HTML visualisation | ❌ |
| `tools/` | CLI entrypoints (build, eval, tournament, viz) | ❌ |
| `configs/` | YAML strategy presets (single source of truth) | inlined into main.py |
| `tests/` | 7 smoke test suites (pytest-compatible) | ❌ |

---

## Quick start

```bash
# 1. Install
pip install kaggle-environments PyYAML pytest

# 2. Verify everything works
make test          # runs 7 smoke suites; expects 237 [OK ] lines
make pytest        # same tests under pytest collector

# 3. Build the current submission file
make build PRESET=blitz       # writes main.py from configs/blitz.yaml

# 4. Play 6 games against the kaggle random agent
python tools/eval.py main.py random -n 6
```

If you don't have `make` on Windows, use the direct `python ...` commands
shown in the [CLI reference](#cli-reference) below.

---

## Architecture

### Layered view

```
┌─────────────────────────────────────────────────────────────────────┐
│                CLI TOOLS  (tools/*.py)                              │
│  build_submission · eval · tournament · viz · replay                │
└───────┬─────────────────┬──────────────┬───────────────┬────────────┘
        │                 │              │               │
        ▼                 ▼              ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              DEV INFRA  (eval/, analysis/)                          │
│  runner · metrics · tournament · replay loader · SVG/HTML viz       │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ uses (one-way; never reverse)
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│           SHIPPABLE CODE  (agents/, core/)                          │
│  Agent ABC · SniperAgent · HeuristicAgent · GameState · geometry    │
└─────────────────────────────────────────────────────────────────────┘
                      │
                      ▼
                Python stdlib + kaggle_environments (runtime only)
```

**Critical invariant**: `core/` and `agents/` never import `eval/`,
`analysis/`, or `tools/`. If they did, the build script could not
inline them into `main.py`. This is enforced by
`tests/smoke_test_build.py`.

### Submission data flow

```
configs/blitz.yaml ─┐
core/geometry.py ───┤
core/state.py ──────┼──► tools/build_submission.py ──► main.py ──► kaggle
agents/base.py ─────┤        (inline + smoke check)     (single file)
agents/heuristic.py ┘
```

The built `main.py` is byte-equivalent (move-for-move) to the
hand-maintained `main.py` on the same observations — guarded by 10
turns of parity tests in `smoke_test_build.py`.

### Evaluation data flow

```
agent specs ──► run_matches ──► [kaggle env in worker] ──► env.steps
("preset:blitz"      │                                          │
 "random"            │                                          ▼
 "file:main.py")     │                              compute_metrics()
                     ▼                                          │
              MatchResult (one per game) ◄─── metrics_a/b ──────┘
                     │
       ┌─────────────┼─────────────────┐
       ▼             ▼                 ▼
   results.jsonl  Summary text    Tournament + Elo
```

---

## Project layout

```
competetion_starwar/
│
├── README.md                    # this file
├── GAME_RULES.md                # the official orbit_wars rules
├── agents.md                    # kaggle CLI cheatsheet (submit/replay/logs)
├── Makefile                     # shortcuts; see `make help`
├── pytest.ini                   # pytest discovery + addopts
├── requirements.txt             # runtime + dev deps
├── .gitignore
│
├── main.py                      # CURRENT KAGGLE SUBMISSION (rebuild via make)
│
├── configs/                     # ── single source of truth for strategies ──
│   ├── blitz.yaml               # 72.2% baseline (default submission)
│   ├── sentinel.yaml            # blitz + defensive reinforcement
│   └── sniper.yaml              # naive nearest-planet baseline
├── search_spaces/               # parameter-search spaces for tools/search_params.py
│   ├── ow_proto_core.yaml       # starter search space for the ow_proto champion
│   └── peaking_core.yaml        # starter search space for the peaking preset
│
├── orbit_wars/                  # ── the package ──
│   ├── __init__.py              # re-export of common symbols
│   ├── core/                    # SHIPPABLE: data + physics primitives
│   │   ├── state.py             # GameState, Planet, Fleet, Move, CometGroup
│   │   └── geometry.py          # fleet_speed, seg_hits_sun, orbital_position
│   ├── agents/                  # SHIPPABLE: agent implementations
│   │   ├── base.py              # Agent ABC, Decision, make_kaggle_agent
│   │   ├── sniper.py            # SniperAgent (baseline)
│   │   └── heuristic.py         # HeuristicAgent + HeuristicConfig
│   ├── eval/                    # DEV ONLY: evaluation harness
│   │   ├── runner.py            # MatchResult, run_match, run_matches
│   │   ├── metrics.py           # PlayerMetrics, compute_metrics
│   │   └── tournament.py        # Tournament, Elo, leaderboard
│   └── analysis/                # DEV ONLY: replay + visualisation
│       ├── replay.py            # load_kaggle_replay, extract_states
│       └── viz.py               # render_frame_svg, render_replay_html
│
├── tools/                       # CLI entrypoints (scripts, not importable)
│   ├── build_submission.py      # YAML preset -> single-file main.py
│   ├── eval.py                  # two-agent local evaluation
│   ├── search_params.py         # generate + evaluate parameter variants
│   ├── tournament.py            # N-agent round-robin + Elo
│   ├── viz.py                   # replay JSON -> interactive HTML
│   └── replay.py                # ad-hoc replay helpers
│
├── tests/                       # smoke suites (also pytest-compatible)
│   ├── conftest.py              # autouse kaggle_environments stub
│   ├── smoke_test_core.py
│   ├── smoke_test_agents.py
│   ├── smoke_test_build.py
│   ├── smoke_test_eval.py
│   ├── smoke_test_metrics.py
│   ├── smoke_test_search_params.py
│   ├── smoke_test_viz.py
│   └── smoke_test_tournament.py
│
├── agents/                      # legacy code, kept for parity tests
│   ├── sniper.py                # old standalone sniper (baseline)
│   └── blitz.py                 # old standalone blitz (still byte-equivalent)
│
├── evaluate.py                  # legacy script; superseded by tools/eval.py
└── information/                 # original notebooks (EDA, hybrid agent, etc.)
    ├── getting-started.ipynb
    ├── orbit-wars-complete-guide-eda-agents-submission.ipynb
    └── orbit-wars-tamrazov-ykhnkf-hybrid.ipynb
```

---

## Common workflows

### Run all tests (sanity check)

```bash
make test            # 7 standalone smoke suites in sequence
make pytest          # pytest collector, parallelisable, nicer output
make pytest-verbose  # add -v -s flags
```

### Tweak strategy parameters

```bash
# 1. Copy an existing preset
cp configs/blitz.yaml configs/aggressive.yaml

# 2. Edit weights (use any text editor)
nano configs/aggressive.yaml
#    e.g. enemy_bonus: 1.0  ->  2.0
#         attack_buffer: 1.0 -> 1.2

# 3. Build and smoke-check
python tools/build_submission.py aggressive -o _build/aggressive.py

# 4. Compare to baseline over 20 games (4 parallel workers)
python tools/eval.py preset:aggressive preset:blitz -n 20 -p 4 -o cmp.jsonl
```

The JSONL file has one row per game with reward, winner, and full
`PlayerMetrics` (planets captured/lost, ships lost to sun, peak
planets, etc.). Pipe through `jq` or load in pandas for analysis.

### Search strategy parameters

Use `tools/search_params.py` when manual YAML tweaking gets slow. It
starts from a base preset, samples or enumerates a search space, builds
each candidate into an isolated file, evaluates it, and writes a ranked
result table.

```bash
python tools/search_params.py configs/ow_proto.yaml search_spaces/ow_proto_core.yaml \
  --opponent preset:ow_proto \
  --mode random \
  --samples 24 \
  --games 10 \
  -p 4 \
  --seed 20260526 \
  --out runs/search-ow-proto-core
```

The output directory contains `base.yaml`, `search_space.yaml`,
generated candidate YAMLs, built candidate files, per-candidate match
JSONL, `results.csv`, `results.json`, `best.yaml`, and a `top/` folder
with the best candidate YAMLs. Use `--mode grid` for a full cartesian
search, or `--dry-run` to generate candidates without running games.

### Run a round-robin tournament

```bash
python tools/tournament.py \
  preset:blitz preset:sentinel preset:sniper preset:aggressive random \
  -n 10 -p 2 --seed 42 -o tourneys/run-2025-05-17
```

Output to stdout: leaderboard sorted by Elo + pairwise winrate matrix.
Output directory: `matches.jsonl`, `leaderboard.csv`,
`tournament.json` (machine-readable summary).

### Visualise a finished game

First dump the replay (in Python):

```python
from pathlib import Path
from kaggle_environments import make
env = make("orbit_wars", configuration={"seed": 7}, debug=False)
env.run(["main.py", "random"])
Path("replays").mkdir(exist_ok=True)
Path("replays/g7.json").write_text(env.toJSON())
```

Then render:

```bash
python tools/viz.py replays/g7.json -o replay.html
# Open replay.html in any browser; use the slider / play button
```

To overlay an agent's decision log (intent rays), pass
`--decisions logs/p0.jsonl` where `p0.jsonl` was produced by
`decisions_to_jsonl(agent.decisions)`.

---

## Submitting to Kaggle

### One-time setup

1. Install the Kaggle CLI: `pip install kaggle`
2. Generate an API token at https://www.kaggle.com/settings → "Create new
   API token". Place the downloaded `kaggle.json` at:
   - Linux/Mac: `~/.kaggle/kaggle.json`
   - Windows:   `C:\Users\<you>\.kaggle\kaggle.json`
3. On the competition page, click "Join Competition" and accept the
   rules: https://www.kaggle.com/competitions/orbit-wars
4. Verify: `kaggle competitions list --group entered` should show
   orbit-wars.

### Submit

```bash
# 1. Rebuild main.py from the YAML preset you want to ship
make build PRESET=blitz
#  → writes main.py, with git commit hash + UTC timestamp in the header
#  → runs a 5-turn smoke check before declaring success

# 2. Submit
kaggle competitions submit orbit-wars -f main.py -m "blitz preset, commit abc123"

# 3. Monitor
kaggle competitions submissions orbit-wars
```

For multi-file bundles (rare — our build inlines everything into one
file), tar.gz with `main.py` at the root then submit the tarball:

```bash
tar -czf sub.tar.gz main.py extra_helper.py model_weights.pkl
kaggle competitions submit orbit-wars -f sub.tar.gz -m "..."
```

### Inspect submissions

```bash
# List your submissions (note the SUBMISSION_ID column)
kaggle competitions submissions orbit-wars

# Episodes the submission played
kaggle competitions episodes <SUBMISSION_ID>

# Download a single replay JSON + agent log
kaggle competitions replay <EPISODE_ID> -p ./replays
kaggle competitions logs <EPISODE_ID> 0 -p ./logs   # 0 = first agent
```

Then `python tools/viz.py replays/<file>.json -o out.html` to inspect
visually.

### Check the leaderboard

```bash
kaggle competitions leaderboard orbit-wars -s
```

---

## Adding a new agent

Subclass `Agent` and implement `act(state) -> list[Move]`:

```python
# orbit_wars/agents/my_idea.py
from orbit_wars.agents.base import Agent
from orbit_wars.core.geometry import angle_to, dist, fleet_speed, seg_hits_sun
from orbit_wars.core.state import GameState, Move

class MyAgent(Agent):
    """One-line description of the strategy."""

    name = "my_idea"

    def act(self, state: GameState) -> list[Move]:
        moves: list[Move] = []
        for src in state.my_planets:
            # ... your strategy ...
            move = Move(src.id, angle_to(src.x, src.y, tgt.x, tgt.y), ships)
            moves.append(move)
            self.log(move, reason="my_reason", **extra_meta)
        return moves
```

You get for free:
- `state.my_planets`, `state.enemy_planets`, `state.neutral_planets`,
  `state.planet_by_id`, `state.my_fleets`, `state.enemy_fleets`,
  `state.comet_planet_ids`
- `state.angular_velocity` + `state.initial_planets` for orbital
  prediction (see `orbit_wars.core.geometry.orbital_position`)
- `state.step`, `state.remaining_time`
- Automatic decision log via `self.log(move, reason=..., **meta)`
- Lifecycle hooks: `on_game_start(state)`, `on_game_end(state, reward)`
- `reset()` for between-game state isolation (called by the runner)

Make it submittable by:

1. Registering the class in `tools/build_submission.py`:
   ```python
   AGENT_MODULES: dict[str, list[Path]] = {
       "SniperAgent":    [ROOT / "orbit_wars" / "agents" / "sniper.py"],
       "HeuristicAgent": [ROOT / "orbit_wars" / "agents" / "heuristic.py"],
       "MyAgent":        [ROOT / "orbit_wars" / "agents" / "my_idea.py"],   # ← add
   }
   ```
2. Adding a render branch in `render_adapter()` for instantiation kwargs
   (only needed if your agent takes constructor args).
3. Creating a YAML preset (see next section).
4. Re-exporting from `orbit_wars/agents/__init__.py` (so tests/imports
   work).

## Adding a new strategy preset

```yaml
# configs/my_idea.yaml
name: my_idea
description: |
  Brief description shown in the built main.py docstring.

agent: MyAgent          # must be a key in tools/build_submission.py
                        # AGENT_MODULES

config:                 # passed as **kwargs to MyAgent(...)
  # If your agent takes a dataclass config like HeuristicConfig:
  some_weight: 1.5
  threshold:   10
```

Then:

```bash
python tools/build_submission.py my_idea -o _build/my_idea.py
python tools/eval.py preset:my_idea preset:blitz -n 50 -p 8 -o cmp.jsonl
```

---

## CLI reference

### `tools/build_submission.py`

| Flag | Default | Meaning |
|---|---|---|
| `preset` (positional) | — | YAML name under `configs/` |
| `-o, --output` | `main.py` | Output path (any file, in or out of repo) |
| `--no-check` | off | Skip the 5-turn import smoke check |

### `tools/eval.py`

| Flag | Default | Meaning |
|---|---|---|
| `agent_a agent_b` | — | Two agent specs (see below) |
| `-n, --games` | 6 | Total games (split evenly between positions) |
| `-p, --parallel` | 1 | Process pool size |
| `--seed` | None | Base seed for deterministic per-game seeds |
| `--no-balance` | off | Skip position swap |
| `--episode-steps` | None | Override kaggle `episodeSteps` (default 500) |
| `-o, --output` | None | Write per-match JSONL here |

### `tools/search_params.py`

| Flag | Default | Meaning |
|---|---|---|
| `base_config search_space` | — | Base preset YAML and parameter-space YAML |
| `--opponent` | `preset:ow_proto` | Opponent spec used for candidate evaluation |
| `--mode` | `random` | Candidate selection mode: `random` or `grid` |
| `--samples` | None | Candidate count for random mode; grid prefix length for grid mode |
| `--games` | 6 | Games per candidate |
| `-p, --parallel` | 1 | Process pool size for each candidate evaluation |
| `--seed` | None | Seed for candidate sampling and match seeds |
| `--episode-steps` | None | Optional kaggle `episodeSteps` override for rough screens |
| `--no-balance` | off | Skip position swap |
| `--out` | timestamped `runs/` dir | Output directory |
| `--prefix` | derived from base | Candidate name prefix |
| `--top-k` | 5 | Copy top K candidate YAMLs into `top/` |
| `--dry-run` | off | Generate candidate YAML/Python files without evaluation |

### `tools/tournament.py`

| Flag | Default | Meaning |
|---|---|---|
| `agents` (positional, ≥2) | — | List of distinct agent specs |
| `-n, --games-per-pair` | 6 | Games each unordered pair plays |
| `-p, --parallel` | 1 | Process pool size |
| `--seed` | None | Base seed |
| `--no-balance` | off | Skip position swap |
| `--k` | 32 | Elo K-factor |
| `--initial-elo` | 1500 | Starting Elo |
| `-o, --output-dir` | None | Write matches.jsonl + leaderboard.csv + tournament.json here |

### `tools/viz.py`

| Flag | Default | Meaning |
|---|---|---|
| `replay` (positional) | — | Kaggle replay JSON path |
| `-o, --output` | `replay.html` | Output HTML path |
| `--player` | 0 | Which player view to use (cosmetic only) |
| `--decisions` | None | Decisions JSONL to overlay |
| `--title` | filename | HTML title |
| `--width` | 640 | SVG pixel width |

### Agent specs accepted by `eval.py` / `tournament.py`

| Spec | Meaning |
|---|---|
| `preset:NAME` | Build `configs/NAME.yaml` to a tmpfile, use that |
| `file:PATH` | Use the .py file at PATH directly |
| `PATH` (e.g. `main.py`) | Same as `file:PATH` if it exists |
| `random` | Kaggle builtin random agent |
| `reaction` | Kaggle builtin reactive agent |

---

## Makefile targets

```text
make help              show this list
make test              run all 7 standalone smoke suites
make test-core         run one suite (replace core with any of:
                          core agents build eval metrics search viz tournament)
make pytest            run every smoke_test_*.py through pytest
make pytest-verbose    pytest with -v -s

make build PRESET=blitz       build main.py from a YAML preset
make build-all                build every preset under _build/
make submit-prep PRESET=blitz build main.py and print the kaggle command

make eval ARGS="preset:blitz random -n 20 -p 4 -o out.jsonl"
                              shortcut to tools/eval.py

make clean             remove _build/ and __pycache__/
```

On Windows without `make`, the right-hand-side commands work as-is.

---

## Test suite

| File | Standalone checks | pytest functions | What it covers |
|---|---:|---:|---|
| `smoke_test_core.py` | 41 | 10 | `GameState` parsing, geometry primitives |
| `smoke_test_agents.py` | 28 |  9 | `Agent` ABC, SniperAgent + blitz parity vs old |
| `smoke_test_build.py` | 32 |  3 | YAML → main.py, built blitz vs old main.py parity |
| `smoke_test_eval.py` | 40 | 10 | Runner, JSONL roundtrip, metrics integration |
| `smoke_test_metrics.py` | 20 |  7 | Pure metrics on synthetic env.steps |
| `smoke_test_search_params.py` | 24 |  5 | Parameter search generation, ranking, CLI dry-run |
| `smoke_test_viz.py` | 31 | 10 | SVG/HTML renderers, replay loader, CLI |
| `smoke_test_tournament.py` | 45 | 12 | Round-robin, pairwise WR, Elo |
| **Total** | **261** | **66** | |

Notes:
- The "standalone check" column counts individual `[OK ]` lines — those
  are the actual assertions, useful for grepping failures.
- pytest treats each `def test_*()` as one test; many tests bundle
  several `[OK ]` checks.
- Both runners must stay green. The standalone form does not require
  pytest; the pytest form needs `pip install pytest`.

Run a subset:

```bash
# Just one suite
python tests/smoke_test_metrics.py

# Or via pytest
pytest tests/smoke_test_metrics.py
pytest tests/smoke_test_metrics.py::test_planet_capture_and_loss
pytest -k parity     # all tests with 'parity' in the name
```

---

## Architecture invariants (the three promises)

The infrastructure makes three promises that the test suite enforces.
Breaking any of them is the most common source of silent regressions:

1. **One-way dependency**: `core/` and `agents/` never import from
   `eval/`, `analysis/`, or `tools/`. Enforced by
   `smoke_test_build.py::test_built_header_carries_metadata` (the
   "no leftover orbit_wars import" check) — if you accidentally add
   such an import, the built `main.py` would carry an unresolvable
   `from orbit_wars...` line and the test fails.
2. **Behaviour parity**: any refactor of `agents/heuristic.py` must
   keep `smoke_test_build.py::test_blitz_parity_against_handmaintained_main`
   green (10 turns of byte-identical moves vs the old `main.py`). This
   is the guardrail that lets you rewrite confidently without risking
   your Kaggle ranking.
3. **Single source of truth**: strategy parameters live only in
   `configs/*.yaml`. The dataclass defaults in `HeuristicConfig` exist
   to make the class usable without a config, but they are not the
   canonical strategy.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'orbit_wars'`

You're running from the wrong directory. All scripts assume you're in
the project root (the directory containing this README). Either `cd`
there or set `PYTHONPATH=.`.

### `ModuleNotFoundError: No module named 'kaggle_environments'`

`pip install kaggle-environments`. This is needed at runtime by
`tools/eval.py`, `tools/tournament.py`, and to actually play games.
Build / metrics / viz / unit tests don't need it (the test suite
provides a stub).

### `make pytest` shows fewer tests than expected

Make sure `pytest.ini` is being picked up (it has
`python_files = test_*.py smoke_test_*.py`). Without it pytest skips
the `smoke_test_*` filenames.

### Built `main.py` works locally but Kaggle says "Agent error"

Check the built file header — it contains the git commit hash and build
timestamp. Open `main.py` and search for `from orbit_wars` — if any
line matches, the strip-imports regex missed something. File an issue
or run `python tools/build_submission.py <preset>` and read the output
of the smoke check.

### `test_metrics_populated_through_runner` fails under pytest only

This used to happen because of `sys.modules` contamination between
smoke tests (each installs its own kaggle env stub at module level,
the last one wins). Already fixed by per-test stub re-install. If you
see it again after editing the smoke tests, make sure any test that
calls `run_match()` / `run_matches()` invokes the local
`_install_fake_kaggle()` at the top of its body.

### Windows: `make` not found

Either install make (`scoop install make` / `choco install make`) or
use the direct `python ...` commands listed in the
[CLI reference](#cli-reference) above. Every `make X` target is just
a one-liner wrapping a python command.

---

## Further reading

- [GAME_RULES.md](GAME_RULES.md) — full Orbit Wars rules: board,
  planets, comets, combat, scoring, observation format.
- [agents.md](agents.md) — additional kaggle CLI examples (submit,
  download replays, leaderboard).
- `information/getting-started.ipynb` — starter notebook from the
  competition.
- `information/orbit-wars-complete-guide-eda-agents-submission.ipynb`
  — EDA + 10-strategy round-robin notebook the blitz preset came
  from.
- `information/orbit-wars-tamrazov-ykhnkf-hybrid.ipynb` — a
  third-party hybrid agent reference.
