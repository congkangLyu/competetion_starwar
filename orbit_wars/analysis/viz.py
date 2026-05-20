"""
SVG / HTML renderers for Orbit Wars game states.

Two functions cover the common cases:

* :func:`render_frame_svg` returns a standalone ``<svg>...</svg>`` for
  a single :class:`GameState`. Useful for inline in notebooks, for
  composing into a GIF, or for ad-hoc inspection.
* :func:`render_replay_html` glues a list of frames into a small
  self-contained HTML page with a time slider and play/pause button.
  No external assets; opens in any modern browser.

Both renderers are **pure string builders** -- no matplotlib, no PIL,
no kaggle dependency. They work in the sandbox and in any environment
that can run Python.

Decision overlays
-----------------
Pass a ``decisions_by_step`` mapping into :func:`render_replay_html`
to draw the intent line for each decision: a dashed yellow ray from
the source planet in the direction the agent fired. Useful when
debugging why an agent picked the targets it did.
"""

from __future__ import annotations

import html as _html
import json
import math
from typing import Iterable

from orbit_wars.agents.base import Decision
from orbit_wars.core.geometry import BOARD_SIZE, SUN_R, SUN_X, SUN_Y, dist, is_orbiting
from orbit_wars.core.state import GameState


# ─── Colour palette ──────────────────────────────────────────────────────
PLAYER_COLORS: dict[int, str] = {
    -1: "#888a99",   # neutral
    0:  "#3b82f6",   # blue
    1:  "#ef4444",   # red
    2:  "#10b981",   # green
    3:  "#f59e0b",   # amber
}


def _color_for(owner: int) -> str:
    return PLAYER_COLORS.get(owner, "#888a99")


def _player_label(player: int, player_names: dict[int, str] | None = None) -> str:
    if player_names and player in player_names:
        return player_names[player]
    if player == -1:
        return "Neutral"
    return f"Player {player}"


def _players_in(states: list[GameState]) -> list[int]:
    owners = {
        p.owner
        for state in states
        for p in state.planets
        if p.owner >= 0
    }
    owners.update({
        f.owner
        for state in states
        for f in state.fleets
        if f.owner >= 0
    })
    return sorted(owners)


def _render_player_legend(
    players: list[int],
    player_names: dict[int, str] | None,
) -> str:
    if not players:
        return ""
    items = []
    for player in players:
        label = _html.escape(_player_label(player, player_names))
        color = _color_for(player)
        items.append(
            '<span class="player">'
            f'<span class="swatch" style="background:{color}"></span>'
            f'<span class="pid">P{player}</span>'
            f'<span>{label}</span>'
            '</span>'
        )
    return '<div class="players">' + "".join(items) + "</div>\n"


