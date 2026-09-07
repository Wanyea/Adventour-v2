# Adventour v2 — current state

September 7: the [repeatable source pilot](verification/2026-09-07/calendar-pilot/README.md)
has run: six sources, 24 parsed pages, 11 candidates, none promoted to production.
[iPhone friends pilot requirements](iphone-friends-pilot.md) now include GPS
anywhere with acquisition/backend on the owner's PC, without seeded-city limits.
Automatic coverage acquisition and iOS distribution are not yet completed. The
[iPhone distribution checklist](iphone-distribution-checklist.md) records the
Mac/Xcode, Firebase, HTTPS, device and TestFlight gates; no iOS build is
claimed from this Windows workspace.
The [pilot measurement contract](pilot-measurement-contract.md) defines the data,
optional questions and verification required before friends testing. Its
[first implementation slice](pilot-runbook.md) adds pilot-only feedback and study
records, verified on Android; the friends release is not ready yet.

**Resumed after PC restart (2026-09-06).** Current checkpoint:
[phase2-results.md](phase2-results.md), with [local-events.md](local-events.md)
for the working event pipeline and remaining coverage gaps. Resume details are
in [restart-handoff.md](restart-handoff.md).

Owner-review fix: New York no longer resolves to an Orlando POI's coordinates.
Worldwide city/address lookup is independent of indexed coverage. Events follow
the selected launch coordinates; changing regions clears prior results;
see the launch correction in [phase2-results.md](phase2-results.md).
City/state labels are now distinct. NYC Parks is connected: 302 eligible dated
occurrences stored, shown only around NYC, alongside seven UCF dates for Orlando.
Both sources refresh every six hours while the local worker runs. See
[local-events.md](local-events.md) for daily-publication limits and screen evidence.

Updated 2026-09-06. Read [HANDOFF.md](../HANDOFF.md) for the closed 23-feature
product and stopping point, then [AGENTS.md](../AGENTS.md) for the working agreement.

**Phase 2 is approved and in progress on `codex-astra`.** The owner authorized
a joint Phase 1/2 review afterward; Phase 1 acceptance gaps remain open. The earlier data-foundation
scope is complete; its evidence is preserved in [scope-a-evidence.md](scope-a-evidence.md).
It is not the same as the current Phase 1. The complete approved direction is in
[takeover-plan.md](takeover-plan.md), with the current slice in
[active-scope.md](active-scope.md).

| Phase | Work | Status |
|---|---|---|
| 1 | Trustworthy core, evaluation, field kit and safe metro ingestion | Core/tooling implemented; emulator review and owner acceptance checkpoint |
| 2 | Discovery quality, hours/closure experiments and local events | Active; personal decks and UCF events demonstrated; quality/coverage gaps remain |
| 3 | Friends, Beacon, taking Adventours and group recommendations | Planned; not open |
| 4 | Full-trip planning and ticket/reservation links | Planned; not open |
| 5 | Travel map, achievements and all-23-feature acceptance | Planned; not open |

There is no phase after HANDOFF §6. Social, events, planning and gamification are
required parts of these five phases. NYC newsletter examples inform Phase 2
source discovery; they do not expand the seed metros.

## Verified starting point and current work

- PostgreSQL 17, Flask, Metro and the Android Pixel_7_API_30 emulator ran locally.
  The Palm Coast deck returned 20 picks without Google credentials. A rejection
  persisted. [Initial screen](verification/2026-09-05/palm-coast-deck.png),
  [after rejection](verification/2026-09-05/after-reject.png).
- Live baseline: 19,385 relevant source records; 15,263 KEEP records and 14,443
  distinct KEEP entities across Orlando and Palm Coast. These are index counts,
  not a claim that every entity should appear in a deck.
- The original harness passed strict despite missing independent end-to-end
  validation. Orlando labels informed the junk filter, so both supplied metros
  are now explicitly development data. Original answers and baseline are intact.
- The repaired harness reports serving eligibility separately from all-tier
  diagnostics, preserves original sampling provenance, and fails strict when
  independent validation is absent. The current
  [report](verification/2026-09-05/evaluation-core.json) exits 1. Do not interpret
  changed metric populations as improved recommendation quality.
