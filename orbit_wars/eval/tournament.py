"""
Round-robin tournament + Elo ratings for Orbit Wars agents.

Given N agent specs, plays every unique pair for ``n_games_per_pair``
games (position-balanced via :func:`run_matches`), then aggregates the
results into:

* a per-pair winrate matrix,
* a leaderboard sorted by Elo,
* an optional JSONL export of every individual match.

Elo update rule
---------------
Standard pairwise Elo, applied **sequentially** to every match in the
order produced by :func:`run_matches` (sorted by seed then position).
For two agents with current ratings ``Ra, Rb``, the expected score for
``a`` is::

    Ea = 1 / (1 + 10**((Rb - Ra) / 400))

and the rating updates are::

    Ra' = Ra + K * (Sa - Ea)
    Rb' = Rb + K * ((1 - Sa) - (1 - Ea))

where ``Sa`` is ``a``'s actual score (1 for win, 0.5 for draw, 0 for
loss) and ``K`` is the K-factor (default 32). Sequential updates mean
the order of matches has a small effect, but with N games per pair
this converges quickly and the ranking is stable.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from itertools import combinations
from pathlib import Path

from orbit_wars.eval.runner import MatchResult, run_matches


# ─── Elo arithmetic ──────────────────────────────────────────────────────
def expected_score(rating_a: float, rating_b: float) -> float:
    """Probability that ``a`` wins, given two Elo ratings."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def compute_elo(
    results: list[MatchResult],
    agents: list[str],
    *,
    initial: float = 1500.0,
    k_factor: float = 32.0,
) -> dict[str, float]:
    """Sequential Elo update across the result list.

    Unknown agents in ``results`` (not in ``agents``) raise KeyError --
    caller is expected to pass a consistent agent list.
    """
    elo: dict[str, float] = {a: initial for a in agents}
    for r in results:
        ra, rb = elo[r.agent_a], elo[r.agent_b]
        ea = expected_score(ra, rb)
        if r.winner == "a":
            sa = 1.0
        elif r.winner == "b":
            sa = 0.0
        else:
            sa = 0.5
        delta = k_factor * (sa - ea)
        elo[r.agent_a] = ra + delta
        elo[r.agent_b] = rb - delta
    return elo


# ─── Tournament result ───────────────────────────────────────────────────
@dataclass
class Tournament:
    agents: list[str]
    results: list[MatchResult]
    pairings: dict[tuple[str, str], list[MatchResult]] = field(default_factory=dict)
    pairwise_winrate: dict[tuple[str, str], float] = field(default_factory=dict)
    elo: dict[str, float] = field(default_factory=dict)
    k_factor: float = 32.0
    initial_elo: float = 1500.0

    # ── Reporting ───────────────────────────────────────────────────
    def leaderboard(self) -> list[tuple[str, float, int, int, int, int]]:
        """``[(agent, elo, games, wins, draws, losses), ...]`` sorted by elo desc."""
        rows = []
        for a in self.agents:
            wins = draws = losses = games = 0
            for r in self.results:
                if r.agent_a == a:
                    games += 1
                    if r.winner == "a":
                        wins += 1
                    elif r.winner == "draw":
                        draws += 1
                    else:
                        losses += 1
                elif r.agent_b == a:
                    games += 1
                    if r.winner == "b":
                        wins += 1
                    elif r.winner == "draw":
                        draws += 1
                    else:
                        losses += 1
            rows.append((a, self.elo.get(a, self.initial_elo),
                         games, wins, draws, losses))
        rows.sort(key=lambda x: x[1], reverse=True)
        return rows

    def leaderboard_text(self) -> str:
        rows = self.leaderboard()
        if not rows:
            return "(no rows)"
        max_name = max(len(r[0]) for r in rows)
        header = f"{'agent':<{max_name}}  {'elo':>6}  {'games':>5}  {'W':>3}  {'D':>3}  {'L':>3}  {'WR':>6}"
        lines = [header, "-" * len(header)]
        for name, elo, games, wins, draws, losses in rows:
            wr = (wins + 0.5 * draws) / games if games else 0.0
            lines.append(
                f"{name:<{max_name}}  {elo:>6.1f}  {games:>5}  {wins:>3}  "
                f"{draws:>3}  {losses:>3}  {wr:>5.1%}"
            )
        return "\n".join(lines)

    def winrate_matrix_text(self) -> str:
        """ASCII winrate matrix. Row vs column reads
        "row's winrate when playing column"."""
        if not self.agents:
            return "(no agents)"
        max_name = max(len(a) for a in self.agents)
        col_width = max(6, max_name)
        header = " " * (max_name + 2) + "  ".join(
            f"{a[:col_width]:>{col_width}}" for a in self.agents
        )
        lines = [header]
        for row_agent in self.agents:
            cells = []
            for col_agent in self.agents:
                if row_agent == col_agent:
                    cells.append(f"{'--':>{col_width}}")
                else:
                    wr = self.pairwise_winrate.get((row_agent, col_agent))
                    cells.append(
                        f"{wr:>{col_width}.1%}" if wr is not None
                        else f"{'?':>{col_width}}"
                    )
            lines.append(f"{row_agent:<{max_name}}  " + "  ".join(cells))
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """JSON-serialisable summary (does NOT include per-match rows)."""
        return {
            "agents": self.agents,
            "elo": dict(self.elo),
            "pairwise_winrate": {
                f"{a}|{b}": v for (a, b), v in self.pairwise_winrate.items()
            },
            "leaderboard": [
                {
                    "agent": name, "elo": elo, "games": games,
                    "wins": wins, "draws": draws, "losses": losses,
                }
                for name, elo, games, wins, draws, losses in self.leaderboard()
            ],
            "k_factor": self.k_factor,
            "initial_elo": self.initial_elo,
        }

    def write_csv(self, path: str | Path) -> None:
        rows = self.leaderboard()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["agent", "elo", "games", "wins", "draws", "losses", "winrate"])
            for name, elo, games, wins, draws, losses in rows:
                wr = (wins + 0.5 * draws) / games if games else 0.0
                w.writerow([name, f"{elo:.2f}", games, wins, draws, losses,
                            f"{wr:.4f}"])


