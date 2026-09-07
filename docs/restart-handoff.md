# Restart handoff — 2026-09-06

## Current checkpoint after resuming (supersedes the pause record below)

Latest owner steering: pilot must collect exact, consistent useful data while
being friendly and encouraging optional responses. Read
[pilot-measurement-contract.md](pilot-measurement-contract.md) before implementing
pilot telemetry. It specifies question versions/ordinal scales, automatic request/
candidate/decision/exposure/source snapshots, explicit missingness and retry rules,
small optional feedback controls, pretest and seven-day review gates. The owner
then approved these controls ONLY in the pilot version. Build configuration and
server-recognized enrollment must gate extra study UI/collection; standard app
keeps normal core logging/reviews only. One engine, no alternative ranker. Design
only; no build separation, algorithm or UI changed yet. Do not ask again for this
narrow pilot UI approval. Verify pilot AND standard behavior before distribution.
Current ranker treats every reject as negative taste; current events lack decision
trace; deck polls visibility at 700ms rather than measuring continuous exposure.
These are named implementation gaps, not completed fixes. Preserve old labels.

September 7 later checkpoint: actual bounded calendar collector implemented in
`Server/data_pipeline/calendar_pilot.py`. Six fixed sources, two preserved runs;
run 2 parsed 24 pages, retained 11 candidates, eight passed date/region prechecks,
zero production-ready. Manual review found a sold-out Sequoia candidate that
JSON-LD did not flag. Four focused tests pass. Full evidence, commands and next
bounded correction: [calendar pilot](verification/2026-09-07/calendar-pilot/README.md).
No production DB/app/source-roster changes in this slice. Preserve the owner's
uncommitted edit to the older event-source-experiment/review.md.

Friends pilot: all testers use iPhones, must use GPS anywhere with no seeded-city
restriction; owner's PC may host the backend/data, no app-bundled index needed.
[Preflight and ordered checkpoints](iphone-friends-pilot.md) records this steering.
Worldwide lookup already works, automatic regional acquisition does not. iOS
Firebase/signing/location configuration, Mac build access and a reachable HTTPS
backend remain unverified. No TestFlight build, remote exposure or invites made.
The source pilot is no longer merely proposed. Next slice is recorded in its
report; do not repeat the original hand-run search and call it the collector.

September 7: owner event review received, E4=0/E1=2/E3=2/E2=1. Verbatim labels
and interpretations are in [owner-review](verification/2026-09-06/event-source-experiment/owner-review.md).
E1 appeals but is explicitly not cafe-relevant; E3's novelty appeals with a
market-style preference; E2's class/signup format is less appealing for ongoing
community. Its dated URL now returns404; general Regalia activity page does not
reconfirm September26. Preserve original scores/results; no model/profile/DB
writes or master-plan amendment approval inferred. Existing uncommitted edit to
the review.md template was left alone.

Owner then approved the next event experiment and proposed a preference-summary
idea for critique (not an instruction to replace serving). The frozen Sep26-27
NYC comparison is in [event-source-experiment](verification/2026-09-06/event-source-experiment/README.md):
12 selected URLs, two coffee-centered general-search leads (one 21+ conditional),
zero additional verified events from source-restricted searches. Human review
pending in its review.md. No app/source roster/DB changes or model inference.
[Preference assessment](preference-profile-assessment.md) records current code,
evidence-backed summary proposal and an unrun fair three-arm comparison. Do not
claim an LLM biography or ranking improvement exists. Phase 2 remains active.

Latest offline follow-up: NYC + September 20 + cafe interest comparison completed.
The owner's Partiful home-cafe event was MISSED by the fixed search and supplied
after retrieval. Its counterfactual 100/100 rubric score is not an organic find
or production personalization. Protocol, selected URLs, evidence labels, replay
and proposed Phase 2 discovery gaps are in
[the comparison report](verification/2026-09-06/cafe-event-comparison/README.md).
No source roster, application or DB changes. Next experiments must preserve this
provenance; the known supplied event cannot be called held-out discovery success.

