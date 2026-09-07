"""Additive study tables; standard requests never write these tables."""

DDL = """
CREATE TABLE IF NOT EXISTS pilot_enrollment (
    pilot_id text NOT NULL, user_id integer NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    participant_id text NOT NULL UNIQUE, active boolean NOT NULL DEFAULT true,
    consent_version text NOT NULL, enrolled_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(pilot_id,user_id)
);
CREATE TABLE IF NOT EXISTS pilot_build (
    pilot_id text NOT NULL, build_id text NOT NULL, active boolean NOT NULL DEFAULT true,
    PRIMARY KEY(pilot_id,build_id)
);
CREATE TABLE IF NOT EXISTS pilot_request (
    id text PRIMARY KEY, pilot_id text NOT NULL, user_id integer NOT NULL,
    session_id text NOT NULL, build_id text NOT NULL, schema_version text NOT NULL,
    test_activity boolean NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    context jsonb NOT NULL, trace jsonb NOT NULL DEFAULT '{}',
    FOREIGN KEY(pilot_id,user_id) REFERENCES pilot_enrollment(pilot_id,user_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS pilot_decision (
    id text PRIMARY KEY, request_id text NOT NULL REFERENCES pilot_request(id) ON DELETE CASCADE,
    item_kind text NOT NULL CHECK(item_kind IN ('place','event')),
    item_key text NOT NULL, rank integer NOT NULL CHECK(rank>0),
    core_decision_id text, payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pilot_request_user_idx ON pilot_request(user_id,created_at);
CREATE INDEX IF NOT EXISTS pilot_decision_request_idx ON pilot_decision(request_id);
CREATE TABLE IF NOT EXISTS pilot_signal (
    id text PRIMARY KEY, decision_id text NOT NULL REFERENCES pilot_decision(id) ON DELETE CASCADE,
    kind text NOT NULL, occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(), payload jsonb NOT NULL,
    UNIQUE(decision_id,kind)
);
CREATE TABLE IF NOT EXISTS pilot_invitation (
    id text PRIMARY KEY, decision_id text NOT NULL REFERENCES pilot_decision(id) ON DELETE CASCADE,
    source text NOT NULL CHECK(source IN ('sampled','voluntary')),
    question text NOT NULL CHECK(question IN ('appeal_v1','relevance_v1')),
    interest text, probability double precision NOT NULL,
    status text NOT NULL DEFAULT 'offered' CHECK(status IN ('offered','skipped','answered')),
    offered_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(decision_id,source)
);
CREATE TABLE IF NOT EXISTS pilot_feedback (
    id text PRIMARY KEY, invitation_id text NOT NULL REFERENCES pilot_invitation(id) ON DELETE CASCADE,
    answer_kind text NOT NULL CHECK(answer_kind IN ('rated','unknown')),
    value integer CHECK(value BETWEEN 0 AND 4), reason text, problem text, note text,
    duration_ms integer NOT NULL CHECK(duration_ms>=0),
    occurred_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
    supersedes text UNIQUE REFERENCES pilot_feedback(id),
    CHECK((answer_kind='rated' AND value IS NOT NULL) OR (answer_kind='unknown' AND value IS NULL)),
    CHECK(length(note)<=280)
);
CREATE UNIQUE INDEX IF NOT EXISTS pilot_first_answer_idx ON pilot_feedback(invitation_id)
    WHERE supersedes IS NULL;
ALTER TABLE pilot_invitation ADD COLUMN IF NOT EXISTS presented_at timestamptz;
"""
