# Recommender Testing

Adventour recommendations should be tested in two ways:

1. Automated behavior tests: fast pass/fail checks for ranking invariants.
2. Scenario lab runs: readable ranked output for product tuning.

## Automated Tests

Run:

```powershell
cd D:\source\Adventour\Adventour-v2
Server\.venv\Scripts\python.exe -m pytest -q Server
```

Current tests cover:

- hidden gems outrank chains for a local-food user
- hard include/exclude tag-group constraints filter candidates before scoring
- hidden gems and generic-risk picks return explainable authenticity evidence
- accept events update user preference vectors, with recent behavior outweighing stale history and stale vector caches rebuilding automatically
- hidden-gem accepts and chain rejections affect future authenticity/chain scoring
- controlled exploration lifts high-authenticity, underexposed local picks until
  they have already been shown
- exploration budget caps first-page experimental picks and blocks exploratory
  boosts when the candidate is too far outside the normal score frontier
- positive place interactions learn a soft price comfort zone used when no explicit budget filter is selected
- passive impressions are logged for exposure/freshness but do not train taste vectors
- group scoring prefers a blended option over one-person-only options
- group scoring penalizes places where the lowest-fit traveler is likely left out
- group scoring only accepts selected members who are accepted friends
- group responses include member summaries and per-person fit details
- group reranking promotes strong matches for under-served party members early in the basket
- time-of-day context nudges morning/evening-appropriate places and explains the timing fit
- diversified result pages preserve the top pick while mixing experience groups early in the basket
- diversified result pages cover user/friend intent groups such as coffee,
  outdoors, arts/culture, food, and nightlife
- recent impressions deprioritize repeated places so fresh local picks get a chance
- exhausted repeats include history and explanation signals when rejected/accepted places must be shown again
- planned itineraries assemble slot-based routes with swap alternatives
- planned itinerary swaps preserve route groups so Discover can refresh route mix, party fit, and known estimates
- planned itinerary slot scoring can rebalance toward a traveler underserved by earlier stops
- planned itineraries summarize per-day party fit so friend trips show whether the route is balanced
- planned itineraries rerank slots with route diversity so full routes do not repeat the same category too often
- planned itineraries support day trip, weekend, and short vacation planning modes
- planned itineraries support relaxed/balanced/full pace and budget/flexible/splurge price preferences
- planned itineraries accept origin and travel dates so flight/stay logistics can move from missing-inputs to provider-ready
- planned itineraries return known cost/logistics estimates without inventing flight or stay prices
- planned itineraries include a booking plan with flight/stay provider status, local transport estimates, and reservation storage metadata
- local transport planning returns walk, train/bus, rideshare, and rental options with a recommended mode from route shape
- planned routes can be started as active Adventour drafts with the first unfinished stop surfaced first
- local event recommendations can surface community events with source and reservation links
- local event ranking prefers actionable source/reservation links when other
  event signals are similar
- route readiness uses local event summary quality instead of treating all event
  matches as equally ready
- Discover can submit community local events back to the backend for recommendation refresh
- impressions are logged when recommendations are returned
- price constraints apply penalties

These tests use in-memory SQLite and mock providers. They do not call Google.

## Real Place Tests

Real place tests are opt-in because they call Places API (New) and can spend quota.

Make sure `Server/.env.local` contains:

```bash
GOOGLE_API_KEY=your_server_key_here
```

Then run:

```powershell
cd D:\source\Adventour\Adventour-v2
$env:ADVENTOUR_RUN_REAL_PLACE_TESTS="true"
Server\.venv\Scripts\python.exe -m pytest -q Server\tests\test_real_places_integration.py
Remove-Item Env:\ADVENTOUR_RUN_REAL_PLACE_TESTS
```

These tests use a tight radius near the Android emulator's default Mountain View location. Keep them out of the normal test loop; use them when changing provider code, Google configuration, or recommendation scoring.

## Scenario Lab

Run:

```powershell
cd D:\source\Adventour\Adventour-v2
Server\.venv\Scripts\python.exe Server\recommender_lab.py local_food
Server\.venv\Scripts\python.exe Server\recommender_lab.py group_blend
Server\.venv\Scripts\python.exe Server\recommender_lab.py budget
```

