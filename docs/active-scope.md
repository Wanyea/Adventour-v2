# Active Scope

**Current: Scope A — Candidate sourcing & cost control**
**Status:** complete. All gates passed and verified on a device 2026-08-18.
**Updated:** 2026-08-17

## In scope

1. Ingest Overture Places (+ FSQ OS Places) for **Orlando, FL and Palm Coast, FL only**.
2. Postgres with H3 indexing for radius queries. **PostGIS was not used** — see CLAUDE.md.
3. Offline feature batch: `chain_probability` (name-frequency clustering), category rarity per H3 cell,
   tourist-cluster density, Overture confidence floor.
4. Opening-hours seed — Layers 0 and 1 per `sourcing-cost-decision-brief.md` §8.
   Start with website extraction; measure coverage before adding OSM or a paid source.
5. Candidate retrieval behind the provider abstraction from `recommender-data-design.md`.
6. Exactly one Google/Foursquare Place Details call, on accept, behind a hard per-user quota.
7. Schema revision to `recommender-data-design.md` §"Database Shape" — `places` becomes a rich owned table.
   Include `external_links` on `adventour_stops` (see brief §10).

## Explicitly out of scope

- **All UI changes.** The freeze in `CLAUDE.md` applies.
- Ranking weights and score tuning — that is Scope B.
- Group/friend preference blending — Scope D.
- Itinerary sequencing (TSPTW/OPTW) — later scope; Scope A only ensures hours data exists to make it possible.
- Ticket/reservation integrations — noted, not built.
- China / international provider support — see brief §10.

## Gate 1 result — website coverage measured 2026-08-17

**Verdict: the hours plan survives. Proceed with website extraction.**

Overture release `2026-07-22.0`, pulled via DuckDB from S3 for both metro bboxes
(112,682 raw places) plus a Florida-wide name-frequency reference (1,138,273 names).
Reproduce with `Server/data_pipeline/pull_overture.py` then `measure_coverage.py`.

**19,385** Adventour-relevant destinations, after excluding worship, gyms, fitness studios,
pools and cemeteries — which were ~4,400 of the raw taxonomy match and are not places anyone
takes an Adventour to.

| class | places | website | socials |
|---|---:|---:|---:|
| chain | 3,438 | 96.5% | 69.3% |
| regional | 1,447 | 86.8% | 67.2% |
| **independent** | **14,500** | **73.6%** | 70.6% |

The feared inverse correlation is real but **not fatal: a 23-point gap, not a cliff.**
Crawl target is **11,922** independent + regional websites.

Three corrections that came out of the measurement:

1. **Report website coverage, not "website or socials."** The combined figure was 93.5%, which
   flattered the plan. Overture's largest contributor is Meta, so social-derived records carry a
   social link by construction — the number partly measures provenance, not reachability. Facebook
   pages are also far harder to extract from and their terms are unfriendly. Website-only is the
   number a crawl plan can stand on.
2. **Strip location suffixes before chain matching.** `Planet Fitness - Orlando (Belle Isle), FL`
   and `Subway @ Orlando Science Center` were scoring as independents. Only 0.6% of records, but
   free to fix and now fixed.
3. **`sports_and_recreation` independents are the weak spot at 61.7%** — mostly public parks, which
   genuinely have no website. Convenient: parks also have the most predictable hours (dawn–dusk),
   so Layer 0 category priors cover exactly where Layer 1 is weakest.

Revised extraction cost: ~11.9k pages, of which perhaps 40% need model extraction after JSON-LD
parsing — on the order of **$10–15, once**. Below the brief's estimate.

**Still open:** add `sources` to the pull and confirm whether social coverage is a Meta-provenance
artifact. Does not gate anything; relevant to which fields we trust in the seed.

## Gate 2 result — extraction spike, 2026-08-17

**Verdict: website extraction underdelivers. It is a contributor, not the primary hours source.**
Reproduce with `Server/data_pipeline/extraction_spike.py --limit 80 --metro both`.

n=80 independent places sampled across both metros, homepage fetched once each.

| outcome | n | % of fetched |
|---|---:|---:|
| structured JSON-LD hours (free parse) | 12 | 21.1% |
| hours in page text (needs a model) | 6 | 10.5% |
| fetched, but no hours in the HTML | 28 | 49.1% |
| JS-rendered — static fetch sees nothing | 11 | 19.3% |

Fetch success was 57/80 (71.3%); the rest were dead links, 403s, timeouts and SSL failures,
which is itself a finding — a slice of Overture's `websites` values are stale.

**Net yield: ~22.5% of sampled sites gave hours.** Against 73.6% website coverage, that is
**roughly 17% of independents** — far below what the brief assumed when it called website
extraction "the highest-leverage move."

### The first run was measuring my crawler, not the web

Two bugs, both fixed, recorded so the numbers above are trusted and the earlier ones are not:

1. **Fake 24% robots-disallowed rate.** `urllib.robotparser.read()` fetches with urllib's default
   User-Agent, which CDNs commonly 403 — and the parser treats 403 as deny-all. Refetching
   robots.txt with `requests` and our own UA dropped the disallowed rate to **1.2%**.
2. **Zero JSON-LD in the first run** was a sampling artifact compounded by not distinguishing
   JS-rendered shells from genuinely hours-free pages. With the fix, JSON-LD hours are 21.1%.