- The field kit has stable manifests, independent quality/closure/access/booking
  answers and a validated multi-metro importer. Focused contracts pass; rendered
  offline HTML and an unaided human return remain unverified. See the
  [owner runbook](data-tooling.md).
- Transactional metro ingestion ran in an isolated database; the emulator showed
  a [St. Augustine deck](verification/2026-09-05/st-augustine-deck.png). An isolated
  test checks refresh/identity/history preservation and rollback. The owner-run
  acceptance check remains.
- The core emulator walkthrough completed dev login, age gate, onboarding, typed
  launch, swipe, directions, arrival, rating/review and saved history. The exact
  serving decision is preserved in events; synthetic activity is marked as test
  data. [Screen/evidence checklist](verification/2026-09-05/phase1-core.md).
- Candidate suppression, canonical H3 geometry, filtering before the batch limit,
  owned-only stop writes and high-intent Google quotas are implemented. Google
  content caches and paid candidate/geocoding paths were removed. The app displays
  a structural index score and its breakdown, not “Match 98%.” See the
  [core contract](core-contract.md) for behavior and verification limits.
- The source limit is 1,200 lines per authored app file; generated lockfiles and
  third-party dependencies are exempt. Home is 771 lines after cohesive extraction;
  Profile is the largest at 1,015. Thirteen focused backend checks and TypeScript
  compilation pass. No new screen, navigation entry, palette or dependency.

Ranking is not declared solved. The failed approaches in HANDOFF describe specific
experiments; they do not rule out semantic, cross-source or venue-owned evidence.
Hours and closure remain open measured problems. Full-trip work is not dependent
on an assumed purchasable hours licence.

## Run locally

From the repo root, in separate terminals:

```powershell
# Backend; Postgres must already be running on localhost:5432.
cd Server
$env:ENV_FILE=".env.local"
.venv\Scripts\python.exe app.py
```

```powershell
cd AdventourApp
npm run android:local:pixel7
```

For an already-installed emulator build, Metro can run with the local environment:

```powershell
cd AdventourApp
$env:ENVFILE=".env.android.local"
npx react-native start
```

The Android SDK is under `$env:LOCALAPPDATA\Android\Sdk`. Reverse ports 8080 and
8081 with adb if needed. `adb emu geo fix -81.2079 29.5844` sets Palm Coast test GPS.
Use emulator test activity as test data, not human preference evidence.

From `Server/`:

```powershell
.venv\Scripts\python.exe -m evaluation.harness --strict
.venv\Scripts\python.exe -m pytest tests/test_evaluation.py tests/test_field_kit.py -q
```

Strict is currently expected to fail on missing holdout/baseline evidence. See
[scope-c-evaluation.md](scope-c-evaluation.md) for interpretation. Follow the
[data runbook](data-tooling.md) for the replacement pipeline; begin in an isolated
database and review the preview before refreshing the working index.

## References

| Document | Purpose |
|---|---|
| [takeover-plan.md](takeover-plan.md) | Five-phase completion plan, keeps/deletions and screen checkpoints |
| [active-scope.md](active-scope.md) | Current authorized work and status |
| [scope-a-evidence.md](scope-a-evidence.md) | Original gate results, unchanged historical record |
| [data-tooling.md](data-tooling.md) | Owner field-kit/import instructions and pipeline status |
| [scope-c-evaluation.md](scope-c-evaluation.md) | Current harness contract and limitations |
| [sourcing-cost-decision-brief.md](sourcing-cost-decision-brief.md) | Provider boundary and cost decisions; apply current high-intent-only rule |
| [recommender-data-design.md](recommender-data-design.md) | Design reference; original schema/scoring claims partly superseded |
| [scope-e-local-events.md](scope-e-local-events.md) | Earlier source survey; Phase 2 plan adds concrete experiments |

`archive/` is historical. The abandoned `codex` branch is reference only; no code
has been ported from it.
# Delivery queue

The current ticket queue and review contract live in [tickets/README.md](tickets/README.md). It breaks the approved five-phase roadmap into dependency-ordered, reviewable slices; it does not create a second roadmap.