Use JSON output when you want to inspect the full response:

```powershell
Server\.venv\Scripts\python.exe Server\recommender_lab.py group_blend --json
```

Compare named scoring profiles without touching app code:

```powershell
Server\.venv\Scripts\python.exe Server\recommender_lab.py local_food --scoring-profile phase1_balanced
Server\.venv\Scripts\python.exe Server\recommender_lab.py local_food --scoring-profile authenticity_forward
Server\.venv\Scripts\python.exe Server\recommender_lab.py group_blend --scoring-profile group_friendly
```

You can also test planned Adventour routes without spending provider quota:

```powershell
Server\.venv\Scripts\python.exe Server\recommender_lab.py planned_city --planned --scoring-profile phase1_balanced
```

To compare every scout style for the same planned city scenario:

```powershell
Server\.venv\Scripts\python.exe Server\recommender_lab.py planned_city --planned --all-profiles
```

The planned-route lab prints route readiness, filled stop count, strengths,
warnings, known per-person estimate, each selected stop, and the first swap
idea with its swap-impact reason. Use this before changing weights so you can
see whether a profile actually improves the whole route, not only the top card.

Both basket and planned-route lab runs also print a `Scenario readiness`
verdict. This is the beta-testing gate for a single launch point:

- `ready`: strong enough for trusted friend testing.
- `watch`: usable, but keep an eye on the listed tradeoffs.
- `needs_attention`: fix the listed issues before trusting the result.

The readiness report checks candidate depth, provider health, local/authentic
mix, hidden-gem presence, generic-chain risk, explanation coverage, variety,
first-swipe variety, model confidence, and group fit when friends are included.
Planned routes additionally check route score, slot coverage, swap options,
route model confidence, trip logistics readiness, booking/logistics usefulness,
local event readiness, and per-person price estimate coverage.

The app uses the same idea through:

```text
POST /api/recommendations/itinerary/compare
```

It returns compact summaries for each requested `scoring_profile`, sorted by a
route-readiness comparison rank. The tie breakers favor filled stops, event
readiness, booking readiness, party fit, fewer warnings, more strengths, and
lower known per-person cost. Discover shows these summaries in the planned
Adventour card so a tester can switch scout styles before rebuilding the route.
The backend reuses the same provider candidate fetch across those profiles, so
the app compares ranking behavior without multiplying Google Places calls for
the same launch point.

## Real Place Lab

Use the live lab when you want to see how the ranking feels against actual provider data without opening the mobile app:

```powershell
cd D:\source\Adventour\Adventour-v2
Server\.venv\Scripts\python.exe Server\real_place_lab.py --tags cafe restaurant park --lat 37.421998333333335 --lng -122.084 --radius 1200 --limit 8
```

Try different locations and taste mixes:

```powershell
Server\.venv\Scripts\python.exe Server\real_place_lab.py --tags museum art_gallery cafe --lat 40.7794 --lng -73.9632 --radius 1600
Server\.venv\Scripts\python.exe Server\real_place_lab.py --tags bakery cafe book_store --lat 47.6097 --lng -122.3331 --radius 1400
```

Use this to tune the recommender manually: inspect the score components, decide what feels wrong, then encode the lesson as either a deterministic scenario test or a small weighting change.

The live lab also prints the same `Scenario readiness` report used by the
deterministic lab. When testing real cities, use it as the first pass:

```powershell
Server\.venv\Scripts\python.exe Server\real_place_lab.py --tags cafe restaurant market art_gallery --lat 28.5383832 --lng -81.3789269 --radius 3200 --limit 12 --scoring-profile authenticity_forward
```

For trusted friend testing, aim for `ready`. A `watch` result can still be
useful for close beta feedback if the warnings are acceptable. Treat
`needs_attention` as a tuning prompt: adjust radius, tag groups, scout style, or
provider setup before judging the user experience.

The live lab can also use named profiles:

