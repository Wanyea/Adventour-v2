# ADTR-26 gate evidence — implementation checkpoint

**Run date:** 2026-09-09
**Status:** blocked pending connector discovery/admission and cold-region acquisition
**Branch:** `adtr-26-bootstrap-decision`

## Evidence collected

The focused backend tests were run from `Server/`:

```text
python -m pytest tests/test_event_demand.py tests/test_event_refresh.py tests/test_local_events.py -q
6 passed, 1 skipped
```

The implementation now includes an H3-cell, 14-day demand queue with coalescing, transactional `SKIP LOCKED` claims, lease expiry recovery, fencing tokens, bounded retry backoff, startup schema creation, and acquisition-state reporting on `/api/local-events`. Ordinary event reads persist demand state even when pilot capture is disabled.

The checked-in baseline remains the previously recorded worldwide launch run: Orlando returned seven events from `ucf_main`; New York and London returned zero events and no sources. That is evidence of the former configured-source limitation, not success for ADTR-26.

## Gate result

ADTR-26 acceptance evidence is still blocked. The queue and worker boundary are implemented, but the approved connector discovery/admission function has not yet been integrated, and no cold San Francisco, held-out-town, no-owned-venues, restart, or physical-device acquisition run has been completed. The worker accepts an injected acquisition function intentionally; it does not invent a provider or persist unapproved provider content. No provider or participant data was added.
