"""
tools/build_submission.py

Bundle an Agent class plus the orbit_wars core it depends on into a
single, self-contained ``main.py`` that Kaggle's evaluator can submit
as-is. The strategy parameters are read from ``configs/<preset>.yaml``
and inlined as a Python literal, so the resulting file has no runtime
dependency on the orbit_wars package or on PyYAML.

Usage
-----
    python tools/build_submission.py blitz
    python tools/build_submission.py sentinel --output submissions/sentinel.py
    python tools/build_submission.py sniper

How the bundling works
----------------------
1. Read the YAML preset, learn which Agent class is the entrypoint.
2. Concatenate the source files of every module the agent depends on,
   in dependency order, after stripping:
     * ``from orbit_wars...`` imports (the modules are inlined below)
     * ``from __future__ import annotations`` (we emit one at the top)
     * ``if TYPE_CHECKING:`` blocks (their imports are inlined too)
3. Append a thin Kaggle adapter that instantiates the agent with the
   preset config and exposes a top-level ``def agent(obs): ...``.
4. Smoke-check the built file by importing it and running one turn on a
   fabricated observation. Fail loud if the result isn't a list.

If smoke-check fails the broken file is *kept on disk* so a human can
inspect what went wrong rather than getting a cryptic "build OK" with a
secretly broken submission.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml  # PyYAML, dev-only dep

ROOT = Path(__file__).resolve().parent.parent
CONFIGS_DIR = ROOT / "configs"

# Modules every agent needs.
SHARED_MODULES = [
    ROOT / "orbit_wars" / "core" / "geometry.py",
    ROOT / "orbit_wars" / "core" / "state.py",
    ROOT / "orbit_wars" / "agents" / "base.py",
]
# Per-agent additional modules.
AGENT_MODULES: dict[str, list[Path]] = {
    "SniperAgent":    [ROOT / "orbit_wars" / "agents" / "sniper.py"],
    "HeuristicAgent": [ROOT / "orbit_wars" / "agents" / "heuristic.py"],
    "PeakingAgent":   [ROOT / "orbit_wars" / "agents" / "peaking.py"],
}


def strip_local_imports(source: str) -> str:
    """Drop imports/blocks that don't make sense after concatenation."""
    # `if TYPE_CHECKING:` blocks with indented bodies
    source = re.sub(r"if TYPE_CHECKING:\s*\n(?:    [^\n]*\n)+", "", source)
    # Parenthesised multi-line `from orbit_wars... import (A, B, ...)`
    source = re.sub(
        r"from orbit_wars[\w.]*\s+import\s+\([^)]*\)\s*\n",
        "", source, flags=re.DOTALL,
    )
    # Single-line `from orbit_wars... import X` (also handles indented)
    source = re.sub(
        r"^\s*from orbit_wars[\w.]*\s+import\s+[^\n]*\n",
        "", source, flags=re.MULTILINE,
    )
    # `from __future__ import ...`
    source = re.sub(
        r"^from __future__ import[^\n]*\n",
        "", source, flags=re.MULTILINE,
    )
    return source


def render_config_kwargs(values: dict) -> str:
    if not values:
        return ""
    return "\n".join(f"    {k}={v!r}," for k, v in values.items())


def git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True,
        ).strip()
        return out or "unknown"
    except Exception:
        return "unknown"


def render_adapter(agent_name: str, config_values: dict) -> str:
    """Bottom-of-file Kaggle entrypoint."""
    if agent_name == "SniperAgent":
        return textwrap.dedent("""\
            # ====================================================================
            # Kaggle entrypoint
            # ====================================================================
            _kaggle_agent = make_kaggle_agent(SniperAgent)

            def agent(obs):
                return _kaggle_agent(obs)
            """)
    if agent_name == "HeuristicAgent":
        kwargs = render_config_kwargs(config_values)
        return (
            "# ====================================================================\n"
            "# Kaggle entrypoint\n"
            "# ====================================================================\n"
            "_config = HeuristicConfig(\n"
            f"{kwargs}\n"
            ")\n"
            "_kaggle_agent = make_kaggle_agent(HeuristicAgent, config=_config)\n"
            "\n"
            "def agent(obs):\n"
            "    return _kaggle_agent(obs)\n"
        )
    if agent_name == "PeakingAgent":
        kwargs = render_config_kwargs(config_values)
        return (
            "# ====================================================================\n"
            "# Kaggle entrypoint\n"
            "# ====================================================================\n"
            "_config = PeakingConfig(\n"
            f"{kwargs}\n"
            ")\n"
            "_kaggle_agent = make_kaggle_agent(PeakingAgent, config=_config)\n"
            "\n"
            "def agent(obs):\n"
            "    return _kaggle_agent(obs)\n"
        )
    sys.exit(f"build: unknown agent class '{agent_name}'")


