# ADTR-23 independent review

Reviewed against `docs/adtr-23-implementation-plan.md` and AGENTS.md on
2026-09-09. Base: `5155249c4b943849180c04d6c4b9e34dfcf4afe8`.
Implementation head: `9097cad2657ce9710a6a611e48cb46fc0304ae04`.
The reviewer did not implement this change.
A separate GPT-5.6 Terra reviewer independently audited the final hook, Home
integration and event lifecycle; it reported no source findings. Neither review
relies on an implementation agent approving its own work.

## Findings and corrections

The initial review requested these bounded corrections, all medium blockers:

- Saved-home exact matching accepted businesses and other nonlocalities.
  The home-specific resolver now requires structured settlement metadata and
  unique normalized matching, while manual selection remains available.
- Backgrounding did not invalidate pending automatic callbacks. It now advances
  the generation and clears automatic launch state before foreground reacquisition.
- Updating home reset manual intent. The reset now belongs to account change or
  explicit GPS retry; same-account home edits preserve manual selection.
- Reacquisition retained old coordinates and deck results. The onAcquiring
  callback now clears coordinates, deck and pending request ownership.
- Home results supplied description, but the app read only city/state. The
  confirmed description now supplies the home label.

Follow-up inspection confirmed logout clears the old account's launch state,
automatic retries after denial check permission without another native prompt,
and explicit GPS retry may request permission. District-typed villages remain
eligible for home search before strict settlement filtering.

No new provider/profile writes, precise-coordinate cache, background location
mode, UI dependency, or screen is introduced. Home uses committed coordinates
for both events and the explicit deck action. Native configuration explicitly
requests when-in-use; Android supports fine and coarse permission paths.

## Verification and limits

The independent reviewer ran 27 backend launch tests, 12 foreground hook tests,
and TypeScript compilation successfully. The implementation/primary packet
reports 19 app tests across two focused suites. The primary also checked the
authored-source ceiling and diff formatting.

The reviewer read the Android runtime report and Mac handoff. The primary
observed GPS locality and events, denied-permission home fallback, unavailable
GPS without home, manual retention across resume, explicit GPS retry, and the
20-card St. Augustine deck. The separate score replay is correctly identified
as corroboration rather than a recommendation-quality result. Screenshots stay
in temporary local storage; this reviewer has not independently viewed them.

## Disposition

No remaining blocking source finding at the implementation head above. Overall
acceptance remains pending, with one medium blocking device/evidence gap:

- Physical-iPhone verification of the exact committed revision is still required,
  including foreground permissions, restriction/reduced precision, settings
  return, manual races and no-location behavior.

Keep the PR draft for these gates and owner review. This document is neither
GitHub approval nor permission to merge, deploy the public pilot, close ADTR-23,
or accept Phase 2. The Mac test backend must match the reviewed app revision.