### Two known, cheap ways to raise the yield

Neither is built yet; both address the largest buckets directly.

- **Follow one internal link.** The spike fetched *homepages only*. Restaurants routinely put hours
  on `/hours`, `/contact` or `/about`. That 49.1% "no hours in HTML" bucket is the single biggest
  pool and is likely to be substantially recoverable for one extra request per site.
- **Headless rendering** for the 19.3% JS shells. Recovers real coverage but costs seconds and
  memory per page instead of milliseconds — a genuine infrastructure step, not a config change.

### What this changes

The four-layer model in `sourcing-cost-decision-brief.md` sec.8 still stands, but the weights move:

- **Layer 0 (category priors) carries more load** than assumed. It is no longer a fallback.
- **Layer 1 (websites) is one input among several**, not the backbone.
- **OSM `opening_hours` coverage for Flagler/Orange County should now actually be measured** rather
  than assumed thin — it was deprioritized on the strength of the website plan.
- **A paid source becomes more likely.** Foursquare Places Pro should be priced properly for a
  bounded per-metro hours refresh, not left as a gap-filler.

## Gate 3a — OSM opening_hours coverage, 2026-08-17

**Verdict: OSM is not a viable hours source for Adventour. Rule it out.**
Reproduce with `Server/data_pipeline/osm_hours_coverage.py` (Overpass responses are cached).

Overpass returned 10,547 elements across both metro bboxes; 4,753 named POIs in Adventour-relevant
categories. Of those, **28.5% carry an `opening_hours` tag** — respectable in isolation, and roughly
in line with the "strong in Germany/UK/NL, thinner in the US" expectation.

But the number that matters is how much lands on *our* records:

| | seed places | with OSM hours | covered |
|---|---:|---:|---:|
| chain | 3,424 | 689 | **20.1%** |
| regional | 1,417 | 42 | 3.0% |
| **independent** | **14,544** | **209** | **1.4%** |

**OSM covers chains 14x better than independents.** It is strongest exactly where Adventour needs it
least. The recoverable sample was Dunkin', LongHorn Steakhouse, Five Guys — the places we actively
deprioritize. Net contribution to the real problem: 209 places out of 14,544.

This also disposes of the ODbL question from the brief. There is no share-alike tradeoff to weigh,
because there is nothing worth taking.

Caveat on method: matching is exact normalized name within ~150m, which is strict. OSM holds only
4,753 relevant POIs against our 19,385, so the ceiling on any matching strategy is ~24%; we achieved
11.7% overall. Fuzzier matching would raise the match rate somewhat, but cannot change the shape —
the chain skew is in OSM's tagging behaviour, not in our join.

## Gate 3b — subpage following, 2026-08-17

**Verdict: real but small. It does not change the conclusion.**
Reproduce with `extraction_spike.py --limit 80 --metro both --follow` (deterministic sample, so
this is a clean A/B against the homepage-only run).

| | homepage only | + subpage follow |
|---|---:|---:|
| structured JSON-LD hours | 12 | 13 |
| hours in page text | 6 | 8 |
| **hours obtained** | **18 (31.6%)** | **21 (36.8%)** |

Followed a subpage on 26 dead homepages and rescued 3 — an 11.5% hit rate on attempts, +5.2 points
overall, for roughly double the request volume. Worth keeping; not a fix.

**Net: 21 of 80 sampled sites (26.3%) yield hours. Against 73.6% website coverage, that is ~19% of
independents.**

## Where the hours problem actually stands

Every free avenue is now measured, not assumed:

| source | coverage of independents |
|---|---:|
| website crawl, incl. subpage following | ~19% |
| OSM `opening_hours` | 1.4% |
| **combined free sourcing** | **~20%** |
| category-daypart priors (Layer 0) | 100%, low precision |

**About 80% of independents have no obtainable real hours from any free source.** The engineering
path is exhausted; further effort (headless rendering for the 12.5% JS shells) buys single-digit
points at real infrastructure cost.

### This is now a commercial question, not an engineering one

Sizing a paid per-metro refresh at Foursquare's published Pro rate ($15.00 CPM, 10k free calls):

```
14,544 independents + 1,417 regional  ~= 16,000 places
16,000 x $0.015                        = ~$240 per full refresh
quarterly                              = ~$960/yr for BOTH metros
```

That is affordable — **if the licence permits storing the hours.** Google's does not, definitively.
Foursquare's *API* terms restrict caching; their *bulk data products* (Places Pro/Premium as a
licensed dataset) are the storable path, and are not publicly priced.

**Next action is to price a storable hours dataset, not to write more crawler code.**

### The good news, and it is genuinely good

Hours gaps hurt the two modes very differently:

- **Spontaneous mode tolerates them.** A place that turns out to be closed is one bad card in a
  swipe deck — the user rejects it and swipes on. Layer 0 priors plus 20% real hours is shippable.
- **Itinerary planning does not.** A wrong closing time invalidates an entire generated day, and
  the user only finds out by standing at a locked door.

Spontaneous-first — the priority already chosen — is therefore well matched to the data obtainable
today. The paid hours licence is what gates full-trip planning, and it can be bought later, when
the feature it unlocks is the one being built.

## Gate 4 — Foursquare pricing, 2026-08-17

