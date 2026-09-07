# Active scope — Phase 2 (resumed after restart)

Phase 2 approved 2026-09-06: "Lets move onto phase 2. ill do a review of both
phases after." This overrides the Phase 1 review/merge prerequisite for this
transition only. Phases 3–5 remain closed. Phase 1 acceptance gaps remain open.

**Resume entry point:** [restart-handoff.md](restart-handoff.md).
Protocol: [phase2-discovery.md](phase2-discovery.md), following Phase 2 of the
approved takeover plan. Personal ranking is demonstrated in both seed metros;
the UCF event pipeline, Discover cards and organizer recheck now work. Current
evidence and unresolved quality/source gaps: [phase2-results.md](phase2-results.md).
Runbook: [local-events.md](local-events.md). Phase 2 is not declared complete.

Current event-coverage slice: owner continued Phase 2 after the NYC preview and
remaining-work review. Connect the NYC Parks factual public dataset with recorded
reuse/location provenance, source-specific refresh/recheck and emulator evidence.
This extends event coverage to NYC; it does not expand the place-index ingestion
scope or open Phase 3. Earlier NYC-preview-only limits are superseded for events.

## Phase 1 record retained for joint review

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

Provide reviewable progress about every two hours. The original review/merge gate is overridden for Phase 2 by the approval above. Fresh human labels are needed for independent
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

Core checkpoint: serving now uses canonical H3 geometry and suppression; events
reference immutable owned decisions; provider access is uncached, accepted-only
and quota-limited. The emulator completed onboarding, typed launch, swipe,
directions, arrival, review, completion and saved history under a separate dev
identity. The original owner's profile/history was preserved. See the
[review packet](verification/2026-09-05/phase1-core.md) and
[core contract](core-contract.md). Home is 771 lines; Profile 1,015 is the largest
authored app source. Thirteen focused backend checks and TypeScript pass.

Phase 1 remains open for review/acceptance. Offline HTML rendered review and an
unaided human return remain outstanding; the browser tool blocked file URLs.
The owner-run metro workflow, live Firebase login, and live Google verification
are not claimed demonstrated. Strict correctly fails for missing held-out labels
and an accepted v2 comparison baseline. No ranking improvement or Phase 2 work is
claimed. Phase 2 was subsequently authorized above; these acceptance gaps remain open.
