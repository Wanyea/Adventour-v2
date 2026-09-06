"""Metrics for the evaluation harness.

Deliberately small and dependency-free. Every metric returns its own sample size
alongside the value, because a metric without an n is how Gate 8's 0.840 got
reported as if it meant something.
"""

import math

from .datasets import BAD, GOOD, JUDGED


def auc(pairs):
    """Rank AUC with ties at half credit. Returns (value, n_pos, n_neg)."""
    pos = [v for v, y in pairs if y]
    neg = [v for v, y in pairs if not y]
    if not pos or not neg:
        return None, len(pos), len(neg)
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg)), len(pos), len(neg)


def auc_ci(value, n_pos, n_neg):
    """Rough 95% interval (Hanley–McNeil).

    Present because the whole Gate 12 lesson is that a point estimate on ~50
    samples is not a fact. An interval that straddles 0.5 says so immediately.
    """
    if value is None or not n_pos or not n_neg:
        return None
    q1 = value / (2 - value)
    q2 = 2 * value ** 2 / (1 + value)
    var = (value * (1 - value)
           + (n_pos - 1) * (q1 - value ** 2)
           + (n_neg - 1) * (q2 - value ** 2)) / (n_pos * n_neg)
    se = math.sqrt(max(var, 0.0))
    return max(0.0, value - 1.96 * se), min(1.0, value + 1.96 * se)


def judged(rows):
    return [r for r in rows if r.get("label") in JUDGED and not r.get("_missing_from_index")]


def junk_filter_scores(all_rows):
    """Recall, precision and — the number that must stay zero — false positives.

    Only meaningful over a sample drawn from ALL tiers. A sample drawn from KEEP
    alone (as Orlando's was) cannot measure recall, because everything in it
    already passed. `residual_bad_rate` is the honest metric in that case.
    """
    rows = judged(all_rows)
    tiers = {r.get("tier") for r in rows}
    keep_only = tiers <= {"KEEP"}

    truth_junk = [r for r in rows if r["label"] == "junk"]
    dropped = [r for r in rows if r.get("tier") and r["tier"] != "KEEP"]
    caught = [r for r in truth_junk if r.get("tier") and r["tier"] != "KEEP"]
    false_pos = [r for r in dropped if r["label"] in GOOD]

    served = [r for r in rows if r.get("tier") == "KEEP"]
    residual_bad = [r for r in served if r["label"] in BAD]
    # Unknowns would still be dealt to a user, so they belong in the denominator
    # of "what fraction of a deck is bad" even though they cannot be scored.
    served_incl_unknown = [r for r in all_rows
                           if r.get("tier") == "KEEP" and not r.get("_missing_from_index")]

    return {
        "sample_is_keep_only": keep_only,
        "recall": None if keep_only or not truth_junk else len(caught) / len(truth_junk),
        "recall_n": len(truth_junk),
        "precision": None if not dropped else sum(1 for r in dropped if r["label"] in BAD) / len(dropped),
        "false_positives": len(false_pos),
        "false_positive_names": [r["name"] for r in false_pos],
        "residual_bad_rate": len(residual_bad) / len(served) if served else None,
        "residual_bad_n": len(residual_bad),
        "served_n": len(served),
        "residual_bad_rate_incl_unknown":
            len(residual_bad) / len(served_incl_unknown) if served_incl_unknown else None,
        "served_incl_unknown_n": len(served_incl_unknown),
    }


def chain_scores(rows):
    rows = judged(rows)
    called = [r for r in rows if r["label"] == "chain"]
    matched = [r for r in called if r.get("chain_class") == "chain"]
    flagged = [r for r in rows if r.get("chain_class") == "chain"]
    wrong = [r for r in flagged if r["label"] in GOOD]
    return {
        "human_chain_n": len(called),
        "matched": len(matched),
        "agreement": len(matched) / len(called) if called else None,
        "flagged_but_liked": len(wrong),
        "flagged_but_liked_names": [r["name"] for r in wrong],
    }


def signal_aucs(rows):
    """AUC of each signal on gem vs generic/not_worth/junk, among judged rows."""
    contrast = [r for r in judged(rows)
                if r["label"] in ("gem", "generic", "not_worth", "junk")
                and r.get("tier") is not None]
    for r in contrast:
        r["_y"] = 1 if r["label"] == "gem" else 0

    signals = {
        "authenticity_score": lambda r: float(r.get("authenticity") or 0),
        "overture_confidence": lambda r: float(r.get("confidence") or 0),
        "has_website": lambda r: 1.0 if r.get("websites") else 0.0,
        "has_socials": lambda r: 1.0 if r.get("socials") else 0.0,
        "cell_density_inverted": lambda r: -math.log1p(r.get("cell_density") or 0),
    }
    out = {}
    for name, fn in signals.items():
        value, npos, nneg = auc([(fn(r), r["_y"]) for r in contrast])
        out[name] = {"auc": value, "n_pos": npos, "n_neg": nneg, "ci": auc_ci(value, npos, nneg)}
    return out


def coverage(rows, freeform):
    """Are the places the labeller named as must-haves actually in the index?

    Recall against a wish list, which precision metrics cannot see.
    """
    wanted = [w.strip() for w in (freeform.get("missing") or "").split(",") if w.strip()]
    return {"named": len(wanted), "names": wanted}