**Verdict: the $240/refresh plan is not legal. Defer the paid-hours decision.**

The sizing in Gate 3b assumed we could call the Foursquare API and keep the results. We cannot.
Under Foursquare's self-service / pay-as-you-go terms, `fsq_place_id`, photo IDs and address IDs
may be cached indefinitely — but **names, categories, hours and ratings may not.** Hours are named
explicitly. That is the same structural trap as Google, at a slightly lower CPM.

So `16,000 × $0.015 = $240` describes an option that does not exist. Withdrawn.

### No Places API sells storable hours

| provider | storage of hours |
|---|---|
| Google Places | prohibited (place ID only; lat/lng 30 days) |
| Foursquare (PAYG) | prohibited (IDs only) |
| HERE | 30-day retention cap |
| Radar | 30 days, and terms forbid building a POI DB |
| Mapbox Search Box | temporary use only |
| Geoapify / Open Places API | **permitted** — but they are OSM/Overture-derived, and we measured that at 1.4% |

The pattern is not coincidence. Providers that permit storage are built on open data, which has no
usable hours. Providers with good hours meter them precisely because hours are the perishable,
expensive-to-maintain field. **The only fields you may keep are the ones nobody needs to buy.**

And the reason Google's hours are best is instructive: businesses maintain them for free through
Google Business Profile, because Google sends them customers. That is a network effect no data
vendor replicates — and exactly why the terms lock it down. Adventour could eventually earn the
same self-reporting loop from businesses; it cannot at cold start.

### The real option: a bulk data licence

Storable hours means licensing a dataset, not calling an API. The closest fit with a published
model is **SafeGraph Places** — 80M+ POIs, ~40 attributes, monthly refresh, delivered as flat files
or via S3/Snowflake/Databricks, with usage rights negotiated per deal. Published range is broad
($0.10 per purchase up to $30,000/yr) because pricing is a custom mix of rows, columns and usage
rights. **A real number requires a sales conversation.**

### Recommendation: defer

1. **No number is obtainable without contacting sales**, and negotiating for ~16k rows across two
   Florida metros with zero users is the weakest possible position. Usage data changes that.
2. **Spontaneous mode tolerates hours gaps** (Gate 3b). ~20% real hours plus category priors is
   shippable for the mode we are actually building.
3. **The buy is better-scoped later.** When trip planning is the active scope, we will know which
   categories and neighbourhoods actually get traffic, and can license rows for those instead of
   paying to cover 16,000 places on the chance someone visits them.

Revisit when full-trip planning becomes the active scope, or when a metro shows real usage.

## Gate 5 — seed loaded, 2026-08-17

19,385 places in local Postgres across 2,239 H3 r8 cells. No PostGIS: H3 cells are computed in
Python and stored as indexed text, radius queries run as `h3_r8 = ANY(grid_disk(...))` plus a
Haversine sort. Reproduce with `Server/data_pipeline/load_postgres.py`.

| metro | chain | regional | independent |
|---|---:|---:|---:|
| orlando | 3,324 | 1,401 | 13,948 |
| palm_coast | 114 | 46 | 552 |

### Finding: Overture `confidence` is an existence score, not a quality score

The first smoke test — nearest independents to downtown Palm Coast — returned
`Country Club Harbor Hoa Inc` (categorised `restaurant`), `Tidelands Condominium Association`
(`historic_site`), and `Blue Springs State Park, Orange City` (`skate_park`, and named after a park
50 miles away). Coordinates checked out; the geo pipeline is correct. The *records* are noisy.

Sizing it across the 14,500 independents:

| kind | count | avg confidence |
|---|---:|---:|
| looks like a real destination | 13,401 | **0.82** |
| corporate-entity name (LLC/Inc/Corp) | 687 | 0.88 |
| residential / HOA / property mgmt | 412 | **0.92** |

**Confidence is inversely correlated with usefulness.** HOAs and property managers score *higher*
than actual destinations, because they are well-attested business registrations — Overture's
confidence answers "does this exist," not "is this somewhere you would go."

This corrects the brief, which listed a confidence floor as a quality filter. It is not one, and
filtering on it would preferentially keep the junk.

~1,100 of 14,500 independents (7.6%) are non-destinations. Scope B needs an explicit junk filter —
name patterns plus category sanity checks — and this is a place where real user rejections will be
high-signal training data almost immediately.

## Gate 6 — ground truth from Palm Coast, 2026-08-17

131 of 132 places labeled by someone who has lived there 18 years, plus free-text.
Raw data: `Server/data_pipeline/qa/adventour_palm_coast_labels.json`.
Reproduce the analysis with `Server/data_pipeline/analyze_labels.py`.

**Headline: coverage is solved, quality is not.** Every one of the 14 must-have places named
independently was already in our database. Two only looked missing because of apostrophes and
because the human typed "Hooligans" for `Houligan's` — Overture's spelling was correct, the input
was not. Overture *has* the gems. This is a ranking and filtering problem, not a sourcing problem.

But **37% of the sample is junk and 9% is permanently closed.**

| label | n | share |
|---|---:|---:|
| junk | 49 | 37.1% |
| gem | 33 | 25.0% |
| not_worth | 19 | 14.4% |
| chain | 12 | 9.1% |
| solid | 10 | 7.6% |
| generic | 8 | 6.1% |

