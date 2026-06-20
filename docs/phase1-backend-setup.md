# Phase 1 Backend Setup

This pass adds the first real Adventour recommender backend:

- normalized place events
- Adventour-owned place identities
- provider references
- place feature scores
- user preference vectors
- provider abstraction
- group-aware recommendation scoring

## Local Development

From `Adventour-v2/Server`, copy the example env file:

```powershell
Copy-Item .env.local.example .env.local
```

Then populate `.env.local`:

```bash
ADVENTOUR_DEV_AUTH=true
DATABASE_URL=sqlite:///adventour_dev.db
GOOGLE_API_KEY=
```

Then run:

```bash
pip install -r requirements.txt
python app.py
```

For local authenticated requests, use:

```http
Authorization: Bearer dev:you@example.com
```

This creates or reuses a local dev user. Production should use Firebase ID tokens.

## New API

### POST `/api/recommendations`

Request:

```json
{
  "mode": "spontaneous",
  "location": { "latitude": 40.7128, "longitude": -74.006 },
  "radius_meters": 3200,
  "member_ids": [],
  "constraints": {
    "price_max": 2,
    "avoid_chains": true,
    "limit": 20
  }
}
```

Response includes:

- Adventour place id
- provider id
- score
- score components
- explanation
- display-safe provider fields

### POST `/api/events`

Records normalized events:

```json
{
  "place_id": 1,
  "event_type": "accept",
  "context": "solo",
  "event_value": null,
  "metadata": {
    "source": "swipe"
  }
}
```

Supported event types:

- `impression`
- `reject`
- `accept`
- `navigate`
- `arrival`
- `rate`
- `save`
- `share`

## Provider Behavior

The recommender currently queries:

1. Local Adventour places from the database.
2. Google Places if `GOOGLE_API_KEY` is set.

Foursquare or Foursquare OS Places can be added by implementing the `PlaceProvider` interface in `Server/adventour_backend/providers/place_providers.py`.

## Existing Cloud SQL Migration Note

`db.create_all()` creates missing tables but does not safely alter existing tables. If you point this code at an existing MySQL database, add migrations before deploying.

Phase 1 added these new tables:

- `place`
- `place_provider_ref`
- `place_feature`
- `user_place_event`
- `user_preference_vector`

It also relaxes `user.firebase_uid`, `user.email`, and `user.username` to nullable for local/dev flows, and adds `user.uuid` for old client compatibility. If starting fresh, keep Firebase fields populated in production even though they are nullable at the DB layer.

## Recommended Next Database Step

Use one of these paths:

- Short term: keep SQLAlchemy + Cloud SQL MySQL and add Alembic/Flask-Migrate.
- Better medium term: move to Postgres on Cloud SQL so `pgvector`, richer JSON, and geospatial indexing are easier later.

For Phase 1, SQLite locally and Cloud SQL in deployed environments are enough.
