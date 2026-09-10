#!/usr/bin/env python3
"""Draw the graph that /crucible:graph computes.

Crucible's graphify ranks the repository with a personalised PageRank over
def/ref edges and prints a budgeted text map for an agent to read. That is the
right output for an agent and the wrong one for a person: a ranked list does not
show you that one module carries a sixth of the graph, or which parts of the
package only ever talk through it.

This renders the same numbers — graphify's own build_graph and pagerank, not a
reimplementation — as one self-contained HTML page: nodes sized by rank share,
edges weighted by reference strength, coloured by architectural layer, with any
import that runs against the declared layering drawn hot.

    python3 scripts/graph_view.py                    # → artifacts/<today>/graph.html
    python3 scripts/graph_view.py --open             # and open it
    python3 scripts/graph_view.py --focus data/cache.py
    python3 scripts/graph_view.py --top 20 --no-tests

The layout is computed here with a fixed seed, so the same repository state
draws the same picture — the page animates into a reproducible arrangement
rather than settling somewhere new on every load.

Stdlib only. Nothing imports this; it is operational glue.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import webbrowser
from datetime import date
from pathlib import Path

EXIT_OK = 0
EXIT_CANNOT_TELL = 2

LAYER_ORDER = [
    "configuration",
    "data",
    "features",
    "models",
    "backtest",
    "evaluation",
    "reporting",
    "orchestration",
    "tests",
    "scripts",
    "other",
]

# A spectrum, cool to warm, walking up the dependency stack. Deliberately not a
# categorical palette: adjacency in hue means adjacency in the architecture.
LAYER_COLOUR = {
    "configuration": "#4DE1C1",
    "data": "#3FB6E8",
    "features": "#6C8BF5",
    "models": "#A472F0",
    "backtest": "#D96BE0",
    "evaluation": "#F26BAE",
    "reporting": "#FF8A6B",
    "orchestration": "#FFC24D",
    "tests": "#6E7A8C",
    "scripts": "#8C93A3",
    "other": "#5A6272",
}

PACKAGE_SEGMENT = "economic_regime_forecasting"

# The arrangement is an ellipse, not a circle: a landscape viewport has more
# width than height, and a circle wastes the difference.
ASPECT = 1.5


# ---------------------------------------------------------------- graphify


def find_graphify(explicit: str | None) -> Path:
    """Locate graphify.py, or say exactly where we looked.

    Order matters. The **installed** plugin wins over any local checkout of
    Foundry: this repository consumes Crucible through the marketplace, so the
    picture must come from the version that is installed, not from whichever
    branch a sibling working tree happens to have checked out. The local
    checkout stays last as a development fallback.
    """
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        candidates.append(Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "scripts" / "graphify.py")

    home = Path.home()
    # Installed by the marketplace: ~/.claude/plugins/cache/<market>/crucible/<version>/
    installed = sorted(
        home.glob(".claude/plugins/cache/*/crucible/*/scripts/graphify.py"), reverse=True
    )
    candidates += installed
    candidates += sorted(home.glob(".claude/plugins/*/crucible/scripts/graphify.py"))
    candidates += sorted(home.glob(".claude/plugins/*/plugins/crucible/scripts/graphify.py"))
    # Development fallback: a sibling checkout of the Foundry repository itself.
    candidates.append(
        home / "Projects" / "Foundry" / "plugins" / "crucible" / "scripts" / "graphify.py"
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    looked = "\n  ".join(str(c) for c in candidates)
    raise SystemExit(
        "graph_view: cannot find graphify.py. Install the crucible plugin, or pass\n"
        "  --graphify /path/to/crucible/scripts/graphify.py\n"
        f"Looked in:\n  {looked}"
    )


def load_graph(graphify_path: Path, root: Path, focus: list[str]) -> tuple[dict, dict, dict]:
    """Refresh graphify's index, then borrow its own graph and ranking."""
    subprocess.run(
        [sys.executable, str(graphify_path), "scan"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=300,
    )
    sys.path.insert(0, str(graphify_path.parent))
    try:
        import graphify  # type: ignore
    except Exception as error:
        raise SystemExit(
            f"graph_view: could not import graphify from {graphify_path}: {error}"
        ) from error

    cache = graphify.load_cache(root)
    if not cache.get("files"):
        raise SystemExit(
            "graph_view: graphify's index is empty. Run `/crucible:graph` (or "
            f"`python3 {graphify_path} scan`) in {root} first."
        )
    focus_files = {f for f in focus if f in cache["files"]}
    edges, _defines, _weight = graphify.build_graph(cache, set(), focus_files)
    ranks = graphify.pagerank(list(cache["files"].keys()), edges, focus_files)
    return cache, edges, ranks


# ---------------------------------------------------------------- shaping


def layer_of(relative_path: str) -> str:
    parts = Path(relative_path).parts
    if parts and parts[0] == "tests":
        return "tests"
    if parts and parts[0] == "scripts":
        return "scripts"
    if PACKAGE_SEGMENT in parts:
        index = parts.index(PACKAGE_SEGMENT)
        rest = parts[index + 1 :]
        if len(rest) > 1:
            return rest[0] if rest[0] in LAYER_COLOUR else "other"
        return "orchestration"
    return "other"


def violation_edges(root: Path) -> set[tuple[str, str]]:
    """Layer-rule violations, as (from_layer, to_layer) pairs, if the check runs."""
    checker = root / "scripts" / "layer_check.py"
    if not checker.is_file():
        return set()
    try:
        completed = subprocess.run(
            [sys.executable, str(checker), "--json"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(completed.stdout or "{}")
    except Exception:
        return set()
    return {
        (v.get("from", ""), v.get("to", "")) for v in payload.get("violations", []) if v.get("to")
    }


def arrange(nodes: list[dict], seed: int, iterations: int = 160) -> dict[str, list[float]]:
    """Place nodes so the picture states the two facts worth reading.

    Distance from the centre is rank: the load-bearing modules sit in the middle
    because that is what carrying the graph looks like. Angle is layer, so the
    architecture reads as sectors. A free force layout on a graph this dense
    (58 files, ~18 edges each) collapses into a hairball that says neither.

    After placing, a repulsion-only relaxation pushes overlapping labels apart
    while a radial spring holds each node near its own rank ring — declumping
    without destroying the meaning of the coordinates.
    """
    count = len(nodes)
    if count == 0:
        return {}
    rng = random.Random(seed)

    by_layer: dict[str, list[dict]] = {}
    for node in nodes:
        by_layer.setdefault(node["layer"], []).append(node)
    layers_present = [layer for layer in LAYER_ORDER if layer in by_layer]

    ordered = sorted(nodes, key=lambda n: -n["share"])
    rank_index = {node["id"]: i for i, node in enumerate(ordered)}

    sectors: dict[str, tuple[float, float]] = {}
    positions: dict[str, list[float]] = {}
    radii: dict[str, float] = {}
    cursor = 0.0
    for layer in layers_present:
        members = by_layer[layer]
        span = 2 * math.pi * len(members) / count
        sectors[layer] = (cursor, cursor + span)
        # Inside a sector, walk the ring in rank order so neighbours are peers.
        members.sort(key=lambda n: rank_index[n["id"]])
        for k, node in enumerate(members):
            fraction = (k + 0.5) / len(members)
            angle = cursor + span * fraction
            depth = rank_index[node["id"]] / max(count - 1, 1)
            radius = 105 + 430 * (depth**0.78) + rng.uniform(-14, 14)
            radii[node["id"]] = radius
            positions[node["id"]] = [radius * math.cos(angle), radius * math.sin(angle)]
        cursor += span

    ids = [node["id"] for node in nodes]
    size = {node["id"]: 4 + math.sqrt(node["share"]) * 62 for node in nodes}

    for _ in range(iterations):
        shift = {node_id: [0.0, 0.0] for node_id in ids}
        for i, a in enumerate(ids):
            ax, ay = positions[a]
            for b in ids[i + 1 :]:
                dx = ax - positions[b][0]
                dy = ay - positions[b][1]
                distance = math.hypot(dx, dy) or 0.01
                floor = size[a] + size[b] + 26
                if distance >= floor:
                    continue
                push = (floor - distance) * 0.5
                ux, uy = dx / distance, dy / distance
                shift[a][0] += ux * push
                shift[a][1] += uy * push
                shift[b][0] -= ux * push
                shift[b][1] -= uy * push
        for node_id in ids:
            x = positions[node_id][0] + shift[node_id][0] * 0.5
            y = positions[node_id][1] + shift[node_id][1] * 0.5
            # Hold the rank ring: the radius is information, the angle is slack.
            distance = math.hypot(x, y) or 0.01
            wanted = radii[node_id]
            corrected = distance + (wanted - distance) * 0.35
            positions[node_id] = [x / distance * corrected, y / distance * corrected]

    for node in nodes:
        node["x"] = round(positions[node["id"]][0] * ASPECT, 2)
        node["y"] = round(positions[node["id"]][1], 2)

    return {
        layer: [round(sectors[layer][0], 4), round(sectors[layer][1], 4)]
        for layer in layers_present
    }


def build_payload(
    root: Path, cache: dict, edges: dict, ranks: dict, top: int, include_tests: bool, seed: int
) -> dict:
    total = sum(ranks.values()) or 1.0
    keep = {path for path in cache["files"] if include_tests or layer_of(path) != "tests"}

    nodes = []
    for path in sorted(keep):
        outgoing = edges.get(path, {})
        incoming = sum(1 for source, targets in edges.items() if path in targets and source in keep)
        nodes.append(
            {
                "id": path,
                "name": Path(path).name,
                "layer": layer_of(path),
                "share": ranks.get(path, 0.0) / total,
                "defs": len(cache["files"][path].get("defs", [])),
                "in": incoming,
                "out": sum(1 for target in outgoing if target in keep),
            }
        )

    ranked = sorted(nodes, key=lambda n: -n["share"])
    for position, node in enumerate(ranked, 1):
        node["rank"] = position

    max_weight = 0.0
    links = []
    for source, targets in edges.items():
        if source not in keep:
            continue
        for target, weight in targets.items():
            if target not in keep:
                continue
            max_weight = max(max_weight, weight)
            links.append({"source": source, "target": target, "weight": weight})

    wrong_way = violation_edges(root)
    layer_by_id = {node["id"]: node["layer"] for node in nodes}
    for link in links:
        link["weight"] = round(link["weight"] / (max_weight or 1.0), 4)
        pair = (layer_by_id.get(link["source"], ""), layer_by_id.get(link["target"], ""))
        link["wrong"] = pair in wrong_way

    sectors = arrange(nodes, seed)
    rim = max((math.hypot(n["x"] / ASPECT, n["y"]) for n in nodes), default=520) + 26

    return {
        "generated_on": date.today().isoformat(),
        "repository": root.name,
        "engine": cache.get("engine") or "unknown",
        "scanned_at": cache.get("scanned_at"),
        "node_count": len(nodes),
        "link_count": len(links),
        "wrong_way_count": sum(1 for link in links if link["wrong"]),
        "top": top,
        "layer_colour": LAYER_COLOUR,
        "layer_order": LAYER_ORDER,
        "aspect": ASPECT,
        "rim": round(rim, 1),
        "rings": [round(rim * f, 1) for f in (0.2, 0.45, 0.72, 0.95)],
        "sectors": sectors,
        "nodes": nodes,
        "links": links,
    }


# ---------------------------------------------------------------- the page

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
  --void:#05070E; --deep:#080B15; --panel:rgba(14,19,33,.82); --edge:rgba(120,150,210,.16);
  --ink:#E8EEFB; --dim:#8FA0C0; --faint:#5C6C8C; --hot:#FF6B57; --line:rgba(120,150,210,.14);
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0; background:var(--void); color:var(--ink); overflow:hidden;
  font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px;
}
#stage{position:fixed; inset:0}
canvas{display:block; width:100%; height:100%; cursor:grab}
canvas.dragging{cursor:grabbing}

.hud{position:fixed; pointer-events:none; z-index:5}
.hud > *{pointer-events:auto}

#head{top:0; left:0; right:0; padding:18px 22px 26px;
  background:linear-gradient(180deg,rgba(5,7,14,.94) 0%,rgba(5,7,14,.72) 55%,transparent 100%)}
#head h1{margin:0; font-size:15px; font-weight:600; letter-spacing:.14em; text-transform:uppercase}
#head h1 span{color:var(--dim); font-weight:400}
#head .sub{margin-top:5px; color:var(--faint); font-size:11.5px; letter-spacing:.04em}

#side{top:86px; left:22px; width:330px; max-height:calc(100vh - 130px); display:flex; flex-direction:column; gap:12px}
.card{background:var(--panel); border:1px solid var(--line); border-radius:10px;
  backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); overflow:hidden}
