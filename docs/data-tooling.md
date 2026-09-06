# Owner data-tooling runbook

Phase 1 work in progress, 2026-09-05. Commands below run from `Server/` using the
existing virtual environment. PostgreSQL must be running; `ADVENTOUR_PG_DSN`
selects the database (default: localhost:5432, postgres user, adventour database).
Keep credentials in your environment, never in returned files or committed docs.

## Send an offline field kit

```powershell
.venv\Scripts\python.exe -m data_pipeline.make_field_kit --metro palm_coast --output data_pipeline/qa/field-kit.html
```

Repeat `--metro` for multiple ingested metros; omit it to include all. The tool
requires postcodes. It samples across tiers and chain classes within each ZIP,
including excluded candidates so reviewers can identify lost gems. `--per-zip`
sets the independent cap **per tier**, not the total deck size. `--min-zip` sets
the minimum number of indexed entities in a ZIP (default 25).

Send only the resulting HTML file. Keep its matching
`Server/evaluation/kits/<kit_id>.json` in this checkout: it records the exact
sample, strata and scoring/filter/dedup source hashes. Regenerating a different
sample creates a different ID; do not replace the original manifest.

Recipient instructions:

1. Save the HTML attachment and open it in a browser. No server or login is
   required; some email attachment previewers will not run interactive HTML.
2. Select only ZIPs you know. Give a quality answer and, independently, what you
   know about operation, public access and booking. Skip anything uncertain.
3. Use Next when ready; choosing a label leaves time to add a note. Maps is an
   optional online link; the kit itself contains its sampled data.
4. Answer the written questions and choose **Export & send**. Email the downloaded
   JSON back. Export before closing if the browser warns that local saving is
   unavailable. **Import** restores an earlier export from the same kit.

The deck does not display the model's chain, booking or score predictions. The
download contains answers and identifiers, not automatically collected personal
details; reviewers should avoid private information in notes.

## Import a returned file

Assign the person a stable anonymous reviewer ID; reuse it for their later returns.

```powershell
.venv\Scripts\python.exe -m evaluation.import_labels C:/path/to/answers.json --reviewer local-reader-a
.venv\Scripts\python.exe -m evaluation.import_labels C:/path/to/answers.json --reviewer local-reader-a --apply
.venv\Scripts\python.exe -m evaluation.harness --strict
```

The first command is a preview. The second writes immutable normalized returns
under `evaluation/returns/` and registers each metro in `label_sets.json`. Names,
metros and source metadata come from the retained manifest, never a returned
client payload. Written answers and independent attributes are preserved.

An identical return is a no-op. Overlapping answers by the same reviewer are
refused rather than double-counted. If a reviewer revises answers, retain both
files and explicitly resolve the replacement in the registry with a review note;
do not invent a second reviewer ID. Other reviewers may judge the same place;
the report counts observations and names the number of reviewers, and its current
intervals do not account for dependence between reviewers or repeated venues.
Cross-metro written answers remain attached to the whole return; do not assume
every named place belongs to every selected metro.

Imports default to **development**. Use `--role holdout` only for a new metro
reserved prospectively, after freezing the candidate model and before anyone
inspects its answers to make implementation choices. Both Orlando and Palm Coast
already informed engineering and cannot be promoted to holdouts. The importer
rejects a metro declared fitted in `label_sets.json`; humans must keep that
declaration honest. Any tuning after inspecting a result makes that metro
development data for the next claim. Do not use synthetic verification returns
as human ground truth. Legacy kit returns require explicit provenance review;
the two original files remain registered and untouched.

## Evaluation and current limits

See [scope-c-evaluation.md](scope-c-evaluation.md). Strict currently fails because
there is no independent held-out metro and no reviewed v2 comparison baseline.
This is expected missing evidence, not a reason to waive strict checks. No
recommendation-quality improvement has been established in Phase 1.

The generated 50-place sample at
[verification/2026-09-05/field-kit.html](verification/2026-09-05/field-kit.html)
is a tooling check, not a new evaluation set. Export/import contracts have focused
automated checks; offline browser rendering and an unaided recipient round trip
remain to be demonstrated. Browser automation was denied access to the local
HTML file by its URL security policy; no rendered-screen claim is made.

## Add a metro

The loader now performs load → filter → score → dedup in one transaction, including
postcodes. It never drops `places` or deletes source records. Absent records become
inactive and remain addressable for history; absence is not proof of closure.
Existing canonical identities are retained. Ambiguous proposed merges spanning
two existing entities stay separate for explicit review.
The former standalone `apply_junk_filter.py`, `score_authenticity.py`, `run_dedup.py`
and `add_postcode.py` scripts were removed: their global partial writes bypassed
this transaction. The pure filter/scorer/dedup algorithms remain in use.

Copy `data_pipeline/st_augustine_example.json`, change the metro name and bounding
box, and choose a broader reference bounding box containing the metro. That area
supplies the name-frequency proxy for chains; changing it can change classifications.
Pin an available Overture release. Metro boxes in one config must not overlap, and
an incoming source ID cannot be reassigned from an existing metro without review.

```powershell
# From Server/. These dependencies were already installed in the verification environment.
.venv\Scripts\python.exe -m pip install -r data_pipeline/requirements.txt
.venv\Scripts\python.exe -m data_pipeline.pull_overture --config data_pipeline/st_augustine_example.json --output data_pipeline/data/st_augustine_snapshot

# Choose a separate database for the first demonstration. Supply local PG credentials
# through libpq/PGPASSWORD as needed; the acquisition step needs no paid API key.
$env:ADVENTOUR_PG_DSN="host=localhost port=5432 user=postgres dbname=adventour_ingest_check_20260905"
.venv\Scripts\python.exe -m data_pipeline.load_postgres --config data_pipeline/st_augustine_example.json --snapshot data_pipeline/data/st_augustine_snapshot --create-db --apply

# Subsequent refresh: preview first, then repeat with --apply after inspecting counts.
.venv\Scripts\python.exe -m data_pipeline.load_postgres --config data_pipeline/st_augustine_example.json --snapshot data_pipeline/data/st_augustine_snapshot
```

Keep `snapshot.json` with both Parquet files: hashes reject partial or mismatched
acquisition. A missing configured metro is an error. A refresh retiring over 30%
of an existing metro is refused unless `--allow-large-change` explicitly accepts
that reviewed change. Preview rolls back every index/schema change; `--create-db`
requires `--apply` and creates exactly the named database. No automatic redirection
to `adventour` occurs. Use the same snapshot against the working database only after
reviewing the isolated result, and omit `--create-db` for an existing database.

Verified on 2026-09-05: the example downtown bounding box acquired 1,838 source
records and a 1,138,273-record Florida name reference; ingestion produced 599
relevant records, 500 KEEP records / 491 KEEP entities. The actual emulator
[showed Gaufre's & Goods, 417 m away](verification/2026-09-05/st-augustine-deck.png)
from a 20-card deck. This bounded example does not cover all of St. Augustine or
establish recommendation quality. A Postgres test verified other-metro preservation,
history identity after a source disappearance, canonical H3 geometry and rollback
after a failed scoring stage. The working seed index was not reingested.

Run those database checks only with `ADVENTOUR_TEST_PG_DSN` pointing to an
`adventour_ingest_check_*` database:
`python -m pytest tests/test_index_ingestion.py -q`. All test mutations roll back.
The owner following this workflow unaided remains an acceptance check.
