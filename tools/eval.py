"""tools/eval.py -- CLI wrapper around orbit_wars.eval.runner.

Usage examples
--------------
    # 20 games, blitz vs sniper, with built-in parallelism
    python tools/eval.py preset:blitz preset:sniper -n 20 -p 4

    # blitz vs the kaggle random agent, write per-match log
    python tools/eval.py preset:blitz random -n 10 -o results.jsonl

    # Quick smoke against the currently-shipped main.py
    python tools/eval.py main.py random -n 4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orbit_wars.eval.runner import run_matches, summarize


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Position-balanced, parallel evaluation of two agents."
    )
    ap.add_argument("agent_a", help="spec, e.g. preset:blitz / file:main.py / random")
    ap.add_argument("agent_b", help="opponent spec, same forms as agent_a")
    ap.add_argument("-n", "--games", type=int, default=6,
                    help="total games (default 6)")
    ap.add_argument("-p", "--parallel", type=int, default=1,
                    help="parallel worker count (default 1)")
    ap.add_argument("--seed", type=int, default=None,
                    help="base RNG seed for deterministic per-game seeds")
    ap.add_argument("--no-balance", action="store_true",
                    help="don't swap positions; agent_a always in slot 0")
    ap.add_argument("--episode-steps", type=int, default=None,
                    help="override max turns (default: kaggle default = 500)")
    ap.add_argument("-o", "--output", default=None,
                    help="write per-match JSONL to this path")
    args = ap.parse_args()

    results = run_matches(
        agent_a=args.agent_a,
        agent_b=args.agent_b,
        n_games=args.games,
        base_seed=args.seed,
        parallel=args.parallel,
        balance_positions=not args.no_balance,
        episode_steps=args.episode_steps,
        output_path=args.output,
    )

    summary = summarize(results)
    print()
    print(summary)
    if args.output:
        print(f"\nWrote {len(results)} match rows -> {args.output}")


if __name__ == "__main__":
    main()