def render_header(preset: str, cfg: dict) -> str:
    desc = (cfg.get("description") or "").strip()
    return (
        f'"""\n'
        f'Orbit Wars submission -- preset: {preset}\n'
        f'\n'
        f'AUTO-GENERATED -- DO NOT EDIT BY HAND.\n'
        f'Source: configs/{preset}.yaml + orbit_wars/ package\n'
        f'Built:  {dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}\n'
        f'Commit: {git_commit()}\n'
        f'\n'
        f'{desc}\n'
        f'"""\n'
        f'from __future__ import annotations\n'
    )


def build(preset: str) -> str:
    cfg_path = CONFIGS_DIR / f"{preset}.yaml"
    if not cfg_path.is_file():
        sys.exit(f"build: config not found: {cfg_path}")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    agent_name = cfg.get("agent")
    if agent_name not in AGENT_MODULES:
        sys.exit(
            f"build: '{agent_name}' is not a known agent class. "
            f"Known: {sorted(AGENT_MODULES)}"
        )

    parts: list[str] = [render_header(preset, cfg)]
    for mod_path in SHARED_MODULES + AGENT_MODULES[agent_name]:
        rel = mod_path.relative_to(ROOT).as_posix()
        parts.append(f"\n# {'='*68}\n# inlined from {rel}\n# {'='*68}\n")
        parts.append(strip_local_imports(mod_path.read_text(encoding="utf-8")))

    parts.append("\n")
    parts.append(render_adapter(agent_name, cfg.get("config") or {}))
    return "".join(parts)


def smoke_check(output_path: Path) -> None:
    """Import the built file and run a few turns on a fabricated obs."""
    mod_name = f"built_{output_path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, output_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    if not callable(getattr(mod, "agent", None)):
        sys.exit("smoke: built file does not expose a callable `agent`")

    sample = {
        "player": 0,
        "planets": [
            [0, 0, 20.0, 20.0, 2.0, 100, 3],
            [1, -1, 60.0, 60.0, 1.5, 5, 2],
            [2, -1, 30.0, 70.0, 1.5, 8, 2],
        ],
        "fleets": [],
        "angular_velocity": 0.03,
        "initial_planets": [
            [0, 0, 20.0, 20.0, 2.0, 100, 3],
            [1, -1, 60.0, 60.0, 1.5, 5, 2],
            [2, -1, 30.0, 70.0, 1.5, 8, 2],
        ],
        "comets": [],
        "comet_planet_ids": [],
        "remainingOverageTime": 60.0,
    }
    result = None
    for _ in range(5):
        result = mod.agent(sample)
    if not isinstance(result, list):
        sys.exit(f"smoke: agent returned {type(result).__name__}, expected list")
    print(f"smoke: agent() ok, last turn produced {len(result)} moves")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a single-file Kaggle submission from a preset YAML.")
    ap.add_argument("preset", help="Preset name under configs/")
    ap.add_argument("-o", "--output", default="main.py",
                    help="Output file (default: main.py at project root)")
    ap.add_argument("--no-check", action="store_true",
                    help="Skip the post-build smoke check")
    args = ap.parse_args()

    out = (ROOT / args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(args.preset), encoding="utf-8")
    try:
        shown = out.relative_to(ROOT).as_posix()
    except ValueError:
        shown = str(out)
    print(f"build: wrote {shown} "
          f"({out.stat().st_size} bytes, "
          f"{out.read_text(encoding='utf-8').count(chr(10)) + 1} lines)")

    if not args.no_check:
        smoke_check(out)


if __name__ == "__main__":
    main()
