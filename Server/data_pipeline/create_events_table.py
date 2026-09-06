"""Create `place_event` -- the go-forward interaction log.

Designed against the Postgres index, not adapted to the legacy `user_place_event`
table, which keys on an integer `place.id` that no longer exists in this
architecture.

Two design points that matter more than the columns:

1. **Events key on `entity_id`, not on a record id.** Gate 9 collapses ~827
   duplicate records into resolved entities; a user's swipe is about the *place*,
   not about whichever Overture row happened to surface. `record_id` is kept
   alongside purely for debugging dedup.

2. **The score is snapshotted at decision time.** Learning from behaviour needs
   to know what the model believed when it showed the card -- otherwise a later
   re-score silently rewrites history and every past event becomes unusable.
   This is the column that turns Gate 8's floor into a future ranker.
"""

import os

import psycopg2

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")

DDL = """
CREATE TABLE IF NOT EXISTS place_event (
    id                    bigserial PRIMARY KEY,
    user_id               integer     NOT NULL,
    entity_id             text        NOT NULL,
    record_id             text,
    event_type            text        NOT NULL,
    event_value           double precision,
    context               text,
    metro                 text,
    score_snapshot        double precision,
    explanation_snapshot  text,
    occurred_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS place_event_user_time_idx ON place_event (user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS place_event_entity_idx    ON place_event (entity_id);
CREATE INDEX IF NOT EXISTS place_event_type_idx      ON place_event (event_type);

-- Suppression list, per the boundary approved 2026-08-17 (CLAUDE.md).
-- Only the provider id and our own timestamp. Never businessStatus, never the
-- reason string, never any other returned field.
CREATE TABLE IF NOT EXISTS suppressed_place (
    google_place_id  text PRIMARY KEY,
    entity_id        text,
    suppressed_at    timestamptz NOT NULL DEFAULT now(),
    source           text NOT NULL DEFAULT 'provider_check'
);
CREATE INDEX IF NOT EXISTS suppressed_entity_idx ON suppressed_place (entity_id);
"""

# The vocabulary the recommender will learn from. `closed_report` exists because
# Gate 6 found 9.1% of the seed permanently closed and no free signal detects it
# -- user reports are the one source that is unambiguously ours.
EVENT_TYPES = (
    "impression", "accept", "reject", "navigate",
    "arrival", "rate", "save", "share", "closed_report",
)


def main():
    with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(DDL)
        conn.commit()
        cur.execute(
            """SELECT column_name, data_type FROM information_schema.columns
               WHERE table_name = 'place_event' ORDER BY ordinal_position"""
        )
        print("place_event:")
        for name, dtype in cur.fetchall():
            print(f"  {name:<22}{dtype}")
        cur.execute("SELECT count(*) FROM place_event")
        print(f"  rows: {cur.fetchone()[0]}")
        cur.execute("SELECT count(*) FROM suppressed_place")
        print(f"suppressed_place rows: {cur.fetchone()[0]}")
    print(f"\nevent types: {', '.join(EVENT_TYPES)}")


if __name__ == "__main__":
    main()
