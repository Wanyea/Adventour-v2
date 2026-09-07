# Pilot controls and logging — first implementation checkpoint

**Implemented and exercised on Android, not ready for friends/TestFlight.**
All interactions in this packet are synthetic dev activity against
`adventour_ingest_check_20260905`. They are not human preference labels or
recommendation-quality evidence. Existing owner labels/history were preserved.

## What the owner can review

- [Pilot question on the actual card](pilot-question.png): Cafe Del Hidalgo,
  with a separate cafe-interest relevance question, optional reason/note and Skip.
- [Acknowledged answer](pilot-saved.png): “Very well” saved as ordinal value 3,
  with “Thanks, saved” shown only after server acknowledgment.
- [Exact score breakdown](pilot-score.png): saved interests 0.5, prior feedback 0,
  distance 0.198188, local policy 0.1, repeat 0 = **0.798188**.
- [Joined phone answer](phone-answer.json): original served payload, request
  context, invitation/presentation, exposure and answer. Replay of all **460**
  scored SQL-eligible candidates matched their saved scores and order exactly.
- [Standard build](standard-deck.png): an enrolled account sees the ordinary
  deck with no study controls. The next place differs because the earlier cafe
  impression affects repeat ranking; these are not different ranking engines.
- [Standard no-write check](standard-no-study-writes.json): requests 2, decisions
  20, signals 1, invitations 1, answers 1, unchanged across standard GPS/deck
  interaction and event reads. Compiled APP_VARIANT was `standard` even with the
  same study/build identifiers present. Core decisions/impressions still work.
- [Event question](event-question.png): explicitly synthetic Orlando occurrence,
  using appeal rather than pretending chronological event ordering is personalized.
- [Interrupted event upload](offline-pending.png): “Can't tell” selected and
  “Saving…” with backend stopped. The app was force-stopped before acknowledgment.
  After restarting the backend/app, the persistent outbox delivered
  [exactly one unknown answer](event-recovered-answer.json), with value null.
  An initial rehearsal exposed that retry only mounted with a card; recovery now
  also runs when the signed-in Home mounts or returns to foreground. The final
  restart demonstrated this correction. The live synthetic occurrences were
  cleaned after verification; their original study snapshots remain traceable.

## Validation

Native Android debug builds succeeded for pilot and standard native configurations.
The first pilot build took 4m27s; subsequent standard/pilot rebuilds took about
25 seconds. These are local build observations, not release or performance SLAs.
Metro supplied development JavaScript; this is not a frozen signed iOS build.

11 focused backend tests passed across pilot, personal-ranking, local-event and
core-lifecycle tests using isolated Postgres. Three client checks passed for
standard-build zero IO/rendering, lack of enrollment decision, and persistent
offline answer retry with stable identity. TypeScript and diff whitespace checks
passed. [Source ceiling](source-ceiling.json) has no authored file above 1,200;
third-party vendor code and generated lockfiles remain explicitly exempt.

The same serving model in both variants is now `personal_v2_ambiguous_rejects`:
an unexplained reject suppresses that item but no longer becomes a negative vote
for every associated category. Historical snapshots remain unchanged. No new
study answer automatically trains the model; no LLM biography was introduced.

## Limits and next slice

The implementation is a reviewable vertical slice, not the whole measurement
contract. [Runbook](../../../pilot-runbook.md) lists the remaining collection,
source coverage, recovery, retention/reporting and distribution gates. In
particular, replay begins after SQL eligibility; original source acquisition and
all pre-SQL exclusions cannot yet be reconstructed from these snapshots alone.

Next: complete the missing request/source/coverage and outcome accounting plus
feedback recovery/reporting, then measure on-demand acquisition for an unseeded
GPS region. Remote HTTPS/Firebase and an actual iPhone build follow that. No
friends were invited, remote endpoint published, or Phase 2 completion claimed.
