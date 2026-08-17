# Adventour Recommendation Architecture

Adventour should keep recommendations useful before it has enough first-party
data for heavier machine learning. The current architecture is staged so the
product can improve without pretending a cold-start model knows more than it
does.

## Stage 1: Hybrid Ranker

The current backend uses a transparent hybrid ranker:

- content and tag matching from onboarding and accepted/rejected places
- authenticity, hidden-gem, chain, quality, distance, and price features
- authenticity evidence payloads that explain hidden-gem/local/generic-risk
  signals instead of hiding them inside one score
- group scoring from the requester plus accepted friends
- lowest-member-fit fairness penalties so a group pick is not carried by one
  enthusiastic traveler while someone else gets a poor match
- party-coverage reranking so early group baskets include strong matches for
  selected friends, not just the average taste profile
- planned-route rebalancing so later itinerary slots can favor a stop that
  better serves a traveler who has been underserved so far
- time-of-day context so morning, afternoon, evening, and late-night searches
  get different category nudges without hard-filtering options
- hard include/exclude type constraints so a user can remove categories from a
  basket or route before scoring begins
- score-then-diversity reranking so early baskets include different local
  experience types instead of ten near-duplicates
- intent-aware coverage bonuses so early baskets represent the traveler's
  active preference lanes, not only item-level dissimilarity
- history-aware novelty so repeatedly shown places are deprioritized before the
  app falls back to repeats on local exhaustion
- bounded exploration scoring for high-authenticity, underexposed local places
  that have not already been shown to the user
- explanation payloads so the app can show why a place was suggested
- structured `explanation_details` rationale cards for hidden-gem/authenticity,
  chain-guard, travel-party fit, timing, budget, and freshness signals
- normalized impression/accept/reject/navigate/rate events for future training

This is the right default while Adventour has low user volume. It makes every
recommendation inspectable and keeps tuning fast. The app should use the plain
sentence explanation for quick copy and `explanation_details` for details-screen
rationale cards instead of parsing English.

### Scoring Profile

The hybrid ranker is controlled by a named `ScoringProfile` in
`Server/adventour_backend/services/recommender_service.py`. The default
`phase1_balanced` profile keeps Adventour's current personality:

- strong personal taste fit without ignoring friend fit
- minimum traveler fit and disagreement guardrails for friend Adventours
- authenticity and hidden-gem boosts
- quality, distance, time-of-day, and novelty nudges
- controlled exploration for promising underexposed local finds
- chain, price, stale-repeat, and already-decided penalties
- diversity and party-coverage bonuses during reranking

The user preference vector also carries learned `hidden_gem_affinity` and
`avoid_chains` values. Positive hidden-gem interactions increase the lift for
future local-gem candidates, while rejected chain-like places strengthen future
chain penalties. For group recommendations, those signals are averaged across
the selected travel party.

Recommendation responses and logged impressions include the active scoring
profile in `components.scoring_profile` and `ranking.scoring_profile`. That
means exported training/evaluation data can be traced back to the ranker profile
that produced it.

Named beta profiles are available through request constraints, the lab tools,
or `ADVENTOUR_SCORING_PROFILE`:

- `phase1_balanced`: default blended taste, authenticity, distance, time, and
  diversity ranking.
- `authenticity_forward`: more aggressive local/hidden-gem weighting and chain
  avoidance.
- `group_friendly`: stronger group-fit and party-coverage influence for friend
  Adventours.
- `fresh_discovery`: more novelty pressure when Adventour keeps seeing the same
  candidates.

## Stage 2: Learning To Rank

Once test users generate enough impressions and outcomes, train a learning-to-
rank model over the same feature payloads the hybrid ranker already produces.
Useful labels:

- positive: accept, navigate, arrive, rate 4-5, save, share
- negative: reject, repeated impression without accept, low rating
- context: location, radius, party members, time of day, trip mode, price budget

The deterministic hybrid score should stay as a fallback and as a feature for
the model.

Preference vectors use recency decay for event-derived taste signals. Fresh
accepts, navigation, arrivals, and ratings steer recommendations more strongly,
while older swipes remain as a soft prior so the user profile can evolve during
testing without forgetting everything. Cached preference vectors refresh after
24 hours so time-based decay keeps working even when the user has not generated
a new event since the last app session. Positive place interactions also learn
a soft `price_preference`; explicit trip budgets still take priority, but when
no budget is selected, unusually pricey places are lightly penalized for users
or groups that usually choose lower-cost stops.

