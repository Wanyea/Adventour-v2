# Anywhere local events: acquisition and freshness architecture

## Decision this research supports

Adventour's location plumbing can accept any city or town, but its event index
currently covers only regions with an approved source adapter. The pilot request
changes the product expectation: a friend using GPS in an unseeded city should
receive useful local events when a permitted source can provide them. This is a
Phase 2 follow-up under ADTR-19. It is not a reason to make an unbounded web
crawler or to call a paid event API every time Home opens.

The recommended architecture is a regional source registry plus a durable,
source-normalized event index. A request first reads that index. Missing or stale
coverage schedules bounded work for the region; it does not synchronously crawl
the web. A later request receives the refreshed snapshot. This is the same basic
separation used by event products and search systems: ingestion and freshness
are background concerns, while serving is a fast local query.

## What the external evidence says

There is no single inexpensive, complete source for the authentic local long
tail. Ticketmaster's Discovery API is broad and location/date searchable, but its
documented content is sourced from Ticketmaster, Universe, FrontGate and resale,
with a default quota of 5,000 calls per day and five requests per second.^1 That
makes it a useful optional breadth source for ticketed events, not a substitute
for neighborhood markets, run clubs or independent cafe events.

Eventbrite's current developer reference still documents the former public event
search shape, but explicitly says that endpoint was shut down in December 2019.^2
Its current platform page advertises access to public events, yet that access is
an application/partner path and must be verified before treating it as a
production source.^3 Meetup's current GraphQL API requires an access token; its
documentation says new OAuth consumers require an active Meetup Pro subscription,
and its API applies a 500-point-per-60-second limit.^4 These services can be
evaluated as licensed adapters, but none should be assumed to provide free,
unrestricted regional discovery.

First-party pages are more promising for Adventour's authenticity goal. Many
organizers publish an `Event` JSON-LD object with a unique event URL, start/end
time and physical location. Google's documentation treats those fields as the
standard shape for an event page and warns against representing business hours,
discounts, or non-events as events.^5 That gives us a common parser target while
leaving source permission, robots rules, rate limits and retention to be checked
per host.

Newsletters can be discovery leads rather than an automatic truth source.
Substack officially exposes a publication RSS feed at `/<publication>/feed`.^6
An RSS item can identify a dated post, but it does not prove that an event is
still scheduled, public, correctly located or permitted for commercial storage.
The item should therefore lead to the organizer's canonical event page, which
must be independently verified before publication.

## Proposed source tiers

1. **Public structured feeds.** Municipal, parks, library, university and venue
   RSS, ICS, JSON, open-data and documented feeds. These are the default because
   they are cheap to refresh and expose dates and locations directly.
2. **Organizer-owned pages.** Pages linked from our indexed venues or from a
   permitted newsletter/social lead. Parse JSON-LD first, then a narrowly scoped
   visible listing parser. Follow same-host event/calendar links only, with a
   host budget and robots/terms check.
3. **Licensed APIs.** Ticketmaster, Meetup, Eventbrite partner access or another
   provider only after terms, quota, cost and field-retention rights are recorded.
   Provider results enter the same normalization and expiry pipeline; they are
   not queried directly by the mobile client.
4. **Social and newsletters.** Instagram, Facebook, TikTok, Partiful and
   Substack are lead sources unless an authorized API/feed or explicit publisher
   permission supports collection. A public URL alone is not permission for bulk
   scraping. Private, invite-only or location-hidden events are excluded.

## System design

The registry should contain a canonical region, source/host, adapter, access
basis, permitted fields, timezone, refresh interval, maximum age, request/page/
byte budgets, parser version, and status. A coverage manifest should separately
record each region's last successful snapshot, next due time, freshness state,
yield, failures, and whether the region has no configured source. This makes an
empty San Francisco result distinguishable from a failed fetch.

Normalized occurrences should retain only permitted factual fields: stable source
and occurrence IDs, title, start/end/timezone, venue or event coordinates,
category, public-access/booking note, canonical URL, source links, verification
time and expiry. Store each recurrence as its own occurrence. Deduplicate by
source identity first, then by normalized title/time/location across sources.
Do not store scraped prose, images, social engagement, or provider content whose
terms do not permit retention.

