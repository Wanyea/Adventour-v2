# Decision Brief: Place Data Sourcing, Cost, and Cold Start

**Date:** 2026-08-17
**Status:** Proposed — needs your approval before Scope A implementation
**Scope:** Where candidate places come from, what we may legally keep, what it costs, and how authenticity works on day one with zero users.

This brief exists to answer the question you said you could never solve: *how do you build a place-based product without either violating provider terms or going bankrupt per user?*

The short answer: **you can build your own place database. Just not from Google.**

---

## 1. The decision

Adopt a **three-tier provider stack**, where each tier has a different legal status and a different cost:

| Tier | Source | License | Cost | Role |
|---|---|---|---|---|
| **Base** | Overture Maps Places + FSQ OS Places | CDLA-Permissive 2.0 / Apache 2.0 | **$0** | Our own durable, storable POI database. Powers all candidate retrieval and ranking. |
| **Live** | Google Places API (New) | Fetch-and-display only | ~$0.005–$0.017 per high-intent action | Hours, phone, photos, live status — fetched only after a user accepts a place. |
| **Owned** | Adventour user events, ratings, gem votes | Ours outright | $0 | The moat. Compounds over time and progressively displaces Tier 2. |

The structural rule that follows: **browsing is free, conversion costs money.** No paid API call is ever made to populate a swipe deck.

---

## 2. Why Google can never be the database (verified)

This is settled, not a judgment call:

- Place IDs are **exempt from caching restrictions** and may be stored indefinitely.
- Latitude/longitude may be cached for **up to 30 consecutive calendar days**, then must be deleted.
- Everything else — names, ratings, reviews, hours, photos, addresses — falls under: *"You must not pre-fetch, cache, or store Places API content beyond the allowed exceptions."*

So the v2 instinct of treating provider data as Adventour's DB is not merely risky, it's structurally impossible. Any ranking signal we want to own must be computed from data we're allowed to keep.

**That constraint is the whole reason Tier 1 matters.**

## 3. Why the open data tier actually works now

This is the part that changed since v1, and it's why the business is viable today when it wasn't four years ago:

**Overture Maps Places** — ~75 million POIs globally (July 2026), CDLA-Permissive 2.0. Freely storable, modifiable, and **monetizable**, with no share-alike obligation. Contains no OpenStreetMap data, so it carries none of OSM's viral licensing. Critically, each record includes:
- a ~2,300-entry category taxonomy (plus a simplified `basic_category`)
- **brand information**
- **a confidence score** (0–1 likelihood the place exists)
- websites, socials, phone, addresses

**FSQ OS Places** — 100M+ POIs, 22 core attributes, Apache 2.0, refreshed monthly. Note: as of October 2025 access moved off the public S3 bucket to a Places Portal / Iceberg catalog (also on Snowflake and HuggingFace), so ingestion needs a registered token.

Between them we get a free, legally clean, commercially usable base layer that we can index, score, and query as much as we want at zero marginal cost.

---

## 4. The cost model

Google Places pricing, 0–100k monthly volume tier, after the March 2025 change that replaced the $200 credit with per-SKU free calls (**Essentials 10,000/mo, Pro 5,000/mo, Enterprise 1,000/mo** — all free):

| SKU | Price / 1,000 |
|---|---|
| Text Search / Nearby Search **Pro** | $32.00 |
| Place Details **Pro** | $17.00 |
| Place Details **Essentials** | $5.00 |
| Autocomplete Essentials | $2.83 |
| Place Details / Text Search **IDs Only** | Free, unlimited |

### Path A — provider-driven decks (what v1 did, and where codex was heading)

One Adventour session = destination autocomplete + ~3 deck refreshes via Nearby Search Pro + details on accept:

```
3 × Nearby Search Pro    3 × $0.032  = $0.096
1 × Place Details Pro    1 × $0.017  = $0.017
~5 × Autocomplete        5 × $0.0028 = $0.014
                         per session ≈ $0.13
```

At 4 sessions/user/month → **$0.52 per user per month.**
At 10,000 MAU → **~$5,200/month**, and the 5,000 free Pro calls are exhausted at roughly **400 active users**.

That is the trap. Worse, cost scales with *browsing*, so your least-engaged and most-indecisive users cost the most, and a user who swipes and never commits costs you money for nothing.

### Path B — Overture-first (recommended)

Candidate retrieval, ranking, and the entire swipe deck run against our own PostGIS index. Google is touched **once**, after the user accepts a place and needs real hours and a photo:

```
0 × Nearby/Text Search               = $0.000
1 × Place Details (Essentials→Pro)   = $0.005–$0.017
                         per session ≈ $0.017
```

