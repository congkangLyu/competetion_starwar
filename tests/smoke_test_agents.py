"""Smoke test for the new Agent abstraction and migrated agents."""

from __future__ import annotations

import math
import sys
from collections import namedtuple
from pathlib import Path
from types import ModuleType, SimpleNamespace

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


from orbit_wars.agents import (
    Agent,
    Decision,
    HeuristicAgent,
    HeuristicConfig,
    PeakingAgent,
    PeakingConfig,
    SniperAgent,
    make_kaggle_agent,
)
from orbit_wars.core.geometry import angle_to
from orbit_wars.core.state import GameState, Move


def sample_obs(player: int = 0) -> dict:
    """Representative obs. Home planet has 100 ships so the heuristic
    can afford either neutral target after solving capture cost."""
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


def test_agent_is_abstract() -> None:
    print("test_agent_is_abstract")
    try:
        Agent()
    except TypeError:
        check("Agent() rejects direct instantiation", True)
        return
    check("Agent() rejects direct instantiation", False)


def test_sniper_basic() -> None:
    print("test_sniper_basic")
    agent = SniperAgent()
    state = GameState.from_obs(sample_obs(), step=0)
    moves = agent._run_turn(state)
    check("returns Move list", all(isinstance(m, Move) for m in moves))
    check("issues at least one move", len(moves) >= 1)
    check("logged a decision per move", len(agent.decisions) == len(moves))
    first = agent.decisions[0]
    check("decision references a target", "target_id" in first.meta)
    check("decision reason is 'nearest'", first.reason == "nearest")


def test_heuristic_waits() -> None:
    print("test_heuristic_waits")
    agent = HeuristicAgent.blitz()
    for step in [0, 1]:
        state = GameState.from_obs(sample_obs(), step=step)
        moves = agent._run_turn(state)
        check(f"step {step} returns []", moves == [])
    state = GameState.from_obs(sample_obs(), step=2)
    moves = agent._run_turn(state)
    check("step 2 produces moves", len(moves) >= 1)
    check("decision log populated", len(agent.decisions) == len(moves))
    reasons = {d.reason for d in agent.decisions}
    check("at least one attack/consolidate decision",
          bool(reasons & {"attack", "consolidate"}))


def test_heuristic_defense_enabled() -> None:
    print("test_heuristic_defense_enabled")
    agent = HeuristicAgent(HeuristicConfig(use_defense=True, wait_turns=0))
    state = GameState.from_obs(sample_obs(), step=0)
    moves = agent._run_turn(state)
    check("runs without crashing with defense on", isinstance(moves, list))


def test_heuristic_orbital_aim_defaults_off() -> None:
    print("test_heuristic_orbital_aim_defaults_off")
    cfg = HeuristicConfig()
    check("orbital aim disabled by default", cfg.use_orbital_aim is False)
    check("aim iterations has sane default", cfg.aim_iterations >= 1)


def moving_target_obs() -> dict:
    return {
        "player": 0,
        "planets": [
            [0, 0, 20.0, 80.0, 2.0, 200, 3],
            [1, -1, 60.0, 60.0, 1.0, 5, 1],
        ],
        "fleets": [],
        "angular_velocity": 0.10,
        "initial_planets": [
            [0, 0, 20.0, 80.0, 2.0, 200, 3],
            [1, -1, 60.0, 60.0, 1.0, 5, 1],
        ],
        "comets": [],
        "comet_planet_ids": [],
        "remainingOverageTime": 60.0,
    }


def static_target_obs() -> dict:
    return {
        "player": 0,
        "planets": [
            [0, 0, 20.0, 80.0, 2.0, 200, 3],
            [1, -1, 90.0, 80.0, 1.0, 5, 1],
        ],
        "fleets": [],
        "angular_velocity": 0.10,
        "initial_planets": [
            [0, 0, 20.0, 80.0, 2.0, 200, 3],
            [1, -1, 90.0, 80.0, 1.0, 5, 1],
        ],
        "comets": [],
        "comet_planet_ids": [],
        "remainingOverageTime": 60.0,
    }


