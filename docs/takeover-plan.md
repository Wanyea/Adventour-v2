# Adventour completion plan — Phase 2 approved and active

**September 7 pilot steering:** the owner requested an iPhone friends pilot,
usable from GPS wherever testers are without a seeded-city restriction, and
offered their PC as the data/backend server. [Pilot requirements and checkpoints](iphone-friends-pilot.md)
extend Phase 2 preparation to on-demand regional acquisition and remote testing;
earlier seed-only pilot/ingestion limits below are superseded for this work.
No place index needs to be bundled into the phone. The five-phase sequence and
closed feature list remain; iOS distribution is an additional owner-requested
pilot checkpoint, not a claim that the Android completion criteria are satisfied.
The [bounded source pilot](verification/2026-09-07/calendar-pilot/README.md) has run.

The subsequent [pilot measurement contract](pilot-measurement-contract.md) makes
traceable collection, short optional feedback, replay/export verification and a
finite review prerequisite to friends testing. It stays inside Phase 2; proposed
small feedback controls still need the UI approval specified in AGENTS.md.

Prepared 2026-09-05 after reading HANDOFF.md completely, AGENTS.md, the references in
HANDOFF §7, and both label files including their written answers. HANDOFF §5 is the
closed feature list; §6 is the stopping point. This replaces the inherited scope
sequence for the work authorized by the owner. Phase 1 was explicitly approved
on 2026-09-05 ("Go ahead with Phase 1"). Phase 2 was approved 2026-09-06 with joint review afterward, overriding the
review/merge prerequisite for this transition only. Phases 3?5 remain closed. The verification below records the pre-implementation baseline.

## Verified starting point

- The checkout was clean on `claude` at `99e3e1c2`, not on the advertised branch.
  Created `codex-astra` from that commit and switched to it. No code was imported
  from `codex`.
- PostgreSQL 17 is running and accepting connections on localhost:5432. The
  `adventour` database contains 19,385 place records: Orlando 18,673, Palm Coast
  712. There are 15,263 KEEP records and 14,443 distinct KEEP entities, versus
  14,484 in the older documentation. These are live counts, not a new ingestion.
- Started the existing Flask backend with `.env.local`; GET `/` returned 200.
  Started Metro from the installed React Native 0.77 dependencies. Booted the
  existing Pixel_7_API_30 emulator, set GPS to Palm Coast, and ran the installed
  app against this checkout's JavaScript. This was not a fresh native build.
- Dev auth, GPS launch, and the deck worked. The app received 20 picks. First:
  Thai By Thai Restaurant, 3,022 metres, displayed as “Match 98%”. A left swipe
  advanced to Palm Harbor Grill and persisted reject event 9 against entity
  `7567ac68-2a18-424c-85f9-d7998d9c12e3`, score snapshot 0.9823.
- [Initial deck](verification/2026-09-05/palm-coast-deck.png) and
  [after rejection](verification/2026-09-05/after-reject.png) are actual emulator
  screenshots. The deck has category artwork and no numerical explanation panel.
- For the actual Thai By Thai entity, the score recomputes as 0.649131 confidence
  contribution + 0.150000 social-link contribution + 0.183177 density contribution,
  multiplied by 1.0 for independent = 0.9823. This is the existing heuristic, not
  a calibrated probability of liking the place. “Active online” is unsupported
  by the mere presence of a social link.
- `Server/.venv/Scripts/python.exe -m evaluation.harness --strict` exited 0.
  Current Orlando authenticity AUC: **0.638**, approximate 95% interval
  **[0.49, 0.79]**, **19 positive / 60 negative** examples. All five reported
  signals include 0.5. Residual bad: **41/100** judged KEEP places, or **41/130**
  including unknowns. Neither number establishes good recommendations.
- Google credentials are absent in the local backend configuration; the deck
  route directly calls the owned-index service. The observed app run logged the
  recommendation request and successful event write. This confirms a deck can
  run with no Google credentials; it is not yet comprehensive outbound-call
  accounting with paid providers enabled.

## Findings that change the order of work

