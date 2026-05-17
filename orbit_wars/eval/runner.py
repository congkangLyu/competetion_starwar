"""
Position-balanced, parallel evaluation runner for Orbit Wars agents.

Compared to the original top-level ``evaluate.py`` this module adds:

* **Preset specs**: ``agent_a="preset:blitz"`` builds the YAML preset on
  the fly and uses the bundled file. No more "copy blitz.py to main.py".
* **Parallel execution**: many games in parallel via
  :class:`~concurrent.futures.ProcessPoolExecutor`.
* **Determinism**: pass a base seed; per-game seeds are derived
  reproducibly.
* **Structured output**: each match is a :class:`MatchResult`
  dataclass; ``output_path`` writes one JSONL line per match for
  downstream analysis (pandas, jq, etc.).
* **Position balance**: by default half the games are played with
  ``agent_a`` in slot 0 and half in slot 1, so the starting-position
  bias is cancelled out.

The kaggle env import is deferred to inside the worker, so importing
this module never requires ``kaggle_environments`` to be installed. That
makes the public API and result types testable in environments without
the dependency.
"""

from __future__ import annotations

import concurrent.futures as cf
import dataclasses as _dc
import json
import random
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field

from orbit_wars.eval.metrics import PlayerMetrics, compute_metrics
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent.parent


# ─── Spec resolution ─────────────────────────────────────────────────────
KAGGLE_BUILTINS = {"random", "reaction"}


def resolve_agent_spec(spec: str, tmp_root: Path | None = None) -> str:
    """Resolve a user-facing spec into something the kaggle env accepts.

    Supported forms:
      ``"preset:NAME"``       build ``configs/NAME.yaml`` to ``tmp_root`` and
                              return the path to the built file.
      ``"file:PATH"``         strip the prefix; return absolute path.
      ``"PATH"``              if the path exists, return it absolute.
      ``"random"`` / ``"reaction"``  pass through (kaggle builtin agents).

    Raises :class:`FileNotFoundError` if the path does not resolve.
    """
    if spec in KAGGLE_BUILTINS:
        return spec
    if spec.startswith("preset:"):
        preset = spec[len("preset:") :]
        if tmp_root is None:
            tmp_root = Path(tempfile.mkdtemp(prefix="ow_eval_"))
        out_path = tmp_root / f"{preset}.py"
        subprocess.check_call(
            [
                sys.executable,
                str(ROOT / "tools" / "build_submission.py"),
                preset,
                "-o",
                str(out_path),
                "--no-check",
            ],
            cwd=ROOT,
        )
        return str(out_path)
    if spec.startswith("file:"):
        spec = spec[len("file:") :]
    p = Path(spec)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"agent spec '{spec}' not found")
    return str(p)


# ─── Result types ────────────────────────────────────────────────────────
@dataclass
class MatchResult:
    """One game's outcome, from ``agent_a``'s perspective."""

    seed: int
    agent_a: str
    agent_b: str
    agent_a_position: int     # 0 = slot 0, 1 = slot 1 (after a swap)
    reward_a: float
    reward_b: float
    n_turns: int
    elapsed_seconds: float
    status_a: str = "DONE"
    status_b: str = "DONE"
    metrics_a: PlayerMetrics | None = None
    metrics_b: PlayerMetrics | None = None

    @property
    def winner(self) -> str:
        """``'a'`` / ``'b'`` / ``'draw'``."""
        if self.reward_a > self.reward_b:
            return "a"
        if self.reward_b > self.reward_a:
            return "b"
        return "draw"

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class Summary:
    """Aggregate stats across many matches (same agent pair)."""

    agent_a: str
    agent_b: str
    games: int
    wins_a: int
    draws: int
    wins_b: int
    winrate_a: float
    mean_reward_diff: float
    mean_seconds: float
    p50_seconds: float

    def __str__(self) -> str:
        return (
            f"{self.agent_a}  vs  {self.agent_b}\n"
            f"  games:    {self.games}\n"
            f"  wins_a:   {self.wins_a}\n"
            f"  draws:    {self.draws}\n"
            f"  wins_b:   {self.wins_b}\n"
            f"  winrate:  {self.winrate_a:.1%}  (a's perspective; draws=0.5)\n"
            f"  mean dR:  {self.mean_reward_diff:+.2f}\n"
            f"  time:     mean {self.mean_seconds:.1f}s, p50 {self.p50_seconds:.1f}s"
        )


