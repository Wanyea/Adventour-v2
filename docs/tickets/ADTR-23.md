# ADTR-23 — Foreground location with home fallback

- Jira: https://adventour.atlassian.net/browse/ADTR-23
- Parent: ADTR-19, Phase Follow-ups; originated in the Phase 2 iPhone walkthrough.
- Sprint: ADTR Sprint 2 (5).
- Owner approved implementation on September 9, 2026.
- Base: `codex-astra`, `5155249c`; branch: `feature/adtr-23-live-location`.
- Detailed approved plan: [implementation plan](../adtr-23-implementation-plan.md).

## Summary and objective

Make Home discover events around a usable foreground device location, falling back
to the authenticated user's resolvable home. Keep manual launch choices authoritative.

## Scope

Foreground permission and one-shot acquisition, transient locality resolution,
Home integration, request invalidation, focused tests and Android/iPhone evidence.
Use the existing UI, geolocation dependency and Photon provider.

## Non-goals

No background tracking, precise-location persistence, profile/schema changes,
new screens/dependencies, ranking or source-acquisition changes, or pilot deployment.

## Dependencies / blockers

ADTR-22 home persistence and shared locality input are merged. The physical-iPhone
acceptance checkpoint requires the Mac session and the exact reviewed commit.

## Acceptance criteria

1. Authenticated Home requests foreground location with grant, denial, restriction,
   disabled/unavailable and stale-fix handling. Accept approximate location.
2. Usable GPS coordinates drive events and requested POI retrieval; locality lookup
   changes the display label only. Label failure preserves GPS.
3. Unusable GPS falls back only to a uniquely resolved home locality. Business,
   street, state, ambiguous or absent home does not become a guessed launch point.
4. With no usable GPS, home or manual launch, no events are queried or shown from
   another location. Existing Home guidance asks for a launch point.
5. Manual intent wins over pending automatic callbacks and profile home edits.
   Account changes, background transitions and new requests invalidate old work.
6. Relaunch/settings return refresh permission state. Automatic reacquisition
   invalidates old results; manual selection remains during the current session.
7. No continuous tracking or precise-location persistence is introduced. All
   authored application files remain under 1,200 lines.
8. Verify Android runtime and physical iPhone grant/deny paths and retained manual
   choice; disclose unavailable device cases instead of claiming completion.

## Testing / evidence

Focused backend locality/reverse tests and app permission, lifecycle, stale-fix,
account and manual-race tests; TypeScript; actual Home/deck screenshots and bounded
request evidence. GPS defaults: 15-second timeout and 10-second maximum fix age.
Exact-commit Mac handoff covers native iPhone permission and settings behavior.

## Bug or finding

The iPhone displayed “Current Location, GPS” even when a city could be resolved.
The owner also explicitly required safe behavior when both GPS and home are absent.
ADTR-22 strips the picker type suffix before saving home, which must be normalized
when matching provider locality descriptions.

## Proposed solution and likely files

A small Home location controller plus launch-service locality/reverse resolution;
Home, LocalEventsSection, homeUtils, Android permissions and adjacent focused tests.

## Stop condition

Escalate any need for background tracking, provider/precise-location persistence,
a new provider, new UI dependency/screen or source-ceiling breach. Keep the physical
iPhone gate visible and the ticket In Review until acceptance and merge.