1. **The harness needs repair before it can police new work.** `junk_filter.py`
   explicitly contains rules derived from Orlando labels, while `FITTED_ON`
   declares only Palm Coast. Sampling provenance is inferred from current tiers,
   so Orlando's original KEEP-only sample is now misleadingly given recall.
   AUC uses all labelled tiers rather than the actual serving population;
   coverage currently lists requested names without resolving them. Strict mode
   does not fail merely because no held-out metro remains. Preserve the old
   results as historical evidence, not as a clean validation set for new tuning.
2. **The core is functional but incomplete.** The recommendation route ignores
   user taste, group members and mode; filtering happens within the 20 returned
   cards. The SQL ranks by authenticity then distance despite the service's
   nearest-first comment. GATED places cannot be opted into through this query.
   The logger reads today's database score rather than the exact served decision.
   No impression was recorded during this baseline deck run.
3. **Closure and provider boundaries need enforcement.** Serving does not consult
   `suppressed_place`. User reports manufacture an `adventour:` value in its
   Google-ID field. Google details/autocomplete have `lru_cache` decorators, and
   trip writes accept arbitrary client display metadata. The inspected baseline
   used owned-index data; these are unsafe paths to repair before enabling paid
   details. Google-origin suppression remains only a real Google place ID and
   our timestamp; user reports remain our event data.
4. **Social “exists” is not enough.** Friend Adventour serialization and copying
   still reference `AdventourStop.place_id` and `provider_ref_id`, which the model
   no longer has. Existing Trip/TripMember/TripPlace routes are live dependencies,
   so deletion must follow migration and an emulator demonstration.
5. **Tooling is not owner-complete.** Metro bounding boxes are hardcoded; the
   loader drops and rebuilds `places`; postcode enrichment is a separate script
   even though the field kit requires it. Field-kit exports can span metros but
   the harness hardcodes two label filenames. An offline export is not yet an
   unaided ingestion workflow.
6. **Events need a product decision, not an invented answer.** Orlando's
   `evsources`, `events`, `venues`, and `evwould` answers are blank. My proposed
   placement is a dated section within Discover, with only currently reachable
   events eligible for spontaneous recommendations. It introduces no top-level
   tab. The owner's answer takes precedence before implementation.

## Five phases, in this order

Each phase contains sequential, bounded review slices. Only one is active at a
time. A phase must be reviewed and merged before the next opens. UI permissions
below are specific to the listed features; they do not permit a redesign.

### 1. Establish a trustworthy core and owner-operated evidence loop

**Feature coverage:** 1–8, 13, 16, 21–23. Complete the foundations and spontaneous
trip lifecycle, with data tooling early enough to collect independent evidence
while later work proceeds.

- Correct evaluation provenance per component, preserve historical reports, and
  evaluate the actual serving population separately from filter coverage. Strict
  mode must detect missing validation, missing index records and agreed serving
  regressions. Do not reset a baseline to hide failure.
- Keep the self-contained offline HTML field kit; add stable kit/sample versions,
  separate quality from closure/access/booking judgements, preserve free text,
  and remove model-derived hints that prime human answers. Add validated import
  of multi-metro, multi-reviewer returns with duplicate handling and provenance.
- Parameterize metro input and document one ordered ingestion workflow:
  load → filter → score → dedup. Include required postcode/schema enrichment,
  protect existing metros and user history, and prove the workflow against an
  isolated database before applying it to the working index. A new metro should
  require configuration, not editing Python.
- Preserve Firebase and dev auth; verify onboarding, age gate, tag persistence,
  GPS and typed launch points. Fix only observed failures. Complete accept →
  directions → arrival → rating/review → completion → saved history, including
  the listed event types and exact served-score snapshots. Mark emulator test
  activity so it is not silently treated as human preference ground truth.
- Enforce suppression in candidate retrieval, owned-data-only persistence,
  high-intent provider access and quotas, and verifiable outbound-call counts.
  Remove Google content caches. Typed city lookup must not become a paid deck
  sourcing path. Do not store third-party display payloads through client writes.
- Extract cohesive logic/components from Home before extending it. Its current
  1,147 lines leave only 53 lines of headroom. Add the score breakdown and honest
  wording within the existing card/detail flow; wire missing feedback controls
  within existing trip/profile surfaces. Preserve navigation, palette and layout.

