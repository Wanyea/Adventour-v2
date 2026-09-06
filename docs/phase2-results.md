# Phase 2 review checkpoint — September 6, 2026

Scope: features 4/6/7 and 19/20, with hours/access research for 17/18. Phase 2
remains active; this is not final product acceptance. Phase 1's open acceptance
items remain in active-scope.md. No Phase 3 work has started.

## Owner-reported launch correction

Reproduced New York, NY displaying Orlando cards and UCF events. The cause was
`JJ Art And Design Productions` (owned record 99960d7d-ef5a-4d68-bdd1-b7552e8c51dd):
its address says New York/NY but its coordinates are 28.5533,-81.3742 in the
Orlando acquisition. Aggregating POI localities had made it a city suggestion.
The event radius filter itself correctly returned no events at real NYC coordinates.

The first correction restricted suggestions to acquired metros. The owner
rejected that restriction: destination search must work beyond Florida. It has
been replaced with worldwide Photon/OSM location lookup, separate from our place
and event index. Selecting a suggestion uses its exact returned coordinates;
editing/selecting a launch clears old cards/events and ignores old responses.
Events query the selected coordinates even when no place deck has loaded.

Verified in the updated emulator: Orlando shows UCF events; selecting New York
removes those events and shows the regional empty state while retaining New York
as a valid launch. Live backend results in `worldwide-launch.json` resolve NYC to
40.7127281,-74.0060152 (zero events), London to 51.5074456,-0.1277653 (zero), and
Orlando to 28.5421218,-81.379045 (seven). These are current acquisition results,
not a claim that those cities have no real events.

Current screenshots under `verification/2026-09-06/`:
`new-york-worldwide-launch.png`, `worldwide-orlando-events.png`, and
`new-york-worldwide-events.png`. Launching the NYC deck also returns zero picks
without old Florida cards (`new-york-worldwide-deck.png`). Previous `new-york-launch-fixed.png` and
`launch-region-fix.json` document the rejected intermediate restriction and are
superseded, not evidence of the final behavior. The two `*-before.png` screenshots
remain the original bug evidence.

All 21 backend tests and TypeScript pass. Tests cover global coordinate
preservation, search outage without metro fallback, disambiguation, and excluding
Orlando events at NYC coordinates. No owned index records or user history were
rewritten by the fix. See local-events.md for the geocoder's transient cache,
attribution and public-service limits. No paid API supplies candidates.

## Personal discovery

`personal_v1` ranks the complete eligible radius pool using saved interests,
the user's own smoothed feedback, distance and local-first policy. Rejections
and recent visits suppress repeats; impressions apply a smaller temporary penalty.
The exact contributions are saved in each serving decision. Structural index
score remains separate. No paid API supplies either deck.

The fixed 8 km comparison used 182 eligible Palm Coast entities and 2,691 Orlando
entities, with no history. First-ten results from `discovery-audit-after.json`:

| Metro / saved interests | Tag matches before → after | Mean distance before → after |
|---|---:|---:|
| Palm Coast / coffee, outdoors | 1 → 10 | 3,155 → 2,187 m |
| Palm Coast / arts, food | 9 → 10 | 3,155 → 1,608 m |
| Orlando / coffee, outdoors | 1 → 10 | 1,933 → 120 m |
| Orlando / arts, food | 8 → 10 | 1,933 → 62 m |

All four lists had zero duplicate entity IDs. These are behavior measurements,
not human quality judgements. In particular, Orlando's expanded pool includes
suspect records such as Orlando Parks & Recreation, Foodfirst Global Restaurants
and Morimoto Street Food near the fixed downtown center. Their presence needs
destination/location investigation; proximity and tag match cannot certify them.
There is no claim that personal ranking solves the index's traps or closures.

Actual emulator evidence: `personal-palm.png`, `personal-breakdown.png`,
`personal-orlando.png`, `orlando-breakdown.png` under verification/2026-09-06/.
The Orlando coffee-filter screen shows Pepito's Full Belly Cafe at fit .7604:
.5 interest + .1604 distance + .1 local policy, with zero feedback/repeat terms.
Its selected locality center differs from the fixed audit center. The launch
lookup has since moved to worldwide Photon/OSM suggestions rather than deriving
cities from indexed venue localities. No paid geocoding was introduced.

## Three experiment dispositions