```powershell
Server\.venv\Scripts\python.exe Server\real_place_lab.py --tags cafe restaurant park --lat 40.7306 --lng -73.9352 --radius 1600 --scoring-profile authenticity_forward
```

When you are ready to spend live Places quota on full route quality, use the
planned live lab:

```powershell
Server\.venv\Scripts\python.exe Server\real_place_lab.py --planned --tags cafe restaurant market art_gallery --lat 40.7306 --lng -73.9352 --radius 3200 --limit 20 --destination-label "NYC"
```

You can compare all scout styles against the same live destination:

```powershell
Server\.venv\Scripts\python.exe Server\real_place_lab.py --planned --all-profiles --tags cafe restaurant market art_gallery --lat 40.7306 --lng -73.9352 --radius 3200 --limit 20 --destination-label "NYC"
```

`--all-profiles` calls the live provider once per profile, so use it
intentionally. For normal tuning, start with `Server/recommender_lab.py`
because it is deterministic and free.

For a small trusted-friend readiness sweep across representative cities, run:

```powershell
Server\.venv\Scripts\python.exe Server\real_place_lab.py --suite friend_beta
```

This suite currently checks:

- Orlando spontaneous local picks
- Austin planned day route
- Chicago friend-blended spontaneous picks
- Seattle friend-balanced planned route
- NYC planned route with event-friendly tags

It prints one line per scenario with `ready`, `watch`, or `needs_attention`,
the friend-test verdict, the top pick, and first next action. Use `--json`
when you want a machine readable report:

```powershell
Server\.venv\Scripts\python.exe Server\real_place_lab.py --suite friend_beta --json
```

Save an acceptance artifact before sending a trusted-friend build:

```powershell
Server\.venv\Scripts\python.exe Server\real_place_lab.py --suite friend_beta --output Server\instance\recommender\friend-beta-readiness.json --fail-on-suite-gate
```

The saved suite report includes:

- `friend_testable_count`: how many scenarios passed the stricter verdict.
- `dimension_summary`: pass/warn/fail counts for dimensions like `model_signal`,
  `first_swipes`, `friends`, `trip_logistics`, and `social_events`.
- `pipeline_issue_summary`: counts the first pipeline issue across scenarios
  such as retrieval supply, filter pressure, local authenticity, variety,
  friend blend, or taste-model signal.
- per-scenario `test_verdict`: compact score, dimensions, blockers, and next
  actions.
- per-scenario `pipeline_diagnostic`: the primary issue, raw/returned counts,
  skipped-candidate summary, and next action for debugging why a city or filter
  mix felt weak.
- per-scenario `failed_checks`: readiness checks that need tuning before the
  scenario should be trusted.
- per-scenario `friend_readiness` when the scenario includes synthetic friends.

By default, the suite gate requires every scenario to be at least `watch`,
meaning no scenario is in `needs_attention`. Use a stricter all-ready gate when
you want to block unless every scenario is fully friend-ready:

```powershell
Server\.venv\Scripts\python.exe Server\real_place_lab.py --suite friend_beta --min-suite-status ready --fail-on-suite-gate
```

The suite calls the live provider once per scenario. Keep it out of normal
development loops; use it before a trusted-friend test build, after provider
changes, or when tuning ranking weights for real cities.

For an ad hoc live group check, pass one `--friend-tags` group per synthetic
friend:

```powershell
Server\.venv\Scripts\python.exe Server\real_place_lab.py --tags cafe restaurant market --friend-tags museum art_gallery park --lat 41.8781 --lng -87.6298 --radius 8000 --limit 16 --scoring-profile group_friendly
```

That creates accepted in-memory lab friends, blends their preferences through
the same group recommender path as Discover, and includes group-fit checks in
the scenario readiness report.

Add `--planned` to check the full route builder with the same synthetic party:

```powershell
Server\.venv\Scripts\python.exe Server\real_place_lab.py --planned --tags cafe bakery market --friend-tags museum art_gallery park --lat 47.6062 --lng -122.3321 --radius 8000 --limit 24 --scoring-profile group_friendly --destination-label "Seattle"
```

## Scoring Profile Tuning

