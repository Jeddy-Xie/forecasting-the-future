"""Score experiment 0002's arms by CODE, from the files each run wrote, never from an agent's report.

Two decisions from this week's research heat are applied here: numbers an agent reports are
machine-extracted rather than transcribed (arxiv-2609.14758), and a summary may not outrank its inputs,
so every verdict is computed from the arm's own outputs rather than assigned by whoever summarises
(arxiv-2609.13299).

Usage, from the main repository root:
    python score_slate.py [--arms-root DIR] [--reviews-dir DIR] [--json OUT]

For each arm directory it reads:
    <worktree>/research/arms/<arm>/paired.json       the paired comparison, both confidence levels
    <worktree>/research/arms/<arm>/compare.json      the plain field comparison
    <worktree>/research/arms/<arm>/exit_codes.json   the runner's exit codes
    research/arms/lookahead-review-*.md              the judged half of the look-ahead defence
and applies proving/experiments/0002-research-slate-2026-09/experiment.json's decision rule, read from
that file, so a rule and its application cannot drift apart.
"""

import argparse
import json
import re
import sys
from pathlib import Path

REGISTRATION = Path("proving/experiments/0002-research-slate-2026-09/experiment.json")
PROMISING_LEVEL = 0.90
HARM_FLOOR = -0.02
PRIMARY_HORIZON = 12
ARMS = {
    "A0": "aa-control",
    "A1": "sticky-dirichlet-prior",
    "A2": "quadrant-structure-levels",
    "A3": "quadrant-structure-surprises",
    "A4": "two-timescale-chains",
    "A5": "direct-horizon-rates",
    "A6": "fixed-climatology-blend",
}


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def horizon_rows(paired: dict) -> dict[int, dict]:
    rows: dict[int, dict] = {}
    for item in walk(paired.get("horizons", paired)):
        if "difference" in item and "indicator" not in item and "horizon_months" in item:
            rows.setdefault(int(item["horizon_months"]), item)
    return rows


def interval(row: dict, level: float) -> tuple[float, float] | None:
    for item in walk(row):
        if isinstance(item, dict) and "lower_bound" in item and abs(float(item.get("confidence_level", -1)) - level) < 5e-4:
            return float(item["lower_bound"]), float(item["upper_bound"])
    return None


def review_sections(text: str) -> dict[str, str]:
    """Split a review into {heading: body} by heading LINES. A regex with DOTALL is not used here:
    it let a heading pattern run from the file's first heading to the end, emptying every section."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1).strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


def review_verdict(reviews_dir: Path, arm: str) -> str:
    """CLEAN / LEAK FOUND / VOID from the judged review's VERDICT: line; PENDING if no review names the arm;
    UNREADABLE if the arm's section has no well-formed VERDICT: line. Prose is never parsed."""
    for path in sorted(reviews_dir.glob("lookahead-review-*.md")):
        for heading, body in review_sections(path.read_text()).items():
            if heading == arm or re.search(rf"(?<![a-z0-9-]){re.escape(arm)}(?![a-z0-9-])", heading):
                line = re.search(r"^\s*VERDICT:\s*(CLEAN|LEAK FOUND|VOID)\s*$", body, flags=re.M | re.I)
                return line.group(1).upper() if line else "UNREADABLE"
    return "PENDING"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms-root", default=str(Path.cwd().parent / "forecasting-the-future-arms"))
    parser.add_argument("--reviews-dir", default="research/arms")
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    rule = json.loads(REGISTRATION.read_text())["decision_rule"]
    family = int(rule["family_size"])
    confirm_level = round(1 - 0.10 / family, 4)          # 0.9833 for a family of six, read from the rule
    rows_out = []
    for label, arm in ARMS.items():
        base = Path(args.arms_root) / arm / "research" / "arms" / arm
        record = {"label": label, "arm": arm}
        try:
            exits = json.loads((base / "exit_codes.json").read_text())
            paired = json.loads((base / "paired.json").read_text())
            plain = json.loads((base / "compare.json").read_text())
        except FileNotFoundError as missing:
            record["status"] = f"NOT RUN ({missing.filename.split('/')[-1]} absent)"
            rows_out.append(record)
            continue
        rows = horizon_rows(paired)
        moved = sum(1 for d in walk(plain) if d.get("band") == "MOVED")
        record.update(
            check_gates_exit=exits.get("check_gates_exit"),
            audit_exit=exits.get("look_ahead_audit_exit"),
            plain_moved=moved,
            commit=exits.get("commit", "")[:7],
        )
        for h, row in sorted(rows.items()):
            record[f"d{h}"] = float(row["difference"])
            record[f"ci90_{h}"] = interval(row, PROMISING_LEVEL)
            record[f"ci{confirm_level}_{h}"] = interval(row, confirm_level)

        if label == "A0":
            exact = all(record.get(f"d{h}") == 0.0 and record.get(f"ci90_{h}") == (0.0, 0.0) for h in rows) and moved == 0
            record["verdict"] = "CONTROL PASSES: reproduces main exactly" if exact else "CONTROL FAILS: the slate is void"
            rows_out.append(record)
            continue

        deterministic_void = record["audit_exit"] != 0
        judged = review_verdict(Path(args.reviews_dir), arm)
        primary90 = record.get(f"ci90_{PRIMARY_HORIZON}")
        primary_confirm = record.get(f"ci{confirm_level}_{PRIMARY_HORIZON}")
        harmful = [h for h in rows if record.get(f"ci90_{h}") and record[f"ci90_{h}"][1] < HARM_FLOOR]
        if deterministic_void:
            verdict = f"VOID (look-ahead audit exit {record['audit_exit']})"
        elif judged in ("LEAK FOUND", "VOID"):
            verdict = f"VOID (look-ahead review: {judged})"
        elif primary90 is None:
            verdict = "UNSCORED (no 90% one-year interval in paired.json)"
        else:
            tier = "none"
            if primary90[0] > 0:
                tier = "PROMISING"
            if primary_confirm is not None and primary_confirm[0] > 0:
                tier = "CONFIRMED_IN_SAMPLE"
            elif primary_confirm is None and tier == "PROMISING":
                tier = "PROMISING (no family-wise interval, so CONFIRMED cannot be assessed)"
            if harmful:
                tier += f"; HARMFUL at {harmful} months, disqualified from combination"
            if judged == "PENDING":
                tier += "; PROVISIONAL: the look-ahead review has not reported"
            elif judged == "UNREADABLE":
                tier += "; PROVISIONAL: the look-ahead review has no well-formed VERDICT: line, so it is NOT counted as clean"
            elif judged != "CLEAN":
                tier += f"; PROVISIONAL: unexpected review state {judged!r}"
            verdict = tier
        record["look_ahead_review"] = judged
        record["verdict"] = verdict
        rows_out.append(record)

    print(f"decision rule read from {REGISTRATION}: family {family}, confirm level {confirm_level}, harm floor {HARM_FLOOR}")
    for r in rows_out:
        if "verdict" not in r:
            print(f"  {r['label']} {r['arm']:30s} {r['status']}")
            continue
        d12, ci = r.get("d12"), r.get("ci90_12")
        head = f"1y {d12:+.4f} 90% [{ci[0]:+.4f}, {ci[1]:+.4f}]" if d12 is not None and ci else "1y n/a"
        print(f"  {r['label']} {r['arm']:30s} {head}  audit={r.get('audit_exit')}  review={r.get('look_ahead_review', '-')}  -> {r['verdict']}")
    if args.json:
        Path(args.json).write_text(json.dumps(rows_out, indent=2, default=list))
    return 0


if __name__ == "__main__":
    sys.exit(main())
