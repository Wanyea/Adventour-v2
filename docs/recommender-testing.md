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
- accept events update user preference vectors
- group scoring prefers a blended option over one-person-only options
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

## How To Read Results

Each recommendation prints:

- total score
- explanation
- personal fit
- group fit
- authenticity
- quality
- context fit
- chain penalty
- price penalty

This makes tuning concrete. For example, if a group scenario barely prefers the blended place, increase the group-fit weight or disagreement penalty. If too many random hidden gems beat obvious taste matches, reduce the hidden-gem/authenticity weight.

## Recommended Next Scenarios

Add scenarios for:

- vegan/allergy hard constraints
- wheelchair/accessibility constraints
- nightlife vs daytime recommendations
- tourist-heavy city center vs neighborhood discovery
- repeated recommendations after rejects
- full-day Adventour route diversity

Keep each scenario small enough that a human can read the ranked output and say whether it feels right.
