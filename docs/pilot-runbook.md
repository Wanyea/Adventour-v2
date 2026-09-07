# Pilot implementation/runbook — September 7, 2026

This is the first implementation slice of the approved
[measurement contract](pilot-measurement-contract.md), not permission to recruit
friends yet. Windows/emulator rehearsal uses the isolated ingestion database.
No TestFlight release or public backend has been configured.
Review [actual screens and joined evidence](verification/2026-09-07/pilot/README.md).

## Build and enrollment boundary

Each friend signs in with their own Firebase account using the existing app auth
flow. The backend derives user identity from the verified token, loads that user's
saved interests/history, and owns the recommendation-to-feedback join. Enrollment
adds a separate study participant ID; it does not replace sign-in. Both enrolled
users and standard users use the same personal recommender. Study questionnaire
answers are kept for analysis and do not yet automatically update taste weights.
Real Firebase sign-in on an iPhone remains a required device checkpoint; the
evidence here uses the explicitly marked local dev-auth bypass.

The native react-native-config values must contain `APP_VARIANT=pilot`, a nonempty
`PILOT_ID` and `APP_BUILD_ID`. Otherwise the app performs no study storage/network
work and renders no study controls, even if a stale card carries a pilot ID.
Use `.env.pilot.example` as the non-secret template. Build with explicit `ENVFILE`;
reloading Metro does not change the native build values. Do not identify all
TestFlight installations as pilot participants automatically.

The backend also requires an active matching build and account enrollment. A
standard request exits before reading study tables. No public enrollment endpoint
exists. Run from `Server` with the intended `ENV_FILE` set, after the participant
has agreed to the study explanation and retention policy:

```powershell
.venv\Scripts\python.exe -m data_pipeline.pilot_admin allow-build --pilot phase2-friends-v1 --build pilot-001
.venv\Scripts\python.exe -m data_pipeline.pilot_admin enroll --pilot phase2-friends-v1 --user-id USER_ID --consent-version pilot-intro-v1
.venv\Scripts\python.exe -m data_pipeline.pilot_admin revoke --pilot phase2-friends-v1 --user-id USER_ID
```

Replace USER_ID with the existing authenticated person's integer ID. The local
rehearsal uses `phase2-local-rehearsal`, `pilot-local-001`, synthetic identities,
and `.env.ingest-check`; never enroll a real friend through a dev-auth identity.
Client build headers are not a cryptographic build attestation. Authentication,
server-approved builds and enrollment enforce this trusted-pilot boundary.

## Implemented

- Additive study tables for enrollment, requests, immutable place/event decisions,
  exposure/action signals, invitations and explicit feedback revisions. Core
  decisions and normal interaction logging continue on the same recommender path.
- Pilot requests record location/radius/interests/build, scoring rules hashes,
  history inputs, SQL-eligible IDs, post-SQL exclusions, full scored order and
  returned card facts. Event snapshots record chronological ordering, not invented
  personal scores. Organizer rechecks get a linked revision for the facts used.
- Optional questions use versioned 0–4 appeal/relevance labels, explicit unknown,
  Skip, optional reason/problem subtype and a 280-character note. No default answer.
  Server sampling probability is 0.25; caps reserve at most two invitations per
  session, three per local day and ten minutes between them. `offered_at` means
  server-issued/reserved; `presented_at` separately records actual UI presentation.
  Reserved but never presented invitations are not counted as answered/skipped.
- View measurement samples half-card foreground visibility at 250ms intervals
  over at least one second. It is an operational approximation; it cannot prove
  attention or visibility between samples. Core legacy impressions retain their
  prior definition; study exposures are separate.
- Study feedback/skip uploads use a persistent account/study/backend-specific
  outbox and stable IDs; server acknowledgments are distinct from pending uploads.
  Revocation blocks delivery. Invalid/conflicting responses are retained locally
  as rejected instead of being retried forever. Standard builds never flush it.
- Ordinary event background refreshes request no study capture and preserve an
  existing decision only if its displayed facts have not changed. Manual refresh
  creates a new request. This prevents minute refreshes from clearing answers to
  an unchanged occurrence.
- Both app variants use `personal_v2_ambiguous_rejects`: rejections still suppress
  that item, but no longer establish a negative category preference. Accept/rate
  evidence remains; questionnaire answers are analysis-only. Historical decisions
  and labels are unchanged. This is a semantic correction, not a measured fit win.

## Export and replay

Exports include private selected coordinates and user-written notes. Keep them
local for the agreed study purpose; do not commit real-participant exports.
The exporter replaces account IDs with participant IDs, joins invitations/answers
and core actions to immutable card records, and refuses to overwrite an output.

```powershell
.venv\Scripts\python.exe -m data_pipeline.pilot_admin export --pilot phase2-friends-v1 --output pilot-private-export.json
.venv\Scripts\python.exe -m data_pipeline.pilot_admin replay --pilot phase2-friends-v1 --request-id REQUEST_UUID
.venv\Scripts\python.exe -m data_pipeline.pilot_admin purge --pilot phase2-friends-v1
```

Replay checks rule fingerprints/model and recomputes scoring/order from captured
SQL-eligible inputs. It does not replay acquisition or the earlier SQL exclusions.
Purge removes study requests older than 30 days and cascades dependent raw study
records. It does not remove normal app history, manually exported files or local
phone outboxes. Scheduling purge and preserving suitable anonymous aggregates
before raw expiry remain required before recruitment.

## Remaining before the friends wave

The measurement contract remains the acceptance checklist. Do not describe this
slice as complete instrumentation: full pre-SQL/source acquisition snapshots,
failed-request/latency accounting, data-release IDs, outcome linkage for event
attendance, source-check failures, complete prompt abandonment accounting,
outbox expiry/withdrawal cleanup and user-visible correction/recovery remain.
The current outbox retries on signed-in Home foreground/mount. One interrupted
event answer survived a force-stop and was uploaded once on emulator restart;
recovery while continuously open still needs verification. Exposure
behavior under all native alerts/modals needs checking. Sampling assignment and
caps are recorded but a full reporting command and pretest are still outstanding.

Then finish GPS-driven regional acquisition on the PC and remote HTTPS/Firebase
rehearsal. For iPhone distribution, follow the bounded [distribution
checklist](iphone-distribution-checklist.md) for iOS configuration, signing,
archive, TestFlight and off-network validation. An empty region is not
worldwide coverage. Keep all Phase 2 source/hour/access and Phase 1 acceptance
gaps visible. No invitations before those readiness gates.