.card h2{margin:0; padding:11px 14px 9px; font-size:10px; letter-spacing:.16em; text-transform:uppercase;
  color:var(--dim); font-weight:500; border-bottom:1px solid var(--line)}
#godlist{list-style:none; margin:0; padding:6px; overflow-y:auto; max-height:44vh}
#godlist li{display:grid; grid-template-columns:22px 1fr auto; gap:9px; align-items:center;
  padding:6px 8px; border-radius:6px; cursor:pointer; transition:background .12s}
#godlist li:hover,#godlist li.on{background:rgba(120,160,240,.12)}
#godlist .n{color:var(--faint); font-size:10.5px; text-align:right}
#godlist .nm{overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12px}
#godlist .nm b{font-weight:500}
#godlist .nm i{font-style:normal; color:var(--faint); font-size:10.5px; display:block}
#godlist .sh{font-size:11px; color:var(--dim); font-variant-numeric:tabular-nums}
.bar{height:2px; background:var(--edge); border-radius:2px; margin-top:3px; overflow:hidden}
.bar i{display:block; height:100%; border-radius:2px}

#legend{padding:9px 12px 12px; display:flex; flex-wrap:wrap; gap:5px}
.lg{display:flex; align-items:center; gap:5px; font-size:10.5px; color:var(--dim);
  padding:3px 7px; border-radius:5px; cursor:pointer; border:1px solid transparent}
