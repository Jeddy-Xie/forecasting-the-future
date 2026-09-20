#!/usr/bin/env python3
"""Build the impact ledger from the registry and the arms' own output files.

The registry (``research/reports/impact-analysis/changes.json``) holds the narrative and,
for anything measured by a research arm, a pointer rather than a number. Pointers are
resolved here through ``score_slate.py``, which reads each arm's own ``paired.json`` and
applies the pre-registered rule, so the page cannot disagree with the files it describes.
An entry may instead carry ``recorded`` with a ``provenance`` line, for a number measured
once by something other than an arm run; those say where they came from.

Registry prose is trusted HTML: it lives in the repository and is reviewed like code.
Values resolved from data are escaped.

    .venv/bin/python research/tools/build_impact_analysis.py [--arms-root DIR] [--output FILE]
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_slate as slate  # noqa: E402

REGISTRY = Path("research/reports/impact-analysis/changes.json")
TEMPLATE = Path("research/reports/impact-analysis/template.html")
OUTPUT = Path("research/reports/impact-analysis/impact-analysis.html")
CONFIRM_LEVEL = 0.9833


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def signed(value: float | None, places: int = 4) -> str:
    return "n/a" if value is None else f"{value:+.{places}f}".replace("-", "−")


def span(interval) -> str:
    return "n/a" if not interval else f"[{signed(interval[0])}, {signed(interval[1])}]"


def chip(kind: str, text: str) -> str:
    known = {"ok", "bad", "wait", "none"}
    return f'<span class="chip chip-{kind if kind in known else "none"}">{esc(text)}</span>'


def score_the_arms(arms_root: Path) -> dict[str, dict]:
    with tempfile.TemporaryDirectory() as scratch:
        out = Path(scratch) / "slate.json"
        subprocess.run(  # noqa: S603
            [sys.executable, str(Path(slate.__file__)), "--arms-root", str(arms_root), "--json", str(out)],
            check=True, capture_output=True, text=True,
        )
        scored = json.loads(out.read_text())
    return {record["arm"]: record for record in scored["arms"]}


def paired_row(arms_root: Path, arm: str, horizon: int = 12) -> dict | None:
    path = arms_root / arm / "research" / "arms" / arm / "paired.json"
    try:
        return slate.horizon_rows(json.loads(path.read_text())).get(horizon)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def measurement(change: dict, by_arm: dict[str, dict], arms_root: Path) -> dict:
    """Numbers for one entry: resolved from the arm's own files, or recorded with provenance."""
    impact = change.get("impact", {})
    if "from_arm" in impact:
        arm = impact["from_arm"]
        record = by_arm.get(arm, {})
        row = paired_row(arms_root, arm)
        return {
            "kind": "resolved",
            "arm": arm,
            "difference": record.get("d12"),
            "ci90": record.get("ci90_12"),
            "ci_confirm": record.get(f"ci{CONFIRM_LEVEL}_12"),
            "review": record.get("look_ahead_review"),
            "verdict": record.get("verdict") or record.get("status", ""),
            "main_skill": row and row.get("baseline_mean_brier_skill_score"),
            "arm_skill": row and row.get("current_mean_brier_skill_score"),
        }
    recorded = impact.get("recorded", {})
    return {
        "kind": "recorded",
        "headline": recorded.get("headline", ""),
        "detail": recorded.get("detail", ""),
        "provenance": impact.get("provenance", ""),
    }