Latest active slice: NYC Parks is now connected and populated (302 eligible
occurrences / 1,198 source rows). Seven UCF events remain. The six-hour local
worker refreshes both adapters; NYC expiry is bounded by daily publication age,
not just fetch age. 38 tests pass; isolated real-snapshot removal passed. Actual
emulator NYC list/source-check screens and API report are saved. Maps directions
also reached the supplied NYC point after clearing the stuck permission
controller; see nyc-event-directions.png. Earlier Maps-blocked notes are historical. See the latest
sections in local-events.md and phase2-results.md; preview-only statements below
are historical. No app layout/source changes in this slice.
Current backend session88728 and worker session89057 replace the sessions/PIDs
below; Metro9447 remains. Both need restart after reboot. Source roster has
ucf_main and nyc_parks. Next coverage gap is Palm Coast, then source-quality and
hours/access follow-through. Phase 2 is still active, not accepted complete.

Latest label follow-up: New York city/state now have distinct typed labels;
new-york-city-state-labels.png shows both on the emulator. Ten focused launch
tests pass. Owner-requested NYC preview completed: 1,198 NYC Parks rows, 1,080 preliminary
candidates after date/radius/basic validity/cancellation filters; no NYC DB
population or schedule change. See local-events.md and nyc-events-preview.json.
The six-hour worker refreshes UCF only, not automatic new-city discovery.

Latest owner-review correction: the acquired-metro-only launch restriction was
rejected and replaced with worldwide Photon/OSM lookup. New York now selects real
NYC coordinates and remains valid even with no indexed events/places. Orlando
shows seven UCF dates; switching to New York clears them and shows the regional
empty state. Both API and emulator verified; London also verified through the
live API. 21 backend tests and TypeScript pass. See phase2-results.md and the
new-york-worldwide-*.png / worldwide-orlando-events.png evidence. Earlier
new-york-launch-fixed.png and launch-region-fix.json are superseded evidence of
the rejected restriction, not the desired behavior. Backend session95609 is the
current normal .env.local service; Metro9447 remains running. Sessions are
transient and must be restarted after reboot.

Phase 2 was resumed after reading HANDOFF and AGENTS. Current review entry point:
[phase2-results.md](phase2-results.md). Event implementation/runbook/source limits:
[local-events.md](local-events.md). Phase 2 remains active; Phase 3 is not authorized.

- The UCF adapter now handles the single-event dictionary feed, its route is
  registered, and Windows timezone data (`tzdata`) is installed/pinned. Seven
  public gallery occurrences are in the working index. The owned gallery match
  avoids the feed's Google Maps payload. No Google content was retained.
- Discover has a 142-line LocalEventsSection below the deck: selected-region
  lookup, dated cards, source/access details, free organizer recheck, foreground/
  minute refresh and client expiry. Existing navigation and palette are retained.
- Screens: events-orlando.png, event-recheck.png, expiry-visible-before.png,
  expiry-visible-after.png, event-test-cancelled.png in verification/2026-09-06/.
  The expiry/cancellation screens use labelled synthetic rows in the isolated DB.
  Fixtures were cleaned; normal backend was restored. Maps opened but System UI
  hung at its permission prompt; directions destination is still unverified.
- Case variants of Orlando no longer produce ambiguous city launch results.
  Both personal deck/score screens exist. The fixed two-metro/two-profile audit
  shows intended tag behavior, but also suspect destination/location records.
  It does not establish recommendation quality. Original labels are unchanged.
- Three experiments are reported: name/category hints (removed generic Cafe
  name hint), FSQ OS (access-limited, no dataset), 60 venue sites plus ten closure
  controls and six Chrome renders. Only diagnostic counts/URLs were saved.
  No hours/closure facts were promoted. See measured outcomes in phase2-results.
- 21 backend tests and TypeScript pass; largest authored app file is 1,021 lines.
  Strict evaluation remains red for no fresh held-out data and no accepted v2
  baseline; its report explicitly does not validate personal fit.
