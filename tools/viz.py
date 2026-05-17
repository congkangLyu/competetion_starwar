"""tools/viz.py -- CLI that turns a kaggle replay JSON into a self-contained
HTML page with a turn slider.

Typical workflow
----------------
1. Run a local game and let the env dump its replay::

       from kaggle_environments import make
       env = make("orbit_wars", configuration={"seed": 7}, debug=False)
       env.run(["main.py", "random"])
       Path("replays/g7.json").write_text(env.toJSON())

   Or download one from kaggle::

       kaggle competitions replay <episode_id> -p replays/

2. Render it::

       python tools/viz.py replays/g7.json -o out.html

3. Optional: overlay the agent's decision rationale::

       python tools/viz.py replays/g7.json --decisions decisions_p0.jsonl -o out.html

The output is a single HTML file (no server needed) with a time slider
and a play/pause button.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orbit_wars.agents import load_decisions_jsonl
from orbit_wars.analysis import (
    extract_states,
    load_kaggle_replay,
    render_replay_html,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Render an Orbit Wars replay JSON to a single-file HTML viewer."
    )
    ap.add_argument("replay", help="path to a kaggle replay JSON")
    ap.add_argument("-o", "--output", default="replay.html",
                    help="output HTML path (default replay.html)")
    ap.add_argument("--player", type=int, default=0,
                    help="which player's view to render (affects nothing\n"
                         "visible -- planets/fleets are global -- but is\n"
                         "used to label the state.my_planets slice)")
    ap.add_argument("--decisions", default=None,
                    help="optional decisions JSONL to overlay (intent rays)")
    ap.add_argument("--title", default=None,
                    help="custom HTML title")
    ap.add_argument("--width", type=int, default=640,
                    help="rendered SVG pixel width (default 640)")
    args = ap.parse_args()

    steps = load_kaggle_replay(args.replay)
    states = extract_states(steps, player=args.player)

    decisions_by_step: dict[int, list] = {}
    if args.decisions:
        for d in load_decisions_jsonl(args.decisions):
            decisions_by_step.setdefault(d.step, []).append(d)

    title = args.title or f"Orbit Wars replay -- {Path(args.replay).name}"
    html = render_replay_html(
        states,
        decisions_by_step=decisions_by_step,
        title=title,
        frame_width=args.width,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(
        f"viz: wrote {out} "
        f"({len(states)} frames, {len(html)} bytes, "
        f"{sum(len(v) for v in decisions_by_step.values())} decisions overlaid)"
    )


if __name__ == "__main__":
    main()
