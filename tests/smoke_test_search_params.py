"""Smoke tests for tools/search_params.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import search_params  # noqa: E402


def check(label: str, cond: bool) -> None:
    if cond:
        print(f"  [OK ] {label}")
    else:
        print(f"  [FAIL] {label}")
        raise AssertionError(label)


def test_extract_parameter_space_shapes() -> None:
    print("test_extract_parameter_space_shapes")
    direct = search_params.extract_parameter_space({"a": [1, 2]})
    via_config = search_params.extract_parameter_space({"config": {"b": [3]}})
    via_params = search_params.extract_parameter_space({"parameters": {"c": [4]}})
    check("direct mapping accepted", direct == {"a": [1, 2]})
    check("config mapping accepted", via_config == {"b": [3]})
    check("parameters mapping accepted", via_params == {"c": [4]})

    try:
        search_params.extract_parameter_space({"parameters": {"bad": 1}})
    except ValueError:
        check("scalar search value rejected", True)
    else:
        check("scalar search value rejected", False)


def test_candidate_selection() -> None:
    print("test_candidate_selection")
    space = {"a": [1, 2], "b": ["x", "y", "z"]}
    grid = search_params.choose_parameter_sets(
        space, mode="grid", samples=None, seed=123
    )
    limited = search_params.choose_parameter_sets(
        space, mode="grid", samples=2, seed=123
    )
    random_a = search_params.choose_parameter_sets(
        space, mode="random", samples=3, seed=123
    )
    random_b = search_params.choose_parameter_sets(
        space, mode="random", samples=3, seed=123
    )
    check("grid has cartesian product", len(grid) == 6)
    check("grid limit works", len(limited) == 2)
    check("random sample count works", len(random_a) == 3)
    check("random sampling deterministic", random_a == random_b)


def test_build_candidate_from_config_imports() -> None:
    print("test_build_candidate_from_config_imports")
    base = search_params.load_yaml(ROOT / "configs" / "ow_proto.yaml")
    candidate = search_params.make_candidate(
        base,
        {"wait_turns": 1, "formula_prod_mult": 22.0},
        index=0,
        prefix="test_search",
    )
    source = search_params.build_from_config(candidate.name, candidate.config)
    check("built source has entrypoint", "def agent(obs):" in source)
    check("built source mentions preset", "preset: test_search_000" in source)

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "candidate.py"
        path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("built_search_candidate", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["built_search_candidate"] = mod
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        check("agent callable", callable(getattr(mod, "agent", None)))


def test_cli_dry_run_writes_candidates() -> None:
    print("test_cli_dry_run_writes_candidates")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        space_path = tmp / "space.yaml"
        out_dir = tmp / "out"
        space_path.write_text(
            yaml.safe_dump(
                {"parameters": {"wait_turns": [1], "formula_dist": [80.0, 100.0]}},
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable,
                "tools/search_params.py",
                "configs/ow_proto.yaml",
                str(space_path),
                "--mode",
                "grid",
                "--out",
                str(out_dir),
                "--dry-run",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)
        check("dry-run exits zero", result.returncode == 0)
        candidates = sorted((out_dir / "candidates").glob("*.yaml"))
        built = sorted((out_dir / "built").glob("*.py"))
        check("two candidate YAMLs written", len(candidates) == 2)
        check("two built files written", len(built) == 2)
        loaded = yaml.safe_load(candidates[0].read_text(encoding="utf-8"))
        check("candidate keeps OwProtoAgent", loaded["agent"] == "OwProtoAgent")
        check("candidate has overridden config", "formula_dist" in loaded["config"])


def test_result_writer_ranks_and_writes_best() -> None:
    print("test_result_writer_ranks_and_writes_best")
    base = search_params.load_yaml(ROOT / "configs" / "ow_proto.yaml")
    c0 = search_params.make_candidate(base, {"wait_turns": 1}, index=0, prefix="rank")
    c1 = search_params.make_candidate(base, {"wait_turns": 2}, index=1, prefix="rank")
    r0 = search_params.CandidateResult(c0, 4, 2, 0, 2, 0.5, 0.0, 10.0, None)
    r1 = search_params.CandidateResult(c1, 4, 3, 0, 1, 0.75, 1.0, 20.0, None)

    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        for c in (c0, c1):
            search_params.write_candidate(c, out)
        ranked = search_params.write_results([r0, r1], out_dir=out, top_k=1)
        check("best candidate first", ranked[0].candidate.name == c1.name)
        check("results.csv written", (out / "results.csv").is_file())
        check("results.json written", (out / "results.json").is_file())
        check("best.yaml written", (out / "best.yaml").is_file())
        data = json.loads((out / "results.json").read_text(encoding="utf-8"))
        check("json has two rows", len(data) == 2)
        check("top copy written", len(list((out / "top").glob("*.yaml"))) == 1)


def main() -> None:
    test_extract_parameter_space_shapes()
    test_candidate_selection()
    test_build_candidate_from_config_imports()
    test_cli_dry_run_writes_candidates()
    test_result_writer_ranks_and_writes_best()
    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    main()
