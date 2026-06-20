# Adventour v2 Recommender and Place Data Design

## Goal

Adventour should recommend places that are personally relevant, local/authentic, affordable to serve, and usable for both spontaneous "next place" discovery and planned multi-stop trips with friends.

The core product bet is not simply "find highly rated places near me." It is:

- Respect the user's taste.
- Prefer local, distinctive places over chains and generic tourist defaults.
- Blend preferences for a group without letting one person's profile dominate.
- Learn from Adventour's own users over time so the product becomes less dependent on expensive third-party place data.

## What v1 and v2 Already Prove

### Adventour v1

Relevant files:

- `Adventour-v1/server/endpoints/api.adventour.get-adventour-place.js`
- `Adventour-v1/server/endpoints/api.adventour.get-foursquare-places.js`
- `Adventour-v1/iOS/ios/ios/StartViewController.swift`

v1 used Foursquare as the live source of candidate places. The server requested places by category and location, excluded previously rejected ids, then filtered by:

- distance
- rating
- popularity
- chain exclusion via Foursquare's `exclude_all_chains`
- open-now status

The iOS app presented one selected place at a time in a swipe-style flow.

This was a good first implementation because it proved the interaction model. The weakness is that the recommender was not really personalized. Category switches and provider popularity are blunt instruments, and popularity can conflict with the "hidden gem" mission.

### Adventour v2

Relevant files:

- `Adventour-v2/Server/app.py`
- `Adventour-v2/Server/adventour_backend/models.py`
- `Adventour-v2/Server/adventour_backend/utils.py`
- `Adventour-v2/Server/adventour_backend/services/google_services_api.py`
- `Adventour-v2/Server/adventour_backend/social_routes.py`

v2 starts moving in the right direction:

- users have stored onboarding preferences
- user feedback is tracked through accept/reject events
- places are scored against inferred tag weights
- chains are penalized
- "hidden gems" are boosted
- trips, friends, ratings, and group recommendations are sketched

The main issue is that v2 is still mostly tag matching. It also treats provider place data as if it can become Adventour's database, which is the business/legal/cost trap to avoid.

There is also a bug in `get_recommendations`: after resolving an authenticated user, the function later calls `User.query.filter_by(uuid=user_id).first()`, but `user_id` is only defined in the legacy fallback branch.

## Provider Data Boundary

Adventour should treat Google Places and Foursquare as candidate/display providers, not as the core database.

Based on current public docs:

- Google Places allows storing `place_id` indefinitely, but says not to prefetch, cache, or store Places API content beyond allowed exceptions. Use field masks to avoid requesting unnecessary fields because billing is based on the highest SKU requested.
- Foursquare's self-service Places API terms require compliance with caching and rate limits, attribution, and restrictions against bulk exposure or systematic querying. Foursquare's pricing page lists pay-as-you-go pricing and a free tier for Pro endpoint calls.
- Foursquare OS Places is promising for a startup-friendly base POI layer because it advertises an open source global POI dataset with 100M+ POIs, 1000+ categories, and 20+ core attributes.

Design implication: store our own facts, scores, tags, interactions, trips, reviews, and derived features. Store provider ids and attribution metadata. Fetch provider display fields just-in-time or through whatever caching rules the chosen provider contract permits.

## Recommended Architecture

Use a hybrid recommender with four phases:

1. Candidate retrieval
2. Feature enrichment
3. Scoring and ranking
4. Learning from outcomes

### 1. Candidate Retrieval

Candidate retrieval should be cheap, broad, and mostly provider-agnostic.

Inputs:

- latitude/longitude or destination
- radius
- desired mode: spontaneous, trip planning, food, activity, entertainment, nightlife, family, date, etc.
- time availability
- group member ids
- budget/accessibility constraints

Candidate sources, in preferred order:

- Adventour-owned place index for cities we have seeded or learned.
- Foursquare OS Places / OpenStreetMap style open datasets for durable baseline POIs.
- Provider API calls when local data is thin, stale, or needs live details.
- User-created places and Adventour community submissions.

Provider calls should be made server-side only. The app should call Adventour, not Google/Foursquare directly, except for SDK-specific UI cases where terms require client use.

### 2. Feature Enrichment

For every candidate place, compute an Adventour-owned feature vector.

Core place features:

- category taxonomy: restaurant, cafe, museum, park, live music, etc.
- cuisine/activity subtypes
- price band
- distance/travel time
- likely visit duration
- indoor/outdoor
- daypart fit: morning, afternoon, evening, late night
- group fit: solo, couple, friends, family
- chain/local signal
- popularity signal
- hidden-gem signal
- tourist-density signal
- neighborhood/local-context signal
- accessibility constraints where available