# ─── Worker entrypoint (one game, one process) ───────────────────────────
def _run_one(spec_args: dict) -> MatchResult:
    """Pickle-safe worker: resolve specs, run one game, return MatchResult.

    The kaggle env import is *inside* this function so module import of
    runner.py doesn't require kaggle_environments to be installed.
    """
    from kaggle_environments import make  # imported per-worker

    tmp_root = Path(tempfile.mkdtemp(prefix="ow_eval_w_"))
    resolved_a = resolve_agent_spec(spec_args["agent_a"], tmp_root)
    resolved_b = resolve_agent_spec(spec_args["agent_b"], tmp_root)

    seed = spec_args["seed"]
    swap = spec_args["swap"]
    config: dict = {"seed": int(seed)}
    if spec_args.get("episode_steps") is not None:
        config["episodeSteps"] = int(spec_args["episode_steps"])
    if spec_args.get("act_timeout") is not None:
        config["actTimeout"] = float(spec_args["act_timeout"])

    if swap:
        slot0, slot1 = resolved_b, resolved_a
    else:
        slot0, slot1 = resolved_a, resolved_b

    env = make("orbit_wars", configuration=config, debug=False)
    t0 = time.perf_counter()
    env.run([slot0, slot1])
    elapsed = time.perf_counter() - t0
    final = env.steps[-1]

    if swap:
        a, b = final[1], final[0]
    else:
        a, b = final[0], final[1]

    # Derived metrics (observer-side; never breaks the run if a step
    # row is missing fields -- compute_metrics is intentionally robust)
    try:
        m_slot0 = compute_metrics(env.steps, 0)
        m_slot1 = compute_metrics(env.steps, 1)
    except Exception:
        m_slot0, m_slot1 = None, None
    if swap:
        m_a, m_b = m_slot1, m_slot0
    else:
        m_a, m_b = m_slot0, m_slot1

    return MatchResult(
        seed=int(seed),
        agent_a=spec_args["agent_a"],
        agent_b=spec_args["agent_b"],
        agent_a_position=1 if swap else 0,
        reward_a=float(getattr(a, "reward", 0) or 0),
        reward_b=float(getattr(b, "reward", 0) or 0),
        n_turns=max(0, len(env.steps) - 1),
        elapsed_seconds=elapsed,
        status_a=str(getattr(a, "status", "DONE")),
        status_b=str(getattr(b, "status", "DONE")),
        metrics_a=m_a,
        metrics_b=m_b,
    )


# ─── Public API ──────────────────────────────────────────────────────────
def run_match(
    agent_a: str,
    agent_b: str,
    seed: int,
    *,
    swap: bool = False,
    episode_steps: int | None = None,
    act_timeout: float | None = None,
) -> MatchResult:
    """Run a single game in the current process."""
    return _run_one(
        {
            "agent_a": agent_a,
            "agent_b": agent_b,
            "seed": int(seed),
            "swap": bool(swap),
            "episode_steps": episode_steps,
            "act_timeout": act_timeout,
        }
    )


def _derive_seeds(n: int, base_seed: int | None) -> list[int]:
    rng = random.Random(0xC0FFEE if base_seed is None else int(base_seed))
    return [rng.randrange(0, 2**31) for _ in range(n)]