def comet_target_obs() -> dict:
    path = [(60.0 + i, 60.0) for i in range(20)]
    return {
        "player": 0,
        "planets": [
            [0, 0, 20.0, 80.0, 2.0, 200, 3],
            [10, -1, 60.0, 60.0, 1.0, 5, 1],
        ],
        "fleets": [],
        "angular_velocity": 0.0,
        "initial_planets": [
            [0, 0, 20.0, 80.0, 2.0, 200, 3],
            [10, -1, 60.0, 60.0, 1.0, 5, 1],
        ],
        "comets": [
            {"planet_ids": [10], "paths": [path], "path_index": 0},
        ],
        "comet_planet_ids": [10],
        "remainingOverageTime": 60.0,
    }


def test_heuristic_orbital_aim_leads_orbiting_planet() -> None:
    print("test_heuristic_orbital_aim_leads_orbiting_planet")
    agent = HeuristicAgent(
        HeuristicConfig(use_orbital_aim=True, wait_turns=0, aim_iterations=4)
    )
    state = GameState.from_obs(moving_target_obs(), step=0)
    moves = agent._run_turn(state)
    check("orbital aim produces a move", len(moves) == 1)
    current_angle = angle_to(20.0, 80.0, 60.0, 60.0)
    check("angle leads current target position",
          abs(moves[0].angle - current_angle) > 1e-6)
    check("decision log records aim point", "aim_x" in agent.decisions[0].meta)


def test_heuristic_orbital_aim_keeps_static_target_current() -> None:
    print("test_heuristic_orbital_aim_keeps_static_target_current")
    agent = HeuristicAgent(
        HeuristicConfig(use_orbital_aim=True, wait_turns=0, aim_iterations=4)
    )
    state = GameState.from_obs(static_target_obs(), step=0)
    moves = agent._run_turn(state)
    check("static aim produces a move", len(moves) == 1)
    current_angle = angle_to(20.0, 80.0, 90.0, 80.0)
    check("static target keeps current aim",
          abs(moves[0].angle - current_angle) < 1e-12)


def test_heuristic_orbital_aim_handles_comet_path() -> None:
    print("test_heuristic_orbital_aim_handles_comet_path")
    agent = HeuristicAgent(
        HeuristicConfig(use_orbital_aim=True, wait_turns=0, aim_iterations=4)
    )
    state = GameState.from_obs(comet_target_obs(), step=0)
    moves = agent._run_turn(state)
    check("comet aim runs without crashing", isinstance(moves, list))


def test_peaking_basic() -> None:
    print("test_peaking_basic")
    agent = PeakingAgent(PeakingConfig(partial_source_min_ships=1))
    state = GameState.from_obs(sample_obs(), step=3)
    moves = agent._run_turn(state)
    check("peaking returns Move list", all(isinstance(m, Move) for m in moves))
    check("peaking runs without crashing", isinstance(moves, list))
    by_id = state.planet_by_id
    check("peaking only launches from owned planets",
          all(by_id[m.from_planet_id].owner == state.player for m in moves))
    sent_by_source = {}
    for m in moves:
        sent_by_source[m.from_planet_id] = sent_by_source.get(m.from_planet_id, 0) + m.ships
    check("peaking never overspends source ships",
          all(sent <= by_id[src_id].ships for src_id, sent in sent_by_source.items()))


def test_peaking_handles_moving_and_comet_targets() -> None:
    print("test_peaking_handles_moving_and_comet_targets")
    agent = PeakingAgent(PeakingConfig(partial_source_min_ships=1))
    for obs in [moving_target_obs(), comet_target_obs()]:
        state = GameState.from_obs(obs, step=0)
        moves = agent._run_turn(state)
        check("peaking accepts moving/comet obs", isinstance(moves, list))


def test_reset_clears_state() -> None:
    print("test_reset_clears_state")
    agent = SniperAgent()
    agent._run_turn(GameState.from_obs(sample_obs(), step=0))
    assert agent.decisions
    agent.reset()
    check("decisions cleared", agent.decisions == [])
    check("step reset", agent._step == 0)
    check("game_started cleared", agent._game_started is False)