.lg:hover{border-color:var(--line)}
.lg.off{opacity:.32}
.lg .dot{width:7px; height:7px; border-radius:2px}

#tools{top:86px; right:22px; width:270px; display:flex; flex-direction:column; gap:12px}
#find{width:100%; background:rgba(8,11,21,.9); border:1px solid var(--line); border-radius:8px;
  padding:9px 12px; color:var(--ink); font-family:inherit; font-size:12px; outline:none}
#find:focus{border-color:rgba(120,190,255,.5)}
#detail{padding:12px 14px 14px; font-size:11.5px; line-height:1.65; color:var(--dim)}
#detail .t{color:var(--ink); font-size:12.5px; word-break:break-all; margin-bottom:7px}
#detail dl{display:grid; grid-template-columns:auto 1fr; gap:2px 10px; margin:0}
#detail dt{color:var(--faint)}
#detail dd{margin:0; color:var(--ink); font-variant-numeric:tabular-nums}
#detail .hint{color:var(--faint); margin-top:9px; font-size:10.5px}

#foot{bottom:0; left:0; right:0; padding:14px 22px 16px; display:flex; gap:18px; flex-wrap:wrap;
  align-items:center; color:var(--faint); font-size:10.5px; letter-spacing:.05em;
  background:linear-gradient(0deg,rgba(5,7,14,.92) 0%,transparent 100%)}