def run_matches(
    agent_a: str,
    agent_b: str,
    n_games: int = 6,
    *,
    seeds: Iterable[int] | None = None,
    base_seed: int | None = None,
    parallel: int = 1,
    balance_positions: bool = True,
    episode_steps: int | None = None,
    act_timeout: float | None = None,
    output_path: str | Path | None = None,
) -> list[MatchResult]:
    """Position-balanced batch of games. Returns one result per game.

    Parameters
    ----------
    agent_a, agent_b
        Specs accepted by :func:`resolve_agent_spec`.
    n_games
        Total number of games. With ``balance_positions=True``,
        roughly half are played with ``agent_a`` in slot 0 and half
        in slot 1.
    seeds
        Optional explicit seed list. Must be at least ``n_games`` long.
    base_seed
        If ``seeds`` is None, seeds are derived deterministically from
        this. ``None`` means use a fixed default (``0xC0FFEE``).
    parallel
        Worker count for the process pool. ``1`` runs in-process.
    balance_positions
        Whether to swap positions for half the games.
    episode_steps / act_timeout
        Pass-through to the kaggle env configuration.
    output_path
        If set, write each result as one JSONL line to this file. The
        parent directory is created if missing.
    """
    if seeds is None:
        seeds_list = _derive_seeds(n_games, base_seed)
    else:
        seeds_list = list(seeds)
        if len(seeds_list) < n_games:
            raise ValueError(
                f"need at least {n_games} seeds, got {len(seeds_list)}"
            )
        seeds_list = seeds_list[:n_games]

    half = n_games // 2 if balance_positions else n_games
    schedule = [
        {
            "agent_a": agent_a,
            "agent_b": agent_b,
            "seed": int(seed),
            "swap": balance_positions and i >= half,
            "episode_steps": episode_steps,
            "act_timeout": act_timeout,
        }
        for i, seed in enumerate(seeds_list)
    ]

    results: list[MatchResult] = []
    if parallel <= 1:
        for args in schedule:
            results.append(_run_one(args))
    else:
        with cf.ProcessPoolExecutor(max_workers=parallel) as pool:
            for r in pool.map(_run_one, schedule):
                results.append(r)

    # Deterministic ordering: (seed, position) so two runs with the same
    # seed list produce the same ordered output, regardless of pool race.
    results.sort(key=lambda r: (r.seed, r.agent_a_position))

    if output_path is not None:
        op = Path(output_path)
        op.parent.mkdir(parents=True, exist_ok=True)
        with op.open("w", encoding="utf-8") as f:
            for r in results:
                f.write(r.to_jsonl() + "\n")

    return results


# ─── Aggregation ─────────────────────────────────────────────────────────
def summarize(results: list[MatchResult]) -> Summary:
    """Aggregate a homogeneous list of results (same agent pair)."""
    if not results:
        raise ValueError("no results to summarize")
    a = results[0].agent_a
    b = results[0].agent_b
    # Sanity: all rows are the same pair
    if not all(r.agent_a == a and r.agent_b == b for r in results):
        raise ValueError("results contain a mix of agent pairs")

    n = len(results)
    wins_a = sum(1 for r in results if r.winner == "a")
    wins_b = sum(1 for r in results if r.winner == "b")
    draws = n - wins_a - wins_b
    winrate = (wins_a + 0.5 * draws) / n
    mean_diff = sum(r.reward_a - r.reward_b for r in results) / n
    times = sorted(r.elapsed_seconds for r in results)
    mean_t = sum(times) / n
    p50_t = times[n // 2]
    return Summary(
        agent_a=a,
        agent_b=b,
        games=n,
        wins_a=wins_a,
        draws=draws,
        wins_b=wins_b,
        winrate_a=winrate,
        mean_reward_diff=mean_diff,
        mean_seconds=mean_t,
        p50_seconds=p50_t,
    )


def load_jsonl(path: str | Path) -> list[MatchResult]:
    """Read a JSONL file written by :func:`run_matches`."""
    field_names = {f.name for f in _dc.fields(MatchResult)}
    out: list[MatchResult] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        d = {k: v for k, v in d.items() if k in field_names}
        if isinstance(d.get('metrics_a'), dict):
            d['metrics_a'] = PlayerMetrics(**d['metrics_a'])
        if isinstance(d.get('metrics_b'), dict):
            d['metrics_b'] = PlayerMetrics(**d['metrics_b'])
        out.append(MatchResult(**d))
    return out
