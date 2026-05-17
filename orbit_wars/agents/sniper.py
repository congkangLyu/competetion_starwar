"""
SniperAgent -- the original nearest-planet baseline.

Strategy
--------
For every planet we own, find the closest planet we do not own. If we
have at least ``garrison + 1`` ships, launch exactly that many at it;
otherwise wait and accumulate.

This is a faithful re-implementation of the original ``agents/sniper.py``
on top of the new :class:`Agent` abstraction:

* Reads :class:`GameState` instead of unpacking raw lists.
* Logs each decision through :meth:`Agent.log` so replays can later show
  which target each launch was aimed at and why.
* Otherwise carries forward the same (deliberately naive) policy so it
  remains a useful low-bar baseline against which to measure improvements.

Known weaknesses (carried over -- improving them is the *algorithm* work,
not the framework work):
  * Ignores travel time -- the target keeps producing during transit.
  * Naive ``garrison + 1`` rather than solving for capture cost.
  * No sun-avoidance -- a straight aim line may pass through the sun.
  * No coordination -- multiple sources may pick the same target.
  * Ignores orbital motion of the inner planets.
"""

from __future__ import annotations

from orbit_wars.core.geometry import angle_to, dist
from orbit_wars.core.state import GameState, Move
from orbit_wars.agents.base import Agent


class SniperAgent(Agent):
    """Greedy nearest-planet baseline. See module docstring."""

    name = "sniper"

    def act(self, state: GameState) -> list[Move]:
        targets = state.non_my_planets
        if not targets:
            return []

        moves: list[Move] = []
        for mine in state.my_planets:
            nearest = min(targets, key=lambda t: dist(mine.x, mine.y, t.x, t.y))
            needed = nearest.ships + 1
            if mine.ships >= needed:
                move = Move(
                    from_planet_id=mine.id,
                    angle=angle_to(mine.x, mine.y, nearest.x, nearest.y),
                    ships=needed,
                )
                moves.append(move)
                self.log(
                    move,
                    reason="nearest",
                    target_id=nearest.id,
                    target_owner=nearest.owner,
                    target_ships=nearest.ships,
                )
        return moves