#foot b{color:var(--dim); font-weight:500}
kbd{border:1px solid var(--line); border-radius:3px; padding:0 4px; color:var(--dim)}
.warn{color:var(--hot)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body>
<div id="stage"><canvas id="c"></canvas></div>

<div class="hud" id="head">
  <h1>__REPO__ <span>· dependency graph</span></h1>
  <div class="sub" id="headsub"></div>
</div>

<div class="hud" id="side">
  <div class="card">
    <h2>Load-bearing modules</h2>
    <ul id="godlist"></ul>
  </div>
  <div class="card">
    <h2>Layers</h2>
    <div id="legend"></div>
  </div>
</div>

<div class="hud" id="tools">
  <input id="find" type="search" placeholder="filter by path…" autocomplete="off" spellcheck="false">
  <div class="card"><h2>Selection</h2><div id="detail"></div></div>
</div>

<div class="hud" id="foot">
  <span><b>drag</b> a node · <b>scroll</b> to zoom · <b>drag</b> the void to pan</span>
  <span><kbd>esc</kbd> clear selection</span>
  <span id="footstat"></span>
</div>

<script id="payload" type="application/json">__DATA__</script>
<script>
(function(){
"use strict";
var DATA = JSON.parse(document.getElementById("payload").textContent);
var canvas = document.getElementById("c"), ctx = canvas.getContext("2d");
var nodes = DATA.nodes, links = DATA.links;
var byId = {}; nodes.forEach(function(n){ byId[n.id] = n; });

// Adjacency, for the neighbourhood highlight.
var neighbours = {};
nodes.forEach(function(n){ neighbours[n.id] = {}; });
links.forEach(function(l){
  if (neighbours[l.source]) neighbours[l.source][l.target] = 1;
  if (neighbours[l.target]) neighbours[l.target][l.source] = 1;
});

var view = {x:0, y:0, k:0.85}, target = {x:0, y:0, k:0.85};
var hovered = null, selected = null, filter = "", hiddenLayers = {};
var entrance = 0;                       // 0 → 1, the settle-in on load
var dragging = null, panning = null, pointer = {x:0, y:0};
var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function radius(n){ return 4 + Math.sqrt(n.share) * 62; }
function colour(n){ return DATA.layer_colour[n.layer] || DATA.layer_colour.other; }
function visible(n){
  if (hiddenLayers[n.layer]) return false;
  if (filter && n.id.toLowerCase().indexOf(filter) === -1) return false;
  return true;
}
function active(n){
  if (!selected) return true;
  return n.id === selected || neighbours[selected][n.id] === 1;
}

var LABEL_COUNT = Math.min(DATA.top, 12);

function fit(){
  var ex = 1, ey = 1;
  nodes.forEach(function(n){ ex = Math.max(ex, Math.abs(n.x)); ey = Math.max(ey, Math.abs(n.y)); });
  // Panels are translucent HUD, so the drawing may run a little under them.
  var narrow = canvas.clientWidth < 1100;
  var usableW = Math.max(300, canvas.clientWidth - (narrow ? 90 : 560));
  var usableH = Math.max(300, canvas.clientHeight - 190);
  var pad = 150;  // room for the sector labels riding outside the outermost ring
  target.k = Math.min(2.2, Math.max(0.32,
    Math.min(usableW / (2 * ex + pad), usableH / (2 * ey + pad))));
  // Centre it in the gap between the two panel columns, not in the window.
  target.x = narrow ? 0 : 44;
  target.y = 14;
  view.k = target.k; view.x = target.x; view.y = target.y;
}

function resize(){
  var ratio = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * ratio;
  canvas.height = canvas.clientHeight * ratio;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  fit();
}
window.addEventListener("resize", resize);

function toScreen(n){
  return {
    x: canvas.clientWidth / 2 + view.x + n.x * view.k,
    y: canvas.clientHeight / 2 + view.y + n.y * view.k
  };
}

function draw(){
  var w = canvas.clientWidth, h = canvas.clientHeight;
  ctx.clearRect(0, 0, w, h);

  // Ground: a slow radial wash so the centre of mass reads as depth, not a hole.
  var wash = ctx.createRadialGradient(w/2, h/2, 0, w/2, h/2, Math.max(w, h) * 0.75);
  wash.addColorStop(0, "#0B1020");
  wash.addColorStop(1, "#05070E");
  ctx.globalAlpha = 1; ctx.fillStyle = wash; ctx.fillRect(0, 0, w, h);
  ctx.globalAlpha = 0.15 + 0.85 * entrance;

  // The instrument face: rank rings and layer sectors. This is what makes the
  // coordinates readable — distance from centre is rank, angle is layer.
  var cx = w/2 + view.x, cy = h/2 + view.y, k = view.k;
  ctx.globalAlpha = 0.15 + 0.85 * entrance;   // the only thing that animates in
  ctx.strokeStyle = "rgba(120,150,210,.055)"; ctx.lineWidth = 1;
  DATA.rings.forEach(function(ring){
    ctx.beginPath();
    ctx.ellipse(cx, cy, ring * k * DATA.aspect, ring * k, 0, 0, 6.2832);
    ctx.stroke();
  });
  Object.keys(DATA.sectors).forEach(function(layer){
    var s = DATA.sectors[layer], mid = (s[0] + s[1]) / 2, rim = DATA.rim * k;
    var ax = DATA.aspect;
    ctx.strokeStyle = "rgba(120,150,210,.05)";
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(s[0]) * 90 * k * ax, cy + Math.sin(s[0]) * 90 * k);
    ctx.lineTo(cx + Math.cos(s[0]) * rim * ax, cy + Math.sin(s[0]) * rim);
    ctx.stroke();
    if (hiddenLayers[layer]) return;
    ctx.save();
    ctx.translate(cx + Math.cos(mid) * (rim * ax + 18), cy + Math.sin(mid) * (rim + 18));
    ctx.rotate(mid + (Math.cos(mid) < 0 ? Math.PI : 0));
    ctx.font = "500 10px ui-monospace,Menlo,monospace";
    ctx.textAlign = Math.cos(mid) < 0 ? "right" : "left";
    ctx.textBaseline = "middle";
    ctx.fillStyle = DATA.layer_colour[layer] || "#5A6272";
    ctx.globalAlpha = .55;
    ctx.fillText(layer.toUpperCase(), 0, 0);
    ctx.globalAlpha = 1;
    ctx.restore();
  });

  var focusId = selected || hovered;

  // Edges first, so nodes sit on top of their own connections.
  links.forEach(function(l){
    var a = byId[l.source], b = byId[l.target];
    if (!a || !b || !visible(a) || !visible(b)) return;
    var lit = focusId && (l.source === focusId || l.target === focusId);
    var dimmed = focusId && !lit;
    var pa = toScreen(a), pb = toScreen(b);
    var alpha = (0.05 + l.weight * 0.5) * (lit ? 1.9 : dimmed ? 0.16 : 1);
    ctx.strokeStyle = l.wrong
      ? "rgba(255,107,87," + Math.min(0.95, alpha * 2.6) + ")"
      : (lit ? "rgba(150,200,255," + Math.min(0.9, alpha) + ")"
             : "rgba(110,145,205," + Math.min(0.6, alpha) + ")");
    ctx.lineWidth = (l.wrong ? 1.6 : 0.7 + l.weight * 2.2) * (lit ? 1.5 : 1);
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    // A slight arc separates the two directions of a mutual dependency.
    var mx = (pa.x + pb.x) / 2, my = (pa.y + pb.y) / 2;
    var dx = pb.x - pa.x, dy = pb.y - pa.y;
    ctx.quadraticCurveTo(mx - dy * 0.09, my + dx * 0.09, pb.x, pb.y);
    ctx.stroke();

    if (lit){  // direction only matters once you are looking at one node
      var ang = Math.atan2(pb.y - my, pb.x - mx), r = radius(b) * view.k + 3;
      var tipX = pb.x - Math.cos(ang) * r, tipY = pb.y - Math.sin(ang) * r;
      ctx.fillStyle = l.wrong ? "rgba(255,107,87,.95)" : "rgba(170,215,255,.85)";
      ctx.beginPath();
      ctx.moveTo(tipX, tipY);
      ctx.lineTo(tipX - Math.cos(ang - 0.42) * 8, tipY - Math.sin(ang - 0.42) * 8);
      ctx.lineTo(tipX - Math.cos(ang + 0.42) * 8, tipY - Math.sin(ang + 0.42) * 8);
      ctx.closePath(); ctx.fill();
    }
  });

  // Nodes, smallest first so the god nodes land on top.
  nodes.slice().sort(function(a, b){ return a.share - b.share; }).forEach(function(n){
    if (!visible(n)) return;
    var p = toScreen(n), r = Math.max(2, radius(n) * view.k);
    var on = active(n), lit = n.id === focusId;
    var c = colour(n);

    ctx.globalAlpha = on ? 1 : 0.14;
    if (n.share > 0.03 || lit){        // only the heavy ones earn a halo
      ctx.shadowColor = c;
      ctx.shadowBlur = (lit ? 34 : 18) * Math.min(2, 0.5 + n.share * 8);
    }
    ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 6.2832);
    ctx.fillStyle = c; ctx.fill();
    ctx.shadowBlur = 0;

    ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 6.2832);
    ctx.strokeStyle = lit ? "rgba(255,255,255,.9)" : "rgba(255,255,255,.22)";
    ctx.lineWidth = lit ? 2 : 1; ctx.stroke();

    var label = n.rank <= LABEL_COUNT || lit || (filter && on);
    if (label && r > 2.5){
      // Push the name outward along the node's own radius: in the dense middle
      // the labels fan apart instead of piling on top of one another.
      var len = Math.hypot(n.x, n.y) || 1;
      var ux = n.x / len, uy = n.y / len;
      var lx = p.x + ux * (r + 9), ly = p.y + uy * (r + 9);
      ctx.font = (lit ? "600 " : "400 ") + (lit ? 12.5 : 11) + "px ui-monospace,Menlo,monospace";
      ctx.textAlign = ux < -0.25 ? "right" : (ux > 0.25 ? "left" : "center");
      ctx.textBaseline = uy < -0.25 ? "bottom" : (uy > 0.25 ? "top" : "middle");
      var tw = ctx.measureText(n.name).width;
      var bx = ctx.textAlign === "right" ? lx - tw - 5 : ctx.textAlign === "left" ? lx - 5 : lx - tw/2 - 5;
      var by = ctx.textBaseline === "bottom" ? ly - 15 : ctx.textBaseline === "top" ? ly - 1 : ly - 8;
      ctx.fillStyle = "rgba(5,7,14,.78)";
      ctx.fillRect(bx, by, tw + 10, 16);
      ctx.fillStyle = lit ? "#FFFFFF" : "rgba(232,238,251,.86)";
      ctx.fillText(n.name, lx, ly);
    }
    ctx.globalAlpha = 1;
  });
}

