# ADTR-23 Android verification — 2026-09-09

This packet records the Android emulator checkpoint for live foreground launch
location, saved-home fallback, manual precedence, and the no-location guard. It
does not claim a recommendation-quality result or complete the physical-iPhone
gate.

## Build and test context

- Backend focused tests: 27 passed.
- Frontend focused tests: 19 passed across two suites; TypeScript compilation
  passed.
- The latest JavaScript ran in the installed Android debug wrapper on the
  Pixel 7 API 30 emulator, using isolated backend port 8082 and database
  `adventour_ingest_check_20260905`. Runtime observations are synthetic test
  activity.
- A fresh Android build is currently blocked on Windows by the CMake 260
  character-path failure, after the Gradle cache workaround. This is a local
  build-environment failure, not a claimed passing fresh build.

## Observed runtime behavior

| Scenario | Observed evidence |
| --- | --- |
| Fresh foreground permission | Native permission prompt displayed. |
| GPS foreground location | St. Augustine coordinates `29.901198333,-81.313998333` resolved to a locality label; the local-events request returned 200. |
| Permission denial with saved home | Android package permission was confirmed false. Saved Palm Coast home resolved to `29.5541432,-81.2207673`; the local-events request returned 200. |
| Unavailable GPS with no home | Existing launch-point guidance appeared and no event query occurred. |
| Manual precedence and resume | A manually selected New York city remained the launch point across background/foreground; local-events requests used the manual destination. |
| Deck request and screen | St. Augustine response served 20 cards with zero provider calls in 96.8 ms. The viewed emulator screen showed 20 cards; its first card was St. Augustine Coffee House at 411 m with Fit `0.774`. The events section truthfully showed no verified events in the region. |
| NYC empty deck | NYC returned an empty POI deck from the limited isolated test index. This is not a recommendation-quality pass. |

Screenshots remain in `%TEMP%` because the default profile asset is personal and
is not suitable for publication in the repository.

The actual St. Augustine deck request is distinct from a separately bounded API
replay at the same coordinates. That replay's top ranking score was `0.774313`
(`interest=0.5`, `distance=0.174313`, `local_policy=0.1`, `feedback=0`,
`repeat=0`), with structural score `0.9936`. These values explain the rendered
Fit value; they are not evidence of recommendation quality.

After background/foreground, the manually selected New York destination was
again confirmed in the screen and event-query evidence. An explicit GPS retry
then returned to St. Augustine from that manual New York state.

## Pending gates

- Fresh Android build after resolving the Windows CMake path-length failure.
- Physical iPhone verification from the exact reviewed commit: first grant,
  denial/restriction, reduced/coarse precision, disabled services, cold relaunch,
  settings-return permission changes, saved-home fallback, manual override race,
  and no-home behavior.
- Independent review and owner review remain required. ADTR-23 and Phase 2 are
  not complete or accepted.