At 4 sessions/user/month → **~$0.068 per user per month.**
At 10,000 MAU → **~$680/month**, before applying free-tier calls.

**~7–8x cheaper, and the shape of the curve is better than the magnitude.** Cost now scales with accepts rather than impressions — meaning spend tracks delivered value, an unbounded browsing session is free, and the unit economics improve as the recommender gets better, because fewer swipes are needed per accept. Under Path A, a better recommender saves you nothing.

---

## 5. Cold start: authenticity with zero users

You do not have proprietary data yet, and the authenticity mission can't wait for it. Every signal below is computable **offline, from the Tier 1 open data, before a single user signs up**:

**Chain detection by name-frequency clustering.** Normalize place names and count occurrences across the national dataset. `Starbucks` appears thousands of times → `chain_probability ≈ 1.0`. `Ana's Taqueria` appears once → `≈ 0.0`. This is one batch job over a Parquet file. It's free, it needs no API, it's more robust than Overture's partial `brand` coverage, and — unlike Foursquare's `exclude_all_chains` flag that v1 leaned on — **it's ours**.

**Local distinctiveness via category rarity.** Score a category against its own H3 cell rather than globally. A taqueria in Mexico City is unremarkable; a Oaxacan mole specialist in Pittsburgh is a find. This is the signal that separates Adventour from every "top rated near me" product, and it's pure computation over data we own.

**Tourist-trap density.** POI density plus concentration of souvenir/tour-operator categories identifies tourist clusters directly from the open dataset. Penalize accordingly, unless the category justifies it.

**Web-presence shape.** Overture ships `websites` and `socials`. Chains have corporate domains with store locators; independents have an Instagram or nothing. A weak signal alone, useful in combination.

**Existence confidence.** Overture's confidence score filters out the dead and dubious before they ever reach a user — a quality floor that costs nothing.

None of this requires Google, a paid call, or a single user. It is a working authenticity engine on day one, and it is the direct answer to the Wanderlog gap you identified: their recommendations respect neither you nor the place.

The owned-data layer (`local_gem_vote`, `would_take_friend`, arrival confirmations) then compounds on top, and progressively replaces these heuristics with real evidence.

---

## 6. What this means for Scope A

Scope A becomes an **ingestion and indexing** problem, not an API-integration problem:

1. Ingest Overture Places (+ FSQ OS Places) for **one metro area only** — enough to prove the pipeline without a continental download.
2. Land it in PostGIS with H3 indexing for cheap radius queries.
3. Compute the offline feature batch: `chain_probability`, category rarity, tourist density, confidence floor.
4. Expose candidate retrieval behind the provider abstraction that `recommender-data-design.md` already specifies.
5. Wire exactly one Google Place Details call, on accept, behind a hard per-user quota.

Note this **invalidates the existing schema assumption** in `recommender-data-design.md` §"Database Shape": `places` is described as a thin identity table because provider content couldn't be stored. With Tier 1, `places` becomes a genuinely rich owned table. That doc needs a revision pass, not a rewrite — the architecture holds, the storage boundary moves.

---

## 7. Confirmed decisions

- **Seed metros:** Orlando, FL and Palm Coast, FL — chosen for ground-truth ability (18 years and 7 years lived).
- **Database:** Postgres + PostGIS.
- **Priority:** spontaneous mode first; full-trip planning is a strategic target, not a deferred nice-to-have (see §9).

---

## 8. Amendment: opening hours (revises §1 and §4)

