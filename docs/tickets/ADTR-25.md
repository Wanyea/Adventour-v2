# ADTR-25 — Regional event acquisition and coverage

Jira: https://adventour.atlassian.net/browse/ADTR-25
Parent: ADTR-19 (Phase Follow-ups). Origin: Phase 2 location/event review.
Owner approved the implementation plan with “start and make sure you are using
the right models”. Jira was verified In Progress on September 8, 2026.

## Approved contract

Extend the owned event index with bounded, operator-selected regional acquisition.
Reuse NYC Parks structured data and the UCF public calendar storage boundary;
add a documented RSS/Atom/ICS acquisition path. Preserve factual provenance,
dated occurrence identity, geographic isolation, atomic refresh, cancellation
removal, and query-time expiry. Listing requests query the database only.

Acceptance evidence must cover source configuration/permission/parser version,
network limits, deterministic duplicate collapse with source links, repeat refresh,
failed/stale refresh, and NYC/UCF/unconfigured-region behavior. Show the existing
event surface on Android. Report yield and latency without claiming metro-wide
coverage or improved preference ranking.

No UI changes, paid provider, broad social scraping, worldwide preloading,
background user tracking, or LLM pipeline are authorized by this ticket.

## Implementation sequence and ownership

1. Validate registry and source-specific timing; select a region/source; support
   dry runs and due-only refresh with concurrency protection.
2. Apply bounded HTTP transport and a documented calendar-feed adapter.
3. Integrate source timezone/freshness validation and deduplication evidence.
4. Run focused Postgres checks, live acquisition, and Android presentation checks;
   prepare the PR and independent review.

GPT-6 Astra handles architecture review and final independent review orchestration.
GPT-5.6 Terra agents implement bounded file sets and report tests and limitations.
The primary agent integrates the work and verifies operational evidence.

## Coverage limitation

Configured-region acquisition is not automatic source discovery for an arbitrary
GPS position. This slice has no demand queue or request-triggered crawl. Unknown
regions must return no configured source/limited coverage, with no Orlando fallback.
ADTR-23 supplies location selection; source onboarding still requires a permitted
source and verified geographic/access mapping. This limit must remain visible in
the runbook and final evidence.

## Branch and evidence

Implementation branch: `feature/adtr-25-regional-events`, based on `b02fc2cf`
(latest `origin/codex-astra` at start). The pilot PR #2 remains open, so `main`
does not yet contain its prerequisite code. Preserve a ticket-only diff against
this baseline; do not include prior phase changes as ADTR-25 implementation.

Baseline: 13 existing local-event/NYC tests passed against isolated Postgres.
Implementation `f7c1aba1` now has 37 passing focused checks, live repeat refresh,
source rechecks, and NYC/UCF/empty-region Android emulator screenshots in the
[verification packet](../verification/2026-09-08/adtr-25/README.md).
No physical phone was attached; physical-device acceptance remains unclaimed.