The base score and reranking bonuses live in the `ScoringProfile` dataclass in
`Server/adventour_backend/services/recommender_service.py`. Keep tuning changes
small and named:

1. Add or adjust a scenario/test that captures the behavior you want.
2. Tune one or two profile weights.
3. Run the scenario lab for readable ranked output.
4. Run offline evaluation after you have real swipe/rating data.

Recommendation responses include `components.scoring_profile` and
`ranking.scoring_profile`, so exported examples can be compared by profile once
we start testing multiple ranker personalities.

The backend accepts a request constraint named `scoring_profile`, and local
backend runs can set `ADVENTOUR_SCORING_PROFILE` as a default. Current profiles:

- `phase1_balanced`: the default production-ish beta behavior.
- `authenticity_forward`: gives more lift to hidden-gem/local signals and more
  pressure against chain-like places.
- `group_friendly`: gives friend/group fit and party coverage more influence.
- `fresh_discovery`: pushes harder against repeat exposure and toward varied
  discovery.

## How To Read Results

Each recommendation prints:

- total score
- explanation
- personal fit
- group fit
- group minimum fit
- group fairness penalty
- route member rebalance bonus
- intent coverage bonus
- exploration
- authenticity
- quality
- context fit
- chain penalty
- price penalty

This makes tuning concrete. For example, if a group scenario barely prefers the blended place, increase the group-fit weight or disagreement penalty. If too many random hidden gems beat obvious taste matches, reduce the hidden-gem/authenticity weight.

## Training Export

When beta testers generate enough interaction history, export labeled examples for a future learning-to-rank model:

```powershell
cd D:\source\Adventour\Adventour-v2
Server\.venv\Scripts\python.exe Server\recommender_training_export.py --output recommender-training.jsonl
```

Use CSV for spreadsheet inspection:

```powershell
Server\.venv\Scripts\python.exe Server\recommender_training_export.py --format csv --output recommender-training.csv
```

Labels are intentionally simple for the first model:

- `accept`, `navigate`, `arrival`, `save`, and `share` become positive labels.
- `reject` becomes a negative label.
- ratings become positive at 4-5, negative at 1-2, and neutral at 3.
- examples include `outcome_weight` so stronger signals such as ratings,
  navigation, saves, shares, and arrivals can matter more than lightweight
  swipes during offline tuning.
- pure impressions are logged but not exported as labels yet.
- recommendation impressions and later swipe outcomes carry `request_id` and
  `rank_position` so offline evaluation can reconstruct what was shown together.
- later `navigate`, `arrival`, and `rate` events inherit request/rank metadata
  from the latest matching impression when the event itself does not carry it.
- CSV/JSONL examples include flattened ranker signals for intent coverage,
  member coverage, group minimum fit, group fairness penalty, exploration,
  authenticity, hidden-gem strength, chain probability, local-event fit,
  event route-anchor strength, event reservation readiness, event friend/social
  signal, and popularity.
- JSONL examples also carry richer diagnostic context such as member-fit rows,
  explanation details, query tags, target intent groups, and authenticity
  evidence. CSV exports flatten those into scan-friendly counts and labels.

## Offline Ranking Evaluation

After exporting examples, run the evaluator to measure whether accepted or highly
rated places are appearing near the top of each recommendation request:

```powershell
cd D:\source\Adventour\Adventour-v2
Server\.venv\Scripts\python.exe Server\recommender_evaluate.py --input recommender-training.jsonl
```

You can also evaluate the local dev database directly:

```powershell
Server\.venv\Scripts\python.exe Server\recommender_evaluate.py
```

Useful metrics:

- `hit@k`: share of recommendation requests with a positive outcome in the top `k`.
- `precision@k`: how many of the top `k` labeled outcomes were positive.
- `avg_label@k`: average label strength in the top `k`, including neutral ratings.
- `weighted_avg@k`: average label strength adjusted by `outcome_weight`, so
  stronger outcomes can influence tuning more than casual swipes.
- `ndcg@k`: rewards positive outcomes appearing higher in the ranked list.
- `MRR`: reciprocal rank of the first positive outcome, averaged by request.
- `quality`: averages authenticity, hidden-gem strength, chain probability, and
  combined local quality for positive outcomes that include place-quality fields.
