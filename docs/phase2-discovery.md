# Phase 2 — bounded discovery protocol

Declared 2026-09-06 before new experiments. Approved parent scope:
[takeover-plan.md](takeover-plan.md), Phase 2. The owner's "Lets move onto phase 2.
ill do a review of both phases after" overrides the Phase 1 review/merge gate for
this transition only. Phases 3–5 remain closed. No acceptance gaps are waived.

## Personal baseline

Use saved tags and only this user's owned feedback. No demographic inference,
popularity penalty, or new preference controls. Rank the full eligible radius
pool before limiting. Keep existing candidate exclusions for comparison.

Version `personal_v1`: interest match (0–0.5), smoothed category feedback
(-0.2–0.2), distance (0–0.2), independent/regional preference (0–0.1).
Latest decisive outcome per entity over 90 days: rating overrides accept/reject,
no compounding nine events into nine votes. Shrink each tag estimate with three
neutral observations. Test-identity history affects only that identity, never
other people's scores or quality evaluation. An explicit filter restricts the
pool; no saved interests means zero interest contribution.

Exclude this user's rejections for 30 days and acceptances/visits for 7 days.
Impressions alone cause a 0.1 penalty for 24 hours, not exclusion. Return exact
contributions, feedback count, version and separate structural score. Neither
score is a probability or authenticity verdict. Deterministic entity-ID ties.
Availability is unknown unless independently verified; never invent hours.

Compare first 10 at Palm Coast (29.5844,-81.2079) and Orlando
(28.5383,-81.3792), 8 km, with coffee/outdoors and arts/food profiles. Record tag
match, distance, duplicates/repeats and named cards before/after. These are
behavior checks, not human quality labels. Preserve original evaluation reports.

## Three experiments, fixed before outcomes

1. **Text:** original development labels; deterministic category/name text
   matching to existing interests versus category-only. Inspect disagreements
   in stable ID order (up to 20 per metro). Retain only explainable useful tag
   changes; a semantic match cannot establish quality, closure or public access.
2. **FSQ OS:** verify official access/license/schema; attempt a bounded extract.
   Match up to 30 independent eligible entities per metro, ordered by SHA256(ID),
   using name and proximity/address. Report matches, conflicting facts and new
   fields. No paid Places API substitute. Stop at the checkpoint if credentials
   are required; report the access limit, not an impossible underlying problem.
3. **Venue sites:** 30 per metro with websites in SHA256(ID) order, plus up to
   10 human-labelled closed venues reported separately. Homepage and at most two
   relevant same-host pages, robots/rate limits. Render up to six permitted JS
   shells. Count structured hours, visible hours, Event records, public-access
   evidence and explicit closure notices separately. HTTP failure is unknown.
   No retained page text or unlicensed production facts. Report website-selection
   bias, acquisition cost, permissions and planning-ready yield.

Each family gets a roughly two-hour checkpoint and a measured keep/drop decision.
Both seed metros are development. Freeze retained models before fresh held-out
human answers arrive; no in-sample generalization claim.

## Events

First fixed sample: UCF main calendar September 6–19, 2026 (14 days). Count all
occurrences, then public/relevant/dated/located/Orlando occurrences with exclusion
and dedup reasons. Calendar visibility alone does not prove public admission.
Record permissions before persistence; UCF documents feeds for custom apps.

Next assess one library/municipal source per seed metro and the website sample.
Report social/newsletter leads and incremental verified events separately, never
infer city-wide coverage from UCF. Jackie's five NYC newsletters in the plan are
source leads; NYC is not an added implementation metro.

Permitted facts carry source/occurrence IDs, timezone, verification/expiry,
location confidence and official links. Refresh <=6 hours; query-time exclusion
at end or verification+24 hours. Failure never renews freshness; successful full
snapshots remove absent/cancelled occurrences within their sampled window.
Recheck selected events before departure. Serve the requested region from our
index. Add dates/access/source inside Discover, preserving navigation/palette,
with no new screen or UI dependency. Prove stale/expired/cancelled removal with
isolated synthetic rows, labelled as tests. All authored app files <=1,200 lines.

## Acceptance still open

Personal deck screens/scores; disposition of three experiments; fresh events and
coverage report; planning-hours/access report. Phase 1 still needs live Firebase/
Google, offline rendered kit, unaided owner tooling, held-out labels and accepted
comparison baseline. Joint review is deferred, not these claims declared passed.
