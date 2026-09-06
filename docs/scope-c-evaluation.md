# Evaluation harness — Phase 1 repair

Updated 2026-09-05. `Server/evaluation/`; original human labels and
`baseline.json` are preserved. The previous harness's green verdict was too weak:
Orlando labels influenced the filter, KEEP-only sampling was inferred from current
rather than original tiers, and AUC did not describe serving eligibility.

From `Server/`:

```powershell
.venv\Scripts\python.exe -m evaluation.harness
.venv\Scripts\python.exe -m evaluation.harness --strict
.venv\Scripts\python.exe -m evaluation.harness --output report.json
```

## What the report means

`label_sets.json` declares reviewer, original sampling population, source file,
metro, development/holdout role and which metros informed each component. Both
Palm Coast and Orlando are development sets. A metro is held out only if all its
registered sets say holdout and no component declares it fitted. This is an
explicit provenance contract, not proof that an engineer never looked at labels.
Prospective models must be frozen before new answers are inspected.

- **Default deck eligibility:** canonical entity, KEEP, authenticity >=0.30 and
  chains excluded, before location/radius/batch limits. It describes the labelled
  eligible sample, not exposure-weighted live user experience. Suppression and
  deterministic representative selection still need alignment in the serving slice.
- **Quality:** bad is junk, not-worth or tourist-trap. Report judged denominators
  and counts including unknowns; unknown does not mean good. Quality and closure
  are separate fields in new returns; an admired but closed place can be both.
- **AUC:** gem versus generic/not-worth/junk, with positive/negative observation
  counts and approximate 95% intervals. Solid, chain, trap and unknown are outside
  this historical contrast; traps still count in residual bad. All-tier signals
  are separate diagnostics. Neither metric estimates an independently sampled
  metro population; kits are stratified, ZIP-selected and judgement-dependent.
- **Filter:** recall only for originally all-tier samples. Reclassifying Orlando
  records cannot turn its KEEP-only sample into a filter-recall experiment.
- **Lost liked places:** count gems/solid places excluded by serving policy,
  including chains and score-floor exclusions. Universal Studios is currently
  exposed by this check; Phase 1 does not silently change chain/ranking policy.
- **Coverage:** normalize names, return exact-name matches and unresolved fuzzy
  suggestions separately. A suggestion is not a confirmed match. Exact name
  presence is not proof of an open, accessible, correct destination; multiple
  entities may share a name. Review aliases manually before claiming coverage.
- **Drift:** missing labelled index records, missing metros and changed answer
  hashes/sets are failures or make comparisons unavailable.

Multiple reviewers are retained as observations; the current confidence intervals
are not clustered by reviewer or entity and must not be presented as independent
user evidence. Named written answers and source provenance remain available.

## Strict and baselines

Strict exits 1 if no held-out metro has both positive and negative eligible
examples, a comparable v2 baseline is absent, labelled records disappear, label
sources change, the AUC contrast changes, or specified metrics regress. Known
liked exclusions and junk false positives cannot increase; residual bad and AUC
use a 0.03 tolerance. Development sets still catch known regressions but never
prove generalization. A green strict run alone will not certify a good deck.

`--save` explicitly records a comparison baseline at `baseline-v2.json`; it does
not waive failures or overwrite the immutable historical baseline. No v2 baseline
has been accepted yet. Compare eligibility changes and review their examples
before accepting one; never reset it to hide a regression.

Current [verification report](verification/2026-09-05/evaluation-v2.json): strict
exits **1**, no held-out metro and no comparable v2 baseline. Canonical serving
sample: Orlando bad **40/88** judged (118 including unknown); Palm Coast **15/65**.
These are development observations, not a ranking improvement. Earlier historical
AUC figures are not directly comparable after changing population/representative.

Eight focused tests cover the exposed evaluator and importer failure modes. The
next independent evidence requires fresh human labels, with the
[field-kit runbook](data-tooling.md). The emulator remains the product checkpoint.