**Screens shown:** onboarding and launch; the same Palm Coast deck with its real
breakdown; accept/directions/arrival/review/completed history. Show an offline
field-kit export/import round trip and a new-metro deck from the documented
pipeline. The latter is an ingestion demonstration, not evidence of good ranking.

**Independent-label dependency:** use the improved kit to obtain a prospective
held-out metro from a human who knows it. Both supplied metros have already
influenced engineering choices. Freeze new candidate models before seeing the
new metro's outcomes. If fresh labels have not arrived, continue independent
feature work, but do not claim generalized ranking improvement or final success.

### 2. Improve discovery and deliver fresh local events

**Feature coverage:** improve 4, 6, 7; deliver 19–20; prepare hours/access facts
needed for 17–18. This is a bounded attack on the unsolved problems, not another
open-ended scoring phase.

- Establish a transparent baseline using explicit interests, owned interactions,
  distance, repeat avoidance and local-first policy. Keep authenticity evidence,
  personal fit and availability separate. Popularity is not an authenticity
  penalty; regional businesses are not automatically excluded. Do not add new
  preference settings beyond the closed list.
- Compare three bounded signal families: names/categories as semantic text;
  FSQ OS cross-reference where access and permitted fields are verified; and
  venue-owned website evidence of destination type, public access, hours and
  current operation. Reuse the existing crawler and try rendering JS shells.
  Predeclare samples and comparisons. No paid runtime calls for candidate decks.
- Each experiment gets a roughly two-hour review checkpoint showing yield,
  examples, failures, cost, sample size and which metros informed it. Keep an
  experiment only if its measured benefit justifies its complexity. Do not tune
  against a held-out result and still call it held out. AUC alone is insufficient:
  inspect top cards, lost gems, traps, closures and repeat behavior.
- A dead website is not proof of closure; a live homepage is not proof of being
  open. Measure closure candidates against human-known open and closed venues.
  Use permitted first-party evidence and user reports; retain quota-limited
  high-intent confirmation where needed. Never verify paid providers on first
  deck exposure, despite that suggestion in the older brief.