Authenticity features:

- non-chain status
- locally unique category or cuisine
- low-to-medium mainstream popularity
- high Adventour user satisfaction
- positive local-language/local-review terms when legally available
- located outside obvious tourist clusters, unless the category strongly justifies it
- user/community "local gem" confirmations

Avoid making "low review count" the main hidden-gem definition. A brand-new mediocre place and an actually beloved local spot can both have low counts. Use it only as one feature.

### 3. Scoring and Ranking

Use a transparent score first:

```text
final_score =
  personal_fit
  + group_fit
  + authenticity
  + quality
  + context_fit
  + novelty
  - chain_penalty
  - tourist_trap_penalty
  - repetition_penalty
  - logistics_penalty
```

Recommended MVP weights:

```text
personal_fit: 30%
group_fit: 20%
authenticity: 20%
quality: 15%
context_fit: 10%
novelty/diversity: 5%
```

For spontaneous Adventours, favor near-term fit:

- closer distance
- open now
- can visit immediately
- not too similar to the last accepted place

For full-trip Adventours, rank itineraries rather than individual places:

- meal/activity cadence
- travel-time minimization
- neighborhood clustering
- diversity across the day
- time-window fit
- group constraints

### 4. Learning From Outcomes

Every interaction should become training data:

- impression: place was shown
- reject: user skipped it
- accept: user wanted to go
- navigation_started
- arrival_confirmed, if consented and privacy-safe
- saved
- shared
- reviewed/rated
- added_to_trip
- swapped_out_of_trip
- friend took this Adventour

Accept/reject is useful, but weak. Arrival, completion, rating, and "would recommend" are much stronger.

## User Preference Model

Create a durable Adventour taste profile for each user.

Store:

- onboarding preferences
- weighted category preferences
- weighted cuisine/activity preferences
- price comfort
- distance tolerance
- novelty tolerance
- chain avoidance strength
- hidden-gem preference strength
- time-of-day patterns
- social context patterns
- negative preferences

Use exponential decay so recent behavior matters more without erasing history.

Example:

```text
new_weight = old_weight * decay + event_weight
```

Event weights:

- reject: -1
- accept: +2
- navigate/start: +3
- arrival/complete: +5
- high rating: +6
- low rating: -5
- saved/shared: +4

## Group Preference Blending

For friends or trip members, avoid simple averaging. Simple averaging creates bland recommendations and hides hard vetoes.

Use three layers:

1. Hard constraints: allergies, budget max, accessibility, age restrictions, distance/time limits.
2. Soft preferences: categories, cuisines, vibe, novelty, price comfort.
3. Fairness/diversity: rotate whose preferences are most represented across a sequence.

For a single place:

```text
group_fit = average(member_fit) - disagreement_penalty + veto_bonus_or_penalty
```

Where:

- average fit rewards places everyone likes.
- disagreement penalty avoids "one person loves it, everyone else hates it."
- veto penalty removes places that violate strong dislikes.

For a multi-stop Adventour:

- include at least one high-fit stop for each member where possible
- avoid repeated cuisines/categories
- explain the blend: "Good match for Maya's art interest and your local-food preference."

## Database Shape

Keep provider data and Adventour-owned data separate.

### places

Adventour's durable place identity.

- id
- canonical_name
- normalized_name
- latitude
- longitude
- geohash or h3_index
- source_confidence
- created_at
- updated_at

Do not blindly store provider descriptions, ratings, reviews, photos, hours, or phone numbers unless the provider license permits it.

### place_provider_refs

- id
- place_id
- provider: google, foursquare, osm, fsq_os_places, user
- provider_place_id
- last_verified_at
- attribution_required

Google `place_id` can be stored indefinitely, but the rest of Google Places content should be treated as fetch/display content unless a specific exception applies.

### place_features

Adventour-owned or license-safe derived features.

- place_id
- category_vector
- cuisine_vector
- activity_vector
- price_band
- chain_probability
- authenticity_score
- hidden_gem_score
- tourist_trap_score
- quality_score_adventour
- popularity_score_adventour
- feature_version

### user_place_events

- user_id
- place_id
- provider_ref_id nullable
- event_type
- event_value
- context: solo, friend_group, trip
- latitude/longitude bucket or city
- occurred_at

### user_preference_vectors