Worth separating: this is **not** evidence of messy source data. It is evidence that human input
is messy. Real users will misspell place names exactly this way when searching or naming a spot, so
fuzzy matching belongs on the **lookup path in Scope B**, not in Scope A ingestion.

### Categories to drop outright

Clean categorical kills — every labeled instance was rejected:

| category | n | good | bad |
|---|---:|---:|---:|
| `historic_site` | 20 | 0 | **20** |
| `religious_organization` | 5 | 0 | 5 |
| `sport_or_recreation_club` | 3 | 0 | 3 |
| null category | 3 | 0 | 3 |

`historic_site` is the big one. In Palm Coast, Overture uses it for **condos, apartments, roads
(`Dixie Highway`) and neighbourhoods (`P Section` — literally the streets beginning with P)**. It is
not a historic-site category here; it is a dumping ground. Dropping it removes 20 junk records at a
stroke.

Keep: `restaurant`, `casual_eatery`, `cafe`, `bar`, `park`, `recreational_trail_or_path`.

### Closed businesses are a first-class problem

**12 of 132 (9.1%) are permanently closed or do not exist** — and the human said they *would have
recommended 6 of them*. Their Overture confidence averages **0.90**, ranging up to **0.99**
(`Samis Pizza`, closed). `operating_status` did not catch a single one.

Closures do not merely add noise, they destroy the best recommendations: a closed local favourite is
exactly the place the recommender will rank highest. This needs its own signal, and it is the
strongest argument yet for a live check before a place is shown.

### Three corrections to the decision brief

1. **Popularity is not the opposite of authenticity.** Asked what authentic means, the answer was:
   *"frequented by tourists and loved by locals. Just because it is popular doesn't mean it can't be
   authentic... being a must-do can sometimes be categorized as authentic."* The brief's
   "low-to-medium mainstream popularity" authenticity feature is therefore **wrong** and would
   actively suppress correct recommendations.
2. **`regional` is a positive signal, not a chain penalty.** Of 14 places we classed regional (3–9
   Florida occurrences), **8 were labeled gem and 0 were labeled chain** — Houligan's, Fancy Sushi,
   Bronx House Pizza, Great Wall, Sushi 99, Salsas, A1A Burrito Works, Waterfront Park. Beloved local
   businesses open second locations. `chain_probability` must not be monotonically penalised.
3. **Confidence barely predicts quality.** Below 0.95 the "good" rate is flat at 21–25%; only the
   0.95+ band reaches 43.8%. It is weak positive evidence at the very top and useless elsewhere.

### Signal scorecard

| signal | verdict |
|---|---|
| chain classifier | **good** — 10 of 12 human "chain" calls matched. Missed Woody's Bar-b-que (small FL chain) and Epic Theatres |
| junk name patterns | **precise, not sensitive** — caught 61% of junk with **zero** false positives |
| category filter | **strong**, once the four dead categories are dropped |
| Overture confidence | **weak** |
| closure detection | **absent** — the biggest gap |

### Interest-gated categories

Golf courses scored 0 good / 4 bad, but the notes explain why: *"if someone had interest in golf I
would, otherwise it's not a real destination to most people."* Five golf courses in a small sample —
Palm Coast is full of them. These are not junk; they are **opt-in**. Same pattern for kids' art
classes and jiu-jitsu gyms. Scope B needs a category tier that only surfaces on explicit user
interest, distinct from both "recommend" and "drop".

Mobile vendors (food trucks, catering) are a third case: real and often good, but not a destination
you can navigate to. `So Good Mochi` and `Dex N Angie House of Flavor` were both rejected on that
basis.

## Gate 7 — junk filter, 2026-08-17

**Verdict: shipped. Hit rate on labeled data nearly doubled, with zero false positives.**
Filter in `Server/data_pipeline/junk_filter.py`; score it with `eval_junk_filter.py`;
apply with `apply_junk_filter.py`.

Four tiers, because the labels showed "show / don't show" is too coarse:

| tier | meaning | places |
|---|---|---:|
| KEEP | a real destination | 15,306 (79.0%) |
| DROP | never show | 3,774 (19.5%) |
| MOBILE | real, but not navigable to a fixed address | 178 (0.9%) |
| GATED | real, but only for someone who asked | 127 (0.7%) |

### Measured against the 131 human labels

| metric | before | after |
|---|---:|---:|
| recall on "junk" | 61.2% | **85.7%** |
| precision (dropped things they rejected) | — | **97.9%** |
| **false positives (dropped a gem)** | 0 | **0** |
| good-place rate in what survives | 32.8% | **55.1%** |

The zero is the number that was optimised for. Junk in a deck costs one swipe; a gem
silently filtered out is invisible and unrecoverable. Every rule was checked to fire on
none of the places the reviewer liked — which is why a bare "Co." suffix is deliberately
absent from the corporate-shell pattern: it would have killed Vessel Sandwich Co. and
Coquina Coast Brewing Co., both gems.

### What does the dropping

| reason | places |
|---|---:|
| category:historic_site | 1,148 |
| category:religious_organization | 700 |
| name:corporate_shell | 629 |
| no_category | 482 |
| category:sport_or_recreation_club | 447 |
| category:stadium_arena | 99 |
| category:sport_field | 81 |
| name:vice_retail | 61 |