The serving path is:

`location → canonical region/H3 cells → fresh local query → ranked events`

If the snapshot is missing or stale, the API returns the current local results
and coverage state immediately, then enqueues one idempotent refresh. A single
flight key `(region, source, time-window)` and a Postgres advisory lock prevent
multiple friends from triggering duplicate work. An unknown region is queued for
source discovery only if the discovery budget permits it; otherwise the API
returns an honest empty result with a coverage explanation. It never falls back
to Orlando or another region.

The worker uses conditional requests where a source supports ETag or
Last-Modified, exponential backoff after failures, a circuit breaker for a sick
host, and a bounded fetch budget. Near-term events refresh more often; distant
events and low-demand regions refresh less often. A successful full snapshot may
remove absent occurrences, while a failed or partial fetch cannot renew
freshness. Query time suppresses ended, cancelled, or over-age occurrences even
if the scheduler is late.

## Cost and quality controls

No paid API call is allowed on swipe-deck or Home request paths. Third-party calls
are pooled by region/source, cached only within the permitted retention rules,
and metered by source, request reason and outcome. A provider is admitted only if
its incremental verified yield and freshness justify its quota or price compared
with first-party feeds. Use a small fixed evaluation set of cities, categories
and dates before expanding coverage.

The ticket should measure source-relative yield, duplicate rate, location/time
accuracy, freshness lag, failure rate, p50/p95 refresh latency, cost per verified
occurrence, and the social/newsletter-only gap. Report the denominator honestly:
coverage of configured sources is not coverage of every event in a city.

## Recommended implementation sequence

First build the coverage manifest, source status, queue/single-flight behavior and
an adapter contract around the existing UCF and NYC implementations. Then add a
generic first-party structured-page adapter and test it against a small set of
owner-approved San Francisco sources. Add one licensed provider only if the
bounded comparison demonstrates meaningful incremental coverage. Finally expose
the coverage state and refresh behavior through the existing local-events
section, with no new screen and no event-provider call from the app.

The first acceptance experiment should include Orlando, New York, San Francisco,
and one additional city selected by a pilot participant. It should demonstrate a
fresh result, an honest empty/no-source result, a failed refresh preserving the
last good snapshot, cancellation/expiry removal, deduplication, and concurrent
requests producing one upstream fetch.

## Astra review amendments (2026-09-09)

The architecture above is approved as the direction, but it is not ready to
hand to an implementation agent until the following contracts are added. The
product requirement is location-independent acquisition: a valid launch point
must enter the same discovery process without an operator adding that city to a
roster. This does not promise that every town has public events or that every
source is legally reusable; those limits must be measured and exposed.

### Cold-region bootstrap and source admission

Before implementation, freeze one concrete bootstrap connector and its access
policy. The lead sequence is: active sources intersecting the radius; owned
venue/organizer links; then a permitted regional catalog or search connector for
municipal, library, university, venue and community calendars. The decision
packet must name the connector, access requirements, price and limits, query
templates, geographic inputs, link-retention rights and output contract. Search
results are leads, never canonical event facts. A cross-host link is a new lead
that requires its own policy.

Source records move through `discovered`, `policy_pending`, `eligible` and
`active`, with explicit `rejected`, `paused` and `failed` states. Automatic
activation requires an already approved collection/retention policy, a
supported parser, a verified geographic footprint and one complete valid
collection. Ambiguous rights, locality or parsing remain quarantined for
operator review. Review applies to a new source or policy, not to every user or
town; measure how often a region still needs manual intervention. Do not add a
US-only runtime allowlist.

The first design ticket must run one bounded dry-run comparing low-cost
first-party/catalog discovery with at most one viable licensed option. It must
use a cold San Francisco region and a held-out small town with independently
verified public events, including a no-owned-venues case. It must report each
stage of the lead-to-eligible funnel and stop after one comparison and one
bounded repair run. Unresolved access or yield is a named blocker, not another
open-ended phase.

