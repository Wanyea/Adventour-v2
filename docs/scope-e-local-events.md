# Scope E (proposed) — Local Events & Third Spaces

**Status:** researched 2026-08-18, not scoped. Requires approval before any implementation.

## The idea

Surface local, recurring, community-run happenings — art markets, run clubs, open mics, first-Friday
walks, pickup sport — alongside places. Two audiences, one mechanism: **locals get a way to find
community in third spaces; visitors get something genuinely of the place rather than a ticketed
attraction.**

This is mission-aligned rather than a bolt-on. Adventour's argument is that authenticity is where
locals actually go; an event is that claim in its strongest form, because it is time-bound and
attended by people who live there.

The third-place framing is real and current: the concept is Ray Oldenburg's (the social space that is
neither home nor work), and there is a documented post-pandemic revival of it among younger people
choosing in-person community over feeds. The gap is **discovery**, not desire.

## The provider landscape, and why it rhymes with the places problem

| source | covers | status |
|---|---|---|
| **Ticketmaster Discovery API** | arena concerts, pro sport, big venues | **free** — 5,000 calls/day, 5 req/s |
| **Eventbrite** | ticketed public events | **public event search was removed in Dec 2019**; distribution-partner programme only |
| **Meetup** | recurring interest groups | **paid**, Pro tier billed per group per month |
| **PredictHQ** | ~20M events, 30k cities | paid, aimed at demand forecasting |

**The pattern is the one we already learned twice.** Ticketmaster gives away the arena show — the
"chain" of events. The farmers market, the run club and the open mic are in no API at any price, for
the same structural reason independents had no hours: nobody monetises the long tail, so nobody
collects it.

Which means the same conclusion applies. **If Adventour solves the local event layer, no vendor can
hand a competitor the same thing.** It is defensible for exactly the reason it is hard.

## The asset we already have

14,484 indexed entities, most with a `websites` value, and a crawler built in Gate 2 that already
follows one internal link looking for structured data.

**Venues host events, and they publish them on their own sites and socials.** So the first event
source is not a provider at all — it is the places we already own, re-crawled for
`schema.org/Event` markup instead of `openingHoursSpecification`. Gate 2 measured ~21% of sites
carrying JSON-LD; event markup is likely rarer, and that must be measured, not assumed.

Second free tier, specific to the seed metros: municipal open-data portals, library and parks
calendars, and university event feeds. Note **32816 is UCF** — a campus feed covering one of the
labelled ZIPs, and exactly the demographic the third-space idea targets.

## What must be answered before building

1. **Yield.** What fraction of our indexed venues publish machine-readable events? Same method as
   Gate 2 — a spike over a sample, not an assumption. If it is under ~10% this needs a different plan.
2. **Licensing.** The same discipline as places: what may be stored? Ticketmaster's terms need
   reading before a single event row is persisted. An event is mostly facts (what, where, when),
   but the description and images are not.
3. **Freshness.** Events are worse than hours — a stale event is not merely unhelpful, it sends
   someone to a parking lot. Anything shown must carry a verified-at timestamp, and expiry has to be
   automatic rather than best-effort.
4. **Does it belong in the deck at all?** A swipe deck answers "where should I go now." An event
   answers "what is happening Saturday." Those may be different surfaces. **Question 9 in the
   Orlando labelling tool asks this directly** — an honest "that is a different app" is a valid and
   valuable answer.

## Where it sits

**After Scope B and C, not before.** The ranking problem is unsolved (490 places share one score)
and there is no evaluation harness. Adding a second content type before either is fixed would mean
two unranked, unmeasured surfaces instead of one.

The cheap part starts now regardless: the Orlando labelling tool asks where locals actually hear
about events, which recurring events matter, and which indexed venues host them. That is free
research attached to work already happening, and it is the input any real scoping would need.
