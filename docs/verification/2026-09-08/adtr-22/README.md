# ADTR-22 Windows checkpoint

PR: https://github.com/Wanyea/Adventour-v2/pull/4
Code and test revision: `0f2e2b14`; base: `82a958ee` (`codex-astra`).

Implemented optional account-bound home city/town in passport setup and Profile.
Android emulator checks pass for setup/save, relaunch, edit/cancel/clear and cleared
relaunch. Saving preserves Profile navigation and the selected manual launch point.
With no selected coordinates, the existing event-query guard stays intact.

- [Runtime details and screenshots](runtime.md)
- [Independent review](review.md): no remaining blocking code findings
- [Approved ticket contract](../../../tickets/ADTR-22.md)
- [Mac build and physical-iPhone handoff](../../../adtr-22-mac-handoff.md)

## Focused validation

Ten backend tests passed against isolated PostgreSQL, covering validation,
authenticated ownership, persistence, omitted/null handling and migration. The
legacy DOB-only migration fixture uses a separate in-memory SQLite database;
the existing PostgreSQL migration is exercised twice for repeatability.

Seven app tests passed across HomeCityEditor and AuthService suites, including
failed saves, mismatched server responses, cancel/clear and the deferred response
after account switch. TypeScript and `git diff --check` pass. The largest authored
app source remains ProfileScreen.tsx at 1,035 lines (ceiling 1,200).

Run backend checks from `Server` with the original Windows venv and the private
isolated environment selected via `ENV_FILE`, then
`python -m pytest tests/test_home_city.py -q`. From `AdventourApp`, run
`npm test -- --runInBand --watch=false src/components/HomeCityEditor.test.tsx src/services/AuthService.test.ts`
and `npx tsc --noEmit`. Never substitute the participant database for test data.

This is an existing Android debug binary loading the new branch's JS through
Metro, not a new native build. Real-iPhone acceptance remains pending; the PR
stays draft. No native dependency/configuration changed. The public pilot backend
has not been deployed from this branch; align it before Mac device verification.

The Android walkthrough covers successful saves and cancellation. Save failures
are covered by the focused component test; real-device offline-save/retry is in
the Mac handoff. No recommendation-quality improvement is claimed by this UI
and profile-persistence change.
