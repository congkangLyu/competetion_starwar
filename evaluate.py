"""
Evaluation harness for Orbit Wars agents.

Plays one agent against another for N games (with position swap) and
reports winrate, draws, losses, and average elapsed time.

Usage:
    python evaluate.py <agent_a> <agent_b> [n_games]

Examples:
    python evaluate.py agents/blitz.py agents/sniper.py 10
    python evaluate.py agents/blitz.py random 20
    python evaluate.py main.py random 6              # quick smoke test

Notes:
  - `agent_a` and `agent_b` can be a path to a .py file or one of the
    builtin Kaggle agents: "random", "reaction".
  - n_games defaults to 6 (3 with each player position).
  - Position swap matters: Player 0 and Player 1 have different starting
    locations, so we play half the games each way.
"""

import sys
import time
from kaggle_environments import make


def play_match(agent_a, agent_b):
    """Run a single game. Returns (reward_a, reward_b)."""
    env = make("orbit_wars", debug=False)
    env.run([agent_a, agent_b])
    final = env.steps[-1]
    return final[0].reward, final[1].reward


def winrate(agent_a, agent_b, n_games=6):
    """Position-balanced winrate of agent_a vs agent_b.

    Half the games are played with agent_a as Player 0, half as Player 1.
    Returns (wins, draws, losses) from agent_a's perspective.
    """
    wins = draws = losses = 0
    half = n_games // 2

    print(f"  Phase 1: {agent_a} as Player 0 ({half} games)")
    for k in range(half):
        t0 = time.perf_counter()
        ra, rb = play_match(agent_a, agent_b)
        dt = time.perf_counter() - t0
        outcome = "W" if ra > rb else ("D" if ra == rb else "L")
        print(f"    game {k+1}/{half}: reward_a={ra:+d} reward_b={rb:+d}  -> {outcome}  ({dt:.1f}s)")
        if ra > rb: wins += 1
        elif ra == rb: draws += 1
        else: losses += 1

    rest = n_games - half
    print(f"  Phase 2: {agent_a} as Player 1 ({rest} games)")
    for k in range(rest):
        t0 = time.perf_counter()
        rb, ra = play_match(agent_b, agent_a)
        dt = time.perf_counter() - t0
        outcome = "W" if ra > rb else ("D" if ra == rb else "L")
        print(f"    game {k+1}/{rest}: reward_a={ra:+d} reward_b={rb:+d}  -> {outcome}  ({dt:.1f}s)")
        if ra > rb: wins += 1
        elif ra == rb: draws += 1
        else: losses += 1

    return wins, draws, losses


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    agent_a = sys.argv[1]
    agent_b = sys.argv[2]
    n_games = int(sys.argv[3]) if len(sys.argv) > 3 else 6

    print("=" * 64)
    print(f"Evaluating: {agent_a}  vs  {agent_b}  ({n_games} games)")
    print("=" * 64)

    t0 = time.time()
    wins, draws, losses = winrate(agent_a, agent_b, n_games)
    elapsed = time.time() - t0

    wr = (wins + 0.5 * draws) / n_games
    print()
    print("-" * 64)
    print(f"Result ({elapsed:.1f}s total, {elapsed/n_games:.1f}s/game):")
    print(f"  Wins:    {wins} / {n_games}")
    print(f"  Draws:   {draws} / {n_games}")
    print(f"  Losses:  {losses} / {n_games}")
    print(f"  Winrate: {wr:.1%}  (draws count as 0.5)")
    print("=" * 64)


if __name__ == "__main__":
    main()
