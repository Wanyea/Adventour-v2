# ADTR-26 connector decision and frozen coverage benchmark

**Status:** implementation packet, approved for ADTR-26
**Date:** 2026-09-09
**Scope:** background discovery of public local-event sources for an arbitrary launch location

This packet freezes the decision and implementation contract for ADTR-26. The ticket owns
the connector decision, backend implementation, and acceptance evidence needed for an
arbitrary launch location to enter automatic acquisition. It does not authorize a paid
plan or storage of provider content.

## Decision

Adventour will use a two-stage, index-first path:

1. **Primary acquisition:** discover and ingest public first-party calendars and event pages
   owned by municipalities, libraries, parks, universities, venues, and community
   organizations. Supported inputs are an approved RSS/Atom, ICS, JSON feed, or an event
   page with supported `schema.org/Event` JSON-LD. The source page is the authority for
   event facts.
2. **Bootstrap lead connector:** use the Ticketmaster Discovery API only as a bounded,
   lead-only catalog comparison and source-lead generator. It is not an event inventory for
   the swipe deck and its response fields must not be copied into the owned event index.
   A developer key and current terms must be verified before any call. The free documented
   quota is a comparison input, not approval to purchase a plan.

The primary path is preferred because it preserves the local long tail and gives Adventour
an explicit source and retention policy. Ticketmaster is useful for measuring whether a
licensed catalog improves discovery, but its documented inventory is expected to skew toward
commercial/arena inventory and its terms must be rechecked before retaining any identifier or
URL. If access or rights cannot be verified, the connector disposition is `access_blocked`.

No Google, Meta, Instagram, TikTok, Partiful, or Substack content is fetched by this ticket.
Substack RSS remains a possible first-party lead only when a publication is public and its
access and retention basis are separately admitted.

## Offline comparison and evidence boundary

The comparison starts from evidence already collected in ADTR-25 and the source documentation
linked below. ADTR-26 must complete the bounded implementation experiment below before its PR
can be approved; it may not defer the required acquisition evidence to another ticket.

| Path | Evidence available now | Expected value | Decision |
|---|---|---|---|
| Owned venue/organizer pages | The index has about 14,000 venues with website/social links; the existing crawler found JSON-LD on 21% of inspected sites. | Local, attributable facts with a reusable freshness basis. | Primary; extend with bounded source admission. |
| Public civic/institutional feeds | The SF Public Library publishes a public events calendar; the existing UCF adapter proves one narrow ICS path. | Good local coverage where a feed exists; cheap to refresh. | Primary; generic support must be narrower than “all ICS/RSS”. |
| Ticketmaster Discovery API | Official documentation advertises regional/date event search and a default 5,000 calls/day quota. | Fast lead coverage and a controlled licensed comparison. | Lead-only comparator; no paid upgrade or deck population. |
| Eventbrite public API | Official platform documentation says public event search was shut down in 2019. | Not a dependable public bootstrap path. | Reject for this ticket. |
| Meetup | Official documentation requires bearer authentication and current access is tied to an application process/Meetup Pro eligibility. | Potential community coverage, but access is uncertain. | Defer as `access_blocked` unless separately approved. |

Measured baseline remains: UCF returns events, NYC returns events, and a cold San Francisco
request returned zero events because no configured source was available. This proves the
current limitation; it is not a coverage result for the new design. The ADTR-25 pilot
traversal produced 11 candidates, eight preliminary date/region passes, and zero
production-ready events. Those figures are retained as baseline evidence and are not mixed
with the new experiment.

## Frozen experiment

Before acquisition, record an independently assembled reference set for:

- San Francisco, CA, within the existing event radius and a 14-day horizon;
- one held-out small town selected for having public events, without selecting it by collector
  success;
- one San Francisco run with owned venue rows excluded, proving the bootstrap path is real;
- category strata covering community, arts/music, food/market, class/fitness, and family or
  civic activity.

For each connector, freeze the exact geographic input (latitude/longitude, radius, canonical
region), date window, query terms, request count, response bytes, wall time, and access mode.
Search snippets or catalog titles are leads only. An occurrence counts as eligible only when
its first-party source supplies a stable URL, title, start time and timezone, physical venue
location, public-access signal, and enough information to determine expiry. Record every
drop with one bounded reason:

`access_blocked`, `terms_unclear`, `robots_or_policy_rejected`, `lead_not_local`,
`unsupported_format`, `missing_start`, `missing_timezone`, `missing_physical_location`,
`private_or_invite_only`, `online_only`, `cancelled`, `duplicate`, `expired`,
`incomplete_snapshot`, `budget_limited`, or `fetch_failed`.

The target gate is at least five eligible distinct occurrences across three venues or
organizers in cold San Francisco and two across two venues or organizers in the held-out
town. The result must include source-relative yield, reference-set recall, eligible
precision, unique organizers, duplicate/conflict count, freshness lag, latency, CPU/memory,
bytes, upstream charges, and operator minutes. A zero result reports zero yield and its
failure reasons; it does not manufacture a cost-per-event.