**The original Path B was wrong on one point.** It treated hours as a post-accept detail. They are not — they are a
hard filter at candidate time (don't recommend a closed place) and a scheduling constraint for itineraries
(don't put the early-closing stop last). This section corrects that.

### The constraint

Hours cannot be simultaneously free, storable, and accurate in the US. Verified:

- **Overture Places has no hours field.** The schema explicitly notes `operating_status` "is not an indication of
  opening hours or that the place is open/closed at the current time-of-day."
- **FSQ OS Places has no hours** — 26 columns, none of them schedule-related. Hours sit behind Places Pro/Premium.
- **OSM has `opening_hours`**, free and storable, but coverage is concentrated in Germany/UK/Netherlands and is
  frequently stale. Thin for Florida.
- **Google has hours but forbids storing them.** This is a licensing block, not a cost problem.

### The fix: hours are a seeded asset, not a per-request lookup

The economics only break if hours are fetched *per user request*. Fetch them *per place*, on a schedule, and the
cost becomes **O(places in metro), amortized across every user forever** instead of O(requests).

Four layers, degrading gracefully:

**Layer 0 — Category-daypart priors. Free, 100% coverage, low precision.**
Derived from the Overture category taxonomy we already own. Nightclubs aren't open at 9am; breakfast diners aren't
open at 10pm; museums usually close Mondays. A prior, not a fact — but it eliminates the embarrassing errors at
zero cost and covers every place including ones with no hours data at all.

**Layer 1 — Owned hours table, seeded per metro. Fixed cost, high value.**
For Orlando + Palm Coast only, in source preference order:
1. **OSM `opening_hours`** where present — free and storable with attribution.
2. **The business's own website.** Overture ships a `websites` field. Hours published on a business's own public
   site are not provider content. A one-time crawl plus small-model extraction across ~25k relevant POIs is a
   tens-of-dollars, run-once cost. **This is probably the highest-leverage move in the whole brief** and it exists
   only because Overture hands us the websites for free.
3. **Foursquare bulk data license** for residual gaps (Places Pro/Premium; enterprise pricing, not public).

Refresh quarterly. Fixed operating cost per metro, serving unlimited users.

**Layer 2 — Live confirmation at accept.** One Place Details call when the user commits, confirming open-now and
fetching photo/live status. Foursquare Pro is **$15.00 CPM** with **10,000 free Pro calls** on signup, versus
Google Place Details Pro at $17.00 — worth benchmarking both on quality for our categories.

**Layer 3 — User arrival feedback.** "Closed when I got there" corrects the owned table over time. No provider
sells this. It compounds into the moat.

### One ODbL caveat worth stating plainly

Overture deliberately contains no OpenStreetMap data specifically to avoid ODbL's share-alike obligations. Pulling
OSM in for hours reintroduces that consideration. Mitigation: keep OSM-derived hours in a **separate, attributed
table** rather than commingling it into `places`, so the share-alike surface stays bounded and auditable. Flagging
this as a real decision rather than burying it.

### Revised cost shape

Per-session variable cost stays at **~$0.017**. Added: a **fixed per-metro hours seed and quarterly refresh**.
The per-user economics in §4 hold, because a fixed cost divided by a growing user base trends to zero — which is
the opposite of Path A, where cost grows with every swipe.

**The §4 rule survives intact: no paid API call populates a swipe deck.** Hours come from our own table.

---

## 9. Full-trip planning: the real competitive wedge

Worth stating because it changes how Scope A should be built.

Wanderlog is mostly manual entry over generic city lists. The gap isn't organization — they do that fine — it's
that **nothing is generated and nothing respects you**. Hours-aware automatic sequencing with taste blending is
precisely what manual entry structurally cannot do.

Two consequences:

**The hours investment buys two features, not one.** Layer 1 is what makes spontaneous mode not embarrassing *and*
what makes itinerary generation possible at all. It is shared foundation, not a detour.

**The sequencing problem has a name and a known solution.** The tension you identified — a place closing before you
reach it if scheduled last, versus taking the shortest path — is exactly what makes this **TSP with Time Windows**
rather than plain TSP. And the full problem is really the **Orienteering Problem with Time Windows**: choose a
*subset* of high-scoring places and sequence them, subject to time windows and a total time budget.

The practical part: a day itinerary is 6–10 stops. At that size, exact dynamic programming (Held–Karp with
time-window feasibility, O(2ⁿ·n²)) runs in **milliseconds** — roughly 100k operations at n=10. No heuristics, no
OR-Tools, no approximation needed initially. We can solve day itineraries *optimally* while competitors let users
drag cards around by hand.

---

## 10. Noted, not scoped

**Ticket / reservation linking** (theme parks, flights, car rental, restaurant bookings). Not a priority now.
Cheap accommodation: give `adventour_stops` an `external_links` JSON field in the Scope A schema. Costs nothing
today, avoids a migration later.

**⚠️ The China trip should not be Adventour's first real-world test.** Concrete blockers:

- **Coordinate systems.** China mandates GCJ-02, which applies a deliberate non-linear offset to WGS-84 producing
  a **100–700m displacement**. Our GPS coordinates would plot wrong against Chinese maps. Reverse conversion
  GCJ-02 → WGS-84 is prohibited under Chinese law. Baidu adds a further BD-09 layer on top.
- **Providers.** Google Places is effectively unusable in mainland China; Amap (AutoNavi) and Baidu are the real
  providers and require separate integration.
- **Base data.** Overture/FSQ coverage in China is thin relative to the US.

Supporting China means a separate provider adapter plus a coordinate-transform layer — a real international scope,
not a config change. Recommend planning that trip by hand and testing Adventour in Orlando and Palm Coast, where
you can actually judge whether a recommendation is good.

---

## 10b. Closure verification (decided 2026-08-17)

Gate 6 measured **9.1% of the seed permanently closed**, invisible to every free signal — mean
Overture confidence 0.90, up to 0.99. Six of the twelve were places the reviewer said they *would
have recommended*. Closures do not add noise, they destroy the best recommendations.

**Decision: verify per place and persist, not per impression.**

Per-impression checking re-breaks the cost curve this whole design exists to protect:

| strategy | $/session | dead cards still shown |
|---|---:|---:|
| no check | $0.000 | 1.09 |
| check top 3 | $0.060 | 0.82 |
| check every card shown | $0.240 | 0.00 |

Verifying per *place* saturates instead, because cost scales with distinct places rather than
browsing. **$387.70 one-time for both current metros**; Palm Coast alone is $14.24 and fits inside
Google's free Enterprise tier of 1,000 calls/month.

Field-mask note: `businessStatus` is Pro tier ($0.017) but `currentOpeningHours` is Enterprise
($0.020). Since the call is being made anyway, **+$0.003 also returns live hours** — the thing
§8 established we cannot source any other way. Closure detection and the hours gap are one purchase.

**Storage boundary, approved by the project owner:** persist the `place_id` and our own
`suppressed_at` timestamp only. No `businessStatus` value, no reason string, no other returned
field. `place_id` is storable indefinitely under Google's terms; a list of ids we decline to show is
our own editorial record. Anything beyond that crosses back into caching provider content.

**Build regardless: user-reported closures.** A human identified all twelve without any API call,
and real users will too. "Closed when I got there" is unambiguously our data, no licensing question
attached, and it is exactly the signal no provider sells.

## 10c. National scale (measured 2026-08-17)

Counted directly from Overture rather than extrapolated. Reproduce with
`Server/data_pipeline/national_scale.py` (~76s scan).

| continental US | places |
|---|---:|
| all named POIs | 16,628,723 |
| in Adventour taxonomy buckets | 3,605,219 |
| **after Gate 6 category drops** | **2,527,473** |

**One afternoon of labeling in Palm Coast removed 1,077,746 places nationally — 30% of the raw
taxonomy match.** Dropping `historic_site` alone accounts for 195,622 of them. Twenty labeled
records generalised to six figures of junk. That is the strongest possible argument for repeating
the ground-truth exercise in each new market.

### Blanket verification does not scale; lazy verification does

| approach | cost |
|---|---:|
| verify entire US index once | $50,549 |
| re-verify entire US quarterly | **$202,198/yr** — not viable |
| top-10 metros, quarterly | $53,377/yr |
| Palm Coast, quarterly | $53/yr |

The quarterly-everything figure is a naive upper bound and nobody should pay it, because **most of
the 2.5M places will never be shown to anyone**. The suppression-list decision (§10b) is what makes
the alternative work:

- **Verify lazily, on first surface.** A place is checked the first time it would enter a deck.
- **Persist the result forever** — permitted, per §10b, as `place_id` + `suppressed_at`.
- **Re-verify only active places**, not the index. A place nobody has seen in a year needs no refresh.
- **User closure reports trigger an immediate re-check**, free and higher-signal than any schedule.

Cost then scales with *distinct places ever surfaced*, which is a small fraction of any metro index
and is bounded by it. Entering a new market costs nothing up front — the first ~1,000 places are
inside Google's free Enterprise tier, which covers a Palm Coast outright.

This is the same shape as the §4 decision: **spend follows delivered value, not inventory.**

## 11. Open question

**Which hours source do we try first for the Orlando/Palm Coast seed?** I'd start with website extraction (Layer 1.2)
because it's cheap, storable outright, and has no share-alike entanglement — then measure coverage and decide
whether OSM or a Foursquare license is needed to fill gaps.

---

## Sources

- [Google Places API policies](https://developers.google.com/maps/documentation/places/web-service/policies)
- [Google Maps Platform Service Specific Terms](https://cloud.google.com/maps-platform/terms/maps-service-terms)
- [Google Maps Platform March 2025 pricing changes](https://developers.google.com/maps/billing-and-pricing/march-2025)
- [Google Maps Platform pricing list](https://developers.google.com/maps/billing-and-pricing/pricing)
- [Overture Maps Places guide](https://docs.overturemaps.org/guides/places/)
- [Overture attribution and licensing](https://docs.overturemaps.org/attribution/)
- [FSQ OS Places](https://opensource.foursquare.com/os-places/)
- [Access FSQ OS Places](https://docs.foursquare.com/data-products/docs/access-fsq-os-places)
