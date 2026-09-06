# Phase 1 review packet

Branch `codex-astra`; Phase 1 remains open for acceptance. Later phases are not
started. The five NYC Substack recommendations remain Phase 2 source leads.

## What changed

- Owned serving decisions preserve the exact score/components for every event.
  Stops cannot store client-supplied provider display fields. Suppression and
  canonical geometry now participate in retrieval. Tag filtering precedes the
  batch limit. The structural model itself was not retuned.
- Google content caches and paid candidate/geocoding functions were removed.
  Accepted-only verification has a persistent per-user daily request quota;
  only genuine provider IDs and our own suppression timestamps are stored.
- The original screens/navigation/palette remain. Home's styles and recommendation
  mapping were extracted before extending it. Changes visible to the reviewer:
  `Index` instead of `Match`, score breakdown, closed-report action, optional trip
  review entry, and sharing a saved place. Profile shows the user's review.
- Dev login follows the selected test email instead of silently using the
  configured owner's token. Sign-out persists; restarting retains the selected
  identity. Onboarding and profile reads require that identity. Existing owner
  history and all original human labels remain intact.

## Emulator walkthrough

Pixel_7_API_30, installed React Native dev build using current Metro JavaScript,
Flask on 8080 and working `adventour` Postgres database. This was not a fresh
native build. Test account `phase1screen@adventour.local`, user 3.

| Feature IDs | Evidence |
|---|---|
| 1–2 dev login, age gate, onboarding | [Under-13 blocked](age-gate.png); [coffee/outdoors selection](onboarding-tags.png); preferences persisted in [API/database record](core-lifecycle.json) |
| 3 typed launch | [Palm Coast owned suggestions](typed-launch.png); selected city resolved and served a deck |
| 3–4 GPS and structural score | [GPS deck](core-deck.png); [score explanation](score-breakdown.png) |
| 4 reject | [Physical left swipe advanced to La Pizza Nostra](phase1-after-pass.png) |
| 5 directions | [Google Maps route](directions.png); navigate event recorded. Maps initially requested location permission; the route used the test GPS origin supplied in Maps |
| 6 filtering | [Full nearby-pool counts](full-pool-tags.png); [nine-card Coffee & Sweets deck](coffee-filter.png) |
| 8 trip arrival/completion | [Arrived stop](arrival.png); [review entered before rating](review-entry.png); session 2 / stop 3 completed |
| 13,16 history and own review | [Completed trip](completed-history.png); [saved four-star review and original score](saved-review.png) |
| 7 share | [Android share sheet](share-sheet.png); dismissed without messaging anyone. This is a share handoff, not evidence of delivery |
| 7 closed report | [Report confirmation](closed-report.png); [deck advanced to Turtle Shack Cafe](after-closed-report.png). Refresh returns eight coffee cards for the reporter, nine for another test user |

La Pizza Nostra was served at **0.9770**. Its accept/save/navigate/arrival/rate
events retain that value and the same components. The text explicitly identifies
the review as an emulator test, not a real visit. Dev interactions are marked
`test_activity=true`. No human recommendation-quality evidence is inferred.
All nine required event types are present in the final database record. The
Twisters report is synthetic, affects only this test account, and is not evidence
that the business is closed. Other users retain that candidate.

Core implementation commit: `90b0cbe3`, 27 files, 1,264 insertions / 1,383 deletions.
This includes the 341-line Home extraction and 137-line lifecycle test. The
obsolete provider-registry test removal is separate at `1ad99ef3`. Earlier tooling
commits remain separate for review; no changes were merged or pushed.

## Checks and limits

- **13 focused backend tests pass**, including a real isolated Postgres lifecycle,
  exact-score persistence after a database rescore, other-user refusal, duplicate
  stop/event protection, untrusted-display exclusion, mocked provider quota and
  suppression, field-kit import and transactional metro refresh rollback.
- Observed backend log for the GPS all-picks and filtered requests:
  `deck_served user=3 cards=20 provider_requests=0` and
  `deck_served user=3 cards=9 provider_requests=0`. The integration test also runs
  with a nonempty test Google key and rejects any outbound HTTP during serving.
- **TypeScript `tsc --noEmit` passes.** [Source ceiling](source-ceiling.json): Home
  771 lines; Profile 1,015, the largest authored app file. Generated lockfiles and
  third-party `node_modules`/`vendor` are explicitly exempt. No minification or
  relocation outside the app was used to evade the rule.
- [Evaluation](evaluation-core.json) still exits **1**: no independent held-out
  metro and no accepted v2 comparison baseline. Development results are unchanged:
  Orlando bad 40/88 judged, Palm Coast 15/65. This is not evidence of better ranking.
- The working index was not reingested or retuned. A separate St. Augustine
  database proves the documented ingestion-to-deck workflow; it does not prove
  that an owner can run it unaided. See [data tooling](../../data-tooling.md).
- Offline field-kit export/import contracts pass. Actual browser rendering and
  an unaided stranger return remain unverified: browser automation rejected the
  local file URL. No alternate browser route was used to bypass that rejection.
- Production Firebase login and live Google Places verification remain unverified
  in this dev configuration. Missing credentials are not treated as proof those
  integrations work. Real Google Maps navigation did open externally.
- Existing social trip-copy defects, profile geography placeholders, personal
  ranking and local-gem evidence remain assigned to the already-approved later
  phases. They are not declared finished by this core checkpoint.

## Review next

Run the app, inspect the linked screens and the [core contract](../../core-contract.md),
then try the [owner field-kit/new-metro runbook](../../data-tooling.md). Record any
step requiring assistance. A knowledgeable reviewer for a fresh metro and live
auth/provider configuration are still needed to close the stated acceptance
gaps. No Phase 2 implementation starts before Phase 1 review and merge.