- user_id
- vector_type
- vector_json or vector column
- updated_at
- version

For Postgres, use `pgvector` later. For MySQL, JSON is enough at first; move vector search to a sidecar service when needed.

### adventours

- id
- created_by
- mode: spontaneous, planned, shared
- destination
- started_at
- ended_at
- visibility
- rating_summary

### adventour_stops

- adventour_id
- place_id
- order_index
- status: suggested, accepted, visited, skipped, swapped
- recommended_score_snapshot
- explanation_snapshot

### group_recommendation_sessions

- id
- created_by
- member_ids
- destination
- constraints
- created_at

### place_reviews_adventour

- user_id
- place_id
- rating
- review_text
- local_gem_vote
- touristy_vote
- would_take_friend
- created_at

This is your data moat. It is legally and strategically different from provider reviews.

## Model Roadmap

### Phase 1: Heuristic Hybrid Recommender

Build this first.

- Use current v2 tags and feedback, but normalize them into preference vectors.
- Add chain/local/authenticity features.
- Add group blending.
- Add score explanations.
- Log every impression and outcome.

This can be implemented without ML infrastructure and will outperform v1 because it learns from behavior and has a mission-specific ranking function.

### Phase 2: Embeddings

Once place/user text and enough events exist:

- embed Adventour-owned review text and place tags
- embed user taste summaries
- use vector similarity for candidate expansion
- keep the transparent scoring layer on top

Do not use embeddings as the entire recommender. They are best for semantic matching and cold-start expansion.

### Phase 3: Learning-to-Rank

When there are thousands of real interactions:

- train a ranking model on impressions and outcomes
- target completion/high-rating, not just accept
- include authenticity and diversity as ranking features
- continue applying business rules for chain penalties, constraints, safety, and provider compliance

Possible model families:

- logistic regression or gradient boosted trees for early ranking
- two-tower retrieval model later
- contextual bandit for exploration/exploitation once traffic exists

## Cost Strategy

1. Never call provider APIs from every swipe if avoidable.
2. Retrieve candidate ids in batches.
3. Request only the fields needed for the current screen.
4. Use provider field masks and session tokens where applicable.
5. Cache only what the license permits.
6. Store your own derived scores and user events.
7. Seed cities with open POI data to reduce paid candidate retrieval.
8. Refresh live details only when a user is likely to see or navigate to a place.
9. Add hard usage quotas per user/session during beta.
10. Prefer one paid details call after a high-intent action over many paid details calls for speculative candidates.

## Recommended Next Implementation Slice

Start with the v2 server and implement:

1. A normalized event table for impressions/accept/reject/rate/navigate.
2. A user preference vector builder.
3. A place feature table with chain/authenticity/hidden-gem fields.
4. A recommendation service module separate from Flask route handlers.
5. Group scoring for member ids.
6. Provider abstraction so Google/Foursquare/open data can be swapped.
7. Score explanations returned to the app.

The target API should look like:

```http
POST /api/recommendations
```

Request:

```json
{
  "mode": "spontaneous",
  "location": { "latitude": 40.7128, "longitude": -74.006 },
  "radius_meters": 3200,
  "member_ids": [1, 2],
  "constraints": {
    "price_max": 2,
    "open_now": true,
    "avoid_chains": true
  }
}
```

Response:

```json
{
  "recommendations": [
    {
      "place_id": 123,
      "provider_refs": [{ "provider": "google", "provider_place_id": "..." }],
      "score": 0.87,
      "components": {
        "personal_fit": 0.92,
        "group_fit": 0.81,
        "authenticity": 0.89,
        "quality": 0.77,
        "context_fit": 0.85
      },
      "explanation": "Strong fit for local food, non-chain, and close enough to visit now."
    }
  ]
}
```

## Product Positioning

Wanderlog and classic travel planners optimize organization. Adventour should optimize discovery with trust.

The differentiator is:

- less manual research
- more personal taste
- friend-aware planning
- local-first ranking
- community feedback loops
- one-tap spontaneous adventure or full-day generated Adventour

The database and model should reinforce that positioning from day one.

## Sources Checked

- Google Places API policies: https://developers.google.com/maps/documentation/places/web-service/policies
- Google Places API usage and billing: https://developers.google.com/maps/documentation/places/web-service/usage-and-billing
- Foursquare Places API self-service EULA: https://foursquare.com/legal/terms/apilicenseagreement/
- Foursquare pricing: https://foursquare.com/pricing/
- Foursquare OS Places: https://opensource.foursquare.com/os-places/
