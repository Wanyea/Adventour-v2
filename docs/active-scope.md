# Active scope — Phase 1

Approved by the owner on 2026-09-05: "Go ahead with Phase 1."
Plan: [takeover-plan.md](takeover-plan.md), phase 1. Branch: `codex-astra`.
The earlier Scope A gates are preserved unchanged in [scope-a-evidence.md](scope-a-evidence.md).

## Scope and review slices

1. Evaluation provenance, serving-population metrics and strict validation.
2. Offline field kit, returned-label import and safe configurable metro ingestion.
3. Data boundary, suppression, exact served-decision logging and provider quotas.
4. Core auth/onboarding, launch, filtering, accept/directions, arrival/review/completion/history.

Feature IDs: 1–8, 13, 16, 21–23. Ranking experiments, events, social expansion,
full-trip generation and gamification stay in later phases.

UI work is explicitly limited to phase 1: extract cohesive Home logic before
extension, add truthful score breakdown and missing core feedback controls, and
fix observed failures. Keep navigation, palette and existing layout stable; no
new top-level screens or dependencies. All authored app source stays <=1,200 lines.

## Checkpoints

- First: corrected harness report with historical comparison and a prospective
  held-out requirement. No claimed recommendation-quality improvement.
- Next: offline field-kit export/import and isolated new-metro ingest/deck.
- Core: emulator screenshots of onboarding/launch, deck/score, directions,
  arrival/review/completion and saved history, with persisted event evidence.

Provide reviewable progress about every two hours. Do not open Phase 2 before
Phase 1 is reviewed and merged. Fresh human labels are needed for independent
validation; their absence must not be disguised by a green strict run.

## Current status

First tooling checkpoint: evaluation provenance/strict repair, offline kit/import,
and transactional configured ingestion implemented. Eight evaluator/import tests
and one isolated Postgres refresh/rollback test pass. Original labels and historical
baseline remain intact; strict correctly fails for missing holdout and v2 baseline.

St. Augustine example: 1,838 acquired records, 599 relevant, 500 KEEP / 491 entities
in `adventour_ingest_check_20260905`. The emulator displayed Gaufre's & Goods,
417 m away, in a 20-card deck. See
[screen](verification/2026-09-05/st-augustine-deck.png). This proves ingestion to
display, not quality. The working Orlando/Palm Coast index was not reingested.

Next: align serving with canonical geometry and suppression, exact decision
snapshots, provider boundary and core lifecycle. Offline HTML rendered review and
an unaided human return remain outstanding; the browser tool blocked file URLs.