# ─── Driver ──────────────────────────────────────────────────────────────
def run_tournament(
    agents: list[str],
    n_games_per_pair: int = 6,
    *,
    base_seed: int | None = None,
    parallel: int = 1,
    balance_positions: bool = True,
    episode_steps: int | None = None,
    output_dir: str | Path | None = None,
    k_factor: float = 32.0,
    initial_elo: float = 1500.0,
) -> Tournament:
    """Round-robin: every unique unordered pair plays ``n_games_per_pair``.

    If ``output_dir`` is given, writes:

    * ``matches.jsonl``     -- every individual match
    * ``leaderboard.csv``   -- final standings
    * ``tournament.json``   -- summary dict

    Per-pair seeds are derived from ``base_seed`` and the pair index, so
    re-running with the same ``base_seed`` reproduces the same matches.
    """
    if len(agents) < 2:
        raise ValueError("need at least 2 agents for a tournament")
    if len(set(agents)) != len(agents):
        raise ValueError(
            "duplicate agent specs would collide in the Elo dict; "
            "deduplicate before running"
        )

    pairs = list(combinations(agents, 2))
    all_results: list[MatchResult] = []
    pairings: dict[tuple[str, str], list[MatchResult]] = {}

    for pi, (a, b) in enumerate(pairs):
        pair_seed = None if base_seed is None else int(base_seed) + pi * 1009
        sub = run_matches(
            agent_a=a, agent_b=b,
            n_games=n_games_per_pair,
            base_seed=pair_seed,
            parallel=parallel,
            balance_positions=balance_positions,
            episode_steps=episode_steps,
        )
        all_results.extend(sub)
        pairings[(a, b)] = list(sub)

    # Pairwise winrate (both directions, from each row's perspective)
    pw: dict[tuple[str, str], float] = {}
    for (a, b), rs in pairings.items():
        if not rs:
            continue
        wins_a = sum(1 for r in rs if r.winner == "a")
        wins_b = sum(1 for r in rs if r.winner == "b")
        draws = len(rs) - wins_a - wins_b
        pw[(a, b)] = (wins_a + 0.5 * draws) / len(rs)
        pw[(b, a)] = (wins_b + 0.5 * draws) / len(rs)

    elo = compute_elo(all_results, agents, initial=initial_elo, k_factor=k_factor)
    t = Tournament(
        agents=list(agents),
        results=all_results,
        pairings=pairings,
        pairwise_winrate=pw,
        elo=elo,
        k_factor=k_factor,
        initial_elo=initial_elo,
    )

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        with (out / "matches.jsonl").open("w", encoding="utf-8") as f:
            for r in all_results:
                f.write(r.to_jsonl() + "\n")
        t.write_csv(out / "leaderboard.csv")
        (out / "tournament.json").write_text(
            json.dumps(t.to_dict(), indent=2), encoding="utf-8"
        )

    return t
