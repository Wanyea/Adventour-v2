# Adventour v2 — Handoff Brief

**For:** the next agent taking over this project
**From:** the previous agent (branch `claude`, commit `727c2a01`)
**Date:** 2026-08-19

Read this file completely before writing any code or any plan.

**Entry points:** this file, then `AGENTS.md` (the working agreement — repo conventions, data
boundary, UI freeze). `CLAUDE.md` is a stub pointing at `AGENTS.md`; ignore it.

Nothing in this repository depends on a particular agent harness. Commands are plain
PowerShell, Bash, `git`, `adb`, `npm` and `python`. Where a doc says "the previous agent" it
means exactly that — no tooling is implied.

---

## 1. What Adventour is

A mobile app that removes the planning barrier from travel and local exploration by
recommending **local, authentic places** — food, activities, entertainment — and actively
discouraging chains and generic tourist defaults.

The interaction is Tinder-like: **swipe left to reject, swipe right to accept and get
directions.** Accepted places accumulate into an "Adventour" — a trip that can be completed,
saved, shared, and taken by friends.

The differentiator, in the owner's words: competitors like Wanderlog optimise *organisation*
and require heavy manual entry, and their recommendations "don't respect you or the
authenticity of the place." Adventour optimises **discovery with trust** — less research,
more personal taste, friend-aware, local-first.

The owner's definition of authentic, given verbatim during labelling:

> "A place with good food or fun activities that are frequented by tourists and loved by
> locals. Just because it is popular doesn't mean it can't be authentic but at the same time
> a popular tourist trap doesn't necessitate the branding of authentic. Being a 'must-do' can
> sometimes be categorized as authentic to that region or city."

**Popularity is not the opposite of authenticity.** A previous design assumed it was and was
wrong. Do not reintroduce that assumption.

---

## 2. Your mandate

Produce **the complete app**, running on the Android emulator, covering the closed feature
list in §5. Then stop.

You are explicitly asked to:

- **Plan from the beginning.** Do not inherit the previous agent's scope sequence. Make your
  own plan, justified, and get it approved before writing code.
- **Keep what makes sense, discard what doesn't.** Everything on the `claude` branch is
  available to you and none of it is sacred. §4 tells you what is evidence and what is guess.
- **Work on your own branch**, cut from `claude` so you inherit the index, the pipeline, the
  268 human labels and the evaluation harness. Delete freely.
- **Deliver data tooling** the owner can use to collect richer ground truth later, without an
  agent in the loop.

---

## 3. Hard constraints — these are not negotiable

These exist because a previous unsupervised agent run (branch `codex`) produced **57,655
insertions across 54 files**, grew `HomeScreen.tsx` from 1,085 lines to **~22,600**, and made
the app unnavigable. The owner could not review it and abandoned it.

**The diagnosis was process, not capability.** That run had no scope contract, no file-size
ceiling, no closed feature list, and no checkpoint anchored to something a human could look
at — so "goal appears satisfied" was optimised for, and ~12,000 lines of self-written tests
made it look correct. Any capable model given those conditions lands in the same place. The
constraints below are the guardrails that were missing, not a comment on whoever ran it.

1. **No file in `AdventourApp/` may exceed 1,200 lines.** If a change would push a file over,
   stop and extract instead.
2. **No feature that is not in the §5 list.** If you believe something is missing, propose it
   and wait. Do not build it.
3. **No paid API call may populate a swipe deck.** Candidate retrieval runs against the owned
   index. This is a business constraint — see `docs/sourcing-cost-decision-brief.md` §4.
4. **Never store Google Places content.** Place IDs are storable indefinitely; names, ratings,
   reviews, hours, photos and addresses are not. Lat/lng at most 30 days. This is legal, not
   stylistic. `docs/sourcing-cost-decision-brief.md` §2.
5. **The checkpoint is the app running on the emulator**, not a passing test. Show the screen.
6. **Do not write large speculative test suites.** The `codex` branch wrote ~12,000 lines of
   tests for designs no human had validated. Test what exists and is agreed.
7. **Never report an in-sample metric as evidence.** See §4 — this is the mistake that cost
   the previous agent the most credibility.

---

## 4. What is actually known — evidence vs guess

This is the most valuable section. Treat the confidence levels as real.

### Solid — verified, reproduce before doubting