Passive impressions are deliberately excluded from preference-vector taste
learning. They still power freshness/repeat penalties and offline evaluation,
but Adventour should not infer that a user likes a place only because the app
showed it.

Provider query tags are built only from positive learned category weights or
onboarding fallbacks. Negative-only signals, such as repeatedly rejecting
museums, appear in `avoided_categories` but do not cause Adventour to search for
more museums.

Recommendation responses include `preference_insights`, and the backend exposes
`GET /api/recommendations/preferences` for the signed-in user. The payload
summarizes learning status, confidence, signal counts, top liked categories,
avoided categories, hidden-gem affinity, chain avoidance, and learned price
comfort so beta testers can debug why Adventour is making certain picks.

Group recommendation responses also include `group_fit_summary`. It reports
average basket fit, fairness, per-member average fit, matched counts, and any
underserved travelers. This separates two different realities that matter in
testing: a basket can be fair across friends while still being weak overall, or
it can be strong for one traveler while leaving another behind.

`Server/recommender_training_export.py` converts stored Adventour events and
place features into JSONL/CSV examples so the first learning-to-rank experiment
can use real beta behavior instead of hand-built assumptions.
Recommendation impressions include request IDs and final rank positions so
offline evaluation can reconstruct each shown result page.
Later navigation, arrival, and rating outcomes can also inherit request/rank
metadata from the latest matching impression, so useful Adventour journey
signals still count even when the later endpoint did not resend card metadata.
The export keeps the full component payload and also flattens important beta
ranker signals such as intent coverage, group minimum fit, group fairness
penalty, exploration, member coverage, friend-adjusted retrieval, newly served
members, newly covered intents, multi-objective score totals, authenticity,
hidden-gem strength, local-event context, route-anchor strength, event
reservation readiness, event friend/social signal, chain probability, and
popularity.
Those are the first model's feature bridge from the transparent ranker to
learning-to-rank.
`Server/recommender_evaluate.py` turns those examples into request-level ranking
metrics such as hit rate, precision, MRR, and NDCG so ranker changes can be
compared before they are trusted in the app. It also reports positive-outcome
quality for authenticity, hidden-gem strength, chain probability, and combined
local quality. That lets Adventour reject a profile that wins clicks by drifting
toward generic places.

## Stage 3: Contextual Bandits

The hybrid ranker already includes a bounded exploration component for
underexposed, high-authenticity local places that pass quality and chain-risk
gates. That bonus is now controlled by a page-level exploration budget and a
score-frontier check, so a hidden gem can be lifted only when it is close enough
to normal ranking quality and only a small share of the first page can be
experimental.