### Durable demand and freshness contract

Keep `/api/local-events` free of outbound acquisition. It may upsert one cheap
demand record keyed by a coarse geographic bucket and the existing 14-day
horizon; the worker consumes that demand. Jobs need a unique work key, state,
due time, attempts, lease expiry, fencing token and bounded error class. Claim
in a short Postgres transaction, fetch outside the transaction, and commit only
when the lease/token still owns the job. Expired leases must recover after a
restart. Coalesce neighboring demand onto one source-global canonical window,
rather than fetching for each slightly different GPS request.

Return events with separate `data_state` (`fresh`, `empty`, `expired`) and
`acquisition_state` (`idle`, `queued`, `running`, `backoff`, `policy_pending`,
`budget_limited`, `failed`), plus snapshot version, checked time, next check
time and bounded reason codes. A valid conditional 304 may revalidate a live
representation when the source policy allows it, but it cannot advance a
publisher's publication clock. Only a complete snapshot may delete absent
occurrences; a partial or parse-collapsed response cannot clear the prior
snapshot. Cancellation evidence must prevent an old duplicate source from
reviving an occurrence.

Proposed starting safety bounds, to validate in the design ticket: one worker,
one active fetch per host, two new-region discovery jobs per minute, 100 queued
regions, 2,000 upstream requests per day, at most 20 hosts and 40 pages per
discovery job, 10 MiB downloaded and five minutes of work per job. Reserve
capacity for active near-term sources. Paid calls remain disabled until a
specific connector and hard dollar cap are approved; moving a call to a worker
does not make it free or permit it on the swipe-deck/Home path.

### Event facts and pilot acceptance

Preserve factual activity, setting, format, access/booking and evidence
provenance where permitted. Do not infer a cafe menu or community character
from a title such as “coffeehouse”; retain unknown facets and an exclusion
reason for missing time, physical location or public access. Recurrence must
honor timezone, exceptions and cancellations with bounded expansion.

The implementation must prove acquisition, not only empty-state correctness:
normal launch selection in cold San Francisco must automatically produce at
least five eligible distinct occurrences across three venues/organizers, and a
held-out town must produce at least two across two venues/organizers, within the
existing radius and 14-day window. The town is selected before knowing whether
our collector succeeds. Inspect every displayed event against its official
source and report precision, source-relative and reference-set recall, unique
organizers, freshness, latency, compute, bytes, charges and operator minutes.
If the gate fails, classify the failure as access blocked, leads missed,
unsupported parsing, insufficient facts, inadequate freshness or insufficient
budget. Queue, schema and empty-result tests alone do not pass the ticket.

### Bounded work tickets

Keep this as one ADTR-19 follow-up with five reviewable tickets, not five new
product phases: (1) connector/access decision and frozen benchmark, (2) automatic
source discovery and admission, (3) durable demand scheduling and freshness,
(4) verified normalization and reusable extraction, and (5) Home acquisition
feedback and iPhone pilot acceptance. Tickets 2–4 depend on ticket 1; ticket 5
depends on all three. Reuse ADTR-25's registry, transport, locking, atomic
replacement, dispatch and duplicate-collapse work. The lower-cost implementer
may not select a vendor, weaken expiry, expand source rights or invent coverage
targets.

## Sources

1. Ticketmaster, [Discovery API](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/), coverage, sources and rate limits.
2. Eventbrite, [API v3 reference](https://www.eventbrite.com/platform/new/api), public event search shutdown notice.
3. Eventbrite, [Platform: bring events to your application](https://www.eventbrite.com/platform/api-keys/), current partner/application positioning.
4. Meetup, [GraphQL API guide](https://www.meetup.com/graphql/guide/) and [API access requirements](https://help.meetup.com/hc/en-us/articles/41453576628749).
5. Google Search Central, [Event structured data](https://developers.google.com/search/docs/appearance/structured-data/event).
6. Substack, [RSS feed for a publication](https://support.substack.com/hc/en-us/articles/360038239391-Is-there-an-RSS-feed-for-my-publication).