### The deck, before and after

Same query — nearest independents to downtown Palm Coast.

**Before:** Portuguese American Cultural Center, *Blue Springs State Park Orange City*,
*Tidelands Condominium Association*, *Country Club Harbor Hoa Inc*, *Bella Harbor*,
*St Augstine*, Emilio's Pizza, Mom & Pops Pizza — five of eight unusable.

**After:** Portuguese American Cultural Center, Emilio's Pizza, Mom & Pops Palm Coast Pizza,
Schnitzel-Time, McSwiggin's Pub, Rodie's Place, Jt's Seafood Shack, Green Lion Cafe,
Hammock Grill by Jt's, La Piazza Cafe, Tropical Kayaks — recognisably a deck.

### The 7 junk records that still survive

All seven are restaurants or bars with ordinary names and no structural signal —
`Cole And Oliver Co`, `Michoacana Bacana`, `The NET by George`, `Ger-Rain's Tiki Shack`,
`The Wandering Hoagie`, `Dex N Angie House Of Flavor`, `Bartolome Colom`.

**Five of the seven are closures**, which is a separate problem with a separate decision
(brief §10b). Two are mobile caterers filed under `restaurant` rather than
`food_truck_stand`, so the category-driven MOBILE tier cannot see them.

That is the natural ceiling for rules. Further gains come from closure verification and
from user rejections, not from more regex — and pushing harder on patterns is how false
positives get created.

### Noted, not fixed

`The Shape of Water Weddings & Events` is filed as `restaurant` and now appears in the
Palm Coast deck. Wedding and banquet venues are a real category of non-destination.
Worth a pattern, but not added on a single example — that is how overfitting starts.
Revisit if the Orlando labels show the same shape.

### Gate 7 amendment — the state park corruption, 2026-08-17

Found by the owner reviewing the deck: **Washington Oaks Gardens State Park was categorised
`skate_park`** and therefore hidden behind the GATED interest tier.

It is systematic. Of 18 `skate_park` records across both metros, **13 are state parks, forests or
trails** — Wekiwa Springs, Gamble Rogers, Faver-Dykes, Bulow Plantation Ruins, Blue Springs, Little
Big Econ State Forest — against only 4 genuine skate parks.

Look at the strings: **"state park" and "skate park" differ by one transposed character.** That
corruption reached Overture's taxonomy and, unchecked, would have buried the best outdoor
destinations in the region.

**Fix: a `PROTECTED_DESTINATION` name rule that runs before any category logic.** State parks,
national parks, state forests, preserves, wildlife refuges and botanical gardens are KEEP regardless
of the category assigned. Real skate parks — `Orlando Skate Park`, `Riverside Skate Park` — keep
their category and stay correctly gated.

Result: **39 places rescued, 15 of which were being mis-tiered.** Label scores unchanged, false
positives still zero.

The lesson is general: a category-only filter cannot see a bad category. Name evidence has to be
able to override it, in both directions.

## Gate 8 — authenticity scoring, 2026-08-17

**Verdict: a working quality floor, not a ranker. Most of the brief's authenticity design
did not survive measurement.**
Signals: `Server/data_pipeline/eval_authenticity_signals.py`. Score: `authenticity.py`,
applied by `score_authenticity.py`.

Every candidate signal was measured against the labels before anything was built —
gem vs generic/not_worth/junk, among places that pass the junk filter, since that is the
only population ranking ever sees. n=55 (46 after the confound check).

| signal | AUC | verdict |
|---|---:|---|
| Overture confidence | **0.821** | strongest |
| has socials | 0.647 | weak |
| H3 cell density | 0.388 | weak, **inverted from the assumption** |
| category rarity | 0.565 | **no signal** |
| local name affinity | 0.553 | no signal |
| chain_class (post-filter) | 0.523 | no signal |
| statewide name count | 0.446 | no signal |

### Two of the brief's core ideas were wrong

**Category rarity failed outright.** The brief argued locally-rare categories are more
authentic — the "Oaxacan mole specialist in Pittsburgh" intuition. In the data, *every one*
of the top gems is a plain `restaurant`, the single most common category in the metro
(232 of them). Rarity would have penalised Joe's NY Pizza, Bronx House, Turtle Shack,
Collettis and Romero's — the actual gems.

**Density is backwards.** The brief proposed penalising dense POI clusters as tourist traps.
Denser cells contain *more* gems, because restaurants cluster where the good areas are —
European Village and the Flagler Beach strip, exactly what the owner named. Clustering is
where locals go, not a warning sign.

### Confidence is not a closure artifact

Suspecting the confidence signal was really re-detecting the 12 closed businesses sitting in
the negative class, closures were removed and it was re-measured. It got **stronger**
(0.778 → 0.821). It is a real signal for quality *among places that pass the junk filter* —
which does not contradict Gate 5, where confidence was useless at separating junk. Different
population, different question.

### The score

Round weights, deliberately unfitted — with n=46 there is nothing to fit but noise.

```
0.65 x confidence  +  0.15 x has_socials  +  0.20 x density     (x 0.55 if chain)
```

The chain multiplier is **policy, not prediction**. Post-filter it does not predict gems, but
the product exists to favour local places and Gate 6 showed the classifier is accurate. It is
kept as a separate multiplier so it can be tuned, or exposed as a user preference, without
disturbing the measured part.