| finding | evidence |
|---|---|
| **Overture Maps Places is a legally storable base layer** — ~75M POIs, CDLA-Permissive 2.0, includes brand data, confidence, a 2,300-category taxonomy, websites and socials | Ingested and running |
| **You cannot build the DB from Google.** Place IDs indefinite; everything else prohibited | Terms verified |
| **Continental US = 2.53M Adventour-relevant places** after category filtering | Direct count |
| **Coverage is not the problem.** All 14 places the owner named as must-haves in Palm Coast were already in the index | Gate 6 |
| **The chain classifier works** — 10/12 and 10/11 agreement with human calls across two metros, via name frequency, not any API | Gates 6, 12 |
| **`historic_site` is a junk category** in this dataset — condos, apartments, roads. Dropping it removes 195,622 records nationally | Gate 6 |
| **"state park" ↔ "skate park"** is a one-character corruption in the taxonomy; 13 of 18 `skate_park` records were state parks | Gate 7 amendment |
| **~9% of the index is permanently closed** and no free signal detects it (mean Overture confidence 0.90) | Gates 6, 12 |
| **No provider sells storable opening hours** at any price. Providers who permit storage are built on open data that has no hours | Gate 4 |
| **The app runs on the emulator against the index with zero Google calls**, and swipes persist | Gates 10, 11 |

### Weak — measured, but the measurement says "we don't know"

- **The authenticity score does not demonstrably work.** In-sample AUC 0.954; out of sample
  **0.639, 95% CI [0.49–0.79]**. The interval includes 0.5. At n=19/60 it is *not
  distinguishable from no signal.* The previously reported 0.840 was overfitting.
- **All five scoring signals straddle 0.5 on the held-out metro.** Overture confidence,
  website presence, socials presence, cell density, and the composite.
- **41% of what the index would serve in Orlando is junk or not-worth**, after filtering.
- Filter recall was 85.7% on the metro it was built on. That number is in-sample.

### Disproved — do not rebuild these