var started = Date.now();
function frame(){
  // Wall time, not frame count: a throttled tab still arrives at rest.
  entrance = reduceMotion ? 1 : Math.min(1, (Date.now() - started) / 620);
  view.x += (target.x - view.x) * 0.16;
  view.y += (target.y - view.y) * 0.16;
  view.k += (target.k - view.k) * 0.16;
  draw();
  requestAnimationFrame(frame);
}

function hit(mx, my){
  var best = null, bestDistance = Infinity;
  nodes.forEach(function(n){
    if (!visible(n)) return;
    var p = toScreen(n), r = Math.max(6, radius(n) * view.k);
    var d = Math.hypot(mx - p.x, my - p.y);
    if (d < r + 4 && d < bestDistance){ best = n; bestDistance = d; }
  });
  return best;
}

canvas.addEventListener("mousemove", function(e){
  var rect = canvas.getBoundingClientRect();
  pointer.x = e.clientX - rect.left; pointer.y = e.clientY - rect.top;
  if (dragging){
    dragging.x = (pointer.x - canvas.clientWidth/2 - view.x) / view.k;
    dragging.y = (pointer.y - canvas.clientHeight/2 - view.y) / view.k;
    return;
  }
  if (panning){
    target.x = panning.vx + (pointer.x - panning.x);
    target.y = panning.vy + (pointer.y - panning.y);
    view.x = target.x; view.y = target.y;
    return;
  }
  var was = hovered;
  hovered = (hit(pointer.x, pointer.y) || {}).id || null;
  if (hovered !== was) detail(hovered ? byId[hovered] : (selected ? byId[selected] : null));
});