- The six-hour event worker is running locally. It is not installed as a Windows
  startup task. Restart with `python -m data_pipeline.refresh_events --watch`
  from Server using its venv and ENV_FILE=.env.local. Logs are ignored at repo root.
- Current backend exec session95609 (normal .env.local, port8080), Metro9447,
  event worker parentPID44780. These are ephemeral, not restart configuration.
  Synthetic backend sessions are stopped. Emulator backend is 10.0.2.2:8080;
  adb reverse cannot redirect that native URL to another server port.
- Use tests/event_screen_fixture.py only with its isolated DB guard. Its `expire`
  action creates a 90-second occurrence for a screen capture after automatic
  refresh; `cancel` applies a successful empty snapshot; `clean` removes fixtures.

Next Phase 2 slice: investigate the suspect ranked Orlando destination/location
records; establish a permitted municipal/library or organizer source for breadth,
and usable hours/access windows. FSQ access is pending owner credentials; the
earlier async question has no answer. Social/newsletter collection needs the
applicable publisher/platform authorization; no outreach is authorized or sent.
All Phase 1 acceptance gaps below remain open. Do not call the joint review,
Phase 2, or HANDOFF §6 complete merely because implementation tests pass.

## Historical pause record (pre-resume; not current status)

The owner requested an immediate pause to restart the PC. Resume Phase 2 from
this checkpoint; do not restart the takeover or request Phase 2 approval again.
Read HANDOFF.md completely, then AGENTS.md and this file before implementation.

## Authorization and limits

- Repo `D:\source\Adventour\Adventour-v2`, branch `codex-astra`, cut from claude.
- Phase 1 approved Sept 5. Phase 2 approved Sept 6: "Lets move onto phase 2. ill
  do a review of both phases after." This explicitly overrides the Phase 1 review/
  merge prerequisite for this transition. No merge or push has been done.
- Five phases/23 features only, ending at HANDOFF §6; no additional features.
  Phase 3 social/Beacon/groups, Phase 4 full-trip/booking, Phase 5 map/achievements
  remain closed. Phase 2 includes discovery, three experiments, hours/access and
  local events. Follow docs/takeover-plan.md and docs/phase2-discovery.md.
- UI additions only fit explanations and dated events inside Discover. No new
  top-level screen, palette/layout redesign or UI dependency. <=1,200 lines per
  authored app source; generated lockfiles and third-party dependencies exempt.
- Reviewable checkpoints roughly every two hours. Never treat tests or in-sample
  labels as proof of recommendation quality. No subagents unless explicitly asked.
- Never store Google Places content; paid APIs never populate decks. Source
  permissions must be checked before event facts are persisted.

## Implemented in the current Phase 2 slice

- `personal_ranking_service.py`: saved-interest match, smoothed own category
  feedback, distance, independent/regional preference, and impression penalty.
  Latest decisive event per entity, not nine votes for nine lifecycle events.
  Recent rejects hidden 30 days; accepted/arrived/rated hidden 7 days; impression
  penalty 24 hours. Owned feedback is user-private. Dev activity affects only its
  own dev user, not other users or evaluation labels.
- `local_index_service.py` ranks the full eligible pool before limiting. Existing
  structural eligibility floor remains; structural score is separate from fit.
  Model `personal_v1`, exact contribution fields and explanations in immutable
  decisions. `decision_service.attach` preserves supplied model version.
- App card/detail shows Fit and its contributions; structural breakdown remains
  explicitly non-personal/non-probabilistic. Profile history reads original
  ranking and structural fields from its serving snapshot.
- Four focused checks passed: two personal-ranking checks plus both existing
  core lifecycle/provider checks against isolated Postgres. `tsc --noEmit` passed.
  These were before the subsequent event scaffolding was written.
