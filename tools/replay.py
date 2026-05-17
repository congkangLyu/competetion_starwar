"""tools/replay.py -- render a kaggle replay JSON into an HTML timeline.

Usage
-----
    # Render a downloaded kaggle replay
    python tools/replay.py replays/abc.json -o replay.html

    # Same thing with orbital paths drawn
    python tools/replay.py replays/abc.json -o replay.html --show-orbits

    # View as player 1's POV
    python tools/replay.py replays/abc.json --player 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orbit_wars.analysis.replay import states_from_replay
from orbit_wars.analysis.viz import render_timeline


def main() -> None:
    ap = argparse.ArgumentParser(description="Render an Orbit Wars replay JSON.")
    ap.add_argument("replay_json", help="Path to a kaggle replay JSON")
    ap.add_argument("-o", "--output", default="replay.html",
                    help="Output HTML file (default: replay.html)")
    ap.add_argument("--player", type=int, default=0,
                    help="Whose POV to render (default: 0)")
    ap.add_argument("--show-orbits", action="store_true",
                    help="Draw dashed orbital circles for each planet")
    ap.add_argument("--width", type=int, default=600)
    ap.add_argument("--height", type=int, default=600)
    args = ap.parse_args()

    states = states_from_replay(args.replay_json, player=args.player)
    if not states:
        sys.exit(f"replay: no usable frames found in {args.replay_json}")

    out = Path(args.output)
    title = out.stem
    render_timeline(
        states,
        title=title,
        width=args.width,
        height=args.height,
        show_orbits=args.show_orbits,
        output_path=out,
    )
    print(f"replay: wrote {out} ({len(states)} frames)")


if __name__ == "__main__":
    main()