# ─── Single-frame SVG ────────────────────────────────────────────────────
def render_frame_svg(
    state: GameState,
    *,
    width: int = 640,
    decisions_at_step: Iterable[Decision] | None = None,
    show_fleet_arrows: bool = True,
    show_comet_marks: bool = True,
    show_orbits: bool = False,
) -> str:
    """Return a self-contained SVG string of one game state.

    The viewBox spans the 100x100 board so all coordinates are in board
    units. ``width`` is the rendered pixel size of the resulting SVG.
    """
    parts: list[str] = []
    parts.append(
        f'<svg viewBox="0 0 {BOARD_SIZE} {BOARD_SIZE}" '
        f'width="{width}" height="{width}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'style="background:#0a0e1a; font-family:monospace;">'
    )
    # Sun + corona
    parts.append(
        f'<circle cx="{SUN_X}" cy="{SUN_Y}" r="{SUN_R + 3}" '
        f'fill="none" stroke="#fbbf24" stroke-width="0.3" opacity="0.25"/>'
    )
    parts.append(
        f'<circle cx="{SUN_X}" cy="{SUN_Y}" r="{SUN_R}" '
        f'fill="#fbbf24" opacity="0.9"/>'
    )

    if show_orbits:
        orbit_radii = sorted({
            round(dist(p.x, p.y, SUN_X, SUN_Y), 3)
            for p in state.initial_planets
            if is_orbiting(p.x, p.y, p.radius)
        })
        for radius in orbit_radii:
            parts.append(
                f'<circle cx="{SUN_X}" cy="{SUN_Y}" r="{radius}" '
                f'fill="none" stroke="#94a3b8" stroke-width="0.15" '
                f'stroke-dasharray="0.8 0.8" opacity="0.45"/>'
            )

    # Planets
    comet_ids = set(state.comet_planet_ids)
    for p in state.planets:
        col = _color_for(p.owner)
        is_comet = p.id in comet_ids
        # The body
        if is_comet and show_comet_marks:
            parts.append(
                f'<circle cx="{p.x}" cy="{p.y}" r="{max(p.radius, 0.8)}" '
                f'fill="{col}" stroke="#fff" stroke-width="0.3" '
                f'stroke-dasharray="0.4 0.4"/>'
            )
        else:
            parts.append(
                f'<circle cx="{p.x}" cy="{p.y}" r="{p.radius}" '
                f'fill="{col}" stroke="white" stroke-width="0.15"/>'
            )
        # Ship count label centred
        parts.append(
            f'<text x="{p.x}" y="{p.y + 0.6}" font-size="1.8" '
            f'fill="white" text-anchor="middle" '
            f'style="paint-order:stroke; stroke:#000; stroke-width:0.3px;">'
            f'{int(p.ships)}</text>'
        )

    # Fleets
    if show_fleet_arrows:
        for f in state.fleets:
            col = _color_for(f.owner)
            dx = math.cos(f.angle)
            dy = math.sin(f.angle)
            tip_x = f.x + dx * 2.2
            tip_y = f.y + dy * 2.2
            # Body + heading line
            parts.append(
                f'<circle cx="{f.x}" cy="{f.y}" r="0.55" fill="{col}"/>'
            )
            parts.append(
                f'<line x1="{f.x}" y1="{f.y}" x2="{tip_x}" y2="{tip_y}" '
                f'stroke="{col}" stroke-width="0.35" stroke-linecap="round"/>'
            )
            # Ship count beside the arrow
            parts.append(
                f'<text x="{tip_x + dx*1.3}" y="{tip_y + dy*1.3 + 0.4}" '
                f'font-size="1.4" fill="{col}" text-anchor="middle">{int(f.ships)}</text>'
            )

    # Decision overlay (dashed yellow rays)
    if decisions_at_step:
        for d in decisions_at_step:
            src = state.planet_by_id.get(d.move.from_planet_id)
            if src is None:
                continue
            tx = src.x + math.cos(d.move.angle) * 8
            ty = src.y + math.sin(d.move.angle) * 8
            parts.append(
                f'<line x1="{src.x}" y1="{src.y}" x2="{tx}" y2="{ty}" '
                f'stroke="#fef08a" stroke-width="0.25" '
                f'stroke-dasharray="0.6 0.4" opacity="0.7"/>'
            )

    # Turn number + score badge
    score = state.total_ships_by_owner
    score_txt = " ".join(
        f'P{k}={v}' for k, v in sorted(score.items())
    ) or "-"
    parts.append(
        f'<text x="2" y="4" font-size="2.5" fill="#eee">'
        f't={state.step}</text>'
    )
    parts.append(
        f'<text x="{BOARD_SIZE - 2}" y="4" font-size="2.2" fill="#eee" '
        f'text-anchor="end">{_html.escape(score_txt)}</text>'
    )

    parts.append('</svg>')
    return "\n".join(parts)