- `group balance`: for accepted group outcomes, reports average lowest-member
  fit, average member-fit spread, and the share of positives where at least one
  traveler looked under-served.
- `event anchors`: for accepted event-backed outcomes, reports event-backed
  positive rate, average event fit, route/action anchor strength, reservation
  readiness, and friend/social signal. This is the quality line to watch when
  testing NYC-style local markets, pop-ups, friend meetups, and other timely
  experiences.
- `guardrails`: pass/warn/fail checks for Adventour's mission fit. They flag
  chain-heavy accepted outcomes, weak authenticity, low hidden-gem signal, and
  group recommendations where the lowest-fit traveler may be under-served.
  Event-backed outcomes also get guardrails for anchor strength and reservation
  readiness so timely recommendations stay actionable.

The evaluator reports examples skipped for missing `request_id` or
`rank_position`. Early data will be sparse because pure impressions are logged
but not labeled yet; this is still enough to compare ranker changes against real
accept/reject/rating behavior.

When examples include `scoring_profile`, the report also prints top-k metrics by
profile. Use that before keeping a new ranker profile, otherwise one strong
manual test can trick you into trusting a change that made the broader basket
worse.

The evaluator also reports top-k metrics by recommendation segment. Current
segments include:

- `solo` and `group`
- `friend_adjusted` when a friend suggestion chip influenced retrieval
- `local_authentic` and `hidden_gem`
- `event_backed`
- `generic_risk`
- `low_signal` for cold-start or sparse-profile examples

Use segment metrics before promoting a learned model. A model that improves
overall NDCG but regresses `group`, `friend_adjusted`, `event_backed`, or
`local_authentic` should stay behind the transparent ranker until more data or
better features fix that regression.

Prefer profiles that improve both ranking metrics and local-quality metrics.
If two profiles have similar hit rate or NDCG, keep the profile with higher
positive authenticity/hidden-gem quality and lower positive chain probability.
That keeps offline tuning aligned with Adventour's local-authentic mission
instead of optimizing for generic but clickable places.

For friend Adventours, also compare `group balance`. A high hit rate is not good
enough if the accepted picks repeatedly work for one person and leave another
with low fit. Prefer profiles that keep `average_lowest_member_fit` healthy,
keep `average_member_fit_spread` low, and avoid a rising
`underserved_positive_rate`.

Treat guardrail failures as a stop sign before keeping a ranking change. A
profile can improve hit rate while becoming too generic, too chain-friendly, or
too uneven for a friend group. `unknown` guardrails mean the export does not
have enough matching fields yet; keep collecting swipe/rating data before using
those checks as proof.

## Learned Ranker Baseline

Once you have enough exported examples, train the dependency-free learned
baseline:

```powershell
cd D:\source\Adventour\Adventour-v2
Server\.venv\Scripts\python.exe Server\recommender_refresh_model.py
```

That one command exports the local dev database to:

```text
Server\instance\recommender\recommender-training.latest.jsonl
```

Then it trains:

```text
Server\instance\recommender\recommender-model.latest.json
```

It also writes baseline and learned-rerank evaluation JSON next to the model.
The console report prints training data health, training/validation quality, the
strongest learned signals, MRR deltas, top-k deltas, event-anchor deltas, and
guardrail status. If it says there are not enough labeled examples yet, collect
more accepts, rejects, ratings, arrivals, saves, or shares in the app and rerun
it.

`Training data health` is the quick reality check before trusting learned
weights. It reports coverage for labeled outcomes, distinct recommendation
requests, group/friend-adjusted examples, event-backed examples,
source/RSVP-ready events, and friend/social event signals. `watch` is acceptable
for local smoke tests, but before a trusted-friend build you want the health
checks moving toward `ready`, especially `group_friend_signal`,
`event_anchor_signal`, and `event_social_signal`.

The refresh command also prints `Learned beta readiness` and writes the same
payload into the model artifact as `live_readiness`. Treat this as the source of
truth before testing in Discover:

- `ready: true` means the artifact matches the current feature schema and passed
  promotion gates.
