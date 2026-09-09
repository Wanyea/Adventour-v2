# ADTR-23 implementation plan

Status: owner approved implementation on 2026-09-09: "also go ahead with ADTR-23".

Base: merged ADTR-22 on `codex-astra`, exact commit `5155249c4b943849180c04d6c4b9e34dfcf4afe8`.
Worktree: `D:/source/Adventour/Adventour-v2.worktrees/adtr-23`.
Branch: `feature/adtr-23-live-location`.

## Objective and boundaries

On authenticated Home startup, obtain a usable foreground device location and display its city/town when resolvable. If GPS is unusable, resolve the authenticated user's saved home city. Manual launch intent wins over pending automatic work. With no usable GPS, resolvable home or manual launch, keep coordinates absent, skip event queries and guide the user through the existing Home launch entry. Never substitute a seeded city.

Reuse existing Home layout, autocomplete, owned-index recommendation and event services. No new screen, navigation, UI dependency, background tracking, precise-location persistence, profile/schema extension, ranking change, event-source acquisition or production deployment. All authored app files remain at most 1,200 lines. Do not touch the running pilot backend.

## Slice 1: transient locality resolution

Extend `Server/adventour_backend/services/launch_service.py` and the existing `/geocode` route for a real city/town display label using the existing Photon source. Verify its official reverse-endpoint contract before implementation. Preserve original GPS coordinates for searching; reverse results supply locality display only. Apply bounded timeout/rate handling without adding a precise-coordinate cache, Google calls, or index/profile writes.

Resolve saved home only on a unique exact normalized locality match. Ambiguous, missing or unavailable resolution makes home unusable; never take the first fuzzy result. The merged shared autocomplete removes the trailing `(City)`, `(Town)` and other known type suffixes before saving, while the current resolver requires an exact full-description match. Normalize that known suffix consistently so selected saved homes resolve. Keep arbitrary free-text homes valid profile data even when they cannot be resolved.

Focused checks: suffix-normalized matching, multiple/no matches, malformed coordinates, provider timeout/failure, and reverse failure without losing valid GPS.

## Slice 2: foreground location controller

Extract cohesive acquisition/state logic into a small Home hook/service using the installed geolocation dependency. On authenticated Home startup, attempt a bounded foreground fix, then resolve saved home if GPS is unusable. Track GPS/home/manual/none origins explicitly.

Proposed defaults for approval: a 15-second fix timeout and a maximum accepted fix age of 10 seconds, matching the existing acquisition options; validate returned timestamps as well as finite coordinate ranges. Accept usable approximate/coarse foreground location rather than requiring precision. No saved coordinate cache.

Configure iOS explicitly for `whenInUse` and background updates disabled. Support Android coarse alongside fine permission. Permission denial/restriction, disabled services, timeout and stale fixes lead to home fallback or existing launch guidance without repeated automatic alerts.

Invalidate asynchronous work on account change, unmount, background transition, manual editing/selection and explicit GPS retry. Manual intent wins over late permission, position, home-resolution and reverse-label callbacks. Reacquire automatic location on a genuine background-to-active return; the permission dialog's inactive/active cycle must not launch duplicate work. Manual choice persists across foreground return in the current session; explicit GPS action opts back into automatic acquisition. Cold relaunch starts automatic acquisition again.

## Slice 3: Home integration and query guards

Keep `currentCoords` as the sole committed location feeding events and POI requests. Preserve the existing Find Places action: automatic location selection does not automatically launch the POI deck. No usable launch leaves `currentCoords` null, makes no event query, and uses the existing Pick a launch point entry and message area.

Invalidate old destination results when the committed destination becomes invalid or changes. Coordinate and label callbacks must share the same request generation. Reverse-label failure retains usable GPS and a truthful generic location label; it must never display the previous destination's label.

Audit `LocalEventsSection` resume handling: it currently refreshes independently on AppState active and can query old GPS before reacquisition. Gate or unmount automatic events while backgrounded or refreshing so stale destination queries cannot slip through. Preserve manual destination behavior.

Allowlist home as an honest `location_origin` in the existing backend request path instead of recording unknown or calling it manual. Preserve pilot privacy processing; do not add precise telemetry. Remove existing precise-coordinate console logging in touched Home paths.

## Slice 4: verification and review packet

Run focused backend/app tests and TypeScript. Cover permission and acquisition failures, stale/invalid fixes, normalized and ambiguous homes, manual-versus-late-callback races, account change, and absent-location/no-event queries. Avoid a broad speculative suite.

Android runtime evidence must include fresh permission grant; denial with resolvable home; denial with no usable home; unavailable/stale GPS; manual override; cold relaunch; settings-return permission changes; and matching coordinates for events and the launched POI deck. Show Home, deck and score details. Screenshots and request evidence prove behavior, not recommendation quality. A real-device checkpoint remains required; emulator evidence is intermediate.

Mac/physical-iPhone gate: build and install the exact reviewed commit, then verify initial permission grant, denial/restriction, reduced precision, disabled services, cold relaunch, settings return, and manual override races. If a restriction setup cannot be reproduced, state that gap explicitly. Confirm only foreground authorization is requested and no background location mode is enabled. The current library supports explicit when-in-use configuration; no new native dependency is justified. Both location usage strings exist in Info.plist; verify native behavior before changing keys solely on README assumptions. Windows cannot close the physical-iPhone gate.

Record changed files, source ceiling, test results, Android and iPhone evidence, commit SHA and remaining acceptance gaps. Obtain independent high-capability review before merge; no automatic merge or phase acceptance.

## Likely files

HomeScreen; a small Home location hook/service; homeUtils; LaunchLocationService; narrowly LocationAutocompleteInput pending-request cleanup if required; LocalEventsSection resume gating; Android manifest; backend launch_service and route/origin allowlist; focused tests; ticket and verification documentation. Auth/profile persistence and schema remain unchanged.

## Risks and decisions

- Merged ADTR-22 now supplies authenticated nullable home_city and shared autocomplete. Its suffix stripping must be accommodated; the prerequisite itself no longer blocks this ticket.
- Reverse geocoding currently returns literal Current Location/GPS. Real city labeling is backend work, not merely changing a label in Home.
- Provider availability and ambiguous free text mean home is not guaranteed. Failure must lead to manual guidance, never a seeded-city fallback.
- Native permission-dialog transitions and LocalEventsSection's separate resume listener can race with acquisition; test these boundaries explicitly.
- Approximate location is usable but does not establish precise distance accuracy. Do not add a precision requirement or persist the fix.
- The approved no-location rule is stronger than assuming every user has a home: no coordinates means no event request.
- Scope stops if implementation requires a new provider, new UI dependency/screen, source-ceiling breach, precise/provider persistence, broader telemetry changes or another ticket's behavior.

No unresolved product ambiguity prevents approval of this bounded plan. The freshness defaults and session-only manual precedence above are explicit proposed choices. Official Photon reverse API verification remains an implementation prerequisite; local code only demonstrates forward search today.
