"""One command for honest regression reporting; diagnostics are not validation."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import coverage, datasets, metrics

BASELINE = Path(__file__).with_name("baseline-v2.json")
HISTORICAL = Path(__file__).with_name("baseline.json")
TOLERANCE = 0.03
REPORT_VERSION = 2


def collect():
    report = {"version": REPORT_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
              "population": "default deck eligibility before location/batch limits", "metros": {}}
    for metro in datasets.available_metros():
        rows, freeform = datasets.load(metro)
        provenance = datasets.metadata(metro)
        report["metros"][metro] = {
            "labelled": len(rows), "judged": len(metrics.judged(rows)),
            "missing_from_index": sum(bool(r.get("_missing_from_index")) for r in rows),
            "provenance": provenance,
            "junk_filter": metrics.junk_filter_scores(rows, provenance["sampling_population"]),
            "chain": metrics.chain_scores(rows),
            "signals": metrics.signal_aucs(rows, served_only=True),
            "diagnostic_all_tiers": metrics.signal_aucs(rows),
            "serving": metrics.serving_scores(rows),
            "coverage": coverage.resolve(metro, freeform),
        }
    return report


def validation_issues(report, baseline):
    issues = []
    if not report["metros"]:
        issues.append("No label sets registered")
    held = [m for m in report["metros"].values() if m["provenance"]["held_out"]
            and m["signals"]["authenticity_score"]["auc"] is not None]
    if not held:
        issues.append("NO HELD-OUT METRO with both positive and negative served examples")
    comparable = baseline and baseline.get("version") == REPORT_VERSION
    if not comparable:
        issues.append("No comparable v2 baseline; historical all-tier AUC is not a serving baseline")
    elif set(baseline["metros"]) - set(report["metros"]):
        issues.append("Previously evaluated metros are missing from the current report")
    for metro, m in report["metros"].items():
        if m["missing_from_index"]:
            issues.append(f"{metro}: {m['missing_from_index']} labelled records missing from index")
        base = baseline.get("metros", {}).get(metro) if comparable else None
        if not base:
            if comparable:
                issues.append(f"{metro}: no baseline for this metro")
            continue
        if m["provenance"]["sets"] != base["provenance"]["sets"]:
            issues.append(f"{metro}: label sets changed; compare like-for-like samples before accepting a baseline")
            continue
        if m["provenance"].get("source_hashes") != base["provenance"].get("source_hashes"):
            issues.append(f"{metro}: human-answer files changed; comparison withheld")
            continue
        for name, current, previous in (
            ("junk false positives", m["junk_filter"]["false_positives"], base["junk_filter"]["false_positives"]),
            ("liked places excluded", m["serving"]["liked_excluded"], base["serving"]["liked_excluded"]),
        ):
            if current > previous:
                issues.append(f"{metro}: {name} {previous} -> {current}")
        # Development sets still protect known behavior; they never prove generalization.
        b, v = base["serving"]["bad_rate"], m["serving"]["bad_rate"]
        if b is not None and v is not None and v > b + TOLERANCE:
            issues.append(f"{metro}: residual bad rate {b:.3f} -> {v:.3f}")
        a, b = m["signals"]["authenticity_score"], base["signals"]["authenticity_score"]
        if (a["n_pos"], a["n_neg"]) != (b["n_pos"], b["n_neg"]):
            issues.append(f"{metro}: serving contrast changed; AUC comparison withheld")
        elif a["auc"] is not None and b["auc"] is not None and a["auc"] < b["auc"] - TOLERANCE:
            issues.append(f"{metro}: served authenticity AUC {b['auc']:.3f} -> {a['auc']:.3f}")
    return issues


def _fmt(value):
    return "n/a" if value is None else f"{value:.3f}"


def render(report, baseline=None):
    for metro, m in report["metros"].items():
        p = m["provenance"]
        tag = "HELD OUT" if p["held_out"] else "DEVELOPMENT — NOT GENERALIZATION EVIDENCE"
        print(f"\n{metro.upper()} [{tag}]")
        print(f"  {m['judged']} judged / {m['labelled']} labelled; {len(p['reviewers'])} reviewer(s)")
        print(f"  Original sampling: {p['sampling_population']}; fitted components: {p['fitted_on']}")
        jf, served = m["junk_filter"], m["serving"]
        print(f"  Junk recall: {_fmt(jf['recall'])}; false positives: {jf['false_positives']}")
        if p["sampling_population"] != "all_tiers":
            print("    Recall withheld: original sample was not drawn across all tiers.")
        print(f"  Default deck sample bad: {served['bad']}/{served['judged']} judged; "
              f"{served['including_unknown']} including unknowns")
        print(f"  Liked examples excluded by deck policy: {served['liked_excluded']}")
        for name in served["liked_excluded_names"]:
            print(f"    {name}")
        print("  Serving-population signals (gem vs generic/not_worth/junk):")
        for name, s in m["signals"].items():
            ci = f"[{s['ci'][0]:.2f}, {s['ci'][1]:.2f}]" if s["ci"] else "n/a"
            print(f"    {name}: {_fmt(s['auc'])} {ci}, n={s['n_pos']}/{s['n_neg']}")
        print("    Intervals are approximate observation-level intervals, not independent-user evidence.")
        a = m["signals"]["authenticity_score"]
        if a["ci"] and a["ci"][0] <= .5 <= a["ci"][1]:
            print("    Authenticity interval includes 0.5: no demonstrated signal.")
        print(f"  Historical-population diagnostic AUC: "
              f"{_fmt(m['diagnostic_all_tiers']['authenticity_score']['auc'])}; not a deck metric")
        print(f"  Must-have exact name matches: {m['coverage']['exact']}/{m['coverage']['named']}; "
              "unresolved suggestions in JSON are not confirmed coverage")
        print(f"  Missing index records: {m['missing_from_index']}")
    issues = validation_issues(report, baseline)
    print("\nSTRICT CHECK:")
    if issues:
        for issue in issues:
            print(f"  FAIL: {issue}")
    else:
        print("  No detected regression; statistical strength and screen review still matter.")
    return issues


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--save", action="store_true", help="explicitly record the v2 comparison baseline")
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    ap.add_argument("--output", type=Path, help="save this report without changing a baseline")
    args = ap.parse_args()
    if args.save and args.baseline.resolve() == HISTORICAL.resolve():
        ap.error("The original historical baseline is immutable; choose a different path")
    try:
        report = collect()
        baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline.exists() else None
    except (OSError, ValueError) as exc:
        print(f"Evaluation unavailable: {exc}", file=sys.stderr)
        return 1
    issues = render(report, baseline)
    for target in ([args.output] if args.output else []) + ([args.baseline] if args.save else []):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Report written: {target}")
    if args.save:
        print("Baseline recorded explicitly; this does not waive any validation failure above.")
    return int(bool(args.strict and issues))


if __name__ == "__main__":
    sys.exit(main())
