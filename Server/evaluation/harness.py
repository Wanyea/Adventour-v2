"""Scope C — one command that says whether a change helped or hurt.

    python -m evaluation.harness              # report, compared to the baseline
    python -m evaluation.harness --save       # accept current numbers as baseline
    python -m evaluation.harness --strict     # non-zero exit on regression (for CI)

Two rules are enforced structurally rather than by discipline:

1. **In-sample results are labelled and excluded from the verdict.** The
   authenticity score and junk filter were fitted on Palm Coast, so Palm Coast
   numbers are memorisation. Only held-out metros count.
2. **Every metric carries its n and, where meaningful, a confidence interval.**
   Gate 8 reported AUC 0.840 on n=46 as though it were settled; out of sample it
   was 0.639. An interval that straddles 0.5 makes that visible immediately.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import datasets, metrics

BASELINE = Path(__file__).resolve().parent / "baseline.json"

# A regression bigger than this on a held-out metric fails --strict. Loose on
# purpose: with ~80 labelled places per metro, small moves are noise.
TOLERANCE = 0.03


def collect():
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "metros": {}}
    for metro in datasets.available_metros():
        rows, freeform = datasets.load(metro)
        judged = metrics.judged(rows)
        report["metros"][metro] = {
            "labelled": len(rows),
            "judged": len(judged),
            "missing_from_index": sum(1 for r in rows if r.get("_missing_from_index")),
            "junk_filter": metrics.junk_filter_scores(rows),
            "chain": metrics.chain_scores(rows),
            "signals": metrics.signal_aucs(rows),
            "coverage": metrics.coverage(rows, freeform),
            "in_sample": {c: datasets.in_sample(c, metro)
                          for c in ("junk_filter", "authenticity")},
        }
    return report


def _fmt(v, pct=False):
    if v is None:
        return "  n/a"
    return f"{100*v:5.1f}%" if pct else f"{v:.3f}"


def render(report, baseline=None):
    regressions = []
    for metro, m in report["metros"].items():
        held_out = not m["in_sample"]["authenticity"]
        tag = "HELD OUT" if held_out else "IN SAMPLE (fitted here — not evidence)"
        print(f"\n{'='*70}\n{metro.upper()}  —  {m['judged']} judged of {m['labelled']} labelled   [{tag}]\n{'='*70}")
        if m["missing_from_index"]:
            print(f"  ! {m['missing_from_index']} labelled places no longer in the index")

        jf = m["junk_filter"]
        print("\n  junk filter")
        if jf["sample_is_keep_only"]:
            print("    recall            n/a  (sample drawn from KEEP only)")
        else:
            print(f"    recall           {_fmt(jf['recall'], True)}  (n={jf['recall_n']})")
        print(f"    precision        {_fmt(jf['precision'], True)}")
        print(f"    false positives  {jf['false_positives']:>5}   <- must stay 0")
        for n in jf["false_positive_names"][:4]:
            print(f"      !! dropped a place they liked: {n[:44]}")
        print(f"    residual bad     {_fmt(jf['residual_bad_rate'], True)}"
              f"  ({jf['residual_bad_n']}/{jf['served_n']} of judged places we would serve)")
        print(f"    ... incl unknown {_fmt(jf['residual_bad_rate_incl_unknown'], True)}"
              f"  ({jf['residual_bad_n']}/{jf['served_incl_unknown_n']} — unknowns get dealt too)")

        ch = m["chain"]
        print(f"\n  chain classifier   {_fmt(ch['agreement'], True)} agreement "
              f"(n={ch['human_chain_n']}), {ch['flagged_but_liked']} liked places flagged as chains")

        print("\n  signals (gem vs generic/not_worth/junk)")
        for name, s in m["signals"].items():
            ci = f"[{s['ci'][0]:.2f}–{s['ci'][1]:.2f}]" if s["ci"] else ""
            weak = " ~ straddles 0.5" if s["ci"] and s["ci"][0] < 0.5 < s["ci"][1] else ""
            print(f"    {name:<24}{_fmt(s['auc'])}  {ci:<14}n={s['n_pos']}/{s['n_neg']}{weak}")

        if baseline and metro in baseline.get("metros", {}):
            base = baseline["metros"][metro]
            print("\n  vs baseline")
            for name, s in m["signals"].items():
                b = base["signals"].get(name, {}).get("auc")
                if b is None or s["auc"] is None:
                    continue
                d = s["auc"] - b
                mark = "  " if abs(d) < 0.005 else ("UP" if d > 0 else "DN")
                flag = ""
                if held_out and d < -TOLERANCE:
                    flag = "   <- REGRESSION"
                    regressions.append(f"{metro}.{name} {b:.3f} -> {s['auc']:.3f}")
                print(f"    {mark} {name:<24}{b:.3f} -> {s['auc']:.3f}  ({d:+.3f}){flag}")
            bfp = base["junk_filter"]["false_positives"]
            if m["junk_filter"]["false_positives"] > bfp:
                regressions.append(
                    f"{metro}.false_positives {bfp} -> {m['junk_filter']['false_positives']}")
                print(f"    DN false_positives      {bfp} -> {m['junk_filter']['false_positives']}"
                      f"   <- REGRESSION")

    print(f"\n{'='*70}")
    held = [k for k, v in report["metros"].items() if not v["in_sample"]["authenticity"]]
    if held:
        print(f"VERDICT is based on held-out metros only: {', '.join(held)}")
        for k in held:
            a = report["metros"][k]["signals"]["authenticity_score"]
            line = f"  {k}: authenticity AUC {_fmt(a['auc'])}"
            if a["ci"]:
                line += f"  {a['ci'][0]:.2f}–{a['ci'][1]:.2f}"
            print(line)
            # The point of the interval is to stop a point estimate being quoted
            # as a fact. Say it in words, not just as a bracket in a column.
            if a["ci"] and a["ci"][0] < 0.5 < a["ci"][1]:
                print(f"    ^ interval includes 0.5: at n={a['n_pos']}/{a['n_neg']} this is")
                print("      NOT DISTINGUISHABLE FROM NO SIGNAL. Do not tune against it;")
                print("      more labels, or a different signal, are needed first.")
            weak = [n for n, s in report["metros"][k]["signals"].items()
                    if s["ci"] and s["ci"][0] < 0.5 < s["ci"][1]]
            if len(weak) == len(report["metros"][k]["signals"]):
                print(f"    ^ ALL {len(weak)} signals straddle 0.5 on {k}.")
    else:
        print("NO HELD-OUT METRO. Every label set was used to fit something —")
        print("these numbers cannot tell you whether anything generalises.")
    if regressions:
        print("\nREGRESSIONS:")
        for r in regressions:
            print(f"  - {r}")
    return regressions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="write current numbers as the baseline")
    ap.add_argument("--strict", action="store_true", help="exit non-zero on a held-out regression")
    args = ap.parse_args()

    report = collect()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else None
    regressions = render(report, baseline)

    if args.save:
        BASELINE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nbaseline written -> {BASELINE.name}")
    elif not baseline:
        print("\n(no baseline yet — run with --save to record one)")

    return 1 if (args.strict and regressions) else 0


if __name__ == "__main__":
    sys.exit(main())