| | AUC |
|---|---:|
| combined score | **0.840** |
| confidence alone | 0.778 |

Encouraging independent check: the top-scored Palm Coast places include **Next Door Beach
Bistro, Break Awayz and Funky Pelican** — three places from the owner's must-have list, which
the scorer had no access to.

### The real limitation: it cannot order the top

| | |
|---|---:|
| places sharing the single most common score (0.994) | **490** |
| places in the top decile | 4,103 |

The score separates good from bad but **not good from great**. A deck shows roughly twenty
cards; with 490-way ties the ordering among them is whatever the database happens to return.

This is a ceiling on cold-start data, not a bug to tune away. The three surviving signals are
all near-binary — confidence clusters high, socials is a boolean, density saturates. Genuine
ordering needs continuously varying evidence, and the only honest source of that is user
behaviour: accepts, rejects, arrivals, ratings. Which is the moat argument again.

**Practical consequence for Scope B:** treat authenticity as a floor and a filter, and let
distance and context drive order within the qualifying set. Do not present the score as a
ranking until there is behavioural data behind it.

**Caveat on all of the above:** n=46, one metro, one labeller, nine signals tested. The 0.821
is strong enough to act on; the 0.647 and 0.388 are marginal and could be noise. Repeat this
in Orlando before treating any of it as settled.

### Gate 8 amendment — instruction businesses and a serving floor, 2026-08-17

Raised by the owner from the deck: `DREAM BIG with Katia.` is filed as `art_gallery` but is a
kids' art-lesson studio. *"I wouldn't include it or stuff like it at all."*

**A new tier boundary.** Instruction businesses are not the same as the GATED tier. A golf
course or a rink can be walked into on the day; a lesson studio requires enrolment. Added an
`INSTRUCTION` name rule — lessons, classes, tutoring, daycare, preschool, "school of". It also
turned out that `dance_school`, `art_school` and `music_school` have **zero records** in the
index, so those GATED entries were dead weight; real lesson businesses hide under
`performing_arts_venue`, `sport_court`, `art_gallery` and even `restaurant`.

Category-level dropping was rejected: Palm Coast's 14 `art_gallery` records are a genuine mix
of real galleries (Baliker, Lotus, Pineapple, Gallery of Local Art) and lesson studios.
Dropping the category would kill the galleries.

**A pattern that was tested and rejected.** `DREAM BIG with Katia.` suggested a
"... with `<FirstName>`" rule for solo practitioners. Run against the whole index it matched
three places, of which **two were false positives** — `A Day in the Park with Barney` (a real
Universal attraction) and `Dan's Donuts with Dad`. 33% precision, discarded. Worth recording
because it looked convincing and was wrong.

**The floor.** `DREAM BIG` is not catchable by name or category, but it scores **0.272**.
Measuring what an authenticity floor costs against the labels:

| floor | gems lost | solids lost | index kept |
|---:|---:|---:|---:|
| 0.25 | 0 | 0 | 15,275 |
| **0.30** | **0** | **0** | **15,193** |
| 0.40 | 0 | 0 | 14,721 |
| 0.50 | 1 | 1 | 13,167 |

`AUTHENTICITY_FLOOR = 0.30` — the lowest value that catches the reported case, and free on the
labelled sample. 0.50 was rejected: it starts costing real gems.

Kept deliberately **separate from `tier`**, because "structurally junk" and "scored too low to
recommend" are different claims, and re-scoring must never rewrite structural classification.

**Honest limit:** the floor removes ~118 places and only one of them is labelled. It is
evidence-backed at 0.30 and speculative above it. Revisit with the Orlando labels.

## Gate 9 — deduplication, 2026-08-17

**Verdict: shipped. 827 duplicate records collapsed; Washington Oaks went from six records to two.**
`Server/data_pipeline/dedup.py`, driven by `run_dedup.py` (dry run by default, `DEDUP_APPLY=1` to write).

| | |
|---|---:|
| KEEP records before | 15,311 |
| clusters with >1 record | 702 |
| records absorbed by merging | **827** |
| distinct entities after | 14,484 |
| clusters flagged with unreliable geometry (>5 km spread) | 265 |

Palm Coast specifically: 547 KEEP rows resolve to **523 distinct places**.

### The design tension

Washington Oaks' duplicates are 21 km apart, so tight spatial matching misses them. But two
Subways 200 m apart are genuinely two places, so loose matching destroys real venues.
**Name distinctiveness sets the distance tolerance**, measured by corpus document frequency.
Records are blocked on their rarest token and compared with IDF-weighted Jaccard.

Survivor selection splits two decisions deliberately: the **most complete record** wins the
identity, while the **spatial medoid** supplies the location, because the richest record is
frequently not the one with plausible coordinates. `confidence` is not used at all — for
Washington Oaks the 0.58 and 0.97 records disagree by 20 km and neither is obviously right.
Clusters keep a `loc_spread_m` so unreliable geometry is visible rather than hidden.

### Four bugs the dry run caught before anything was written

Recorded because each is a standard entity-resolution trap and each was invisible until measured.

