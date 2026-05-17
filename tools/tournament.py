"""tools/tournament.py -- round-robin N agents and emit a leaderboard.

Example
-------
    python tools/tournament.py \\
        preset:blitz preset:sentinel preset:sniper random \\
        -n 10 -p 4 --output tourneys/aug

The output directory will contain:

    matches.jsonl     -- every individual MatchResult, one per line
    leaderboard.csv   -- final Elo + W/D/L per agent
    tournament.json   -- machine-readable summary (elo, pairwise winrate)

The CLI prints both the leaderboard and the pairwise winrate matrix to
stdout for quick eyeballing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orbit_wars.eval.tournament import run_tournament


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Round-robin tournament with Elo ratings."
    )
    ap.add_argument("agents", nargs="+",
                    help="agent specs (preset:NAME / file:PATH / random / reaction)")
    ap.add_argument("-n", "--games-per-pair", type=int, default=6,
                    help="games each unordered pair plays (default 6)")
    ap.add_argument("-p", "--parallel", type=int, default=1,
                    help="parallel workers (default 1)")
    ap.add_argument("--seed", type=int, default=None,
                    help="base RNG seed for deterministic seeding")
    ap.add_argument("--episode-steps", type=int, default=None,
                    help="override kaggle episodeSteps (default 500)")
    ap.add_argument("--no-balance", action="store_true",
                    help="skip position swap")
    ap.add_argument("--k", type=float, default=32.0,
                    help="Elo K-factor (default 32)")
    ap.add_argument("--initial-elo", type=float, default=1500.0,
                    help="starting Elo (default 1500)")
    ap.add_argument("-o", "--output-dir", default=None,
                    help="write matches.jsonl / leaderboard.csv / tournament.json here")
    args = ap.parse_args()

    t = run_tournament(
        agents=args.agents,
        n_games_per_pair=args.games_per_pair,
        base_seed=args.seed,
        parallel=args.parallel,
        balance_positions=not args.no_balance,
        episode_steps=args.episode_steps,
        output_dir=args.output_dir,
        k_factor=args.k,
        initial_elo=args.initial_elo,
    )

    print()
    print("Leaderboard")
    print("===========")
    print(t.leaderboard_text())
    print()
    print("Pairwise winrate (row's WR vs column)")
    print("=====================================")
    print(t.winrate_matrix_text())
    if args.output_dir:
        print(f"\nArtifacts: {args.output_dir}")


if __name__ == "__main__":
    main()
