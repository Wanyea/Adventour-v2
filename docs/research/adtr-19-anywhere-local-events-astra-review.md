# Astra architecture review: events beyond configured cities

Reviewed 2026-09-09 by GPT-6 Astra, independently of the proposal author.
Artifact reviewed: `docs/research/adtr-19-anywhere-local-events.md` at local
`4b3403d5`. Current implementation was inspected in the ADTR-23 worktree at
`de7d39a0`, which contains the merged ADTR-25 work; the research checkout itself
is behind `origin/codex-astra`. This review changes documentation only.

## Verdict

**Agree with the index-first architecture; request amendments before handing
the whole implementation to a lower-cost agent.** The proposal protects fast
serving and establishes sensible source and freshness boundaries. It does not
yet specify how a region with neither a configured calendar nor indexed venue
websites acquires its first useful events. Implementing the proposed sequence
literally could produce another manually seeded city and leave the owner's
central requirement unmet.

The product requirement is location-independent acquisition with measured
coverage: any valid launch location can enter the same discovery process,
without an operator adding that city to an allowlist. That does not establish
that every town has public events, that every event can be licensed, or that
first-use results can be instantaneous. Those are distinct limits to expose and
measure, not substitutes for implementing discovery.

## Findings and required amendments

| Severity | Finding | Required amendment |
|---|---|---|
| Severe | Unknown-region discovery is a sentence, not a design. A registry only knows sources already entered into it. Owned venue URLs are unavailable in many unacquired regions. | Specify a bootstrap connector, its allowed discovery inputs, quotas, location matching, output contract and admission rules. Prove a cold region with no configured sources and no owned venue rows. |
| Severe | Source admission can become a hidden permanent manual city gate. Robots permission, a public URL and Event markup do not establish reuse rights. | Use explicit source states and pre-approved access/retention policies. Automatically activate only matches to an already approved policy and supported parser. Ambiguous sources enter an operator review queue. Measure the share of regions that still require manual intervention. |
| Severe | No acceptance test currently requires automatic acquisition to yield real relevant events. Empty-state correctness alone can pass the entire proposed test set. | Require actual newly acquired public events in SF and a held-out town, with acquisition initiated by normal launch selection and no per-region code/config change. A failed yield gate keeps the product outcome open. |
| Medium | Existing ADTR-25 work is omitted from the implementation baseline. | Reuse its registry validation, bounded transport, source timing, advisory lock, atomic replacement, dispatch and duplicate collapse. Extend them; do not create a second pipeline. |
| Medium | Conditional refresh and adaptive cadence are underspecified relative to the existing 24-hour rule. | Preserve separate fetch, publication and verification clocks. Specify when a 304 revalidates a live source, and when publication time remains authoritative. Sleeping a source beyond its allowed age makes its cards unavailable until successfully reverified. |
| Medium | A region/source/window lock is insufficient for durable jobs and inefficient for shared sources. | Add durable state, lease recovery, retry times and commit fencing. Aggregate demand by geography, but coalesce refresh by source and canonical bounded window so neighboring regions share one fetch. |
| Medium | Richness is reduced to one category, and chronological results are described as ranked events without clarifying personalization. | Preserve useful factual activity, setting, format, booking/access and evidence provenance where permitted. Keep current chronological ordering for acquisition acceptance; nuanced ranking is a separately approved comparison. |
| Medium | No numeric global resource limits, rejection behavior or cost model are defined. | Set worker, queue, host, region and daily request/byte budgets; reserve provider budget before calls. Report third-party charges, Windows processing time and operator time separately. |
| Medium | A successful empty response is not necessarily a complete source snapshot. | Require explicit completeness/pagination evidence before deleting absent events. Handle cancellations across duplicate sources so an old mirror cannot revive a cancelled occurrence. |
| Medium | Generic RSS/ICS/JSON-LD support is overestimated. | Preserve UCF's narrow adapter. Define the supported generic contract and reject/report unsupported recurrence, missing time, ambiguous locality and source-specific access requirements. |
| Medium | Home's acquisition progress, retries and rollout are unspecified. | Add a bounded response-state contract, reuse existing refresh behavior, suppress stale responses after location changes, and show actual acquisition-to-card behavior on a physical iPhone. Keep the public service rollout explicit. |