1. **Unstable blocking.** Blocking on the alphabetically-first token put "Washington Oaks State
   Park" (`oaks`) and "Washington Oaks Gardens State Park" (`gardens`) in different blocks — the
   exact case this was built for was never compared. Now blocks on the rarest token, which does
   not move when a word is inserted.
2. **No IDF.** Plain Jaccard rates `park` as informative as `washington`, so 18 unrelated Winter
   Park businesses and 14 different sports bars merged. Tokens are now IDF-weighted.
3. **Self-defeating tolerance.** Distance tolerance keyed on `fl_name_count` — but duplicates
   inflate their own statewide name count, tightening the tolerance and blocking the merge that
   would have removed them. Washington Oaks merged 2 of 6 for precisely this reason. Tolerance
   now comes from corpus document frequency instead.
4. **Key collision that silently destroyed clusters.** The chain-splitting step wrote
   `clusters[m["id"]]`, but union-find roots *are* member ids — so when a split-off member
   happened to be the root, it overwrote its own cluster. Washington Oaks vanished from the
   output despite six matching pairs. Keys are now namespaced.

### Multi-location businesses are not duplicates

An early pass merged `Sus Hi Eatstation` (7 records, 17 km) and `Mecatos Bakery` (6 records,
23 km) — real multi-location businesses, and precisely the `regional` class the Palm Coast
labels showed are gems. The long-distance merge is now restricted to `SINGLETON_CATEGORIES`:
parks, trails, museums, beaches, theme parks. **A state park does not have seven branches; a
restaurant does.**

Correct large merges after the fix: Magic Kingdom (12 records), Walt Disney World (10),
Universal Studios (9), Cross Seminole Trail (6).

### Safety check

Four labelled gems/solids were absorbed into other records — every one into a record with the
**same name**, i.e. correct merges where the survivor happened to be the unlabelled twin. No gem
was merged into a different place.

### Known limitation

Washington Oaks' medoid lands at 29.6262, about 1 km from the true location, and the cluster
carries a 20 km spread flag. The medoid is robust to outliers but cannot invent a correct
coordinate when four of five records are wrong. `loc_spread_m > 5000` marks 265 clusters whose
geometry should not be trusted for turn-by-turn navigation — a good candidate for the one live
API call at accept time, which returns an authoritative location anyway.

## Gate 10 — running on a device, 2026-08-18

**Verdict: the checkpoint the working agreement actually asks for. Passed.**

Adventour running on the Pixel_7_API_30 emulator, GPS mocked to downtown Palm Coast, deck served
entirely from the Postgres index. **One `/api/recommendations` call, zero calls to Google.**

Twenty picks. First card Thai By Thai Restaurant (3,022 m, match 98%), second Palm Harbor Grill —
both labelled gems in Gate 6. Overture's `restaurant` correctly lit the Food & Drink chip with no
change to the app: `local_index_service` emits the existing response shape, so the UI freeze held.

Setup notes worth keeping: the emulator needed **SVM Mode enabled in UEFI** (x86 images will not
run without it) and then WHPX, not the AEHD driver — AEHD conflicts with Hyper-V. `API_AUTH_MODE=dev`
in `.env.android.local` bypasses the Firebase login.

### The device caught what nothing else did

Swipes failed with `invalid input syntax for type integer` — `/api/events` resolved `place_id`
against the integer-keyed legacy `place` table while the index returns Overture UUIDs. Every swipe
500'd.

This mattered more than a normal bug: Gate 8 concluded behavioural data is the only thing that can
break the 490-way score ties, so a dead write path would have made the score permanently unrankable.

Fixed by `place_event` (see Gate 11). Verified live: accept on Smiles Nite Club, rejects on Palm
Harbor Grill and Portugal Wine Bar & Grill, all with `score_snapshot = 0.977`.

**Those three rows are Gate 8's problem in live data — identical scores, one accepted, two rejected.
That is exactly the signal that breaks the tie.**

## Gate 11 — legacy removal, 2026-08-18

**Verdict: one architecture, one code path, no feature flag.**

Deleted: `Place`, `PlaceProviderRef`, `PlaceFeature`, `UserPlaceEvent`, `UserPreferenceVector`,
`UserTagFeedback`, `UserPlaceInteraction`, `RecommendationService`, the `providers/` package,
`recommender_lab.py`, `real_place_lab.py`, an orphaned `place_classification.py`, four legacy test
files, the v1 `GET /recommendations` / `POST /feedback` / `POST /fetch-places` endpoints, the dev
seed-place route, and 4,553 stale `.pyc` files including bytecode for codex services that no longer
exist.

**`app.py`: 1,240 → 904 lines.**

New schema, designed against the index rather than adapted to the old one:

- **`place_event`** — keys on `entity_id` (the deduplicated entity, not the record shown), and
  snapshots `score_snapshot` at decision time. Without that snapshot a re-score silently rewrites
  history and every past event becomes untrainable.
- **`suppressed_place`** — `google_place_id` plus our own timestamp only, per the boundary in
  `CLAUDE.md`. A `closed_report` event type writes to it directly.
- **`AdventourStop.entity_id`** (text, deliberately not a foreign key) so a saved stop survives an
  index rebuild. Display coordinates come from the snapshot captured when the card was shown.

### Kept on purpose

