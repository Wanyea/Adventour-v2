# Local events — initial Phase 2 implementation

The approved surface is a dated section below the swipe deck in Discover. Events
are queried around the selected launch point (50 km, next 14 days), independently
of the phone GPS. The regular place deck and navigation tabs remain unchanged.

Launch lookup is worldwide and independent of indexed place/event coverage.
The owner rejected the interim acquired-metro-only restriction. Photon now
resolves typed cities and addresses; selecting a suggestion uses its returned
coordinates directly. Editing/selecting a launch clears previous results and
ignores late responses. Events load for that selected point even before launching
the place deck. No nearby indexed events means an empty regional list, never a
fallback to Orlando. Current NYC coverage is empty; NYC remains a valid launch.

Location search uses the free [Photon API](https://github.com/komoot/photon),
which permits reasonable public-service use without an availability guarantee.
The app debounces input; each backend process spaces upstream calls one second
apart and keeps at most 128 query results for 60 seconds in memory. Searches have
no Florida/country/radius restriction. No search payload enriches our place/event
index. The app links [OpenStreetMap attribution](https://www.openstreetmap.org/copyright).
Set `PHOTON_BASE_URL` to the base URL of a compatible hosted/self-hosted service
for deployment; the modest-use public endpoint is a local-development dependency,
not demonstrated production capacity. Search failures are shown separately from
no matches, and GPS remains available.

## NYC Parks connected (September 6, supersedes preview-only status below)

NYC Parks is now a second configured source. The owner continued Phase 2 after
reviewing the NYC preview and the remaining source/storage work. NYC Open Data's
[technical standards and law, section 23-502(d)](https://cityofnewyork.github.io/opendatatsm/LocalLaw11of2012.html)
provide the factual-dataset reuse basis. This is a specific addition for dataset
[w3wp-dpdi](https://data.cityofnewyork.us/d/w3wp-dpdi), not a blanket change to the
Google or social-platform data boundary. The roster records source, version,
modifications, fields and retention. No Google API or Maps-link parsing is used.
Named meeting points and coordinates come from the city's published dataset;
require a single park ID, a location name and valid NYC-bounded coordinates.
No NYC place-index acquisition or changes to the 19,385 owned places occurred.

The Sept6-19 snapshot has 302 eligible dated occurrences out of 1,198 source rows.
Disjoint exclusions: 685 restricted/age-focused programs, 109 ambiguous/nonpark
locations, 53 cancellations/closed registration, 18 ended, 17 outside the window,
12 unusable coordinates and two invalid durations. This source-specific yield
counts recurring sessions separately. It does not measure all NYC events or prove
that every admitted event suits the user. Fees, capacity and requirements remain
organizer checks. The earlier 1,080-row preview used fewer checks and was never
an ingestion-quality result.

Both scheduled refresh and explicit event recheck now dispatch to the correct
adapter. The existing worker refreshes UCF and NYC every six hours. NYC's public
publication is daily: `verified_at` is its `rowsUpdatedAt`, not download time.
At publication+24h or event end, whichever is earlier, rows disappear; repeated
fetches of the same version do not extend expiry. Missing/stale/future metadata,
HTTP failure, unexpected schema or a truncated feed cannot replace the snapshot
or renew freshness. This conservative rule can leave temporary coverage gaps
between publication expiry and a successful refresh. A successful full snapshot
removes disappeared/cancelled occurrences. The next cycle discovers newly
published occurrences in this configured source; it does not discover new sites.

The check button re-fetches the current official dataset for that occurrence.
It is a published-source check, not a live organizer-capacity promise; the event
note explicitly says the calendar updates daily and to check before leaving.
Official event links remain available. Event-page fetches were blocked in the
research environment, so no separate page-crawl verification is claimed.

Working API: NYC returns the first 50 dates from 302 stored occurrences, Orlando
returns seven UCF dates, and Palm Coast returns zero. NYC source check returns200.
Emulator proof: `nyc-events-screen.png` and `nyc-event-recheck.png` in
verification/2026-09-06; machine evidence is `nyc-events-live.json`.
All 38 backend tests pass. The real NYC snapshot was first written to the isolated
DB, queried in NYC/Orlando, removed through a successful empty snapshot and cleaned.
Tests cover cancellation, registration closure, location validity, stale/truncated
source failure and publication age. A pre-existing test used a UTC date for a
New York calendar window; that fixture now uses the calendar timezone.
No app source, screen structure, styles or dependencies changed in this slice.
The Maps handoff initially encountered a stuck permission-controller dialog.
Stopping that controller and granting location on this test emulator unblocked it.
The app then opened directions to the supplied Bryant Park coordinates in NYC
(`nyc-event-directions.png`). The origin remains the emulator GPS in Palm Coast;
this verifies the NYC destination handoff, not a surveyed entrance or route quality.

## Source and storage boundary

The initial working source is UCF's documented JSON feeds. Its
[developer documentation](https://events.ucf.edu/help/) permits feed consumption
in custom applications. The [gallery admission policy](https://cah.ucf.edu/events/ticketing/)
confirms public gallery admission and receptions. This subset is deliberately
narrow; a campus calendar listing alone does not establish public access.

The roster in `Server/data_pipeline/event_sources.json` records acquisition,
permission basis, fields, retention, source identity and verified venue criteria.
Only factual title/date/time/location/access/source fields enter `local_event`.
No description, image, contact details or Google location payload is stored.
Gallery coordinates come from the owned Overture record, matched by name,
geographic bounds and venue website host. The feed's Google Maps link is ignored.

The Sept6–19 sample contained 98 occurrences, 7 eligible gallery dates and 91
excluded because public access or location was not verified by this adapter.
This is **7/98 source-relative eligibility, not 7% city coverage**. See
`verification/2026-09-06/events-live.json`. The series has an opening reception
and six subsequent dated exhibition sessions. No student-only activity is enabled.

## Freshness and operation

From `Server/`, with the backend dependencies installed and Postgres running:

```powershell
$env:ENV_FILE='.env.local'
.venv\Scripts\python.exe -m data_pipeline.refresh_events --watch
```

The worker refreshes every six hours while running. Without `--watch`, it performs
one refresh and exits. Local dev requires restarting this worker after a reboot,
just like Flask/Metro; no Windows scheduled task or production deployment is
claimed. A failed fetch does not renew verification. `event_source` exposes last
attempt/success and error class; it never stores response bodies in error text.

Full source-window replacement is atomic. Missing/cancelled occurrences disappear
on a successful refresh. Ended rows are purged on successful refresh. Query-time
checks remove ended or verification-over-24-hour entries even if the worker stops.
The app also removes cached entries at expiry and refetches on foreground/focus
and every minute. The timestamp bound describes source verification, not a promise
that an organizer cannot change an event immediately afterward.

`GET /api/local-events` reads Postgres only. The explicit check/directions button
calls `POST /api/local-events/<source>/<occurrence>/verify`, which rechecks the
free official feed and admission policy. It shows current date/location/access
before opening organizer details or directions. Failure blocks that action;
an expired confirmation must be checked again. No paid API is called.

## Measured gaps

Palm Coast has useful [municipal listings](https://www.palmcoast.gov/events),
including the Sept19 waterway cleanup and Sept17 community expo. Its
[terms](https://www.palmcoast.gov/privacy-policy) have been read, but a reusable
acquisition/storage route has not been enabled. The
[Orange County library calendar](https://ocls.org/calendar/) is another lead;
no library feed coverage or permission claim is made yet.

The bounded 60-venue crawl found Event markup on two sites (six nodes), but did
not establish that these were current, public, navigable local events. Neither
those counts nor UCF's success measure the social/newsletter-only long tail.
Substack, Partiful, Instagram/Facebook and TikTok acquisition remain open within
Phase 2. The five NYC newsletter leads are preserved in the approved plan.

The pipeline and freshness tests are implemented. The actual emulator list and
organizer recheck are saved as `events-orlando.png` and `event-recheck.png` under
`verification/2026-09-06/`. Synthetic cancellation removal is also captured.
`expiry-visible-before.png` and `expiry-visible-after.png` show a timed synthetic
occurrence disappearing while the current control remains. `event-test-cancelled.png`
shows removal after a successful empty source snapshot. These used only the isolated
ingest-check database; the fixtures were cleaned and the normal backend restored.
The 24-hour stale bound and failed-refresh behavior also pass isolated backend
tests; the screen test accelerates an event end, not a full 24-hour wait.
This document does not declare Phase 2 complete.

## Additional source assessment (September 6)

The Palm Coast municipal sample has four listings starting Sept6–19: two clear
public community events, a memorial with a suspicious 25-hour end timestamp, and
Senior Games restricted to ages 50+. These are source leads, not four eligible
indexed events. Its terms do not by themselves supply an explicit feed/storage
agreement. OCLS's public calendar warns that registration/capacity can constrain
attendance; its linked privacy policy concerns patron data, not a redistribution
license. Neither source has been promoted to scheduled collection yet.

The social/newsletter acquisition assessment has **zero enabled sources and no
measured incremental verified-event yield**. That means unmeasured, not proof
these sources lack local events:

| Family | Concrete access result | Next permitted route |
|---|---|---|
| Substack | [Terms](https://substack.com/tos) prohibit scraping; documented RSS availability does not override that | Publisher-supplied event facts/feed with rights for Adventour, or platform authorization; verify linked organizers |
| Partiful | [Terms](https://partiful.com/terms) limit commercial use without written permission, and restrict competing event-planning platforms | Written platform authorization or independently supplied organizer facts; no private/invite-only collection |
| Instagram / Facebook | No authorized organizer account/API access supplied; the direct automated-collection terms URL redirects to login | Applicable approved Meta access and organizer authorization; no logged-in scraping |
| TikTok | [Display API](https://developers.tiktok.com/doc/display-api-get-started/) requires user authorization and approved scopes; it is not a general regional discovery feed | Authorized organizer integration or independently published organizer event facts |

A small public search for Substack/Partiful leads in the two seed metros did not
establish a usable source sample or coverage denominator. General tourism/arena
results were not substituted. Jackie's @nycforfree, @thekatieromero, @coolstuffnyc,
@clubraisin and @fieldnotesnyc remain named publisher leads; no paid/private post
was collected, no publisher was contacted, and NYC was not added as a metro.

## Owner-requested NYC live preview (September 6)

The six-hour worker refreshes configured sources only. It currently has one UCF
adapter; it does not discover sources for newly selected launch cities. The owner
requested running New York to see available results. A separate read-only preview
now runs with `python -m data_pipeline.preview_nyc_events` from Server's venv.
It makes no DB writes and does not change the worker roster or app results.

Source: [NYC Parks Public Events, Upcoming 14 Days](https://data.cityofnewyork.us/d/w3wp-dpdi),
with a working public JSON endpoint and source metadata declaring daily updates.
At 19:12 EDT on Sept6 it returned 1,198 occurrences. Filtering to not-ended events
before Sept20 and within 50 km of NYC's selected coordinates left 1,080 preliminary
candidates: 55 ended/outside-window, five invalid time orders, 12 unusable/missing
coordinates or times, and 46 explicit cancellations/closed registrations excluded.
342 candidates have registration links. Repeated sessions count separately.
This is source yield, not city coverage or 1,080 verified recommendations.

Examples in the feed: Sept7 yoga at Bella Abzug Park (registration link), Sept8
poetry at Bryant Park, and Sept8 yoga at Randall's Island (registration not required
according to the feed). Individual official event-page fetches returned 403 in
this environment, so separate organizer verification was not completed. Sample
links and diagnostics are in `verification/2026-09-06/nyc-events-preview.json`.
No descriptions, images, contacts, or event row payloads were saved in that report.

Historical preview gaps (subsequently resolved or bounded as described above): implement source dispatch (the worker and
organizer recheck currently assume UCF), record an approved factual-storage basis
under AGENTS' data boundary, establish venue/coordinate provenance independently
of Google, and demonstrate cancellation/expiry and access handling on the emulator.
The [Open Data terms](https://opendata.cityofnewyork.us/overview/#termsofuse) and
[NYC terms](https://www.nyc.gov/main/terms-of-use) were read; this preview does not
claim a new blanket provider-storage approval. A six-hour fetch of this daily
publication cannot promise six-hour knowledge of organizer changes. These are
Phase 2 event-source tasks; no NYC ingestion ETA or running schedule is claimed.