- Start events with UCF's documented machine-readable calendar feeds, then a
  library/municipal source for breadth and a bounded sample of indexed venue
  calendars. UCF explicitly documents JSON/RSS/XML/ICS feeds for reuse in custom
  applications ([UCF feed documentation](https://events.ucf.edu/help/)). Orange
  County Library publishes a [live calendar](https://ocls.org/calendar/).
  These are verified leads, not yet
  measured coverage or permission for unrestricted retention of descriptions.
- Before event persistence, check source terms and retain only permitted facts
  with source URL, timezone, occurrence identity, verification time and expiry.
  Measure public, relevant, navigable events against a fixed source/date sample;
  report both source-relative coverage and the unmeasured metro-wide long tail.
  Exclude student-only events unless access is actually satisfied. Treat every
  recurrence as a dated occurrence, not an immortal place.
- Proposed freshness contract: refresh at least every six hours; exclude events
  once their source verification is over 24 hours old or their end time passes,
  whichever comes first. Check this at query time even if the scheduler fails.
  Handle cancellations and recheck selected events before departure. This is a
  bounded freshness guarantee, not a promise that organizers never change plans.
- Build the approved dated section in Discover and demonstrate at least one seed
  metro with a working local source. Assess both seed metros and report the
  coverage gap honestly; do not substitute arena events for community discovery.

**Event sourcing and storage, clarified after owner review:** the intended model
is scheduled collection into our own regional event index. Opening the app queries
that index; it does not trigger a social-platform crawl for each user.

| Source family | Acquisition plan within phase 2 | Current evidence / limit |
|---|---|---|
| University, library, parks and municipal calendars | Prefer JSON/RSS/ICS feeds; parse public calendar pages where permitted | UCF documents reusable feeds; other sources require individual verification and coverage measurement |
| Venue and organizer websites | Seed from indexed venue URLs; follow event/calendar links; extract Event JSON-LD or visible dated listings; render JS pages when necessary | Existing crawler is reusable, but event extraction/yield is unverified |
| Substack and local newsletters | Evaluate city/neighborhood event roundups through documented public RSS feeds or an authorized publisher/platform integration; follow linked organizer pages to verify dates, location and cancellation status | Added at the owner's suggestion on 2026-09-05, based on a friend's NYC experience. Substack documents RSS, but its terms prohibit scraping; feed availability alone does not establish permission for commercial extraction or storage. Verify the permitted route before collection; do not ingest paid/private posts |
| Public Partiful event pages | Evaluate public event URLs linked by venues/organizers and public discovery; prefer an approved feed/integration if available | Partiful documents discovery in Explore, but that alone establishes neither a bulk API nor storage rights; private/invite-only listings are excluded |
| Instagram and Facebook | Evaluate venue/organizer accounts already linked from the index, permitted APIs or authorized collection, and links to their public event pages | Explicit acquisition experiments, not assumed unrestricted scraping; measure whether these recover events absent from websites |
| TikTok | Evaluate local organizer/venue posts as event-discovery leads, then verify the event at its linked source; direct ingestion only through an applicable permitted access route | Its documented Display API requires account authorization; it does not establish general regional event search |

Primary references for the platform-specific limits above:
[Partiful discovery](https://help.partiful.com/en-us/articles/15525517-how-do-i-find-events-to-go-to),
[Meta's explanation of authorized and unauthorized scraping](https://www.facebook.com/help/463983701520800),
and [TikTok Display API authorization](https://developers.tiktok.com/docs/en/display-api-get-started).
For Substack, see its [RSS documentation](https://support.substack.com/hc/en-us/articles/360038239391-Is-there-an-RSS-feed-for-my-publication),
[Terms of Use](https://substack.com/tos), and
[Developer API terms](https://substack.com/api-tos). No working Substack integration
or measured event yield is claimed yet. NYC is a source-discovery lead, not an
expansion of the Orlando/Palm Coast implementation scope.
These are leads to evaluate, not a conclusion that social-only events cannot be
collected. Do not introduce an organizer account-linking product or event-hosting
feature without separate approval; this work is the sourcing behind feature 19.

**Owner-supplied newsletter examples (2026-09-05):** an NYC-based local reader
recommended the following, with cafes, coffee, desserts and parks as taste context:
[nycforfree](https://substack.com/@nycforfree),
[thekatieromero / Bite The Apple](https://substack.com/@thekatieromero),
[coolstuffnyc](https://substack.com/@coolstuffnyc),
[clubraisin](https://substack.com/@clubraisin), and
[fieldnotesnyc](https://substack.com/@fieldnotesnyc).
These are concrete Phase 2 discovery leads, not acquired datasets or evidence of
event coverage. Four profile descriptions were readable when checked; nycforfree
could not be retrieved in that check. Assess dated events separately from evergreen
place recommendations, verify linked organizer facts, and check permitted access
before collection. The owner explicitly confirmed that these examples leave Phase 1
and the phase ordering unchanged. NYC is not added as an implementation metro.

The collection sequence is: **regional source roster → scheduled fetch → extract
dated event facts → verify access/location/time → deduplicate → match venue →
store permitted fields → serve by requested region, date and interests**.

- The source roster records its metro, venue/organizer, access method, allowed
  fields/retention, refresh interval and last successful verification. Discover
  new event pages on that schedule as well as refreshing already-known events.
- Proposed event records hold title, start/end/timezone, category, public-access
  and booking requirements, official event/ticket URL, source identifiers,
  verification/expiry timestamps, and venue entity ID where confidently matched.
  Each occurrence has its own identity, even for a weekly event. Retain multiple
  source links when the same event appears on Instagram, Partiful and a website.
- Match venues using name/address and proximity, not name alone. Store permitted
  event-location coordinates and H3 cells so park meetups or events without a
  matching indexed business still belong to the right region. Ambiguous or hidden
  locations are not presented as navigable destinations. The user's selected
  region can differ from their current GPS location.
- Refresh eligible sources at least every six hours where source access permits;
  otherwise the source cannot promise that service level. Recheck near-term
  selected events before departure. A failed request does not renew freshness.
  Suppress cancelled, expired or over-24-hour-unverified occurrences at query time.
  Keep historical facts only where retention permits, outside active results.
- Report yield, duplicate rate, location/time accuracy, freshness and incremental
  coverage by source family. Specifically measure the social-only gap; do not
  report a successful UCF feed as proof of covering local run clubs and open mics.
  Include newsletter-only discoveries in that comparison. A freshly fetched old
  newsletter does not verify that its listed event is still happening; retain the
  publication date and recheck the underlying event source when available.

**Screens shown:** comparable Palm Coast and Orlando decks with explanations;
an event list with real times, venue, public-access/booking information and source;
the same list after an expiry/cancellation/outage test removes ineligible entries.

**Exit:** a usable personal deck, measured disposition of all three experiments,
fresh events, and an explicit hours-coverage report for the planning phase. Weak
evidence remains labelled weak; this phase does not demand an invented AUC win.

### 3. Make Adventours social and group recommendations fair

**Feature coverage:** 9–12. Do this after trustworthy single-user data and before
planning, so both spontaneous and planned groups use the same preference logic.

- Verify friend search/request/accept/decline with separate dev identities.
  Repair completed-trip serialization and “take Adventour,” preserve source
  attribution, and re-resolve current eligibility without overwriting the source.
- Add the Beacon board inside the existing Friends & Trips screen: an Adventour
  feed with view/share/take behavior. Start with the established friend audience;
  do not invent a global social network, messaging, follows, or new tabs.
- Select friends for a shared deck. Enforce applicable existing age/access/time
  constraints, score each member's soft preferences, penalize disagreement, and
  rotate whose interests are represented over accepted stops. Show member-level
  explanations and honest empty results when no feasible common option exists.
- Converge spontaneous, copied and planned Adventours on one session/stop model.
  Migrate any live Trip/TripMember/TripPlace dependencies and their data first;
  then remove the competing trip endpoints and rating-average “collaborative”
  recommender. Preserve friendships, reviews and history.

**Screens shown:** two-user friendship flow; a completed Adventour appearing on
Beacon and being taken by a friend; the same location's solo and group decks with
per-member fit, disagreement and fairness across multiple stops.

### 4. Generate a full trip with feasible times and booking links

**Feature coverage:** 17–18; reuse events and groups from phases 2–3.

- Add full-trip mode within the existing Discover/trip flow: dates, available
  time and companions → generated days → swap a stop → recomputed feasible days
  → navigate and complete using the same lifecycle as spontaneous mode.
- Select a subset and order it under visit durations, travel estimates, opening
  windows, event times and daily budgets. Use a bounded candidate pool and exact
  dynamic programming where practical. Benchmark the actual pool: “6–10 selected
  stops” does not mean there were only 6–10 candidate places. Report optimality
  only within the evaluated pool and stated travel/time assumptions.
- Promote successfully sourced hours from phase 2, with provenance/freshness and
  timezone handling. Category priors cannot certify a booked itinerary. When
  verified windows are insufficient, state that and offer unscheduled alternatives
  to check rather than fabricate a feasible day. Demonstrate actual generated
  days from usable sourced windows; a placeholder does not complete feature 17.
- Add official ticket/reservation links and `needs_booking` presentation; preserve
  the distinction between a theme park and a shop behind its admission gate.
  Link out only. No purchases, booking engine, flight search or car-rental system.

**Screens shown:** a real one-day and multi-day plan; a swap that respects a
closing time; a group plan including a dated event; a booking link opening the
correct destination; completion appearing in history and Beacon.

### 5. Finish profile, gamification and the complete-product acceptance run

**Feature coverage:** finish 13–16 and validate every item 1–23 against §6.

- Show actual travelled areas on a map in the existing Profile surface. Use
  arrival/completion history and owned geography, not accepted-only counts or
  parsing “3022 m away” as an address. A map is sufficient; no 3D globe is required.
  Propose any necessary UI dependency before installing it.
- Add a finite achievement set for the three requested behaviors: visits to
  supported local gems, regional coverage, and friends taking and highly rating
  one's Adventours. Derive awards from owned records with explicit rules and
  duplicate protection. No points economy, streaks, leaderboards or extra game.
- Finish integration, remove superseded implementation paths and unused flags,
  and update docs/README.md plus the runbooks to the state actually demonstrated.
  Do not mass-refactor working code as “polish.”
- Walk all 23 features on the emulator; keep a feature-to-screenshot checklist
  with corresponding API/persistence evidence where needed. Run strict evaluation
  with honest held-out provenance, demonstrate zero paid deck calls in logs,
  and verify the source-file ceiling. The owner follows the new-metro and
  send/return/import field-kit instructions unaided; assistance needed means the
  runbook is not finished. Event coverage and expiry evidence must remain valid.

**Screens shown:** the history map; all three achievement types earned from
traceable test activity; the complete connected workflow and final 23-item record.

**Stop:** when every HANDOFF §6 checkbox is satisfied. No sixth phase, model
roadmap, international expansion, or extra feature follows it. Unresolved required
work stays visibly incomplete inside these five phases.

## Keep, replace and remove

| Keep and build on | Replace or remove, with timing |
|---|---|
| Postgres/H3, Overture data, taxonomy adapters, dedup and stable entity identity | Harden destructive ingestion and geography consistency in phase 1; no PostGIS migration |
| All original human labels and written answers; historical experiment reports | Correct sampling/fitting declarations and misleading in-sample reporting in phase 1 |
| Chain classifier and measured junk-filter baseline | Improve only with evidence in phase 2; no blanket rarity, low-popularity or tourist-density penalties |
| Existing crawler and offline field kit | Add bounded rendering/extraction in phase 2 and owner import workflow in phase 1 |
| Existing auth, navigation, visual language and working trip interactions | Narrow feature UI additions; extract Home logic without redesign in phase 1 |
| place_event, owned reviews/history, friendships and session/stop identity | Repair served-score snapshots and suppression in phase 1; converge duplicate trip models in phase 3 |
| Existing authenticity score as a reproducible comparison | Remove its “match probability” presentation in phase 1; retain or replace production scoring based on phase 2 evidence, with one serving path |
| Permitted high-intent detail adapter | Remove Google-content caches, unused paid candidate fetch functions after call-site audit, and dead local-index flag helpers in phase 1 |

No deletion of labels or user history. No code from the abandoned `codex` branch.
Mechanical removals are separate reviewable commits, not mixed with behavior changes.

## Review contract and approval boundaries

- Roughly every two hours, provide a runnable checkpoint or a concise blocked
  result: feature IDs, changed behavior, screenshot when UI is involved, key
  evidence, file/diff size, and the single next slice. Do not spend an afternoon
  silently growing screens. If a slice overruns, reduce its scope and show the
  current evidence before continuing.
- Each slice is one coherent commit-sized change. Tests cover observed contracts
  and failure modes; large speculative suites do not substitute for the emulator.
- Keep existing navigation stable. This plan proposes feature-specific UI work
  only: card explanations/feedback, dated events in Discover, Beacon/groups in
  Friends & Trips, full-trip controls in the trip flow, and map/awards in Profile.
  New top-level navigation or UI dependencies require a concrete separate proposal.
- Source ceiling: current authored screen counts are Home 1,147; Profile 1,019;
  Social 715; RecommendationDeck 602; JourneyPanel 516; FirebaseAuth 432.
  **Clarification approved by the owner on 2026-09-05:** the 1,200-line limit
  applies to every authored application source file, including agent-written
  code. Generated dependency lockfiles and third-party dependencies are exempt;
  the existing package-lock.json has 13,397 lines. This clarification is recorded
  in AGENTS.md. Do not minify or relocate authored code to evade the ceiling.
- The event-surface choice above is a proposal because the field-kit answer is
  blank. No answer is inferred from silence. It can be resolved as part of this
  plan's approval before event UI work starts.
- Phase 1 approved 2026-09-05. See active-scope.md for the current checkpoint.
  Phase 2 approved 2026-09-06 with joint review afterward; the normal review/merge
  gate resumes for Phase 3.