`Trip` / `TripMember` / `TripPlace` / `PlaceRating` look v1-era but `social_routes.py` uses them for
the **Friends & Trips screen, which is live**. Deleting them would have broken a working feature.
Their `place_id` is free-text, not a foreign key into the removed `Place` table, so they carry no
legacy coupling.

### Verified rather than assumed

All eight endpoints the app calls return 2xx. Full Adventour lifecycle runs: navigate → arrive →
rate → new stop → complete. The removal did break `serialize_adventour_stop`, which still referenced
a `place` local — it threw a 500 *after* the event had already been written. Fixed, then the AST was
scanned for other orphaned `place` / `provider_ref` / `feature` locals. None. Deck reloaded clean on
the device afterwards.

## Where Scope A ended up

| | |
|---|---:|
| raw Overture records ingested | 112,682 |
| Adventour-relevant after category filtering | 19,385 |
| KEEP after the junk filter | 15,311 |
| distinct entities after dedup | **14,484** |
| servable in Palm Coast (KEEP + above floor) | **513** |
| Postgres tables | 11 |
| `app.py` | 904 lines |


## Gate 12 — Orlando labels: the Palm Coast findings did not generalise, 2026-08-19

**Verdict: the authenticity score is much weaker than Gate 8 reported, and the junk filter has a
large blind spot in a big metro. Both were single-metro artifacts.**

137 places labelled across four ZIPs the owner knows — 32819 (Restaurant Row / tourist corridor),
32803 (Mills 50 / Lake Eola), 32839 (Millenia), 32816 (UCF).
Reproduce with `Server/data_pipeline/compare_metros.py`.

### The score was overfit

| signal | Palm Coast | Orlando |
|---|---:|---:|
| **our authenticity score** | **0.954** | **0.639** |
| Overture confidence | 0.777 | 0.637 |
| has website | 0.630 | 0.589 |
| has socials | 0.632 | 0.568 |
| H3 cell density | 0.268 | 0.396 |

**The 0.954 is meaningless.** The score was built *on* the Palm Coast labels, so scoring it against
them measures memorisation. **Orlando is the first out-of-sample test, and it says 0.639** — barely
better than the 0.5 of no signal at all, and far below the 0.840 Gate 8 reported.

Overture confidence, the one signal Gate 8 trusted at 0.821, drops to **0.637**. Its Palm Coast
strength was substantially a small-sample artifact. Cell density stays inverted in direction but
weakens.

The only thing that generalised cleanly is the **chain classifier: 10/11 human "chain" calls
matched, matching Palm Coast's 10/12.**

### The filter's blind spot is much larger here

Every Orlando place sampled was already `tier = KEEP`, so these are places we *would serve*:

**47 of 137 (34.3%) are junk or not-worth.** In Palm Coast the equivalent residual was ~23%.
Twenty-four were labelled outright junk, mostly filed as `restaurant` (10) — no structural signal
in either name or category.

### Five failure modes Palm Coast could not have revealed

1. **University-only (10 places).** Student dining, a sorority house, campus tennis courts, an
   observatory "not open to the public". 32816 is UCF and none of this was visible in a town with
   no campus. Needs an institutional-access concept, not another name pattern.
2. **Requires a ticket or advance booking (9).** Islands of Adventure, Universal Studios and
   Orlando Shakespeare Theater are **labelled gems** — these are not junk, they are the best places
   in the metro. But recommending them like a walk-in restaurant is wrong. This is an *attribute*,
   not a tier.
3. **Inside a paid venue (4).** `Florean Fortescue's Ice-Cream Parlour` is inside Universal and
   cannot be visited without park admission — junk as a standalone recommendation, sensible as a
   suggestion once someone has accepted the park. Nested venues need a parent relationship.
4. **Hotel food service (2).** A hotel buffet is not a destination.
5. **Tourist ticket resellers (2).** Both `ticket_office_or_booth`; one labelled outright **trap** —
   the first trap label in either metro, and exactly the thing Adventour exists to avoid.

Plus **15 permanently closed** — higher than Palm Coast's 12, reinforcing that closure detection is
the single biggest data-quality gap.

### What this changes

- **Gate 8's headline number is withdrawn.** The honest figure is AUC ~0.64 out of sample. The score
  remains usable as a floor; it is further than ever from being a ranker.
- **Weights must not be tuned on Palm Coast again.** Any future scoring change is measured on the
  metro it was *not* fitted to, or it is not measured at all.
- **The ticketing/booking attribute is now load-bearing.** Brief §10 parked ticket linking as
  "noted, not scoped". Orlando says several of the metro's best places are unusable without it.
  The reserved `external_links` field is needed sooner than assumed.
- **Scope C (evaluation) is now clearly the next scope.** This gate only exists because a second
  metro was labelled by hand; that check needs to be a harness, not an afternoon.

### Method note

30 of 137 were labelled "don't know it" — expected in a metro of 18,673 records versus a town of
712, and excluded from the contrast. The comparison uses gem vs generic/not_worth/junk in both
metros, so the two AUCs are directly comparable.

## Definition of done

- Orlando + Palm Coast POIs queryable from our own Postgres with zero paid API calls.
- A deck of candidates renders on a real Android device, showing places that are actually open.
- Score components visible per place so recommendations can be judged, not just observed.
- Ground-truth check: you review a deck for a Palm Coast location and confirm the local/chain split is right.
