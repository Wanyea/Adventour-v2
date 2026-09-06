# Adventour v2 — Working Agreement

Adventour recommends local, authentic places (food, activities, entertainment) and discourages chains
and generic tourist defaults. Swipe left to reject, right to accept and get directions.

## Scope discipline

Work happens in **one scope at a time**. The active scope is named in `docs/active-scope.md`.
If a change doesn't belong to the active scope, don't make it — note it and move on.

Current scope sequence:

- **A — Candidate sourcing & cost control** (open data ingestion, H3 index, offline features) — **done**
- **B — Ranking & authenticity scoring** — next
- **C — Evaluation harness**
- **D — Multi-user preference blending**

Do not begin a scope without an approved plan. Do not start the next scope until the current one merges.

## UI freeze

The UI is **locked** unless the active scope is explicitly a UI scope.

Backend and algorithm work must not change screens, navigation, styling, or component structure.
A recommender change may alter *what data* a screen receives; it may not alter *how the screen looks*.

Baseline as of 2026-08-17 (`main`) — these are the only screens, and their sizes are the reference:

| File | Lines |
|---|---|
| `AdventourApp/HomeScreen.tsx` | 1,085 |
| `AdventourApp/Screens/ProfileScreen.tsx` | 971 |
| `AdventourApp/Screens/SocialScreen.tsx` | 685 |
| `AdventourApp/src/components/RecommendationDeck.tsx` | 572 |
| `AdventourApp/src/components/AdventourJourneyPanel.tsx` | 496 |
| `AdventourApp/Screens/FirebaseAuthScreen.tsx` | 399 |

Hard rules:

- **No file in `AdventourApp/` may exceed 1,200 lines.** If a change would push it over, stop and propose
  an extraction instead. (For context: an unsupervised agent run grew `HomeScreen.tsx` to ~22,600 lines and
  made the app unnavigable. That is the failure this rule exists to prevent.)
- No new top-level screens or navigation entries without explicit approval.
- No restyling, no palette changes, no layout rewrites as a side effect of other work.
- No new UI dependency without asking.

## Verification

**The checkpoint is the app running on a real device, not a passing test.**

Tests are necessary but they are not evidence that a recommendation is *good*. Before claiming a
recommender change works, show the deck on the phone and the score breakdown that produced it.

- Android only for local dev — this is a Windows machine, iOS can't build here.
- Launch: `npm run android:phone` (or `android:local:pixel7` for the emulator) from `AdventourApp/`.
- `adb` is available; screenshots via `adb exec-out screencap -p`.

Do not write large speculative test suites for unvalidated designs. Test what exists and is agreed.

## Data boundary

This is a legal constraint, not a preference. See `docs/sourcing-cost-decision-brief.md`.

- **Storable indefinitely, ours:** Overture Maps Places, FSQ OS Places, and everything we derive from them.
  Google `place_id` values.
- **Never stored:** Google Places content — names, ratings, reviews, hours, photos, addresses.
  Fetch just-in-time for display and discard. (Google lat/lng may be cached at most 30 consecutive days.)
- **No paid API call may populate a swipe deck.** Candidate retrieval runs against our own index.
  Google is touched only after a high-intent action, behind a per-user quota.

- **Suppression list (approved 2026-08-17):** we may store a Google `place_id` plus our own
  `suppressed_at` timestamp to stop showing a place once Google reports it closed. Store **only**
  the id and our own flag — never `businessStatus`, never the reason string, never any other
  returned field. The distinction that makes this sound: `place_id` is storable indefinitely, and a
  list of ids we have chosen not to show is our editorial record, not a cache of Google content.

If a change would put provider content into our database, stop and raise it.

## Stack

- **App:** React Native 0.77 (bare, not Expo), TypeScript, React Navigation 7, Firebase Auth.
- **Server:** Flask, SQLAlchemy, in `Server/adventour_backend/`. Services live in `services/`,
  routes stay thin.
- **DB:** Postgres 17 on `localhost:5432`, database `adventour`. **No PostGIS.** H3 cell ids are
  computed in Python and stored as indexed text columns; radius queries are an H3 `grid_disk`
  lookup plus a Haversine filter. This was a deliberate choice -- `h3-pg` has no reliable Windows
  build and nothing in Scope A needs polygon operations.
- **Index:** `places` (built by `Server/data_pipeline/`), `place_event`, `suppressed_place`.
  The Phase-1 recommender tables were deleted 2026-08-18; there is one code path, no feature flag.

## Reference

- `docs/recommender-data-design.md` — architecture, scoring, blending, model roadmap. Still authoritative,
  except the `places` schema section, which the decision brief supersedes.
- `docs/sourcing-cost-decision-brief.md` — provider stack, cost model, cold-start signals.
- `Adventour-v1/` — the 2022 implementation. Proved the swipe model; recommender was not personalized.
- The `codex` branch is **reference only**. Do not port code from it without explicit approval.