canvas.addEventListener("mousedown", function(e){
  var rect = canvas.getBoundingClientRect();
  var mx = e.clientX - rect.left, my = e.clientY - rect.top;
  var node = hit(mx, my);
  if (node){ dragging = node; canvas.classList.add("dragging"); }
  else { panning = {x:mx, y:my, vx:view.x, vy:view.y}; canvas.classList.add("dragging"); }
});

window.addEventListener("mouseup", function(){
  dragging = null; panning = null; canvas.classList.remove("dragging");
});

canvas.addEventListener("click", function(e){
  var rect = canvas.getBoundingClientRect();
  var node = hit(e.clientX - rect.left, e.clientY - rect.top);
  select(node ? node.id : null);
});

canvas.addEventListener("wheel", function(e){
  e.preventDefault();
  var factor = Math.exp(-e.deltaY * 0.0012);
  target.k = Math.min(4.5, Math.max(0.28, target.k * factor));
}, {passive:false});

window.addEventListener("keydown", function(e){
  if (e.key === "Escape"){ select(null); document.getElementById("find").value = ""; setFilter(""); }
});

function select(id){
  selected = (selected === id) ? null : id;
  detail(selected ? byId[selected] : null);
  Array.prototype.forEach.call(document.querySelectorAll("#godlist li"), function(li){
    li.classList.toggle("on", li.getAttribute("data-id") === selected);
  });
}

