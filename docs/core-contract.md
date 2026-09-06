# Phase 1 core contract

The app reads the owned Postgres index. Existing structural scores remain a
comparison baseline, not a claim of authentic quality or personal fit. Phase 2
owns ranking experiments, hours and event sourcing. No new navigation or UI
dependency was added in Phase 1.

## Serving and interaction history

Each returned card receives a server-generated `decision_id`. Its immutable
`recommendation_decision.payload` contains the owned record/entity IDs, score,
components, explanation, display fields and batch rank. Events must reference
that user's decision. Client scores, explanations and display payloads are not
trusted. A database rescore cannot change the score attached to an old swipe.

Accept and reject are mutually exclusive for one decision. Retries of the same
event are idempotent. Impressions require the current card to be at least half
visible while Discover is focused and the app is in the foreground. They are not
recorded merely because a batch arrived. Dev-auth decisions/events are marked
`test_activity=true`, including the known earlier dev-account events; exclude
these from future behavioral training. Human field-kit labels stay separate.

Trip acceptance saves a stop from the server's owned snapshot and records accept
and save atomically. Duplicate submissions return the existing stop. Only one
unfinished stop is allowed. Directions launch records navigate; arrival must
precede completion. A 1–5 integer rating and optional review are the user's own
data. Completing a trip retains its stops and review in Profile. Existing trips
without a decision receive an explicitly unsnapshotted legacy decision when an
interaction requires one; no historical score is invented.

`share` means handing a saved place to Android's share flow. It does not prove
delivery to another person: Android cannot reliably distinguish cancellation
from a successful handoff through React Native's standard Share result. There
is no new messaging feature. Repeated event types for one decision retain the
first event; subsequent edits update the user's rating/review record.

## Geometry, filters and closure

Candidate retrieval uses canonical H3 geometry, exact radius filtering, active
KEEP records, the existing 0.30 floor, chain policy and suppression. It selects
one eligible representative per entity, ordered by cluster size, score and ID.
Deck ordering remains score then distance. Tag selection applies to the entire
eligible nearby pool before the 20-card limit; counts reflect that pool.
Local Gems has no inferred members until Phase 2 supplies supporting evidence.
Neither unknown categories nor low popularity imply authenticity.

Typed launch suggestions come from indexed localities, metro names and places.
Locality coordinates are an average of source points, not an official city
center. Coverage is limited to the owned index; ambiguous or uncovered input
requires another selection. GPS uses device coordinates directly.

A user's closed report excludes that entity for that user. Editorial reports
under user 0 exclude it globally. Reports never manufacture Google IDs. Google
suppression joins our entity-to-ID reference and excludes every mapped entity.
`suppressed_place` contains only the genuine Google ID and our timestamp.

## High-intent provider verification

`GET /api/places/details` requires an existing accepted decision. With a configured
Google key, it performs an ID-only text search when needed, then transient detail
verification. Exact normalized name and <=150 m proximity must agree before a
mapping or suppression is written. This conservative match can miss legitimate
renames or imprecise coordinates; it is not a solved closure detector.

Only the real `place_id` and our suppression timestamp survive. No Google names,
addresses, photos, ratings, reviews, hours, status strings or coordinates are
stored or returned as Adventour display content. There is no content cache.
Directions open Google Maps using owned coordinates (a name for approximate
locations), optionally adding a verified Google ID. No Overture ID is sent as a
Google destination ID. Missing credentials, network failure, mismatch or quota
exhaustion leave owned-coordinate navigation available; they do not certify open.

`GOOGLE_DAILY_CALL_LIMIT` defaults to six HTTP requests per user per UTC day,
bounded to 0–20. Search counts too. A separate transaction reserves quota before
network I/O, including failed requests; application rollback cannot refund it.
`provider_request` logs operation/count without keys or response content.
`deck_served ... provider_requests=0` is paired with a runtime guard on the only
Google adapter and an integration check that forbids outbound HTTP during deck
building. Google is absent from candidate retrieval and typed launch lookup.

## Verification limits

See [Phase 1 evidence](verification/2026-09-05/phase1-core.md). Real Google Places
verification and production Firebase login have not been demonstrated with live
credentials in this dev build. Provider response/quota behavior has isolated
mock-response coverage. The emulator's Google Maps app is an external navigation
destination, not a source for our place database.

Evaluation uses default eligibility across the metro, before radius/batch limits,
with the same representative ordering, active status and global suppression. It
keeps the originally labelled record's filter tier for filter diagnostics. User
reports only affect that user's deck, not the reference user-0 evaluation.
