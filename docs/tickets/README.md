# Adventour delivery tickets

This is the working queue beneath the five-phase roadmap. It keeps work small enough to review every few hours without creating a second product plan. Only one ticket is implementing at a time; review is part of that ticket. A ticket is `done` only when its code, tests, runtime evidence, and documentation agree.

## Ticket format

```markdown
# P2-XX — Observable outcome
Status: queued | ready | implementing | review | blocked | done
Phase/scope:
Authority:
Depends on:
Outcome:
In scope:
Excluded:
Allowed files/areas:
Acceptance:
- Observable behavior and failure behavior
- Required device/data evidence
Validation:
Evidence paths:
Implementation model:
Reviewer/model:
Blocker or decision needed:
Commit:
```

## Phase 2 queue

| Ticket | Observable result | Depends on |
| --- | --- | --- |
| P2-01 | Reconcile the measurement contract against implemented behavior, evidence, and gaps. | — |
| P2-02 | Capture bounded pre-SQL candidate membership, ordered exclusions, source/data releases, and replayable acquisition provenance. | P2-01 |
| P2-03 | Record request failures, durations, cold/warm state, acquisition linkage, source-check failures, and provider counts. | P2-02 |
| P2-04 | Complete feedback lifecycle: abandonment, event outcome linkage, corrections, continuously-open retry, and modal exposure checks. | P2-01 |
| P2-05 | Add retention/withdrawal operations, local outbox/export cleanup, and approved aggregate preservation. | P2-04 |
| P2-06 | Produce the reporting command and a full sampling/cap/missingness/replay rehearsal; recheck that standard builds write no study records. | P2-02–P2-05 |
| P2-07 | Acquire an unseeded GPS region through the PC service and show its local deck and score without disturbing existing metros/history. | P2-06 |
| P2-08 | Verify remote HTTPS access, real Firebase identity, local-only Postgres, restart/health behavior, and an off-network feedback join. | P2-07 |
| P2-09 | Configure iOS location/privacy, Firebase, pilot/standard native values, signing, and a macOS build path; produce an installable artifact without committing credentials. | P2-01; integrates with P2-08 |
| P2-10 | On a physical iPhone, verify login, GPS permission behavior, unseeded local deck, event links/expiry, feedback, offline delivery, and PC outage/cold acquisition. | P2-08, P2-09 |
| P2-11 | Prepare a concrete TestFlight artifact and review information, then run the two-person burden/comprehension pretest and freeze versions. | P2-10 |
| P2-12 | Run the finite seven-day pilot and report coverage, appeal/relevance, missingness, factual issues, burden, and the next evidence-backed slice. | P2-11 |

P2-09 through P2-11 are distribution/readiness work, not a new product phase. They remain blocked by external Apple/macOS, Firebase, HTTPS, and TestFlight access until those are actually available and verified.

Social, gamification, full-trip planning, and local-event expansion remain later roadmap features. They do not enter the Phase 2 queue merely because the pilot may generate evidence about them.

## Review record

Each closed ticket should link its evidence packet and commit here. Keep Phase 1 acceptance debt visible; closing this queue does not silently accept Phase 1 or open Phase 3.