# ─── Multi-frame HTML with slider ────────────────────────────────────────
def render_replay_html(
    states: list[GameState],
    *,
    decisions_by_step: dict[int, list[Decision]] | None = None,
    player_names: dict[int, str] | None = None,
    title: str = "Orbit Wars replay",
    frame_width: int = 640,
    autoplay_ms: int = 100,
    show_orbits: bool = False,
) -> str:
    """Return a standalone HTML document with a time-slider replay.

    Pre-renders every frame as SVG (eagerly inlined into the page as a
    JavaScript array), so the result is a single file that can be opened
    in any browser without a server.
    """
    decisions_by_step = decisions_by_step or {}
    rendered: list[str] = []
    for s in states:
        decs = decisions_by_step.get(s.step, [])
        rendered.append(
            render_frame_svg(
                s,
                width=frame_width,
                decisions_at_step=decs,
                show_orbits=show_orbits,
            )
        )
    frames_js = json.dumps(rendered)
    player_legend = _render_player_legend(_players_in(states), player_names)

    return (
        "<!doctype html>\n"
        '<html lang="en"><head>\n'
        '<meta charset="utf-8">\n'
        f"<title>{_html.escape(title)}</title>\n"
        "<style>\n"
        "  body{font-family:monospace;background:#111;color:#eee;margin:0;padding:24px}\n"
        f"  .wrap{{max-width:{frame_width + 40}px;margin:0 auto}}\n"
        "  .frame{background:#000;border-radius:8px;overflow:hidden;line-height:0}\n"
        "  .controls{margin-top:16px}\n"
        "  .label{display:flex;justify-content:space-between;font-size:13px;margin-bottom:6px}\n"
        "  input[type=range]{width:100%}\n"
        "  button{background:#374151;color:#eee;border:0;padding:6px 14px;cursor:pointer;border-radius:4px;font-family:inherit}\n"
        "  button:hover{background:#4b5563}\n"
        "  h2{font-weight:normal;font-size:18px;margin:0 0 16px 0}\n"
        "  .players{display:flex;flex-wrap:wrap;gap:10px 16px;margin:-6px 0 14px 0;font-size:13px}\n"
        "  .player{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}\n"
        "  .swatch{width:10px;height:10px;border-radius:50%;display:inline-block;border:1px solid rgba(255,255,255,.45)}\n"
        "  .pid{color:#aeb7c7}\n"
        "</style>\n"
        "</head><body>\n"
        '<div class="wrap">\n'
        f"<h2>{_html.escape(title)}</h2>\n"
        f"{player_legend}"
        '<div class="frame" id="f"></div>\n'
        '<div class="controls">\n'
        '<div class="label"><span>turn <span id="t">0</span> / '
        f"{max(0, len(rendered)-1)}</span>"
        '<span><button id="p">play</button> '
        '<button id="r">restart</button></span></div>\n'
        f'<input type="range" id="s" min="0" max="{max(0, len(rendered)-1)}" value="0">\n'
        "</div></div>\n"
        "<script>\n"
        f"var F={frames_js};\n"
        "var f=document.getElementById('f'),s=document.getElementById('s'),"
        "t=document.getElementById('t'),p=document.getElementById('p'),"
        "r=document.getElementById('r');\n"
        "function show(i){i=Math.max(0,Math.min(F.length-1,parseInt(i)||0));"
        "f.innerHTML=F[i];t.textContent=i;s.value=i;}\n"
        "s.addEventListener('input',function(){show(s.value);});\n"
        "var playing=false,tm;\n"
        "p.addEventListener('click',function(){playing=!playing;p.textContent=playing?'pause':'play';"
        "if(playing){tm=setInterval(function(){var v=parseInt(s.value);"
        f"if(v>=F.length-1){{playing=false;p.textContent='play';clearInterval(tm);return;}}show(v+1);}},{autoplay_ms});"
        "}else{clearInterval(tm);}});\n"
        "r.addEventListener('click',function(){show(0);});\n"
        "show(0);\n"
        "</script>\n"
        "</body></html>\n"
    )
