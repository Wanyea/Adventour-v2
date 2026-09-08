# ADTR-25 verification

Implementation: `f7c1aba1`. Tested on Windows with Postgres and the existing
Pixel_7_API_30 Android emulator. No physical phone was attached; these screenshots
are emulator evidence, not new iPhone or physical-Android acceptance.

## Live acquisition and serving

`runtime.json` is produced by `run.py` against the private isolated Postgres
database. Both configured regions were refreshed twice; stored counts stayed
309 NYC Parks occurrences and eight UCF gallery occurrences. One existing owned
Overture gallery record was supplied to the isolated DB for UCF's venue match.
The public pilot service/database was not modified. No participant export or
credentials are in this packet.

| Source | Input occurrences | Eligible | Requests | Bytes | First refresh |
|---|---:|---:|---:|---:|---:|
| NYC Parks | 1,271 | 309 | 2 | 1,476,096 | 2.516 s |
| UCF ICS + category verification | 104 | 8 | 23 | 222,194 | 13.250 s |

Source duplicate counts were zero in this sample; repeated refresh did not grow
the index. Cross-source duplicate collapse is tested with synthetic overlapping
sources; these geographically disjoint live feeds do not measure that rate.
The source-specific yields are not metro-wide coverage estimates or preference
quality measurements. No new source outside these two existing calendars is
claimed. ICS adds a working feed-format path, not additional geographic coverage.

NYC listing returned the first 50 records; UCF returned eight; Seattle returned
zero. Each list ran with outbound requests prohibited and took approximately
196–227 ms. Both explicit source rechecks matched the stored occurrence, taking
1.499 seconds for UCF and 1.829 seconds for NYC. These are single-run elapsed
measurements, not load-test percentiles or availability promises.

At four similar refreshes/day, the observed request count projects to 100 requests
and approximately 6.8 MB/day across both sources, excluding explicit rechecks,
HTTP/TLS overhead and retries. No paid API or LLM was used. UCF currently has no
observed ETag/Last-Modified; no conditional-fetch savings are claimed. Source
facts and event verification keep the existing at-most-24-hour freshness bound.

## Android checkpoint

The emulator initially had no host network route. A cold restart restored it.
The existing app ran against the ADTR-25 development backend on port 8082 and
the isolated database; the public pilot port 8080 remained running.

GPS was set through the emulator controls and selected through the existing
location button. Screens were inspected after each selection:

- [NYC](nyc-android.png): NYC Parks events, dates, locations and source attribution.
- [UCF](ucf-android.png): UCF gallery events after changing the selected location.
- [Seattle](empty-android.png): explicit no verified events, with no UCF fallback.

The generic “Current Location, GPS” label is existing behavior owned by ADTR-23.
This ticket changes no app screen, component, navigation or dependency.

## Focused checks

37 tests passed, zero skips, with the original Windows venv and isolated Postgres
configuration: `test_local_events`, `test_nyc_parks_events`, `test_event_http`,
`test_event_region_contract`, `test_event_refresh`, and `test_ucf_ics_events`.
They cover expiry, cancellation, failed refresh preserving records and last
success, source identity/columns, source timezone, future verification rejection,
mixed-identity deduplication, geographic isolation, no-request listing, registry
validation, due backoff, and network budgets. Real localhost HTTP tests exercise
both successful reads and a slow response terminated at the absolute deadline,
with no leftover fetch child process.

`git diff --check` passed. No authored app source changed; the largest checked
TypeScript/JavaScript app file is ProfileScreen.tsx at 1,021 lines.

## Review disposition

Initial independent review used GPT-6 Astra with a separate GPT-5.6 Terra review
slice. Four blocking code findings were corrected before `f7c1aba1`: ICS status
cancellation, mixed-identity dedupe aliases, slow-stream absolute deadlines, and
an outage test patching an obsolete adapter. Final review is recorded separately.
Final technical approval: GPT-6 Astra approved code commit `389cb05f` after
reproducing the distinct-entity regression. The final 37-test run passed in
2.52 seconds; a DB-only replay of NYC/UCF/empty listing on that commit matched
the recorded 50/8/0 result counts. The live screenshot/acquisition packet above
was collected on `f7c1aba1`; the subsequent change only addresses overlapping
cross-source entity identities. No blocking code findings remain.

The HTTP deadline terminates the fetch worker; a short OS process-cleanup interval
can follow the deadline. It does not leave a remote slow-stream request running.
Real-phone verification and owner acceptance are not inferred from these tests.