def test_kaggle_adapter_shapes() -> None:
    print("test_kaggle_adapter_shapes")
    fn = make_kaggle_agent(SniperAgent)
    out = fn(sample_obs())
    check("returns a list", isinstance(out, list))
    check("each move is [int, float, int]",
          all(isinstance(m, list) and len(m) == 3 for m in out))
    check("planet ids are int", all(isinstance(m[0], int) for m in out))
    check("angles are float", all(isinstance(m[1], float) for m in out))
    check("ship counts are int", all(isinstance(m[2], int) for m in out))
    check("agent_instance attached", hasattr(fn, "agent_instance"))
    check("step counter after 1 turn", fn.agent_instance._step == 0)
    fn(sample_obs())
    check("step counter advances", fn.agent_instance._step == 1)


def test_kaggle_adapter_handles_namespace_obs() -> None:
    print("test_kaggle_adapter_handles_namespace_obs")
    fn = make_kaggle_agent(SniperAgent)
    out = fn(SimpleNamespace(**sample_obs()))
    check("namespace obs accepted", isinstance(out, list))


def _moves_equal(a_list, b_list) -> bool:
    if len(a_list) != len(b_list):
        return False
    a_sorted = sorted(a_list)
    b_sorted = sorted(b_list)
    return all(
        a[0] == b[0] and abs(a[1] - b[1]) < 1e-12 and a[2] == b[2]
        for a, b in zip(a_sorted, b_sorted)
    )


def test_sniper_parity_with_old_implementation() -> None:
    """New SniperAgent must produce identical moves to old agents/sniper.py."""
    print("test_sniper_parity_with_old_implementation")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "old_sniper", str(ROOT / "agents" / "sniper.py")
    )
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    for player in (0, 1):
        obs = sample_obs(player=player)
        old_moves = old.agent(obs)
        new_agent = SniperAgent()
        state = GameState.from_obs(obs, step=0)
        new_moves = [m.to_list() for m in new_agent._run_turn(state)]
        same = _moves_equal(old_moves, new_moves)
        if not same:
            print(f"    old: {sorted(old_moves)}")
            print(f"    new: {sorted(new_moves)}")
        check(f"player={player}: new sniper matches old", same)


def test_heuristic_parity_with_old_blitz() -> None:
    """New HeuristicAgent.blitz() must produce identical moves to old
    agents/blitz.py at the same effective turn. The old module uses a
    closure counter that skips WAIT_TURNS calls; we advance it manually."""
    print("test_heuristic_parity_with_old_blitz")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "old_blitz", str(ROOT / "agents" / "blitz.py")
    )
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    for player in (0, 1):
        obs = sample_obs(player=player)
        old_fn = old.make_fresh_agent()
        for _ in range(old.WAIT_TURNS):
            assert old_fn(obs) == []
        old_moves = old_fn(obs)
        new_agent = HeuristicAgent.blitz()
        state = GameState.from_obs(obs, step=old.WAIT_TURNS)
        new_moves = [m.to_list() for m in new_agent._run_turn(state)]
        same = _moves_equal(old_moves, new_moves)
        if not same:
            print(f"    old: {sorted(old_moves)}")
            print(f"    new: {sorted(new_moves)}")
        check(f"player={player}: new blitz matches old", same)


def main() -> None:
    test_agent_is_abstract()
    test_sniper_basic()
    test_heuristic_waits()
    test_heuristic_defense_enabled()
    test_heuristic_orbital_aim_defaults_off()
    test_heuristic_orbital_aim_leads_orbiting_planet()
    test_heuristic_orbital_aim_keeps_static_target_current()
    test_heuristic_orbital_aim_handles_comet_path()
    test_peaking_basic()
    test_peaking_handles_moving_and_comet_targets()
    test_reset_clears_state()
    test_kaggle_adapter_shapes()
    test_kaggle_adapter_handles_namespace_obs()
    test_sniper_parity_with_old_implementation()
    test_heuristic_parity_with_old_blitz()
    print("\nAll agent smoke tests passed.")


if __name__ == "__main__":
    main()