This follows the practical lesson from contextual-bandit recommendation
research: exploration is useful, but risky contexts should explore less.
[R-UCB](https://arxiv.org/abs/1408.2195) frames mobile context-aware
recommendation as exploration/exploitation with risk-aware throttling, while
[LinUCB](https://arxiv.org/abs/1003.0146) shows how contextual bandits can
learn from recommendation feedback over time. Adventour should stay with bounded
deterministic exploration until beta data is large enough for the promotion gate
to prove a learned or bandit-style ranker improves ranking without hurting local
quality or group fairness. Live learned rerank also requires the artifact's
feature schema to match the current Adventour feature contract; stale artifacts
must be retrained instead of running with missing friend, intent, event, or
objective signals.

## Trip Planning

Planned Adventours should use the same ranked candidates, then add route slots,
swap alternatives, local events, and booking logistics. Flight and stay prices
must come from live providers or manual reservations; Adventour should not invent
those estimates.

Itinerary responses include a `route_explanation` object for the app's compact
"why this route" card. It contains a headline, reasons, cautions, and stats for
stop count, route variety, party fit, booking readiness, local-event readiness,
paired event count, and known local cost range. This explanation is also stored
when a planned Adventour starts so Passport and friend-shared routes can explain
the recommendation later without rebuilding the itinerary.

Booking logistics return a provider-neutral readiness summary. It scores whether
the route has the needed origin, destination, dates, local transport estimates,
and reservation storage support before live flight, lodging, or ticket providers
are connected. Planned route readiness uses that summary so a route with missing
trip inputs or disconnected logistics cannot look as complete as a route that is
ready for provider quotes and saved confirmations.
Each booking component also returns next steps, missing component inputs, search
hints, and provider options. Flight and stay components can point users toward
manual search or future providers without claiming a quote, while `next_best_actions`
gives Discover a compact checklist for what to do before starting the trip.
Local transport also returns setup guidance for known beta cities, such as
transit pass/app setup, rideshare fallback, parking/rental warnings, and source
links. These are planning instructions rather than fare guarantees, so Adventour
can reduce day-of friction without pretending to be a live booking provider.

When multiple scout styles are compared for the same planned route, Adventour
sorts by a comparison rank rather than raw score alone. The rank prioritizes
overall route readiness, filled stop count, stop coverage, local event readiness,
booking readiness, party fit, fewer warnings, more strengths, and lower known
per-person cost.

The reservation storage layer is provider-neutral so bookings can be saved today
and connected to provider APIs later.
Saved reservations use the same Adventour ownership model as sessions: each row
belongs to one user and can optionally attach to an Adventour session. The API
stores reservation type, provider, confirmation code, start/end times, booking
URL, notes, total cost, and metadata, then surfaces those reservations in
Adventour history payloads so completed/planned trips can show the user's saved
flight, stay, local transport, event, and place confirmations.
Session payloads also include a `booking_summary` built from attached
reservations. It reports reservation count, confirmation/link coverage, known
booking cost, known cost per person, type counts, type cost totals, currency,
and a readiness status. This gives Discover, Passport, and shared Adventour
cards the same provider-neutral booking-cost contract instead of each client
recalculating it differently.
When a user starts a planned Adventour from an itinerary, unattached reservation
draft IDs can be claimed into the new session so booking details saved during
planning follow the trip instead of remaining as loose notes.
The started session also preserves route readiness, scout style, trip settings,
route explanation, local event recommendations, filter summary, price breakdown, and booking plan
metadata. Completion adds visit stats without erasing that planning context, and
friend-taken Adventours inherit the same summary so shared routes keep their
recommendation rationale and actionable event/booking links.

## Local Events

Local event recommendations use the same transparent scoring philosophy as
places. Community events and future external connectors are ranked by:

- preference fit to the user's selected tags and route query tags
- authenticity/local signal
- distance from the launch point
- timing fit, including exact travel-date windows
- source quality, so linked local calendars/blogs/community posts beat vague
  unsourced listings
- source freshness/current-detail confidence, so local-blog or external-source
  leads without RSVP links are treated as confirmation-needed instead of fully
  ready event anchors
- reservation readiness, so actionable events surface before research-only
  mentions

Local event results also include a summary with top event score, average score,
reservation-ready count, sourced count, source mix, and readiness score.
Each event carries source metadata with a kind such as `official`, `community`,
`local_blog`, `event_platform`, `external`, or `unsourced`, plus a badge, domain,
trust score, and source freshness score. Planned Adventour route readiness uses
that summary so a route with actionable local events is treated as more complete
than a route with weak, stale, or unsourced event mentions.
The summary also includes `source_summary`, a UI-ready rollup of trusted source
count, unsourced count, reservation-ready count, source badges, and a short
message. Discover uses that to show whether the local-event layer is backed by
official/community/local-blog/event-platform signals or still needs research.

When local events are returned inside a planned Adventour itinerary, the
itinerary service also adds `route_context` to each event it can pair with a
route stop. That context includes the day, slot, nearby stop name, distance to
the stop when coordinates are available, route-fit score, and short reasons such
as category fit or timing fit. This keeps event recommendations useful in the
actual route instead of showing them as a detached destination-wide list.

Users can mark local events as `interested` or `going`. Recommendations expose
aggregate counts and the viewer's own status, then apply a small social-signal
boost so community momentum can help surface events without overpowering
authenticity, timing, source quality, or reservation readiness. When selected
trip members or accepted friends have marked an event, the payload also exposes
friend-only counts and a short accepted-friend preview so Discover can say who
is interested without turning events into a public attendee list.

## Research Notes

- Context-aware recommenders and mobile travel recommendations are a fit because
  location, time, radius, group, and trip mode all change what "good" means.
- Group recommenders need per-member fit and fair aggregation so one person does
  not dominate the route.
- Learning-to-rank is a natural second stage because Adventour already logs
  ranked impressions and user outcomes.
- Contextual bandits are useful later for exploration versus exploitation, but
  they need careful live evaluation and should not be the first beta model.
