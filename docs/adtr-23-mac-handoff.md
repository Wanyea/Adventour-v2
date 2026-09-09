# ADTR-23 Mac / physical-iPhone handoff

Use the exact reviewed commit SHA recorded in the ADTR-23 PR and its handoff comment. Do not treat this
Android-only checkpoint as a public-pilot deployment authorization.

## What Android established

- 27 focused backend tests passed.
- 19 frontend tests across two suites and TypeScript compilation passed.
- On Pixel 7 API 30, the installed Android debug wrapper used isolated backend
  port 8082 and `adventour_ingest_check_20260905` for synthetic runtime activity.
- The native foreground permission prompt displayed; a St. Augustine GPS fix
  (`29.901198333,-81.313998333`) resolved to a locality label and events returned
  200.
- With Android permission confirmed false, saved Palm Coast home resolved to
  `29.5541432,-81.2207673` and events returned 200.
- With no usable GPS and no home, Home showed launch guidance and made no event
  query.
- A manually selected New York city persisted through background/foreground and
  supplied the event destination; an explicit GPS retry then returned to St.
  Augustine.
- The viewed St. Augustine screen showed a 20-card deck with St. Augustine
  Coffee House first at 411 m and Fit `0.774`; events truthfully reported no
  verified region events. This is runtime behavior evidence, not a quality
  claim. A separate bounded API replay gave top ranking `0.774313`
  (`interest=0.5`, `distance=0.174313`, `local_policy=0.1`, `feedback=0`,
  `repeat=0`) and structural score `0.9936`.

The fresh Android build is not green: Windows CMake currently fails at its
260-character path limit after the Gradle cache workaround. Android runtime
evidence came from the installed debug wrapper.

## Required physical-iPhone checklist

1. Fetch `feature/adtr-23-live-location` and verify the exact SHA in the PR handoff comment. Coordinate with Windows to serve that same backend revision on a reachable test endpoint before testing; the public service still runs the previous ADTR-22 revision. Build and install that SHA on a physical iPhone.
2. Verify a fresh foreground permission grant and that only foreground access is
   requested.
3. Verify denial and restriction, including disabled location services.
4. Verify reduced/coarse precision is accepted as usable location.
5. Verify cold relaunch and settings-return permission changes.
6. Verify saved-home fallback after unusable GPS.
7. Verify manual selection wins against late location, home-resolution, and
   reverse-label callbacks, including a background/foreground transition.
8. Verify no GPS and no resolvable home shows launch guidance and does not query
   events.
9. Capture Home, events, deck, and score-detail request evidence. State any
   unreproducible restriction setup explicitly.

No public pilot deployment occurs until this handoff is completed and reviewed.
ADTR-23 and Phase 2 remain pending acceptance.