These are architecture findings, not a claim that all existing source adapters
have the corresponding bugs.

## What to keep from the branch

`docs/tickets/ADTR-25.md` explicitly scoped operator-selected acquisition. Its
implementation already provides `event_registry.py`, `event_http.py`,
`refresh_events.py`, `event_adapters.py`, and transactional source-window
replacement in `local_event_service.py`. Current registry entries remain UCF and
NYC Parks. Selection of a missing region returns `no_configured_source`; it does
not discover new sources.

The ICS adapter is `ucf_ics_events.py`, explicitly specialized for UCF. It rejects
recurrence properties and all-day forms rather than expanding arbitrary
calendars. `calendar_pilot.py` is a useful offline traversal/extraction component,
but its September 7 report records 11 candidates, eight preliminary date/region
passes and **zero production-ready events**. Neither component should be
represented as a working general event collector.

`local_event_service.listing` already uses H3 plus a distance check, rejects stale
or ended occurrences, collapses some duplicates and preserves source links.
`routes/local_events.py` records the pilot model as `event_chronological_v1` and
`personalized: False`. These are the migration and comparison baselines.

Keep ADTR-23's current/manual/home location precedence separate from acquisition.
Do not reset profiles, widen UI navigation or rebuild the POI pipeline here.

## Concrete system amendments

### 1. Bootstrap and admission

Freeze a deterministic lead sequence before the first blind run:

1. Reuse active source footprints that intersect the requested radius.
2. Query owned local venue/organizer website links if available.
3. Query a selected, permitted regional catalog or web-search connector for
   municipal, library, university, venue and community calendars. This is the
   essential fallback when step 2 is empty. The decision packet must name the
   connector, actual access requirements, price/limits, link-retention rights,
   query templates and geographic inputs. It cannot leave `discover_sources()`
   as an implementation placeholder.
4. Follow bounded event/calendar links from admitted sources. Cross-host links
   are new leads requiring their own access policy, not automatic authorization.

Search results identify leads; snippets are not canonical event facts. Source
records move through `discovered -> policy_pending -> eligible -> active`, with
explicit `rejected`, `paused` and `failed` dispositions. `eligible` requires
approved collection and retention, supported parsing, a verified geographic
footprint and a tested freshness basis. `active` requires one complete valid
collection. Operator review must concern a new source/policy, not every user or
every town. A source can serve several demand regions.

Do not silently impose a US-only runtime gate. The acceptance sample can be US
based, matching the current pilot, while unsupported language/source/geography
is recorded honestly. Worldwide effectiveness remains unmeasured.

The exact bootstrap vendor and access policy are **still design decisions** in
the reviewed artifact. They must be resolved with a bounded dry-run and owner
review before enabling new acquisition or spending. This review does not buy an
API plan, authorize a new storage basis or contact publishers.

### 2. Serving, demand and jobs

Keep `GET /api/local-events` free of outbound acquisition. It may make one cheap
transactional demand upsert; worker scheduling can consume that demand. Key
demand by a coarse geographic bucket and the existing 14-day horizon, not raw
GPS, user ID or an exact current timestamp. Preserve the actual requested radius
for final H3/distance filtering. Requests spanning a boundary must not miss an
already active neighboring source or be treated as a different source identity.

Use the existing Postgres 17 instance for the first durable queue. A job needs
kind, unique work key, state, due time, attempt count, lease expiry, fencing token
and bounded error class. Claim in a short transaction; release the transaction
while fetching; commit only if the lease/token still owns the work. Reuse the
existing source serialization guard where needed. Queue uniqueness and
idempotent source writes remain necessary even with advisory locks.

