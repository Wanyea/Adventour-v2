# ADTR-22 — Mac build and iPhone verification

This ticket adds optional home city/town capture in existing passport setup and
Profile editing. It does not enable startup GPS or home-based discovery; ADTR-23
owns that next step. See [ticket contract](tickets/ADTR-22.md).

## Source and backend alignment

Branch: `feature/adtr-22-home-city`, PR base: `codex-astra`. Fetch the final PR
head before testing; record its full SHA alongside the iPhone build ID. If it has
merged, use the corresponding updated `codex-astra`. Do not reset or overwrite
uncommitted Mac work, local Firebase files, signing settings, or env files.

The Windows public service must run that backend revision (or its merge) before
iPhone acceptance. An older backend can ignore an unknown home field, which is
not a successful save. Confirm authenticated `/user/profile` and self-profile
responses contain `home_city`, and verify a read after relaunch matches the saved
value. Never paste a token or participant payload into the PR or Jira.

Windows verification uses isolated dev data; it does not by itself establish
that the public pilot service has been updated. Coordinate that deployment with
the Windows session before the real-device walkthrough.

## Mac work

Use the existing working iOS pilot setup and signing configuration described in
[remote pilot service](remote-pilot-service.md) and the
[distribution checklist](iphone-distribution-checklist.md). This feature is
JavaScript/TypeScript plus a backend field. No new native package, location
permission, entitlement, Firebase configuration, or Xcode setting is expected.

A packaged iPhone build needs its JavaScript bundle rebuilt and the app
reinstalled. Reuse the established pilot scheme and private environment; do not
replace working configuration with example files. Record a new build identifier
for distributed artifacts. A Debug app connected to Metro can reload the new JS,
but that alone is not packaged-build distribution evidence.

## Real-iPhone walkthrough

Use a designated test account; do not reset an existing participant's account.

1. Fresh setup shows optional Home city or town alongside passport details.
   Save a locality with region/country. Finish the existing mood flow.
2. Profile displays the same home. Force-close/relaunch and confirm persistence.
3. Edit it to an international locality (for example `São Paulo, Brazil`), save,
   and verify after another relaunch. Cancel an edit and confirm no change.
4. Clear home, save, and relaunch. It stays unset and does not force onboarding.
5. With a fresh second test account, leave optional home blank. Verify account
   separation and usable Home/Profile. With no selected launch coordinates,
   there should be no local-event listing request. Startup GPS is not in ADTR-22.
6. During a save, temporarily make the backend unreachable. Confirm an error,
   no false saved state, and successful retry after connectivity returns.

Capture only designated test-account screens. Record OS/device, build ID, source
SHA, backend revision, pass/fail for each step, and any issue. Required iPhone
evidence is still pending until this walkthrough is performed; do not close the
ticket based solely on Windows tests or screenshots.

## Prompt to give Mac Codex

> Continue ADTR-22 iPhone verification from docs/adtr-22-mac-handoff.md. Read
> HANDOFF.md completely, AGENTS.md, and docs/tickets/ADTR-22.md. Fetch the final
> feature/adtr-22-home-city PR head (or its codex-astra merge), preserving local
> work and private signing/Firebase/env files. Reuse the working pilot iOS build
> setup. Coordinate backend revision with the Windows session before the
> walkthrough. No new Xcode configuration is expected; rebuild/reinstall and run
> the real-device checks in the handoff, recording SHA/build ID and evidence.
> Do not implement ADTR-23 yet. Never claim its automatic location/home fallback
> is delivered by ADTR-22, and never commit participant data or credentials.
