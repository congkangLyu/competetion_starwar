"""
Agent base class and the kaggle adapter.

Design
------
Every Orbit Wars agent is a subclass of :class:`Agent` that implements
``act(state) -> list[Move]``. The base class provides:

* **Step counting**: the raw kaggle observation does not include the turn
  number, but our :class:`GameState` does. The base class threads the
  step counter through so each call to ``act`` sees ``state.step`` and so
  decision logs can be timestamped.
* **Decision logging**: subclasses can call :meth:`Agent.log` to record
  *why* a move was made. The runner (Step 4) and the replay analyser
  (Step 6) read these to explain agent behaviour after the fact.
* **Lifecycle hooks**: :meth:`Agent.on_game_start` /
  :meth:`Agent.on_game_end` are called automatically on the first and
  (where the runner can detect it) last turn of a game. Override them for
  per-game setup / teardown without polluting ``act``.
* **Game-isolation via reset**: ``reset()`` clears per-game state so the
  same agent instance can be reused across many games during local
  evaluation without leaking the turn counter or decision log between
  games.

The :func:`make_kaggle_agent` factory hides all of this behind the plain
``(obs) -> list[list]`` callable that ``env.run([fn, ...])`` expects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from orbit_wars.core.state import GameState, Move


# ─────────────────────────────────────────────────────────────────────────
# Decision log entry
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class Decision:
    """One reasoning trace entry attached to one issued :class:`Move`.

    ``meta`` is intentionally free-form -- subclasses can stash any extra
    fields they care about (e.g. ``target_owner``, ``predicted_arrival``).
    """

    step: int
    move: Move
    reason: str = ""
    score: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
# Agent base class
# ─────────────────────────────────────────────────────────────────────────
class Agent(ABC):
    """Abstract base class for all Orbit Wars agents.

    Subclasses must implement :meth:`act`. Subclasses *may* override
    :meth:`on_game_start` / :meth:`on_game_end` for setup or teardown.

    Subclasses should call :meth:`log` for every move they issue, so the
    decision log stays in sync with the moves returned.
    """

    #: Human-readable name. Override per subclass; used in eval output.
    name: str = "agent"

    def __init__(self) -> None:
        self._step: int = 0
        self._decisions: list[Decision] = []
        self._game_started: bool = False

    # ── Lifecycle ────────────────────────────────────────────────────
    def on_game_start(self, state: GameState) -> None:
        """Called once, on the first turn of a new game."""

    @abstractmethod
    def act(self, state: GameState) -> list[Move]:
        """Decide what to do this turn. Return the list of launches."""

    def on_game_end(self, state: GameState, reward: int) -> None:
        """Called by the runner after the final turn. May not fire if the
        agent is invoked through the bare kaggle adapter (kaggle does not
        give us a clean end-of-game callback)."""

    # ── Decision logging ─────────────────────────────────────────────
    def log(
        self,
        move: Move,
        *,
        reason: str = "",
        score: float | None = None,
        **meta: Any,
    ) -> None:
        """Record a decision. Call from inside :meth:`act` when issuing a move."""
        self._decisions.append(
            Decision(step=self._step, move=move, reason=reason, score=score, meta=dict(meta))
        )

    @property
    def decisions(self) -> list[Decision]:
        """All decisions logged so far (across the current game)."""
        return list(self._decisions)

    # ── Runner-facing internals ──────────────────────────────────────
    def _run_turn(self, state: GameState) -> list[Move]:
        """Internal: drive one turn. Used by the kaggle adapter and the
        evaluation runner; subclasses should *not* call this themselves."""
        if not self._game_started:
            self._game_started = True
            self.on_game_start(state)
        self._step = state.step
        return self.act(state)

    def reset(self) -> None:
        """Clear per-game state. The runner calls this between games."""
        self._step = 0
        self._decisions.clear()
        self._game_started = False


# ─────────────────────────────────────────────────────────────────────────
# Kaggle adapter
# ─────────────────────────────────────────────────────────────────────────
def make_kaggle_agent(agent_cls: type[Agent], **kwargs: Any):
    """Adapt an Agent class into a callable that ``kaggle_environments``
    can consume directly:

    >>> env = kaggle_environments.make("orbit_wars")
    >>> env.run([make_kaggle_agent(SniperAgent), "random"])

    The returned function tracks the turn number internally (kaggle does
    not include it in the observation), parses the raw obs into a
    :class:`GameState`, and serialises moves back to list-of-lists. The
    underlying Agent instance is attached to the function as
    ``fn.agent_instance`` so callers can read its decision log afterwards.
    """
    instance = agent_cls(**kwargs)
    step_counter = [0]

    def kaggle_fn(obs):
        state = GameState.from_obs(obs, step=step_counter[0])
        moves = instance._run_turn(state)
        step_counter[0] += 1
        return [m.to_list() for m in moves]

    kaggle_fn.agent_instance = instance  # type: ignore[attr-defined]
    kaggle_fn.__name__ = f"kaggle_{agent_cls.__name__}"
    return kaggle_fn

# ─────────────────────────────────────────────────────────────────────────
# Decision log serialisation
# ─────────────────────────────────────────────────────────────────────────
def decisions_to_jsonl(decisions: list[Decision]) -> str:
    """Render a list of :class:`Decision` as a JSONL blob (one row per move).

    Each row has the fields ``step``, ``move`` (as ``[id, angle, ships]``),
    ``reason``, ``score``, ``meta`` (free-form dict). Suitable for replay
    analysis, agent-vs-agent comparison, or feeding into pandas:

        for d in agent.decisions:
            ...
        path.write_text(decisions_to_jsonl(agent.decisions))
    """
    import json as _json
    lines = []
    for d in decisions:
        row = {
            "step": d.step,
            "move": list(d.move.to_list()),
            "reason": d.reason,
            "score": d.score,
            "meta": dict(d.meta),
        }
        lines.append(_json.dumps(row, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


def load_decisions_jsonl(path) -> list[Decision]:
    """Inverse of :func:`decisions_to_jsonl`. Reads a JSONL file back into
    :class:`Decision` objects. ``move`` is reconstructed as :class:`Move`."""
    import json as _json
    from pathlib import Path as _P

    out: list[Decision] = []
    for line in _P(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = _json.loads(line)
        move_list = row.get("move") or [0, 0.0, 0]
        out.append(
            Decision(
                step=int(row.get("step", 0)),
                move=Move(int(move_list[0]), float(move_list[1]), int(move_list[2])),
                reason=str(row.get("reason", "")),
                score=row.get("score"),
                meta=dict(row.get("meta", {})),
            )
        )
    return out
