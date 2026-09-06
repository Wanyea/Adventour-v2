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
    suppressed_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS place_provider_ref (
    entity_id text PRIMARY KEY, google_place_id text NOT NULL
);
ALTER TABLE place_provider_ref DROP CONSTRAINT IF EXISTS place_provider_ref_google_place_id_key;
CREATE TABLE IF NOT EXISTS recommendation_decision (
    id text PRIMARY KEY, user_id integer NOT NULL, entity_id text NOT NULL,
    record_id text NOT NULL, metro text NOT NULL, payload jsonb NOT NULL,
    test_activity boolean NOT NULL DEFAULT false, verdict text,
    served_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS decision_user_entity_idx ON recommendation_decision(user_id,entity_id);
ALTER TABLE place_event ADD COLUMN IF NOT EXISTS decision_id text;
ALTER TABLE place_event ADD COLUMN IF NOT EXISTS components_snapshot jsonb;
ALTER TABLE place_event ADD COLUMN IF NOT EXISTS test_activity boolean NOT NULL DEFAULT false;
CREATE UNIQUE INDEX IF NOT EXISTS place_event_decision_type_idx
    ON place_event(user_id,decision_id,event_type) WHERE decision_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS provider_usage (
    user_id integer NOT NULL, usage_day date NOT NULL, calls integer NOT NULL DEFAULT 0,
    PRIMARY KEY(user_id,usage_day)
);
-- Migrate the old schema once; provider suppression keeps only ID + our timestamp.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='suppressed_place'
               AND column_name='entity_id' AND table_schema=current_schema()) THEN
        INSERT INTO place_provider_ref(entity_id,google_place_id)
            SELECT entity_id,google_place_id FROM suppressed_place
            WHERE entity_id IS NOT NULL AND google_place_id NOT LIKE 'adventour:%%'
            ON CONFLICT DO NOTHING;
        INSERT INTO place_event(user_id,entity_id,event_type,context,occurred_at)
            SELECT 0,COALESCE(entity_id,substr(google_place_id,11)),
                   'closed_report','legacy_editorial_suppression',suppressed_at
            FROM suppressed_place s WHERE google_place_id LIKE 'adventour:%%'
            AND NOT EXISTS (SELECT 1 FROM place_event e WHERE e.event_type='closed_report'
                            AND e.entity_id=COALESCE(s.entity_id,substr(s.google_place_id,11)));
        DELETE FROM suppressed_place WHERE google_place_id LIKE 'adventour:%%';
        ALTER TABLE suppressed_place DROP COLUMN entity_id;
        ALTER TABLE suppressed_place DROP COLUMN source;
    END IF;
END $$;
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
