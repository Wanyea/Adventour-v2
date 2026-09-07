# Repeatable calendar source pilot — September 7, 2026

The collector was implemented and run twice. This is an offline acquisition
experiment, not a production adapter or a recommendation-quality result.
Six fixed source roots, four content pages each, September 7 through October 4
(America/New_York). Known NYC development leads were used; no held-out claim.
The owner's supplied Last Bite Partiful URL was never a seed or an organic find.

## Measured results

| Source | Run 2 parsed pages | Unique candidates | Date/region precheck passes |
|---|---:|---:|---:|
| Multimodal Roasting | 4 | 2 | 0 |
| Sequoia Cafe | 4 | 3 | 3 |
| Corgi NYC / Luma | 4 | 6 | 5 |
| NYC for FREE website | 4 | 0 | 0 |
| Orange County Library | 4 | 0 | 0 |
| Palm Coast municipal calendar | 4 | 0 | 0 |
| Total | 24 | 11 | 8 |

**Zero production-ready events.** Precheck passes do not establish admission,
ticket availability, precise navigable location, freshness or storage rights.
Run 2 used 32 HTTP requests including robots/redirect handling, 7,185,075 response
bytes and 42.17 seconds. These are one local run's costs, not a throughput SLA.

Run 1 retained eight candidates, five passing the date/region precheck:
28 requests, 4,209,818 bytes, 44.44 seconds. The library timed out then but was
accessible in run 2. That failure does not prove the source is unusable.

The original protocol was committed as `9306e2c1`; initial code and result as
`01a3ff5e`. Before rerunning, protocol v2 was committed as `37b50582`: repair
compact timezone offsets, exclude calendar exports, and prioritize links in
dated calendar articles. Both artifacts remain unchanged. Improved extraction
on these same sources is development evidence, not independent validation.

## Review findings and limits

- Multimodal yielded two dated occurrences, but their Event nodes lacked region
  evidence. The site's footer was deliberately not used to invent event venues.
- Sequoia yielded drawing, Sunset Social and journal-making occurrences.
  A separate September 7 spot-check of the
  [journal workshop](https://www.sequoiacafenyc.com/events/leather-crafting-event)
  found an explicit sold-out notice. The structured-data precheck missed it.
  **Exclude this event from attendance recommendations.** Do not revise the raw
  extraction artifact to pretend the collector detected availability.
  The [drawing page](https://www.sequoiacafenyc.com/events/draw-from-memory-challenge-w-matt-p)
  corroborated September 10, 6–8pm, but did not settle admission requirements.
- Luma calendar nodes supplied six candidates, five with region evidence.
  Their saved `source_url` identifies the inspected calendar, not a verified
  occurrence detail URL. Traversal also spent pages on broad Luma collections.
  Prioritizing explicit Event URLs and checking eligibility is still needed;
  professional/registration-based gatherings are not automatically public.
- NYC for FREE, the library and Palm Coast exposed event/calendar pages but no
  extractable Event JSON-LD in this bounded traversal. This is a parser/traversal
  gap, not evidence that their calendars contain no events. Visible-date parsing
  and documented feeds are concrete next methods to test.
- Coffee-related text is only a diagnostic flag, not a cafe-interest fit score.
  No new preference model, summary biography or calibrated fit score was run.
- No source prose/images or Google content was acquired into the production DB.
  Source retention permission and an operational freshness policy remain open.

## Reproduce

From `Server`, using its existing virtual environment:

```powershell
.venv\Scripts\python.exe -m data_pipeline.calendar_pilot --protocol ../docs/verification/2026-09-07/calendar-pilot/protocol-v2.json --output ../docs/verification/2026-09-07/calendar-pilot/run-next.json
.venv\Scripts\python.exe -m unittest tests.test_calendar_pilot
```

Use a new output filename to preserve historical evidence. Live source contents
can change. Four focused regression tests passed: numeric timezone offsets,
future-link ordering/export exclusion, missing event location and cancellation.
The collector has no DB write path. Tests do not validate recommendation quality.

## Next bounded slice

Preserve the six-source sample. Prioritize occurrence detail URLs, add scoped
availability/access checks, and test a visible-event parser or documented feed
for one zero-yield source. Record a protocol amendment before another run.
Only promote a source after its retention basis, precise venue, freshness and
expiry are established. Then show actual app cards and their evidence before
claiming a serving improvement. Phase 2 remains active.
