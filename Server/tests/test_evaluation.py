"""Regression cases exposed by the takeover audit; no provider or database calls."""

from copy import deepcopy

from evaluation import datasets, metrics
from evaluation.harness import validation_issues


def row(label="gem", **changes):
    return {"id": "a", "name": "Example", "tier": "KEEP", "authenticity": .8,
            "chain_class": "independent", "label": label, **changes}


def test_keep_only_sampling_cannot_turn_into_recall_after_retiering():
    result = metrics.junk_filter_scores([row("junk", tier="DROP"), row()], "keep_only")
    assert result["recall"] is None
    assert result["sample_is_keep_only"] is True


def test_served_metric_excludes_chain_and_below_floor_but_counts_unknowns():
    rows = [row(), row("junk", authenticity=.1), row("chain", chain_class="chain"),
            row("unknown"), row("trap")]
    result = metrics.serving_scores(rows)
    assert (result["bad"], result["judged"], result["including_unknown"]) == (1, 2, 3)
    assert metrics.signal_aucs(rows, served_only=True)["authenticity_score"]["n_neg"] == 0


def report(held_out=True):
    rows = [row(), row("junk", authenticity=.5)]
    return {"version": 2, "metros": {"example": {
        "provenance": {"held_out": held_out, "sets": ["example"]},
        "missing_from_index": 0, "junk_filter": metrics.junk_filter_scores(rows, "all_tiers"),
        "serving": metrics.serving_scores(rows), "signals": metrics.signal_aucs(rows, True),
    }}}


def test_strict_fails_without_holdout_even_against_identical_baseline():
    r = report(held_out=False)
    assert any("NO HELD-OUT" in x for x in validation_issues(r, r))
    assert datasets.metadata("orlando")["fitted_on"]["junk_filter"] is True
    assert datasets.metadata("orlando")["held_out"] is False


def test_strict_detects_drift_and_lost_gems_even_on_development_set():
    baseline = report(False)
    current = deepcopy(baseline)
    m = current["metros"]["example"]
    m["missing_from_index"] = 1
    m["serving"]["liked_excluded"] = 1
    errors = validation_issues(current, baseline)
    assert any("missing from index" in e for e in errors)
    assert any("liked places excluded" in e for e in errors)


def test_changed_population_cannot_pass_as_auc_improvement():
    baseline = report()
    current = deepcopy(baseline)
    current["metros"]["example"]["signals"]["authenticity_score"]["n_neg"] = 0
    assert any("contrast changed" in e for e in validation_issues(current, baseline))
    assert validation_issues(baseline, baseline) == []