function detail(node){
  var el = document.getElementById("detail");
  if (!node){
    el.innerHTML = '<div class="hint">Hover a node for its numbers. Click to isolate its ' +
                   'neighbourhood — everything it references, and everything referencing it.</div>';
    return;
  }
  var wrong = links.filter(function(l){
    return l.wrong && (l.source === node.id || l.target === node.id);
  }).length;
  el.innerHTML =
    '<div class="t">' + node.id + "</div>" +
    "<dl>" +
    "<dt>layer</dt><dd>" + node.layer + "</dd>" +
    "<dt>rank</dt><dd>#" + node.rank + " of " + DATA.node_count + "</dd>" +
    "<dt>share</dt><dd>" + (node.share * 100).toFixed(2) + "%</dd>" +
    "<dt>referenced by</dt><dd>" + node["in"] + "</dd>" +
    "<dt>references</dt><dd>" + node.out + "</dd>" +
    "<dt>definitions</dt><dd>" + node.defs + "</dd>" +
    (wrong ? '<dt class="warn">wrong-way</dt><dd class="warn">' + wrong + "</dd>" : "") +
    "</dl>";
}

// --- the god-node list -----------------------------------------------------
var ranked = nodes.slice().sort(function(a, b){ return b.share - a.share; }).slice(0, DATA.top);
var listEl = document.getElementById("godlist");
var peak = ranked.length ? ranked[0].share : 1;
ranked.forEach(function(n){
  var li = document.createElement("li");
  li.setAttribute("data-id", n.id);
  li.innerHTML =
    '<span class="n">' + n.rank + "</span>" +
    '<span class="nm"><b>' + n.name + "</b><i>" + n.id.replace(/\/[^/]+$/, "") + "</i>" +
      '<span class="bar"><i style="width:' + (n.share / peak * 100).toFixed(1) +
      "%;background:" + colour(n) + '"></i></span></span>' +
    '<span class="sh">' + (n.share * 100).toFixed(1) + "%</span>";
  li.addEventListener("click", function(){ select(n.id); });
  li.addEventListener("mouseenter", function(){ hovered = n.id; detail(n); });
  li.addEventListener("mouseleave", function(){ hovered = null; detail(selected ? byId[selected] : null); });
  listEl.appendChild(li);
});