- **Category rarity as an authenticity signal.** The intuition ("a Oaxacan specialist in
  Pittsburgh is distinctive") failed: every top gem was a plain `restaurant`, the most common
  category in the metro. AUC 0.565.
- **POI density as a tourist-trap penalty.** Backwards. Dense cells contain *more* gems,
  because good places cluster. The owner's own answer named the dense strips.
- **Low popularity as an authenticity proxy.** Contradicted by the owner directly.
- **OSM as an hours source.** 1.4% coverage of independents, and 14x better on chains than
  independents — strongest exactly where it is least useful.
- **Overture `confidence` as a junk filter.** HOAs and property managers score *higher* than
  real destinations. It is an existence score, not a quality score.

### Unsolved — these are invitations, not walls

**Read this framing carefully.** Everything above under *disproved* is a measured fact about a
**specific approach that was tried**. None of it proves the underlying problem is unsolvable.
The previous agent ran out of ideas, not out of possibilities.

You are explicitly encouraged to attack these. Finding a better answer is **in scope and
wanted** — it is the opposite of scope creep. The only rule is the same one that governs
everything else: **measure it, hold out a metro, and report the sample size.** Do not assert a
solution works; show it.

1. **The score cannot rank.** 490 places share one value; ties break by distance. The previous
   agent concluded this needs behavioural data and stopped. That conclusion may be too
   pessimistic — it tested five signals, all cheap and structural. Text embeddings over names
   and categories, review-free quality proxies, cross-referencing FSQ OS Places, or signals
   from the venue's own website were never tried. `place_event` already snapshots the score at
   decision time, so behavioural data works when it exists — but it is not the only route.
2. **Closure detection.** ~9% of the index is dead and no free signal finds it. Plan of record
   is lazy per-place verification with a persisted suppression list — `$387.70` one-time for
   both metros, Palm Coast fits in Google's free tier, cost scales with distinct places rather
   than impressions (brief §10b/§10c). The owner has approved storing a Google `place_id` plus
   our own `suppressed_at` and nothing else. **A cheaper or free detector would be a real
   win** and was not seriously attempted: HTTP liveness of the venue's own website, socials
   activity recency, and user reports are all unexplored.
3. **Hours.** ~80% of independents have none obtainable *by the methods tried* — static
   homepage fetch plus one subpage. Headless rendering for the 19% JS-shell sites was costed
   but never built. Category-daypart priors cover spontaneous mode; full-trip planning is the
   mode that genuinely needs better hours. Brief §8.
4. **Local events / third spaces.** See §5F — now in scope, and the most open-ended of these.

---

## 5. The complete app — a closed list

**This is the whole product. Nothing here is optional; nothing outside it is in scope.**
The owner's stretch goals are included deliberately so that "done" is a real state.

### A. Foundation (largely exists — verify, don't rebuild blindly)
1. Firebase auth, plus a dev-auth bypass for emulator work
2. Onboarding: display name, birthdate/age gate, travel-mood tag selection
3. Launch point: GPS or typed city/neighbourhood

### B. Core loop
4. Swipe deck from the owned index — accept / reject, with the score breakdown available
5. Directions on accept
6. Tag-group filtering of the deck
7. Interaction logging: impression, accept, reject, navigate, arrival, rate, save, share,
   closed_report — all already defined in `place_event`
8. **Trip mode:** accepted places accumulate into an Adventour session; arrive, rate,
   complete. Exists end to end; verify it.

### C. Social
9. Friend search by display name, request, accept/decline
10. Friend Adventours: see what friends did, and **take** their Adventour
11. **Beacon board** — a social feed of Adventours. Named in the original v1 vision, never
    built in v2.
12. **Group / blended recommendations** — pick one or more friends, get places that respect
    each person's taste. Design guidance in `docs/recommender-data-design.md`: hard
    constraints, soft preferences, fairness rotation, and a disagreement penalty rather than
    naive averaging.

### D. Profile & gamification
13. Profile with travel history (accepted/visited places)
14. **Globe or map visualisation** of areas travelled
15. **Achievements** — for visiting local gems, covering regions, and for other users taking
    and rating your Adventours highly
16. Place ratings and reviews by the user (this is the data moat; no provider sells it)

### E. Planning
17. **Full-trip mode** — a generated multi-day/day itinerary with swappable stops, as opposed
    to the spontaneous one-at-a-time flow. Note the real shape of this problem: it is the
    **Orienteering Problem with Time Windows** (choose a subset *and* sequence it under
    opening hours and a time budget). At 6–10 stops, exact dynamic programming solves it in
    milliseconds — no heuristics needed. `docs/sourcing-cost-decision-brief.md` §9.
18. **Ticket / reservation links** — Orlando labelling showed several of the metro's *best*
    places (Universal, Islands of Adventure, Orlando Shakespeare) are unusable without
    advance booking. `needs_booking` is already computed; `external_links` is reserved on
    `adventour_stops`. Linking out is sufficient; do not build a booking engine.

### F. Local events & third spaces

The owner's framing, and why this is core rather than a bolt-on: young people in Orlando and
elsewhere want to build community and have no good way to find or organise the things they
would actually care about — local art markets, run clubs, open mics, pickup sport. Surfacing
those serves **locals** looking for third spaces *and* **visitors** wanting something genuinely
of the place. It is the authenticity thesis in its strongest form, because an event is
time-bound and attended by people who live there.

19. **Local events surfaced in the app** for the seed metros, from at least one working source,
    with an explicit freshness guarantee and automatic expiry. A stale event does not merely
    disappoint — it sends someone to an empty parking lot.
20. **A decision, made and documented, on where events belong in the product.** A swipe deck
    answers "where should I go now"; an event answers "what is happening Saturday." Those may
    be different surfaces. The Orlando field-kit questions ask the owner directly whether they
    would use Adventour to find an event; **read their answer before designing this.**

Research is in `docs/scope-e-local-events.md`. **It is research, not a verdict.** What is
known: Ticketmaster's Discovery API is free (5,000 calls/day) but covers arena shows — the
"chain" equivalent of events. Eventbrite removed public event search in Dec 2019. Meetup is
paid per group. The genuinely local long tail is in no API at any price.

**That is a gap, not a dead end — and closing it is the interesting part of this feature.** The
strongest untried lead is that we already hold ~14,000 indexed venues with websites and
socials, and a crawler that follows internal links looking for structured data. Venues host
events and publish them on their own sites; `schema.org/Event` is the same shape of problem as
the hours crawl, which yielded 21% JSON-LD. Municipal open-data portals, library and parks
calendars, and university feeds are also unexplored — note **32816 is UCF**, inside a
ZIP the owner labelled, and squarely the demographic this feature is for.

Do not treat the previous agent's provider survey as the ceiling. It surveyed vendors; it did
not seriously try to build the thing.

### G. Data tooling the owner keeps
21. **Field kit** — a single self-contained HTML file the owner emails to anyone; recipient
    picks their ZIPs, labels a deck, answers written questions, exports JSON.
    `Server/data_pipeline/make_field_kit.py`. Improve it; keep it emailable and offline.
22. **Evaluation harness** — `Server/evaluation/`. One command, held-out discipline,
    regression detection.
23. **Ingest pipeline** for adding a new metro. Ordering matters:
    `load_postgres` → `apply_junk_filter` → `score_authenticity` → `run_dedup`.

---

## 6. Definition of done

The project is complete when **all** of these are true. There is no phase after this.

- [ ] Every item in §5 works on the Android emulator, demonstrated by screenshot
- [ ] One backend, one code path, no feature flags gating dead alternatives
- [ ] No file in `AdventourApp/` over 1,200 lines
- [ ] `python -m evaluation.harness --strict` exits 0
- [ ] The owner can add a new metro by running the documented pipeline, unaided
- [ ] The owner can send the field kit to a stranger and ingest what comes back, unaided
- [ ] Local events appear in the app for at least one seed metro, from a source whose coverage
      you have **measured and reported**, with expiry that provably works
- [ ] `docs/README.md` accurately describes the state of the repo
- [ ] No paid API call occurs while building a deck (verifiable in the server log)

**If you find yourself proposing a Phase 6, stop.** Either it belongs in §5 and you missed
it, or it is scope creep. Say which.

---

## 7. Where to read, in order

1. `docs/README.md` — state of the world, phase tracker, run commands
2. `docs/active-scope.md` — **every gate result with its evidence.** Long, and the most
   valuable file in the repo. Gates 6, 8 and 12 matter most
3. `docs/sourcing-cost-decision-brief.md` — provider stack, licensing, cost model at national
   scale, closure verification, the trip-planning problem shape
4. `docs/scope-c-evaluation.md` — how the harness works and why it refuses in-sample numbers
5. `docs/recommender-data-design.md` — original architecture. **Partly superseded**: its
   `places` schema and its authenticity signals were both disproved. Its blending and event
   design are still good
6. `docs/scope-e-local-events.md` — local events / third spaces. **This is now in scope
   (§5F).** Read it as a starting survey, not a verdict: it establishes that the local long
   tail is in no API, and stops there. Closing that gap is your problem to solve
7. `AGENTS.md` — working agreement and the data boundary
8. `Server/data_pipeline/qa/*.json` — **the 268 human labels. The only ground truth that
   exists.** Read the free-text answers, not just the labels

`docs/archive/` describes a backend that no longer exists. History only.

`Adventour-v1/` is the 2022 implementation. It proved the swipe model; its recommender was
not personalised.

The `codex` branch is the abandoned unsupervised run. Useful as a cautionary example of what
happens without the §3 constraints — not as a judgement of the agent that produced it. Do not
port code from it without asking; the owner has asked for that explicitly.

---

## 8. Things the previous agent got wrong

Stated plainly so you can avoid them, and so you calibrate how much to trust the rest.

1. **Reported AUC 0.840 as a result when it was measured on the data it was fitted to.** The
   honest figure was 0.639 and the interval included "no signal at all". The evaluation
   harness now exists specifically to make this mistake structurally hard.
2. **Asserted authenticity signals from intuition** — category rarity, density-as-trap,
   popularity-as-inauthentic — and had to withdraw all three after measurement.
3. **Wired the read path and never exercised the write path.** Swipes 500'd on the device
   because `/api/events` still resolved against an integer-keyed table. Found only by driving
   the real app.
4. **Sized a $240/refresh Foursquare plan that their terms forbid** — hours are explicitly
   non-cacheable. Withdrawn.
5. **Nearly reported 93.5% website+socials coverage** when the honest, crawlable figure was
   73.6%; the combined number partly measured Meta provenance rather than reachability.
6. **Deleted `Trip`/`TripMember`/`TripPlace` in a first pass**, which would have broken the
   live Friends & Trips screen. Caught before it shipped.

The pattern: **the errors were all in the direction of over-claiming**. When you report a
number, report its sample size and whether it was held out.

---

## 9. First deliverable

Do not write application code yet.

1. Read §7 in order.
2. Verify the environment: Postgres up, backend serving, app on the emulator, harness green.
   Run the deck once and look at it. Everything in §4 should be independently checkable.
3. Produce **your own plan** to reach §6: phases, ordering, what you are keeping from this
   branch and what you are deleting, and why. Include the stretch goals (§5 C, D, E) with a
   real position in the sequence — not an appendix.
4. Name the checkpoints where you will show the owner a screen.
5. Get it approved.

The owner's stated failure mode with a previous agent: *"the UI kept evolving and when I'd
check in every couple of hours I couldn't even navigate it."* Optimise for a reviewer who
looks every few hours and needs to understand what changed.
