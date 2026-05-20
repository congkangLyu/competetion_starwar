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

from orbit_wars.analysis import (
    extract_states,
    load_kaggle_replay,
    render_replay_html,
)


def parse_player_names(raw: str | None) -> dict[int, str]:
    if not raw:
        return {}
    return {
        idx: name.strip()
        for idx, name in enumerate(raw.split(","))
        if name.strip()
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Render an Orbit Wars replay JSON.")
    ap.add_argument("replay_json", help="Path to a kaggle replay JSON")
    ap.add_argument("-o", "--output", default="replay.html",
                    help="Output HTML file (default: replay.html)")
    ap.add_argument("--player", type=int, default=0,
                    help="Whose POV to render (default: 0)")
    ap.add_argument("--show-orbits", action="store_true",
                    help="Draw dashed orbital circles for each planet")
    ap.add_argument("--names", default=None,
                    help="Comma-separated player names, e.g. 'ow_proto,blitz'")
    ap.add_argument("--width", type=int, default=600)
    ap.add_argument("--height", type=int, default=600)
    args = ap.parse_args()

    steps = load_kaggle_replay(args.replay_json)
    states = extract_states(steps, player=args.player)
    if not states:
        sys.exit(f"replay: no usable frames found in {args.replay_json}")

    out = Path(args.output)
    title = out.stem
    html = render_replay_html(
        states,
        title=title,
        player_names=parse_player_names(args.names),
        frame_width=args.width,
        show_orbits=args.show_orbits,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"replay: wrote {out} ({len(states)} frames)")


if __name__ == "__main__":
    main()
