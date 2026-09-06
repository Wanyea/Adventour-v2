# Adventour v2 — Where We Are

Start here. This file answers "what phase are we in" so nothing gets lost between sessions.

**Last updated:** 2026-08-18

---

## Current position

> **Phase 1 — Data foundation. Complete and running on a device.**
> Scope A is done. Next decision: which of Scope B / C / D to open.

The index is built, filtered, scored and deduplicated; the app reads it on an emulator with zero
paid API calls; swipe feedback persists. The legacy Phase-1 recommender has been deleted — there is
one code path and no feature flag.

**The UI has still never been touched.** The app is frozen at its `main` baseline (see `../AGENTS.md`).

---

## Phases

| # | Phase | Status | Scope doc |
|---|---|---|---|
| 0 | **Decisions** — provider stack, cost model, licensing | ✅ done | `sourcing-cost-decision-brief.md` |
| 1 | **Data foundation** — ingest, index, filter, score, dedup, serve | ✅ **done** | `active-scope.md` (Scope A) |
| 2 | **Ranking** — scoring, weights, explanations | ⛔ **blocked** — no measurable signal yet | Scope B |
| 3 | **Evaluation** — how we know a recommendation is good | ✅ **done** | `scope-c-evaluation.md` |
| 4 | **Group blending** — friend-aware recommendations | ⬜ not started | Scope D |
| 5 | **Local events & third spaces** | 🔍 researched; **in scope for the next agent** (HANDOFF §5F) | `scope-e-local-events.md` |

Deferred by explicit decision, not forgotten:

- **Full-trip planning** (TSPTW/OPTW sequencing) — gated on a paid hours licence. Brief §9.
- **Paid hours data** — revisit when trip planning is active or a metro shows real usage. Brief §10b.
- **Closure verification** — lazy per-place, persisted via `suppressed_place`. Brief §10b/§10c.
- **Ticket / reservation linking** — noted, `external_links` reserved. Brief §10.
- **International / China** — needs a provider adapter and GCJ-02 transform. Brief §10.

---

## Scope A gates — all passed

| gate | question | verdict |
|---|---|---|
| 1 | Do independents have websites? | ✅ 73.6% |
| 2 | Can we extract hours from them? | ⚠️ ~19% only |
| 3a | Does OSM have hours? | ❌ 1.4% of independents — ruled out |
| 3b | Does subpage following help? | ⚠️ +5 points |
| 4 | Can we buy storable hours? | ⚠️ not from any API — deferred |
| 5 | Seed loaded and queryable? | ✅ 19,385 places |
| 6 | Ground truth from a local | ✅ 131 labels — coverage solved, quality was the problem |
| 7 | Junk filter | ✅ 85.7% recall, **0 false positives**, hit rate 33%→55% |
| 8 | Authenticity scoring | ⚠️ **AUC 0.64 out of sample** — see Gate 12, the 0.840 was overfit |
| 9 | Deduplication | ✅ 827 records collapsed; Washington Oaks 6 → 2 |
| 10 | **Running on a device** | ✅ deck served from the index, 0 Google calls |
| 11 | Legacy removal | ✅ `app.py` 1,240 → 904 lines, one code path |
| 12 | **Orlando labels — did it generalise?** | ❌ **no.** Score 0.954→0.639; 34% of served places are junk |

Full detail and reproduction commands: `active-scope.md`.

## The index today

| | |
|---|---:|
| raw Overture records ingested | 112,682 |
| Adventour-relevant | 19,385 |
| KEEP after junk filter | 15,311 |
| **distinct entities after dedup** | **14,484** |
| servable in Palm Coast | 513 |
| **junk still served in Orlando** | **34.3% of sampled** |

---

## The three open problems

Carried forward deliberately. Each is measured, not suspected.

1. **The score barely works out of sample.** AUC 0.639 in Orlando versus 0.954 on the metro it was
   fitted to. It is a weak floor, not a ranker, and 490 places still share one value. Only
   behavioural data breaks the tie — which is why `place_event` snapshots the score at decision time.
2. **~9% of the seed is permanently closed** and no free signal detects it (mean Overture confidence
   0.90). Plan is lazy per-place verification with a persisted suppression list.
3. **~80% of independents have no obtainable hours.** Category priors cover the gap for spontaneous
   mode; trip planning needs a paid licence.

---

## Documents

| file | what it is |
|---|---|
| `active-scope.md` | Scope A contract and every gate result, with reproduction commands |
| `sourcing-cost-decision-brief.md` | Provider stack, cost model, licensing, cold start, national scale |
| `recommender-data-design.md` | Architecture and model roadmap. **Partly superseded** — its `places` schema and its authenticity signals were both disproved by Gates 6–8 |
| `development-testing-strategy.md` | Local dev / phone / deploy workflow |
| `scope-c-evaluation.md` | The evaluation harness: what it measures and why |
| `scope-e-local-events.md` | Local events / third spaces — provider landscape and open questions |

`archive/` — documents the pre-Scope-A backend. That backend no longer exists; keep for history only.

---

## Working rules

See `../AGENTS.md`:

- One scope at a time. UI is frozen unless the scope is a UI scope.
- No file in `AdventourApp/` over 1,200 lines.
- No paid API call may populate a swipe deck.
- **The checkpoint is the app on a real device, not a passing test.**

---

## Running things

```powershell
# Postgres (Windows service, port 5432, db `adventour`)
$env:PGPASSWORD="adventour_dev"
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost -d adventour

# Backend (serves the index; ENV_FILE sets ADVENTOUR_USE_LOCAL_INDEX + dev auth)
cd Server; $env:ENV_FILE=".env.local"; .venv\Scripts\python.exe app.py

# App on the emulator
& "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -avd Pixel_7_API_30
cd AdventourApp; adb reverse tcp:8081 tcp:8081; adb reverse tcp:8080 tcp:8080
adb emu geo fix -81.2079 29.5844          # downtown Palm Coast
npx react-native start                     # then: adb shell am start -n com.adventourapp/.MainActivity
```

```powershell
# Evaluation harness, from Server/
.venv\Scripts\python.exe -m evaluation.harness            # report vs baseline
.venv\Scripts\python.exe -m evaluation.harness --strict   # exit 1 on regression

# Data pipeline, from Server/  (ADVENTOUR_PG_DSN must be set)
.venv\Scripts\python.exe data_pipeline\pull_overture.py         # re-pull Overture
.venv\Scripts\python.exe data_pipeline\load_postgres.py         # rebuild `places`
.venv\Scripts\python.exe data_pipeline\apply_junk_filter.py     # gate 7 tiers
.venv\Scripts\python.exe data_pipeline\score_authenticity.py    # gate 8 scores
.venv\Scripts\python.exe data_pipeline\run_dedup.py             # gate 9 (DEDUP_APPLY=1 to write)
.venv\Scripts\python.exe data_pipeline\verify_tag_mapping.py    # asserts tag groups are correct
.venv\Scripts\python.exe data_pipeline\eval_junk_filter.py      # scores the filter vs labels
.venv\Scripts\python.exe data_pipeline\make_deck_preview.py     # qa/deck_preview.html
```

Order matters after a re-ingest: `load_postgres` → `apply_junk_filter` → `score_authenticity` → `run_dedup`.