def methods_table(changes: list[dict], by_arm: dict[str, dict], arms_root: Path) -> str:
    rows = []
    entries = [c for c in changes if c["kind"] == "method"]
    measured = [(c, measurement(c, by_arm, arms_root)) for c in entries]
    measured.sort(
        key=lambda pair: (
            pair[1]["kind"] != "recorded",
            pair[1].get("difference") is None,
            -(pair[1].get("difference") or 0),
        )
    )
    for change, m in measured:
        if m["kind"] == "recorded":
            # A method's impact need not come from an arm run: this one was measured on main
            # itself, by the regression harness, after the change landed.
            detail = (
                f"<td colspan='3' class='measure'>{m['headline']}"
                + (f"<br><span class='sub'>{m['detail']}</span>" if m.get("detail") else "")
                + (f"<br><span class='provenance'>{m['provenance']}</span>" if m.get("provenance") else "")
                + "</td>"
            )
        else:
            detail = (
                f"<td class='num'><b>{signed(m['difference'])}</b><br><span class='sub'>{span(m['ci90'])}<br>"
                f"{span(m['ci_confirm'])}</span></td>"
                f"<td class='num'>{signed(m['main_skill'])} → {signed(m['arm_skill'])}</td>"
                f"<td>{esc((m.get('review') or '—').title())}</td>"
            )
        rows.append(
            f"<tr><td><b>{esc(change['id'])}</b><br><span class='sub'>{esc(change.get('date',''))}</span></td>"
            f"<td>{change['title']}</td>{detail}"
            f"<td>{chip(change.get('status_kind','none'), change['status'])}</td></tr>"
        )
    table = (
        "<div class='table-scroll'><table><thead><tr><th>Id</th><th>Method</th>"
        "<th class='num'>1 year vs main<br><span class='sub'>90% · 98.33%</span></th>"
        "<th class='num'>skill: main → arm</th><th>Review</th><th>Status</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )
    cards = []
    for change, _ in measured:
        notes = "".join(f"<li>{note}</li>" for note in change.get("notes", []))
        cards.append(
            f"<article class='entry'><header><h3>{esc(change['id'])} · {change['title']}</h3></header>"
            f"<p>{change['what_changed']}</p>"
            + (f"<ul>{notes}</ul>" if notes else "")
            + "</article>"
        )
    return table + "".join(cards)


def entries_list(changes: list[dict], kind: str, by_arm: dict[str, dict], arms_root: Path) -> str:
    cards = []
    for change in [c for c in changes if c["kind"] == kind]:
        m = measurement(change, by_arm, arms_root)
        notes = "".join(f"<li>{note}</li>" for note in change.get("notes", []))
        measured = (
            f"<p class='measure'>{m['headline']}"
            + (f" — {m['detail']}" if m.get("detail") else "")
            + "</p>"
            + (f"<p class='provenance'>{m['provenance']}</p>" if m.get("provenance") else "")
        ) if m["kind"] == "recorded" else ""
        cards.append(
            f"<article class='entry'><header><h3>{change['title']}</h3>"
            f"{chip(change.get('status_kind','none'), change['status'])}</header>"
            f"<p>{change['what_changed']}</p>{measured}"
            + (f"<ul>{notes}</ul>" if notes else "")
            + "</article>"
        )
    return "".join(cards)


def leading_method(changes: list[dict], by_arm: dict[str, dict], arms_root: Path):
    best, best_measure = None, None
    for change in [c for c in changes if c["kind"] == "method"]:
        m = measurement(change, by_arm, arms_root)
        verdict = (m.get("verdict") or "")
        if not verdict.startswith("CONFIRMED") or m.get("review") != "CLEAN":
            continue
        if best_measure is None or (m["difference"] or 0) > (best_measure["difference"] or 0):
            best, best_measure = change, m
    return best, best_measure


def forecast_table(arm: str, arms_root: Path, main_root: Path) -> str:
    import pandas as pd

    candidate = arms_root / arm / ".cache" / "models" / "current_forecasts.parquet"
    shipped = main_root / ".cache" / "models" / "current_forecasts.parquet"
    if not candidate.exists() or not shipped.exists():
        return "<p class='sub'>Today's forecasts are not both available to compare.</p>"
    a = pd.read_parquet(candidate).set_index(["indicator", "horizon_months"])
    m = pd.read_parquet(shipped).set_index(["indicator", "horizon_months"])
    questions = a["question"].groupby(level=0).first().to_dict()
    rows = []
    for indicator in sorted(questions, key=lambda k: str(questions[k])):
        cells = []
        for horizon in (12, 60, 120):
            key = (indicator, horizon)
            if key not in a.index or key not in m.index:
                cells.append("<td class='num'>n/a</td>")
                continue
            new, old = float(a.loc[key, "probability"]), float(m.loc[key, "probability"])
            delta = new - old
            arrow = "up" if delta > 0 else ("down" if delta < 0 else "")
            cells.append(
                f"<td class='num'>{new * 100:.1f}%<br><span class='sub {arrow}'>{signed(delta * 100, 1)}</span></td>"
            )
        rows.append(f"<tr><td>{esc(questions[indicator])}</td>{''.join(cells)}</tr>")
    return (
        "<div class='table-scroll'><table><thead><tr><th>Question</th>"
        "<th class='num'>1 year</th><th class='num'>5 years</th><th class='num'>10 years</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        "<p class='sub'>Each cell is the candidate's probability, with its change against the shipped model beneath.</p>"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms-root", default=str(Path.cwd().parent / "forecasting-the-future-arms"))
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--template", default=str(TEMPLATE))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    arms_root = Path(args.arms_root)

    registry = json.loads(Path(args.registry).read_text())
    changes = registry["changes"]
    by_arm = score_the_arms(arms_root)
    best, best_measure = leading_method(changes, by_arm, arms_root)

    counts = {kind: sum(1 for c in changes if c["kind"] == kind) for kind in ("method", "integrity", "infrastructure")}
    adopted = next((c for c in changes if c.get("id", "").startswith("ADOPT-")), None)
    standing = (
        "It is the pipeline's method as of "
        f"{esc(adopted.get('date', ''))}: merged and running by default, but NOT shipped — the "
        "submission still carries the older configuration, and re-shipping needs the owner's token."
        if adopted
        else "It is a validated candidate, not the shipped method: nothing has been merged, shipped "
        "or registered forward."
    )
    endpoint = registry["primary_endpoint"]
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()  # noqa: S603, S607
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")

    if best is None:
        bottom = "<p class='lede'>No method has yet cleared the registered bar.</p>"
    else:
        bottom = (
            f"<p class='lede'><b>{best['title']}</b> is the strongest method measured so far: "
            f"{signed(best_measure['difference'])} on the one-year endpoint against the shipped model, "
            f"with a {endpoint['confirm_level']:.4g} interval of {span(best_measure['ci_confirm'])} and a clean "
            f"independent look-ahead review. Mean one-year skill goes {signed(best_measure['main_skill'])} "
            f"→ {signed(best_measure['arm_skill'])}.</p>"
            f"<p class='prose'>{standing} {counts['method']} methods have been measured this way, alongside "
            f"{counts['integrity']} integrity findings and {counts['infrastructure']} pieces of measurement "
            f"machinery.</p>"
        )

    fragments = {
        "GENERATED": f"generated {esc(stamp)} from <code>{esc(commit)}</code> by "
                     f"<code>research/tools/build_impact_analysis.py</code>, reading "
                     f"<code>changes.json</code> and each arm's own output files",
        "BOTTOM_LINE": bottom,
        "ENDPOINT": f"The endpoint is the {endpoint['name']}. {endpoint['note']} "
                    f"<b>Promising</b> is a {endpoint['promising_level']:.2g} interval above zero, "
                    f"<b>confirmed in sample</b> a {endpoint['confirm_level']:.4g} one, and <b>harmful</b> any "
                    f"horizon whose interval sits below {signed(endpoint['harm_floor'], 2)}.",
        "METHODS": methods_table(changes, by_arm, arms_root),
        "FORECASTS": forecast_table(best["impact"]["from_arm"], arms_root, Path.cwd()) if best else "",
        "INTEGRITY": entries_list(changes, "integrity", by_arm, arms_root),
        "INFRASTRUCTURE": entries_list(changes, "infrastructure", by_arm, arms_root),
        "LIMITS": "<div class='prose'><ul class='limits'>"
                  + "".join(f"<li>{item}</li>" for item in registry["limits"]) + "</ul></div>",
        "DECISIONS": "<div class='prose'><ol class='decisions'>"
                     + "".join(f"<li><b>{d['title']}.</b> {d['detail']}</li>" for d in registry["decisions"])
                     + "</ol></div>",
        "NEXT": "<div class='prose'><ul>"
                + "".join(
                    f"<li><b>{c['title']}.</b> {c['detail']}"
                    + (f"<br><span class='sub'>Provable here? {c['provability']}</span>" if c.get("provability") else "")
                    + "</li>"
                    for c in registry["next_candidates"]
                )
                + "</ul></div>",
        "HOWTO": registry["how_to_update"],
    }

    page = Path(args.template).read_text()
    for key, fragment in fragments.items():
        marker = f"<!--@{key}-->"
        if page.count(marker) != 1:
            raise SystemExit(f"template must contain {marker} exactly once, found {page.count(marker)}")
        page = page.replace(marker, fragment)
    Path(args.output).write_text(page)
    print(f"wrote {args.output}: {len(page):,} bytes; leading method {best['id'] if best else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
