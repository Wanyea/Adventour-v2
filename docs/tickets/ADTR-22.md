# ADTR-22 — Capture and edit home city or town

Jira: https://adventour.atlassian.net/browse/ADTR-22
Parent: ADTR-19 (Phase Follow-ups). Origin: Phase 1/2 UI walkthrough.
Lane: In Progress, observed September 8, 2026.

## Summary

Capture an optional home city/town during passport setup and allow the signed-in
user to edit or clear it in the existing Profile screen.

## Objective

Supply a durable, account-bound home locality for ADTR-23's location fallback.
The owner approved the dependency-first plan and said to implement ADTR-22 first.

## Scope

- Nullable `home_city` user-authored text, trimmed, up to 160 Unicode characters.
- Existing authenticated profile update and self-profile responses carry it.
- Omitted field preserves the value; null/blank clears it. Existing users remain
  valid, and home is not required for profile completion.
- Onboarding prompts for city/town, with region/country encouraged; Profile can
  save/edit/clear it with visible pending/error behavior and server confirmation.
- Additive, repeatable schema upgrade; no participant-data backfill or deletion.

## Non-goals

No new screen, navigation entry, UI dependency, restyling, ranking change,
background tracking, stored GPS coordinates, or geocoder/provider payloads.
Free text is a user declaration, not proof of a valid geographic settlement.
ADTR-23 handles transient resolution and ambiguous/unresolvable home entries.

## Dependencies / blockers

Based on `origin/codex-astra` at `82a958ee`, containing merged ADTR-25.
Physical iPhone verification needs a Mac build and the updated backend. Windows
can supply Android evidence but cannot satisfy the iPhone gate.

## Acceptance criteria

1. First-time passport setup asks for home city/town before completion, optionally.
2. Profile displays the saved value and supports edit, save, cancel, and clear.
3. Unicode/worldwide locality names work without US-state-format restrictions.
4. The value belongs to the authenticated user, persists across relaunch, and is
   neither lost by unrelated profile updates nor leaked to another account.
5. Store only the user-entered locality field, not GPS/address objects or provider
   content. UI asks for a city/town, never a precise home address.
6. Verify on Android and a real iPhone build; keep unmet device gates explicit.

## Testing / evidence

Focused profile validation/persistence/account-isolation and repeatable migration
checks; TypeScript and scoped component tests; Android passport/Profile runtime
screenshots including relaunch/edit/clear. Mac handoff covers the same iPhone flow.
Preserve Home's coordinate guard: no coordinates means no local-event request.

## Bug or finding

ADTR-23 planning found no home field in the User model or app contract, and its
fallback acceptance depends on this ticket. Existing Profile city labels derive
from travel history and cannot represent a user's home.

## Proposed solution

Reuse profile persistence and existing form styles, with a small cohesive home
editor to keep Profile under 1,200 lines. Preserve name/DOB profile completion.
GPT-6 Astra plans and independently reviews; GPT-5.6 Terra implements bounded
backend/app slices and gathers runtime evidence.

## Likely files

Server user model, app profile/schema paths, small validation helper and tests;
AuthService, ProfileSetupScreen, ProfileScreen and home editor component/tests.

## Stop condition

Do not add new UI dependencies/screens, cross the source ceiling, persist provider
content, or absorb ADTR-23 into this ticket. PR targets `codex-astra`; no auto-merge.

## ADTR-23 owner clarification

Current GPS and saved home may both be missing. With no usable manual launch
either, skip event requests and encourage the user to set a launch point. Home
alone is not a guaranteed fallback. Preserve manual launch selection over late
automatic resolution. This requirement is recorded for the next ticket; ADTR-22
does not begin automatic location selection.

## Implementation and review record

PR: https://github.com/Wanyea/Adventour-v2/pull/4 (draft, base `codex-astra`).
Implementation: `c08ad7a9`; review corrections: `5e9eb983`; focused response-race
test correction: `0f2e2b14`. Ten focused backend checks passed on isolated
PostgreSQL, and seven app tests across two suites plus TypeScript passed.

Independent GPT-6 Astra review with a GPT-5.6 Terra backend audit found two
blocking app issues: stale-account profile-response caching and navigator
remounts after saving. Both were corrected; the reviewer found no remaining
blocking source issue at `5e9eb983`. The final test-only correction explicitly
waits for the outbound request before switching accounts. Device evidence and
ticket acceptance remain separate from that source review.

[Mac handoff](../adtr-22-mac-handoff.md) contains the build and physical-iPhone
walkthrough. No native dependency/configuration change is required by this diff.
The public Windows pilot has not been deployed from this feature branch.
