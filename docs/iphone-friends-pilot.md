# Friends pilot — requirements and preflight, September 7

The owner requested an iPhone pilot with recommendation feedback, GPS wherever
testers are, and no seeded-city restriction. The owner offered their Windows PC
as the server. These requirements supersede earlier seed-only pilot assumptions.
This is pilot preparation within Phase 2, not a sixth phase or authorization to
open Phase 3 social features. No build has been distributed or server published.

## Proposed delivery

The iPhone sends its selected launch coordinates and preferences over HTTPS to
Flask on the owner's PC. Postgres, acquisition workers, ranking and feedback
storage stay on the PC. The phone receives small result batches; the place index
is not bundled into the app. This matches the existing client/server structure.

Provide a stable HTTPS route to the backend, using a tunnel or equivalent remote
access arrangement. Keep Postgres local. The PC and workers must remain online
during testing. Reuse Firebase identities so observations belong to each tester;
the public endpoint must not use the local emulator's dev-auth bypass. The remote
endpoint and its operational behavior have not been configured or tested yet.

For unacquired areas, the server needs bounded regional acquisition from the
permitted owned-data sources, then the existing filter/score/dedup pipeline and
regional serving. Reuse acquired areas across testers. No city allowlist and no
paid candidate calls. First-use acquisition latency, duplicate/overlap handling,
failure recovery and refresh must be measured before promising instant results.
Event source coverage is separate from place coverage: loading Overture places
does not discover all local events. Honest local gaps must never substitute
Orlando events or unrelated distant places.

Existing tools `pull_overture.py`, `metro_config.py` and `load_postgres.py` support
configured acquisition and transactional ingestion. They are not yet an automatic
GPS-triggered acquisition queue. Current place coverage remains Orlando/Palm Coast;
NYC event coverage does not mean NYC place coverage. Worldwide launch lookup works,
but useful recommendations everywhere have not been demonstrated.

## iOS readiness

The repo has a bare React Native iOS project and Podfile, bundle identifier
`com.adventour.app`. No iOS build was run on this Windows machine.

- Location usage description in Info.plist is empty; provide a clear foreground
  purpose and verify allow/deny behavior on an actual iPhone.
- Firebase iOS service configuration was not found in the inspected tree;
  verify configuration and initialization with the real project on macOS.
- Signing team is not configured in the inspected Xcode project. Apple Developer
  membership and access to a Mac or macOS build service are still needed.
- The deployed backend URL example is not evidence of a working pilot endpoint.

[TestFlight](https://developer.apple.com/testflight/) supports installation and
screenshot/crash feedback from friends. Apple requires review of the first build
shared with external testers. An Apple account, signing/build access and reachable
backend are prerequisites; no accounts were purchased or invitations sent.

## Study trace and feedback

The owner's follow-up requires consistent, useful data and low-effort feedback.
The [measurement contract](pilot-measurement-contract.md) now defines exact
questions/scales, automatic records, exposure/skip semantics, sampling limits,
replay/export gates and the finite first review. This is the instrumentation
specification for implementation; the small Discover feedback controls are
proposed for explicit UI approval, not already built.

Existing place decisions preserve rank, model, score components and user identity;
interaction events can reference the immutable decision. Existing trip-stop
reviews collect stars and notes. These are a useful starting point, not complete
feedback coverage for every card: rejected-card opinions and event recommendations
do not yet have an equivalent complete trace/review path.

Before inviting testers, produce one export joining recommendation, components,
interaction and review, with app/model/data version and tester context. Keep
subjective appeal separate from interest relevance, access and location accuracy.
TestFlight comments help diagnose UI problems but cannot alone reconstruct ranking.
Use existing review surfaces first; propose any additional feedback UI explicitly.

## Ordered checkpoints within Phase 2

1. Complete the current repeatable source pilot and record its misses/yield.
   [Completed offline report](verification/2026-09-07/calendar-pilot/README.md).
   Next implement the reviewed measurement contract and demonstrate one joined
   place/event feedback export before inviting testers or comparing algorithms.
2. Measure on-demand place acquisition for an unseeded location on this PC,
   including repeat requests and a failed acquisition, then show its deck/score.
   This extends the earlier seed-only ingestion boundary at the owner's request.
3. Connect remote HTTPS access and real tester auth; verify an off-network request
   plus a persisted recommendation/feedback export. Keep the PC as the server.
4. Build/sign on macOS, verify GPS and the same flow on iPhone, then prepare the
   concrete TestFlight build and review information for distribution.

No phase completion or global event-coverage claim follows from these checkpoints.
Source quality, hours/access and the existing Phase 1 acceptance gaps remain visible.