- Actual emulator screens: `verification/2026-09-06/personal-palm.png` (Rodie's
  Place, fit .6976) and `personal-breakdown.png` (interest .5, feedback 0,
  distance .0976, local policy .1, repeat 0). The screen is a synthetic test-user
  behavior demonstration, not a human quality judgement.
- `personal-palm.json` is a SEPARATE API call after the visible card generated an
  impression. Its ordering differs legitimately; do not claim it is the exact
  screenshot's serving decision. Query recommendation_decision for that if needed.
- Remaining ranking verification: comparable Orlando screen, declared 8km two-
  profile before/after report, current full suite/ceiling check and honest harness
  annotation that its authenticity diagnostic does not evaluate personalized fit.

## Event work is unfinished — exact pause point

New files (not yet exercised as a complete system):

- `Server/data_pipeline/event_sources.json`: UCF source roster, permitted fields,
  six-hour refresh/24-hour maximum age, gallery admission and owned location rule.
- `ucf_events.py`: collect fourteen daily documented feeds, transient description
  inspection, retain factual fields only, conservative gallery-only eligibility,
  owned name+bounding-box+website host location match, explicit-selection recheck.
- `local_event_service.py`: two-table schema, atomic source-window replacement,
  query-time expiry/staleness, geographic query and dedup with source provenance.
- `refresh_events.py`: one-shot refresh / optional six-hour watch loop.
- `routes/local_events.py`: draft list/recheck blueprint. **Known unfinished
  import: it refers to nonexistent `adventour_backend.extensions`; db actually
  lives in `adventour_backend.models`. Fix this before registering the blueprint.**
- `index_schema_service.py` now includes event DDL. No backend restart/test has
  run since that edit; event tables/real event persistence are not claimed done.
- Blueprint is NOT imported or registered by app.py. There is NO event UI yet.
  No refresh worker or scheduled task is installed/running. Do not claim events
  are operational or that automatic expiry has been demonstrated.
- Next: finish imports/wiring, inspect single-event feed shape, focused isolated
  tests for end/stale/cancel/failed refresh and source replacement. Run first
  permitted refresh, then small dated Discover component. Preserve existing deck
  navigation. Show real events and expiry on emulator. Check latest source facts
  again after reboot; dates and verification are time-sensitive.

## Measured sourcing evidence and pending experiments

- UCF help explicitly documents JSON/RSS/XML/ICS feeds for custom applications:
  https://events.ucf.edu/help/ . Daily path `/2026/9/7/feed.json` returned HTTP200
  and a list. Single event path is documented but not yet checked by this adapter.
- Fixed sample Sept 6–19: **98 occurrences, 98 unique IDs**. Categories include
  20 workshops, 16 tour/info sessions, 12 recreation, 8 socials, 8 lectures,
  7 health, **7 art exhibits**, 6 sports, 6 careers, and other smaller categories.
  This count was printed in research, not yet saved as a reproducible report.
- Public campus visibility does not establish public access. Gallery is an
  initial explicitly verified subset, not all 98 events or city-wide coverage.
- Current gallery series: Connective Tissue by Hanna Washburn; opening reception
  Sept10 5–7pm, exhibition Sept11/14/15/16/17/18 10am–5pm, America/New_York.
  Example https://events.ucf.edu/event/4151936/opening-reception-and-artist-talk-connective-tissue-by-hanna-washburn/
- https://cah.ucf.edu/events/ticketing/ explicitly confirms free public gallery
  admission/receptions. Adapter rechecks that policy; no description/image/contact
  retention. Feed's Google Maps location URL is deliberately not used for coords.
- Owned Overture gallery ID `09f69bf0-1c91-4414-99bc-ce44c0144682`, lat28.6027336121,
  lon-81.2037887573, website `http://gallery.cah.ucf.edu/`. A different school-of-
  visual-arts record was downtown; do not match it by loose name alone.
- Palm Coast https://www.palmcoast.gov/events and Orlando https://ocls.org/calendar/
  both show current community activities. No permitted storage route measured
  or implemented for them yet. Their guessed policy URLs were unusable; inspect
  actual site links rather than guessing more URLs. UCF gallery site web open
  was blocked; do not bypass tool URL security policy via another route.