// --- legend doubles as a layer filter --------------------------------------
var legendEl = document.getElementById("legend");
var present = {};
nodes.forEach(function(n){ present[n.layer] = (present[n.layer] || 0) + 1; });
DATA.layer_order.forEach(function(layer){
  if (!present[layer]) return;
  var el = document.createElement("div");
  el.className = "lg";
  el.innerHTML = '<span class="dot" style="background:' + DATA.layer_colour[layer] + '"></span>' +
                 layer + " <span style='color:var(--faint)'>" + present[layer] + "</span>";
  el.addEventListener("click", function(){
    hiddenLayers[layer] = !hiddenLayers[layer];
    el.classList.toggle("off", !!hiddenLayers[layer]);
  });
  legendEl.appendChild(el);
});

function setFilter(value){ filter = (value || "").toLowerCase().trim(); }
document.getElementById("find").addEventListener("input", function(e){ setFilter(e.target.value); });

document.getElementById("headsub").textContent =
  DATA.node_count + " files · " + DATA.link_count + " reference edges · " +
  DATA.engine + " engine · indexed " + (DATA.scanned_at || "just now");
document.getElementById("footstat").innerHTML =
  DATA.wrong_way_count
    ? '<span class="warn">' + DATA.wrong_way_count + " edge(s) against the declared layering</span>"
    : "<b>no wrong-way imports</b>";

detail(null); resize(); frame();
})();
</script></body></html>
"""


def render(payload: dict, output: Path) -> None:
    html = (
        TEMPLATE.replace("__TITLE__", f"{payload['repository']} dependency graph")
        .replace("__REPO__", payload["repository"])
        .replace("__DATA__", json.dumps(payload, separators=(",", ":")))
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html)


def main() -> int:
    parser = argparse.ArgumentParser(prog="graph_view.py", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out", default=None, help="output path (default: artifacts/<today>/graph.html)"
    )
    parser.add_argument(
        "--focus",
        action="append",
        default=[],
        help="bias the ranking toward this file (repeatable)",
    )
    parser.add_argument("--top", type=int, default=14, help="how many modules the side panel lists")
    parser.add_argument("--no-tests", action="store_true", help="exclude the test suite")
    parser.add_argument("--seed", type=int, default=20260908, help="layout seed (determinism)")
    parser.add_argument("--graphify", default=None, help="path to crucible's graphify.py")
    parser.add_argument("--open", action="store_true", help="open the page when it is written")
    arguments = parser.parse_args()

    root = Path.cwd()
    for candidate in [root, *root.parents]:
        if (candidate / "pyproject.toml").exists():
            root = candidate
            break

    graphify_path = find_graphify(arguments.graphify)
    cache, edges, ranks = load_graph(graphify_path, root, arguments.focus)
    payload = build_payload(
        root, cache, edges, ranks, arguments.top, not arguments.no_tests, arguments.seed
    )

    output = (
        Path(arguments.out)
        if arguments.out
        else (root / "artifacts" / date.today().isoformat() / "graph.html")
    )
    render(payload, output)

    print(
        f"graph_view: {payload['node_count']} nodes, {payload['link_count']} edges "
        f"({payload['engine']} engine)"
    )
    top = sorted(payload["nodes"], key=lambda n: -n["share"])[:5]
    for node in top:
        print(
            f"  {node['share'] * 100:5.2f}%  in:{node['in']:<3} out:{node['out']:<3} {node['id']}"
        )
    if payload["wrong_way_count"]:
        print(
            f"  {payload['wrong_way_count']} edge(s) run against the declared layering "
            "(drawn hot; run scripts/layer_check.py for the list)"
        )
    print(f"→ {output}")

    if arguments.open:
        webbrowser.open(output.resolve().as_uri())
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