**Text — retain the small, explainable tag path; remove a false-positive hint.**
The original 268 labelled development records were inspected for category/name
disagreements. Generic `cafe` in a name also tagged Thai and other restaurants as
coffee/sweets. That name-only hint was removed in backend and app; an actual cafe
category still qualifies. Explicit coffee/ice-cream hints remain. Six disagreements
remain (three per metro), including Swillerbees and Kelly's ice cream. `Farm & Haus
East End Market` gaining shopping is a remaining ambiguity, not a validated win.
No embedding service, authenticity weight, label or exclusion was added.

The first audit included one unlabelled Palm Coast row (269 raw rows total).
The corrected after-report excludes it (131 + 137 = 268 labels); the first report
is preserved rather than rewritten. Both metros remain development data.

**FSQ OS — access-limited, no quality result.** The official
[access documentation](https://docs.foursquare.com/data-products/docs/access-fsq-os-places)
requires a portal token or access to the gated
[Hugging Face dataset](https://huggingface.co/datasets/foursquare/fsq-os-places).
No credentials were supplied and no organization/contact/marketing terms were
accepted for the owner. The [schema](https://docs.foursquare.com/data-products/docs/places-os-data-schema)
describes the Apache-licensed OS fields. Zero records were matched; that is an
access limit, not evidence FSQ cannot help. No paid Places API or gated-data mirror
was substituted. Resume the declared 30-per-metro match when access is available.

**Venue sites — retain the bounded audit tool, do not promote a broad crawler.**
The frozen SHA256 sample was 30 eligible independent venues with websites per
metro, plus ten original closure-note controls reported separately. Homepages
and at most two same-host pages were tried, respecting robots and rate limits.
Six permitted JavaScript shells were rendered with the installed Chrome browser.
No HTML/descriptions or production provider facts were retained.

- 27/60 sites were readable; 14 were skipped for robots denial/unavailability,
  seven for unsupported/nonpublic URLs, five returned 404, three had SSL errors,
  and four had other HTTP/network failures.
- Five sites had structured hours; 13 had structured or visible hours signals.
  These are extraction candidates, not 13 verified planning schedules.
- Rendering recovered one additional visible-hours signal among six trials.
  It also exposed a parked landing page; rendering success is not venue validity.
- Two sites contained six Event nodes. Date, public access, location and source
  rights were not verified, so zero were promoted to the event index.
- Of ten human closure-note controls: four had no website, three returned 404,
  one had an SSL error and two were reachable. Hidden Treasure's reachable brand
  site does not establish that its labelled branch is open; Bird of Paradise's
  page had no usable visible text. No automatic closure or suppression was made.
- Cost: 267.2 seconds, 199 static requests and 12,966,727 static response bytes,
  including robots/control requests. Six browser renders add network traffic
  not included in those byte/request totals. No paid calls.

The sample favors indexed venues with websites. Human closure notes include
uncertainty and are not a fresh independently verified open/closed control set.
False-positive/negative closure rates and planning-ready yield remain unmeasured.
Unknown hours stay unknown. Phase 4 must verify usable windows and rights before
claiming a feasible itinerary; merely finding JSON-LD is insufficient.

## Local events and verification

The UCF feed, owned venue match, scheduled refresh loop, regional index API and
dated Discover section now work together. Seven public gallery occurrences were
eligible out of 98 occurrences in the fixed Sept 6–19 source sample. This is one
venue/series, not city-wide coverage. See [local-events.md](local-events.md) for
fields, provenance, retention, freshness, source gaps and restart command.

Actual emulator screens: `events-orlando.png` and `event-recheck.png`. The latter
follows a successful free organizer recheck and shows current date/location/access.
Maps launched but the emulator System UI hung at its location permission dialog;
the directions destination is not yet accepted as a successful visual check.

`expiry-visible-before.png` and `expiry-visible-after.png` show isolated timed
expiry, with the current control retained. `event-test-cancelled.png` shows
successful snapshot cancellation removal. No real event freshness was falsified.
The 24-hour stale bound and failure-not-renewing rule pass isolated backend tests.
All 18 backend tests pass against the isolated database; TypeScript compilation
passes. The largest authored app source is ProfileScreen.tsx at 1,021 lines;
HomeScreen.tsx is 773 and LocalEventsSection.tsx is 142. Generated lockfiles and
dependencies are exempt under the owner's approved exception. Strict evaluation
remains red for missing fresh held-out data and an
accepted comparison baseline. Its report now explicitly states that the existing
place-label diagnostics do not validate personalized fit. No baseline was reset.

## Review and remaining work

Review the fit explanations and dated Discover section jointly with Phase 1.
Remaining Phase 2 items are broader permitted source coverage, usable verified
hours/access evidence, and the destination/location issues exposed by the ranked
pool. Source access is not silently treated as solved. Preserve the five-phase
sequence; these gaps do not create additional phases or features.