## Source admission contract

Source records use these states:

`discovered -> policy_pending -> eligible -> active`, with terminal or operational states
`rejected`, `paused`, and `failed`.

Automatic activation requires an approved access/retention policy, a supported parser, a
verified geographic footprint, a freshness basis, and one complete valid collection. A public
URL or `robots.txt` permission alone is insufficient. Cross-host links become new leads and
must pass the same policy. Operator review applies to a new source policy, not to every town
or user request. A source can serve multiple nearby demand regions.

Persist only normalized facts permitted by the source policy: stable source/occurrence IDs,
title, start/end/timezone, physical venue coordinates or a confident owned-venue match,
activity/format facets, access or booking link, canonical URL, source provenance,
`fetched_at`, `verified_at`, `expires_at`, parser version, and bounded error state. Do not
persist provider prose, images, ratings, social engagement, snippets, or unlicensed provider
fields. City centroids, organizer headquarters, online-only events, and inferred cafe
character are not event locations.

## Connector and runtime limits

The implementation must keep `GET /api/local-events` free of outbound acquisition. A request
may upsert one coarse geographic demand record; a background worker consumes it. Demand is
coalesced by geographic bucket and canonical 14-day window, while refresh is coalesced by
source and window.

Starting safety bounds are:

- one worker and one active fetch per host;
- two new-region discovery jobs per minute and at most 100 queued regions;
- 2,000 upstream requests/day globally, with a reserved share for active near-term sources;
- at most 20 hosts, 40 pages, 10 MiB, and five minutes per discovery job;
- conditional requests and source-specific backoff; honor `Retry-After`;
- no paid request unless separately approved with a hard dollar cap;
- no provider request while constructing a swipe deck;
- reject private, local, metadata, redirect, oversized, and unsafe outbound targets.

Queue rows require a unique work key, state, due time, attempts, lease expiry, fencing token,
and bounded error class. Claim in a short Postgres transaction, fetch outside the transaction,
and commit only while holding the lease/token. Expired leases are recoverable after restart.

Expose separate data and acquisition state: `fresh|empty|expired` and
`idle|queued|running|backoff|policy_pending|budget_limited|failed`, with snapshot version,
checked time, next check time, and reason code. A failed or partial snapshot cannot delete the
last good snapshot. A publication timestamp cannot be renewed merely because an unchanged
HTTP 304 was received. Hide events at the earliest of end time, verification plus the approved
maximum age, or a shorter source retention limit.

## Implementation handoff and stop conditions

The implementation extends ADTR-25's registry, bounded transport, adapters, atomic replacement,
locking, and duplicate-collapse code. It adds arbitrary-location demand mapping, bounded
bootstrap lead discovery, policy-gated source admission, durable refresh scheduling, and
coverage/acquisition state on the existing local-events response. The worker owns all outbound
connector work; Home and the swipe deck remain index reads. It may not select another vendor,
enable paid access, weaken expiry, add a manual city allowlist, or change UI/navigation.

The implementation must demonstrate the full path: a normal launch selection for a cold region
creates one bounded demand job; the worker discovers permitted first-party leads (using the
selected connector only as a lead source), admits supported sources, fetches and normalizes
eligible occurrences, and atomically publishes them to the existing index. Repeated requests
coalesce, a restart recovers a lease, stale or failed work never masquerades as fresh, and a
location change cannot display the previous region's events. The API must return explicit
coverage/acquisition states while this work is pending.

Stop and return a review disposition if the connector cannot establish access/retention
rights, if the parser cannot prove locality or time, if the reference gate misses, or if the
budget is exceeded. Valid dispositions are `access_blocked`, `leads_missed`,
`parsing_unsupported`, `facts_insufficient`, `freshness_inadequate`, and `budget_insufficient`.
After one comparison and one bounded repair run, unresolved gaps block ADTR-26; they are not
silently moved into another ticket or product phase.

## Official sources

- [Ticketmaster Discovery API](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/)
- [Ticketmaster terms of use](https://developer.ticketmaster.com/support/terms-of-use/)
- [Eventbrite API platform](https://www.eventbrite.com/platform/api-keys/)
- [Meetup GraphQL guide](https://www.meetup.com/graphql/guide/)
- [Meetup API access changes](https://help.meetup.com/hc/en-us/articles/41453576628749)
- [Google Event structured data](https://developers.google.com/search/docs/appearance/structured-data/event)
- [Substack RSS documentation](https://support.substack.com/hc/en-us/articles/360038239391-Is-there-an-RSS-feed-for-my-publication)
- [PostgreSQL queue locking](https://www.postgresql.org/docs/17/sql-select.html)
- [HTTP 304 semantics, RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.4.5)