One source-global rolling-window refresh should satisfy multiple region demands.
Use a canonical window/version rather than a different job for every request's
slightly shifted 14-day interval. Restarted workers recover expired leases.
Honor Retry-After and jittered backoff. A parser or authorization failure pauses
promotion and alerts the operator rather than retrying every minute forever.
PostgreSQL documents `SKIP LOCKED` specifically as suitable for queue-like
consumers; this supports keeping the pilot deployment small. [PostgreSQL 17 SELECT](https://www.postgresql.org/docs/17/sql-select.html)

Return existing events plus separate data and acquisition states, for example
`data_state: fresh|empty|expired` and
`acquisition_state: idle|queued|running|backoff|policy_pending|budget_limited|failed`.
Include `snapshot_version`, `checked_at`, `next_check_at` and bounded reason codes.
`empty` after checking admitted sources must remain distinct from no source or a
failed job. Keep any last successful snapshot for recovery only within its legal
retention; hide rows immediately when eligibility/freshness expires.

The existing client polls while focused approximately once a minute. Reuse that
flow for the first implementation, honor server next-check guidance, retain
manual refresh, and do not introduce continuous polling in the background.
Any changed coverage copy belongs to an explicitly approved narrow UI slice.

### 3. Facts, freshness and richness

Preserve `fetched_at`, `source_published_at` when available,
`verified_at`, `expires_at`, parser/policy version and source-event identity.
For a live authoritative feed, a valid conditional 304 can revalidate the same
representation when the source policy permits and matching parsed facts are
retained. For NYC's publication-based feed, downloading or revalidating an
unchanged snapshot cannot move the publication clock. HTTP 304 establishes an
unchanged selected representation, not organizer availability. Existing
`event_http.py` rejects all 304 responses, so this is a deliberate adapter/transport
change with targeted tests. [HTTP semantics, RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.4.5)

Keep the current active-event hard expiry at the earliest of end time,
verification + at most 24 hours, and any shorter source retention limit. A
six-hour fetch cadence cannot promise six-hour knowledge from a daily publisher.
Prioritize near-term/demanded events but do not advertise a looser age guarantee
for distant events without an approved contract change. Discover new listings
separately from rechecking existing details; otherwise a rich pool never grows.

Only complete snapshots for an explicit source/time footprint can delete absent
records. A 200 page with failed pagination, parse collapse or an invalid schema
is not an empty snapshot. Retain per-source assertions when collapsing
duplicates; prefer current organizer cancellation/access evidence to a stale
aggregator. Stable source occurrence IDs survive title corrections or reschedules.
Calendar recurrence needs bounded expansion with timezone, exception and
cancellation semantics; weekly rules must not create immortal or duplicated
events. [iCalendar, RFC 5545](https://datatracker.ietf.org/doc/html/rfc5545)

Permitted normalized facets should separate activity from venue and social format:
coffee tasting at a cafe, a DJ gathering, a market, a class and a church concert
can have different relevance even when their names contain coffeehouse. Preserve
unknown values and links to the factual evidence that supported extraction.
Do not infer a cafe menu or community character from the title alone. These
distinctions directly address the owner's E1-E4 labels. Start with deterministic
extraction and inspect exclusions; an LLM is not required for this acquisition
slice. Natural-language user summaries and changed personal ranking remain the
separate comparison described in `preference-profile-assessment.md`.

Actual entrance/event coordinates require permitted source evidence or a
confident owned venue match. City centroids and organizer headquarters are not
event venues. Quarantine ambiguous location rather than obtaining Google
content for persistence. Missing attendance/end-time facts need an explicit
exclusion reason, not invented defaults. Public online-only events are not
physical local destinations. [Schema.org Event](https://schema.org/Event)

### 4. Cost and operations

Proposed starting engineering bounds, to validate in the decision ticket:
one background worker, one active fetch per host, two new-region discovery jobs
admitted per minute, at most 100 queued regions, and a global 2,000 upstream
requests/day cap. A discovery job may examine at most 20 hosts, fetch at most
40 pages, download at most 10 MiB and use at most five minutes. Existing admitted
source limits still apply where stricter. These are proposed safety bounds,
not measured throughput promises or approved spending.

Reserve daily capacity for already active near-term events so discovery cannot
starve freshness. Coalesce repeated demand, cool down empty/no-lead outcomes,
and aggregate demand for seven days rather than keeping a precise movement log.
No new participant data is needed for the queue. A general discovered-URL
fetcher must reject private/local/metadata addresses, revalidate redirects and
DNS destinations, and cap body size; the Windows PC must not become a proxy to
its own private services. [OWASP SSRF](https://owasp.org/www-community/attacks/Server_Side_Request_Forgery)

At first, paid upstream calls are disabled unless the owner approves a specific
background connector and hard dollar cap. A paid search/provider call does not
become permitted merely because a request was moved to a worker. No paid call may
populate a swipe deck, and no paid fallback runs on Home. Any approved
background event connector must have an explicit relationship to that boundary.

Compare total recurring workload as:
`source refreshes x requests per refresh + detail rechecks + lead discovery + retries`.
Charge duplicate and failed work too. Report upstream dollars, wall/CPU time,
peak memory, bytes, active source count, stale-card suppression and operator
minutes per activated source. Divide costs by unique verified occurrences and by
successful user requests; report zero yield without manufacturing a finite
cost-per-event. Source priority should consider unique eligible yield per unit
cost, freshness failures and demand, while reserving a small fixed exploration
budget for overlooked source families.

Windows restart evidence must cover the worker as well as Flask: start/stop,
process health, bounded logs, lease recovery and a due refresh after restart.
Do not require Redis, Kafka, Kubernetes, a vector database or an LLM serving
service for this workload.

## What industry evidence actually supports

Google describes crawl capacity, demand, source health, duplicate URL control
and conditional requests as separate constraints. These support prioritizing a
bounded source frontier; they do not prove that our local-event yield will be
good. [Google crawl budget guidance](https://developers.google.com/crawling/docs/crawl-budget)

Microsoft's cache-aside guidance explains demand-driven loading, per-item
lifetimes and consistency limits. Adventour should borrow the separation of
retrieval and freshness while enforcing its stricter event eligibility gate;
generic cache-aside's synchronous miss fallback is unsuitable for expensive
discovery in Home. [Azure architecture guidance](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside)

Ticketmaster's documented quota and regional search are useful comparison
inputs. Its terms explicitly limit retention, require requested removals and
restrict some competing uses. It is not automatically an indefinitely owned
inventory or an approved fallback. [Discovery API](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/),
[API terms](https://developer.ticketmaster.com/support/terms-of-use/)

Robots rules are crawler instructions, not authorization or a commercial reuse
license. Substack's documented RSS availability similarly does not override its
terms. Avoid the proposal's malformed feed shorthand; the publication's actual
documented feed must be verified. [Robots standard, RFC 9309](https://datatracker.ietf.org/doc/html/rfc9309),
[Substack RSS documentation](https://support.substack.com/hc/en-us/articles/360038239391-Is-there-an-RSS-feed-for-my-publication),
[Substack terms](https://substack.com/tos)

The SF Public Library has an actual public events calendar, so it is a concrete
source lead for the SF study. This review has not established an ingestion
license, adapter success or qualified event yield for it. An upstream source
page existing is useful evidence; a production coverage claim requires the
rest of the pipeline. [SFPL calendar](https://sfpl.org/events)

Do not state that no vendor can cover this market at any price. The evidence
supports fragmented access and unmeasured long-tail coverage, not that universal
negative. A licensed aggregator can be compared if it offers a suitable contract;
it must win on our local-interest sample and total cost, not raw global counts.

## Bounded tickets under ADTR-19

These are proposed contracts, not created Jira issues or approved implementation.
Keep Phase 2 as origin metadata, not the parent. Each ticket uses a small number
of reviewable commits with an owner checkpoint roughly every two hours. Astra
owns the design/independent acceptance review; Terra implements the bounded
files against the approved contract. Implementers must not select a new vendor,
weaken expiry, expand source rights or invent coverage targets.

1. **Acquisition decision and frozen coverage benchmark (design/experiment).**
   Select the actual bootstrap connector and source admission policies; compare
   low-cost first-party/catalog discovery and one viable licensed option if
   accessible. Register SF plus one held-out small town, a date window, category
   strata and independently collected reference events before the run. Include
   a no-owned-venues scenario. AC: connector/access/cost decision, measured
   lead-to-eligible-event funnel, concrete failed-stage reasons, and a frozen
   implementation contract. Stop after one comparison and one bounded repair
   run; unresolved access/yield is a named blocker, not another open phase.
2. **Automatic source discovery and admission.** Implement the selected bounded
   connector and source state machine, extending ADTR-25. AC: cold-region input
   finds real source leads without a hand-entered regional roster; approved
   policies activate a working source; ambiguous rights or location remain
   quarantined; no prohibited field reaches DB; budgets and outbound-address
   controls hold. A manually seeded SF success cannot satisfy this ticket.
3. **Durable demand scheduling and freshness.** Add queue/demand records,
   source-global coalescing, lease recovery, global budgets, source-specific
   clocks, completeness gates and Windows operation. AC: concurrent SF and
   neighboring launches share work; retry/restart cannot duplicate publication;
   NYC repeated publications do not renew age; partial refresh cannot clear the
   snapshot; cancellation/expiry and budget exhaustion behave as specified.
4. **Verified event normalization and reusable extraction.** Implement only the
   parsers/source families selected by ticket 1; extract permitted facets,
   identity, location, access and recurrence. AC: real results cover more than a
   single venue/series, explicit counterexamples cover coffee-title ambiguity,
   sold-out/private/online/mislocated events and recurrence exceptions; report
   unknowns, misses and duplicate conflicts. Reuse the existing recheck route.
5. **Home acquisition feedback and pilot acceptance.** Connect response states
   to the existing section, preserving ADTR-23 precedence and pilot traces.
   AC: selecting cold SF and the held-out town triggers acquisition and then
   displays actual verified events without an operator adding those regions;
   original regions remain correct; location switches cannot display prior
   region results; warm-list latency and time-to-first-result are measured;
   the iPhone flow and Windows restart/export are shown with no paid deck calls.

Tickets 2-4 require ticket 1's approved concrete decisions. Ticket 5 requires
all three. Adapt file ownership to keep changes coherent; this is one bounded
follow-up, not five new product phases. No ticket is allowed to disappear simply
because its technical subset passes tests.

## Acceptance threshold to review before implementation

For the proposed first sample, require at least five eligible distinct
occurrences across at least three venues/organizers in cold SF, and two across
two venues/organizers in the held-out town, within the existing radius and
14-day window. Select a town with independently verified public events; do not
select it by whether our collector succeeds. Include community/independent
activity rather than accepting only arena inventory. These are proposed pilot
utility gates, not a promise about every possible town or date.

Inspect every displayed event in that small acceptance sample against its
official source: correct date/time/timezone, physical venue, public access,
booking/cancellation status and freshness. Report extraction yield, eligible
precision, reference-set recall, unique organizers, error counts, n, latency,
compute and charges. Report source-relative recall separately from reference-set
recall and unmeasured metro-wide completeness. The supplied Last Bite link is
development evidence and cannot become a new organic discovery success.

Failure to obtain these results should produce one of the concrete dispositions:
access blocked, leads missed, parsing unsupported, facts insufficient, freshness
inadequate or budget insufficient. That makes the next owner decision clear.
Passing queue, empty-state or schema tests alone does not satisfy the requirement.
