#!/usr/bin/env python3
"""Build experiment 0002's consolidated report from the arms' own output files.

Every number on the page comes from a file an arm's run wrote (paired.json, exit_codes.json) or
from score_slate.py, which reads the same files and applies the pre-registered rule. Nothing is
typed by hand: the narrative lives in the template, and the numbers are injected here, so a
number on the page and a number in a file cannot disagree.

    .venv/bin/python research/tools/build_slate_report.py [--arms-root DIR] [--output FILE]
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_slate as slate  # noqa: E402

TEMPLATE = Path("research/reports/0002-slate/template.html")
OUTPUT = Path("research/reports/0002-slate/report.html")
CONFIRM_LEVEL = 0.9833
IDEAS = {
    "A0": "Control: main, unchanged",
    "A1": "Sticky prior on the transition matrix",
    "A2": "All Weather quadrants over levels, four states",
    "A3": "All Weather quadrants over surprises",
    "A4": "Two chains: growth, and inflation with rates",
    "A5": "Direct per-horizon regime rates",
    "A6": "Fixed 50/50 blend with climatology",
}
SEED_VARIANTS = ("a4-seed-20260909", "a4-seed-20260910")
REGISTERED_SEED = "20260908"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def signed(value: float | None, places: int = 4) -> str:
    return "n/a" if value is None else f"{value:+.{places}f}".replace("-", "−")


def span(ci: tuple[float, float] | list[float] | None) -> str:
    return "n/a" if not ci else f"[{signed(ci[0])}, {signed(ci[1])}]"


def verdict_class(record: dict) -> str:
    if "verdict" not in record:
        return "pending"
    verdict = record["verdict"]
    head = verdict.split(";")[0].strip()
    if verdict.startswith("VOID"):
        return "void"
    if head.startswith("CONTROL"):
        return "control" if "PASSES" in head else "void"
    if "HARMFUL" in verdict:
        return "harmful"
    if head.startswith("CONFIRMED"):
        return "confirmed"
    if head.startswith("PROMISING"):
        return "promising"
    return "none"


CHIP_TEXT = {
    "confirmed": "Confirmed in sample",
    "promising": "Promising",
    "harmful": "Harmful",
    "none": "No verdict",
    "pending": "Not yet scored",
    "void": "Void",
    "control": "Control passes",
}


def chip(record: dict) -> str:
    kind = verdict_class(record)
    provisional = "<br><span class='sub'>provisional</span>" if "PROVISIONAL" in record.get("verdict", "") else ""
    return f'<span class="verdict"><span class="chip chip-{kind}">{esc(CHIP_TEXT[kind])}</span>{provisional}</span>'


def score_the_slate(arms_root: Path) -> dict:
    with tempfile.TemporaryDirectory() as scratch:
        out = Path(scratch) / "slate.json"
        subprocess.run(  # noqa: S603
            [sys.executable, str(Path(slate.__file__)), "--arms-root", str(arms_root), "--json", str(out)],
            check=True, capture_output=True, text=True,
        )
        return json.loads(out.read_text())


def paired_rows(arms_root: Path, arm: str) -> dict[int, dict]:
    path = arms_root / arm / "research" / "arms" / arm / "paired.json"
    try:
        return slate.horizon_rows(json.loads(path.read_text()))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def verdict_table(records: list[dict], arms_root: Path) -> str:
    main_rows = paired_rows(arms_root, "aa-control")
    head = (
        "<thead><tr><th>Arm</th><th>Idea</th>"
        "<th class='num'>1 year: arm − main<br><span class='sub'>90% · 98.33%</span></th>"
        "<th class='num'>5 years<br><span class='sub'>90%</span></th>"
        "<th class='num'>10 years<br><span class='sub'>90%</span></th>"
        "<th>Audit</th><th>Review</th><th>Verdict</th></tr></thead>"
    )
    body = []
    if main_rows:
        cells = "".join(
            f"<td class='num'>{signed(main_rows[h]['baseline_mean_brier_skill_score'])}</td>" if h in main_rows else "<td></td>"
            for h in (12, 60, 120)
        )
        body.append(f"<tr class='reference'><td>main</td><td>Brier skill score of main itself</td>{cells}<td></td><td></td><td></td></tr>")
    for record in records:
        label = record["label"]
        idea = esc(IDEAS.get(label, record["arm"]))
        name = f"<b>{esc(label)}</b>"
        if "verdict" not in record:
            body.append(
                f"<tr class='pending'><td>{name}</td><td>{idea}</td>"
                f"<td colspan='5' class='status'>{esc(record.get('status', ''))}</td><td>{chip(record)}</td></tr>"
            )
            continue
        one = (
            f"<td class='num'><b>{signed(record.get('d12'))}</b><br>"
            f"<span class='sub'>{span(record.get('ci90_12'))}<br>{span(record.get(f'ci{CONFIRM_LEVEL}_12'))}</span></td>"
        )
        later = "".join(
            f"<td class='num'>{signed(record.get(f'd{h}'))}<br><span class='sub'>{span(record.get(f'ci90_{h}'))}</span></td>"
            for h in (60, 120)
        )
        audit = "exit 0" if record.get("audit_exit") == 0 else f"exit {esc(record.get('audit_exit'))}"
        review = esc(record.get("look_ahead_review", "—")).title()
        body.append(f"<tr><td>{name}</td><td>{idea}</td>{one}{later}<td>{audit}</td><td>{review}</td><td>{chip(record)}</td></tr>")
    return f"<div class='table-scroll'><table class='verdicts'>{head}<tbody>{''.join(body)}</tbody></table></div>"


def nice_step(span_width: float) -> float:
    for step in (0.01, 0.02, 0.05, 0.1, 0.2, 0.5):
        if span_width / step <= 8:
            return step
    return 1.0


def forest(records: list[dict], horizon: int, caption: str) -> str:
    """Point estimate, 90% interval (thick) and 98.33% interval (thin) of arm minus main."""
    rows = [r for r in records if r["label"] != "A0"]
    scored = [r for r in rows if r.get(f"d{horizon}") is not None]
    ends = [0.0, slate.HARM_FLOOR]
    for r in scored:
        for key in (f"ci90_{horizon}", f"ci{CONFIRM_LEVEL}_{horizon}"):
            if r.get(key):
                ends += list(r[key])
    low, high = min(ends), max(ends)
    pad = (high - low) * 0.06
    low, high = low - pad, high + pad
    step = nice_step(high - low)
    width, left, right, row_h, top = 820, 250, 610, 46, 34
    height = top + row_h * len(rows) + 30

    def x(value: float) -> float:
        return left + (value - low) / (high - low) * (right - left)

    parts = [f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{esc(caption)}' class='forest'>"]
    for k in range(math.ceil(low / step), math.floor(high / step) + 1):
        tick = round(k * step, 10)
        tx = x(tick)
        parts.append(f"<line x1='{tx:.1f}' x2='{tx:.1f}' y1='{top - 8}' y2='{height - 26}' class='grid'/>")
        parts.append(f"<text x='{tx:.1f}' y='{height - 10}' class='tick' text-anchor='middle'>{'0' if k == 0 else signed(tick, 2)}</text>")
    parts.append(f"<line x1='{x(0):.1f}' x2='{x(0):.1f}' y1='{top - 14}' y2='{height - 26}' class='zero'/>")
    parts.append(f"<text x='{x(0) + 5:.1f}' y='{top - 18}' class='tick' text-anchor='start'>no difference</text>")
    hx = x(slate.HARM_FLOOR)
    parts.append(f"<line x1='{hx:.1f}' x2='{hx:.1f}' y1='{top - 14}' y2='{height - 26}' class='harm'/>")
    parts.append(f"<text x='{hx - 5:.1f}' y='{top - 18}' class='tick harm-label' text-anchor='end'>harm floor −0.02</text>")
    for i, r in enumerate(rows):
        cy = top + row_h * i + row_h / 2
        kind = verdict_class(r)
        parts.append(f"<text x='0' y='{cy - 3:.1f}' class='row-label'>{esc(r['label'])} · {esc(IDEAS.get(r['label'], r['arm']))}</text>")
        parts.append(f"<text x='0' y='{cy + 13:.1f}' class='row-sub'>{esc(CHIP_TEXT[kind])}{' · provisional' if 'PROVISIONAL' in r.get('verdict', '') else ''}</text>")
        d = r.get(f"d{horizon}")
        if d is None:
            parts.append(f"<text x='{left}' y='{cy + 4:.1f}' class='row-sub'>not yet scored</text>")
            continue
        wide, narrow = r.get(f"ci{CONFIRM_LEVEL}_{horizon}"), r.get(f"ci90_{horizon}")
        title = f"{r['label']} at {horizon} months: {signed(d)}, 90% {span(narrow)}, 98.33% {span(wide)}"
        parts.append(f"<g class='mark mark-{kind}'><title>{esc(title)}</title>")
        parts.append(f"<rect x='{left - 4}' y='{cy - row_h / 2 + 2:.1f}' width='{right - left + 8}' height='{row_h - 4}' class='hit'/>")
        if wide:
            parts.append(f"<line x1='{x(wide[0]):.1f}' x2='{x(wide[1]):.1f}' y1='{cy:.1f}' y2='{cy:.1f}' class='ci-wide'/>")
        if narrow:
            parts.append(f"<rect x='{x(narrow[0]):.1f}' y='{cy - 4:.1f}' width='{max(x(narrow[1]) - x(narrow[0]), 2):.1f}' height='8' rx='4' class='ci-narrow'/>")
        parts.append(f"<circle cx='{x(d):.1f}' cy='{cy:.1f}' r='5.5' class='point'/></g>")
        parts.append(f"<text x='{right + 16}' y='{cy + 4:.1f}' class='value'>{signed(d)} <tspan class='value-sub'>{span(narrow)}</tspan></text>")
    parts.append("</svg>")
    return f"<figure class='chart'>{''.join(parts)}<figcaption>{esc(caption)}</figcaption></figure>"


def chain_counts(check_gates_log: Path) -> str:
    """Each chain's chosen state count at 1994-03-01, read from the run's own gate log."""
    try:
        text = check_gates_log.read_text()
    except FileNotFoundError:
        return "n/a"
    found = re.search(r"regimes chosen as of 1994-03-01.*?Growth chain: (\d+) states.*?Inflation-and-rates chain: (\d+) states", text, re.S)
    return f"{found.group(1)} × {found.group(2)}" if found else "not found in log"


def seed_section(arms_root: Path, registered: dict | None) -> str:
    rows, lows = [], []
    if registered:
        rows.append(
            f"<tr><td>{REGISTERED_SEED} (registered)</td><td>{chain_counts(arms_root / 'two-timescale-chains' / 'research' / 'arms' / 'two-timescale-chains' / 'check_gates.log')}</td><td class='num'>{signed(registered.get('d12'))}</td>"
            f"<td class='num'>{span(registered.get('ci90_12'))}</td><td>exit {esc(registered.get('audit_exit'))}</td><td>the scored run</td></tr>"
        )
    state = "complete"
    for variant in SEED_VARIANTS:
        out = arms_root / variant / "research" / "arms" / variant
        seed = variant.rsplit("-", 1)[1]
        try:
            exits = json.loads((out / "exit_codes.json").read_text())
            row = slate.horizon_rows(json.loads((out / "paired.json").read_text()))[12]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            rows.append(f"<tr class='pending'><td>{seed}</td><td colspan='5' class='status'>still running</td></tr>")
            state = "pending"
            continue
        stale = slate.code_changed_since_run(arms_root / variant, str(exits.get("commit", "")))
        ci = slate.interval(row, 0.90)
        audit = exits.get("look_ahead_audit_exit")
        note = stale or ("void: audit failed" if audit != 0 else "")
        if stale or audit != 0:
            state = "void"
        elif ci:
            lows.append(ci[0])
        rows.append(
            f"<tr><td>{seed}</td><td>{chain_counts(out / 'check_gates.log')}</td><td class='num'>{signed(float(row['difference']))}</td><td class='num'>{span(ci)}</td>"
            f"<td>exit {esc(audit)}</td><td>{esc(note)}</td></tr>"
        )
    if state == "complete" and len(lows) == len(SEED_VARIANTS):
        reading = "ROBUST TO INITIALISATION" if all(lo > 0 for lo in lows) else "SEED-DEPENDENT"
    elif state == "void":
        reading = "NOT READABLE: a variant is void or its code does not match its run"
    else:
        reading = "PENDING: a variant is still running"
    table = (
        "<div class='table-scroll'><table class='seeds'><thead><tr><th>Seed</th><th>States: growth × levels</th><th class='num'>1 year: arm − main</th>"
        "<th class='num'>90% interval</th><th>Audit</th><th>Note</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )
    return f"<p class='reading'>Reading under diagnostic 0004's pre-committed rule: <b>{esc(reading)}</b></p>{table}"


def arm_cards(records: list[dict], prose_dir: Path) -> str:
    """One card per arm: the header comes from the data, the body from a hand-written prose file."""
    cards = []
    for record in records:
        label = record["label"]
        if label == "A0":
            continue
        body_path = prose_dir / f"arm-{label}.html"
        body = body_path.read_text() if body_path.exists() else "<p class='sub'>Report and review not yet in.</p>"
        body = fill_fields(body, {r["label"]: r for r in records})
        if record.get("d12") is not None:
            headline = f"<p class='label'>research/{esc(record['arm'])} · 1 year {signed(record['d12'])} · 90% {span(record.get('ci90_12'))} · review {esc(record.get('look_ahead_review', '—')).lower()}</p>"
        else:
            headline = f"<p class='label'>{esc(record.get('status', 'not yet scored'))}</p>"
        cards.append(
            f"<article class='arm'><header><h3>{esc(label)} · {esc(IDEAS.get(label, record['arm']))}</h3>{chip(record)}</header>"
            f"{headline}{body}</article>"
        )
    return f"<div class='arms'>{''.join(cards)}</div>"


def fill_fields(text: str, by_label: dict[str, dict]) -> str:
    """Replace {{A4.d12}}-style fields in hand-written prose with values from the scored records, so the
    prose quotes no number by hand. An unknown field is an error, not a blank."""

    def value(match: re.Match[str]) -> str:
        label, key = match.group(1), match.group(2)
        found = by_label.get(label, {}).get(key)
        if found is None:
            raise SystemExit(f"prose field {{{{{label}.{key}}}}} has no value in the scored records")
        return span(found) if isinstance(found, (list, tuple)) else signed(float(found))

    return re.sub(r"\{\{(A\d)\.([A-Za-z0-9_.]+)\}\}", value, text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms-root", default=str(Path.cwd().parent / "forecasting-the-future-arms"))
    parser.add_argument("--template", default=str(TEMPLATE))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    arms_root = Path(args.arms_root)

    scored = score_the_slate(arms_root)
    records = scored["arms"]
    by_label = {r["label"]: r for r in records}
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()  # noqa: S603, S607
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    fragments = {
        "GENERATED": f"generated {esc(stamp)} from main at <code>{esc(commit)}</code> by <code>research/tools/build_slate_report.py</code>",
        "VERDICT_TABLE": verdict_table(records, arms_root),
        "FOREST_12": forest(records, 12, "One year, the registered primary endpoint. Dot: arm minus main in mean Brier skill score. Thick bar: 90% interval, which decides PROMISING. Thin line: 98.33% interval (1 − 0.10/6, Bonferroni across six arms), which decides CONFIRMED_IN_SAMPLE."),
        "FOREST_60": forest(records, 60, "Five years. About 5.5 independent observations, so read the width, not the dot."),
        "FOREST_120": forest(records, 120, "Ten years. About 2.2 independent observations: no ten-year result here is informative."),
        "SEEDS": seed_section(arms_root, by_label.get("A4")),
        "COMBINATION": f"<p class='reading'><b>{esc(scored['combination']['plan'])}</b></p>"
                       f"<p class='sub'>Eligible under 0003's rule: {esc(', '.join(scored['combination']['eligible']) or 'none')}.</p>",
    }
    prose_dir = Path(args.template).parent / "prose"
    fragments["ARM_CARDS"] = arm_cards(records, prose_dir)
    for key in ("ANSWER", "NARRATIVE_TAIL"):
        path = prose_dir / f"{key.lower()}.html"
        fragments[key] = fill_fields(path.read_text(), by_label) if path.exists() else f"<p class='sub'>[{key.lower()} not yet written]</p>"
    page = Path(args.template).read_text()
    for key, fragment in fragments.items():
        marker = f"<!--@{key}-->"
        if page.count(marker) != 1:
            raise SystemExit(f"template must contain {marker} exactly once, found {page.count(marker)}")
        page = page.replace(marker, fragment)
    Path(args.output).write_text(page)
    print(f"wrote {args.output}: {len(page):,} bytes; {scored['combination']['plan']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
