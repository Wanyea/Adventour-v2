# ADTR-26 gate evidence — current baseline

**Run date:** 2026-09-09
**Status:** blocked pending the arbitrary-location acquisition implementation
**Branch:** `adtr-26-bootstrap-decision`

## Evidence collected

The focused ADTR-25 event-path tests were run from `Server/`:

```text
python -m pytest tests/test_event_refresh.py tests/test_local_events.py -q
5 passed, 1 skipped
```

These tests verify the existing configured-source refresh, freshness, replacement, and local-event listing behavior. They do not prove arbitrary-city acquisition.

The checked-in baseline remains the previously recorded worldwide launch run: Orlando returned seven events from `ucf_main`; New York and London returned zero events and no sources. That is evidence of the current configured-source limitation, not success for ADTR-26.

## Gate result

ADTR-26 acceptance evidence cannot yet be marked passed. The branch currently contains the connector decision and implementation contract, but not the worker, demand mapping, source discovery, or arbitrary-location publication path required by the ticket. A successful cold San Francisco run, held-out-town run, no-owned-venues run, restart/lease run, and device demonstration must be added after implementation. No provider or participant data was added here.
