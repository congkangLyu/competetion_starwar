"""Evaluation harness for Orbit Wars agents.

Public surface:
    run_match(agent_a, agent_b, seed)             -> single MatchResult
    run_matches(agent_a, agent_b, n_games, ...)   -> list[MatchResult]
    summarize(results)                            -> Summary
    load_jsonl(path)                              -> list[MatchResult]
    resolve_agent_spec(spec)                      -> path or builtin name

All agent specs are *strings* so they round-trip cleanly through
multiprocessing workers and JSONL output. Supported forms:

    "preset:blitz"            build configs/blitz.yaml, run the built file
    "file:agents/blitz.py"    run an existing .py file
    "agents/blitz.py"         (shorthand for the above)
    "random" / "reaction"     kaggle builtin agents
"""

from orbit_wars.eval.tournament import (
    Tournament,
    compute_elo,
    expected_score,
    run_tournament,
)
from orbit_wars.eval.metrics import PlayerMetrics, compute_metrics
from orbit_wars.eval.runner import (
    MatchResult,
    Summary,
    load_jsonl,
    resolve_agent_spec,
    run_match,
    run_matches,
    summarize,
)

__all__ = [
    "MatchResult",
    "Summary",
    "load_jsonl",
    "resolve_agent_spec",
    "run_match",
    "run_matches",
    "summarize",
    "PlayerMetrics",
    "compute_metrics",
    "Tournament",
    "run_tournament",
    "compute_elo",
    "expected_score",
]
