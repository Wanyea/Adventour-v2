# Scope C — Evaluation Harness

**Status:** built and verified 2026-08-19. `Server/evaluation/`.

```
python -m evaluation.harness            # report against the stored baseline
python -m evaluation.harness --save     # accept current numbers as baseline
python -m evaluation.harness --strict   # exit 1 on a held-out regression
```

## Why it exists

Gate 12. The authenticity score was fitted on Palm Coast, reported at AUC 0.954 against those same
labels, and turned out to be 0.639 out of sample. That gate only happened because a second metro was
hand-labelled on a hunch. The harness makes that check automatic and makes the mistake structurally
hard to repeat.

## The two rules it enforces

**1. In-sample results are labelled and excluded from the verdict.** `datasets.FITTED_ON` records
which metro each component was tuned on. Palm Coast is marked IN SAMPLE for the junk filter and the
authenticity score, and its numbers never reach the verdict line. If every label set has been used
for fitting, the harness says so rather than printing a reassuring number:

> NO HELD-OUT METRO. Every label set was used to fit something — these numbers cannot tell you
> whether anything generalises.

**2. Every metric carries its n and a confidence interval.** A point estimate on ~80 places is not a
fact. Where the 95% interval includes 0.5 the harness says, in words, that the signal is not
distinguishable from noise.

## What it measures

- **junk filter** — recall, precision, and false positives (the number that must stay 0). Recall is
  reported `n/a` when the sample was drawn from KEEP only, because everything in such a sample
  already passed; `residual bad rate` is the honest metric there, given **both** with and without
  unknowns in the denominator, since unknowns still get dealt to a user.
- **chain classifier** — agreement with human "chain" calls, plus any liked place wrongly flagged.
- **signals** — AUC for the authenticity score and each input, with intervals.
- **coverage** — the must-have places the labeller named, which precision metrics cannot see.
- **index drift** — labelled places that no longer exist in the index after a re-ingest.

## Verified, not assumed

The harness was tested by deliberately breaking the score — `W_CONFIDENCE` set to 0 and the weight
moved to socials — then re-scoring:

```
DN authenticity_score  0.639 -> 0.586  (-0.053)   <- REGRESSION
REGRESSIONS:
  - orlando.authenticity_score 0.639 -> 0.586
--strict exit 1
```

Reverted and re-scored, `--strict` returns 0. So it detects a real regression on the held-out metro
and passes when the code is sound.

## What it says about the current state

| | Palm Coast (in sample) | Orlando (held out) |
|---|---:|---:|
| authenticity AUC | 0.954 | **0.639**  [0.49–0.79] |
| overture confidence | 0.777 | 0.637  [0.49–0.79] |
| junk false positives | 0 | 0 |
| residual bad in served deck | 20.8% | **43.9%** (34.3% incl. unknowns) |
| chain agreement | 83.3% | 90.9% |

**All five signals on Orlando straddle 0.5.** The honest reading is not "the score is weak" but
"at n=19/60 we cannot tell whether it works at all."

## What this means for Scope B

Scope B cannot proceed as ranking-weight tuning. There is nothing measurable to tune against: the
only held-out evidence has intervals wide enough to contain "no signal". Tuning weights now would
fit noise and the harness would correctly refuse to confirm any improvement.

Two things unblock it, in order of cost:

1. **More labels.** Intervals shrink with n. Another metro, or deeper coverage of Orlando, moves
   0.49–0.79 toward something decidable. Cheap, and it is the labeller's time rather than build time.
2. **Behavioural data.** `place_event` already snapshots the score at decision time; accepts and
   rejects are the signal that does not depend on anyone's afternoon. This needs real usage.

Until one of those lands, the useful work is reducing the 43.9% residual junk — a problem the
Orlando labels describe concretely (university-only, ticket-required, inside-a-venue, hotel, closed)
and which needs no statistical power to act on.