- `status: needs_evaluation` means a model was trained but has not been through
  the refresh/evaluation gate yet.
- `status: blocked` means the schema or promotion gate failed; keep Auto scout
  on the transparent profiles until the reason is fixed.

Start the backend with the latest local model:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev-backend.ps1 -LearnedRanker
```

Then choose `Learned beta` in Discover's scout style filter. The backend will
still run the transparent balanced ranker first, then let the learned model
rerank that candidate set. If the app says the learned model is not loaded,
rerun the refresh command and restart the backend with `-LearnedRanker`.

You can still run the individual steps by hand when you want deeper inspection.

```powershell
cd D:\source\Adventour\Adventour-v2
Server\.venv\Scripts\python.exe Server\recommender_train_model.py --input recommender-training.jsonl --output recommender-model.json
```

You can also train directly from the local dev database:

```powershell
Server\.venv\Scripts\python.exe Server\recommender_train_model.py --output recommender-model.json
```

The baseline is a small logistic learning-to-rank model over Adventour's own
transparent ranker signals: personal fit, group fit, authenticity,
hidden-gem strength, chain risk, time fit, exploration, diversity bonuses,
friend-adjusted retrieval, newly covered intent groups, newly served party
members, multi-objective score totals, price comfort, local-event context, and
event route-anchor/social signal, and repeat freshness. It writes a JSON artifact with feature weights, feature
normalization stats, log loss, pairwise request accuracy, and the strongest
positive/negative signals.

Do not treat this as production ranking just because it trains. Use it as a
comparison scout:

1. Export real beta data.
2. Train `recommender-model.json`.
3. Compare its top weights against Adventour's mission.
4. Run offline evaluation and guardrails before changing live scoring.

Compare shown-order rankings against the learned model rerank:

```powershell
Server\.venv\Scripts\python.exe Server\recommender_evaluate.py --input recommender-training.jsonl --model recommender-model.json
```

The report prints the original shown-order evaluation, the learned rerank
evaluation, and deltas for MRR, hit rate, precision, weighted labels, and NDCG.
It also prints a promotion gate. The gate requires enough evaluated requests,
ranking improvement, safe authenticity/chain guardrails, preserved top-result
exposure quality, preserved group balance, preserved critical recommendation
segments, and preserved event/social anchor quality. The learned model only
deserves app integration when the gate says `pass`.

The exposure-quality line is deliberately separate from accepted-outcome
quality. A reranker changes what Adventour shows first, so it must not improve
click metrics by pushing generic or chain-like places higher in the basket.

To try the model in live backend recommendations, start the backend with:

```powershell
$env:ADVENTOUR_LEARNED_RANKER_PATH = "D:\source\Adventour\Adventour-v2\Server\instance\recommender\recommender-model.latest.json"
```

Or use the dev script shortcut:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev-backend.ps1 -LearnedRanker
```

Then include `"learned_rerank": true` in recommendation constraints, or select
`Learned beta` from the app. The transparent ranker still runs first; the
learned model only reranks that candidate set before the normal diversity pass.
Responses include
`learned_rerank` plus per-card `learned_score`/`learned_rank_position` when it
is active. Keep this opt-in until offline metrics, guardrails, group balance,
and real tester feel all agree.

Live learned rerank also checks the artifact's `feature_schema_version` and
`feature_names` before it can change ordering. If a response reports
`feature_schema_mismatch`, `feature_schema_version_mismatch`, or
`feature_names_missing`, retrain the model with the current code before testing
the learned beta. Do not use the dev override for stale artifacts; old models
can silently ignore newer friend, intent, objective, or event signals.

If the model learns that chain-like popularity is stronger than authenticity,
that is not a win; it means the data or ranker needs a closer look.

## Recommended Next Scenarios

Add scenarios for:

- vegan/allergy hard constraints
- wheelchair/accessibility constraints
- nightlife vs daytime recommendations
- tourist-heavy city center vs neighborhood discovery
- repeated recommendations after rejects
- full-day Adventour route diversity

Keep each scenario small enough that a human can read the ranked output and say whether it feels right.