- FSQ OS: official access now requires Places Portal account/token; old public
  S3 dataset deprecated. https://docs.foursquare.com/data-products/docs/access-fsq-os-places
  Hugging Face official dataset is also gated (contact sharing and organization
  marketing terms): https://huggingface.co/datasets/foursquare/fsq-os-places .
  No credentials/terms accepted, no extract acquired, no match-rate claim.
  An async question asks whether owner already has access; no answer yet. Continue
  independent work while awaiting. Do not substitute paid API or bypass access.
- Text and website experiments were PREDECLARED in phase2-discovery.md, not run.
  Reuse extraction_spike parsing but fix crawl failure semantics before new crawl;
  do not infer closure from failed HTTP. Try up to six permitted JS-shell renders.
- Jackie's NYC leads retained in plan: @nycforfree, @thekatieromero, @coolstuffnyc,
  @clubraisin, @fieldnotesnyc on Substack; cafes/coffee/desserts/parks taste context.
  NYC is not a new implementation metro. Public RSS alone does not grant commercial
  collection rights. Social/Partiful/newsletter sources still need bounded access
  and incremental-coverage assessment; not written off as impossible.

## Restart environment

1. Confirm PostgreSQL17 service, localhost5432, DB `adventour`; no PostGIS.
2. Backend from `Server`: `$env:ENV_FILE='.env.local'`, then
   `.venv\Scripts\python.exe app.py` (8080). Never print credentials from env files.
3. From `AdventourApp`, `npm run android:local:pixel7`; existing installed dev build
   uses `.env.android.local`. Metro8081; Android backend10.0.2.2:8080. SDK:
   `C:\Users\wanye\AppData\Local\Android\Sdk`, device emulator-5554, Pixel_7_API_30.
4. Emulator identity `phase1screen@adventour.local`, dev token syntax
   `Bearer dev:phase1screen@adventour.local`, user3. Onboarded coffee_sweets/outdoors,
   DOB1995-01-01. Owner user1 remains preserved. All emulator activity test-marked.
5. GPS Palm Coast: `adb emu geo fix -81.2079 29.5844`. App was in the fit-details
   modal; stored app/profile/index state survives a normal reboot.
6. Isolated test database `adventour_ingest_check_20260905`, `.env.ingest-check`,
   StAugustine sample. Run core/personal tests with ENV_FILE set to that file;
   never point default app at it. Full index test also needs ADVENTOUR_TEST_PG_DSN
   derived securely from its DATABASE_URL. Avoid printing passwords.
7. Before reboot backend exec session57095, verified Python parentPID30724/child29336;
   these IDs/sessions are invalid after reboot. No running ingestion or event
   refresh was in flight at pause. Metro/emulator were running. Normal reboot is
   sufficient; do not kill unrelated Python/Node processes.

Use `git -c safe.directory=D:/source/Adventour/Adventour-v2 ...` on this machine.
PowerShell login=false avoids noisy profiles. UTF-8 text through PowerShell→Python
stdin previously lost Unicode replacement matches: verify document edits actually
applied. Prefer apply_patch. For screenshots use adb shell screencap then adb pull
(binary safe), then view_image; displayed image coords scale from1080x2400.

## Phase 1 acceptance carried forward

See verification/2026-09-05/phase1-core.md and core-contract.md. Core/tooling are
implemented; 13 focused backend checks and TS passed before Phase 2. Historical
labels unchanged. Both metros are development, no fresh heldout: harness strict
correctly fails. Accepted v2 baseline also absent. Live Firebase/Google, offline
HTML rendered review, unaided owner kit/metro workflows remain unverified. Do not
claim joint review or HANDOFF §6 complete. Phase 1 latest commit19e154dc; Phase 2
protocol commitd4f9ef27. This restart checkpoint saves partial work, not acceptance.
