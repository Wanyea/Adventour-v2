# Adventour Wild Testing Staging Guide

This is the testing lane for your iPhone and trusted friends before Adventour is
ready for the App Store. The goal is simple: real accounts, real devices, one
shared backend, one shared database, and no dependency on your PC or home Wi-Fi.

## Target Shape

```text
Tester phone
  -> Adventour beta build
  -> Firebase Authentication
  -> Adventour staging API over HTTPS
  -> Shared staging database
  -> Google Places API, called only from the backend
```

Local development still stays local:

```text
Android emulator
  -> http://10.0.2.2:8080
  -> local Flask backend
  -> local SQLite dev database
```

Do not expose the Flask server running on your PC with port forwarding or a
tunnel for friend testing. That is fine for a quick demo, but it is fragile and
easy to confuse with the real app behavior.

## Recommended First Staging Stack

Use the services that match the codebase with the least churn:

- Backend: Google App Engine or Cloud Run.
- Database: Cloud SQL MySQL for the first staging DB.
- Auth: Firebase Authentication.
- Backend identity verification: Firebase Admin SDK.
- Places/geocode/autocomplete: Google Places API, server key only.
- iPhone distribution: TestFlight.
- Android distribution, later: Firebase App Distribution.

Cloud SQL MySQL is the easiest database move because the backend already has
`PyMySQL` and MySQL connection settings. Postgres is a good future option, but
it would require changing dependencies and connection config.

## Backend Environment

The deployed backend must not use SQLite. SQLite is only for local development.

Staging needs these values:

```bash
ADVENTOUR_DEV_AUTH=false
FIREBASE_PROJECT_ID=adventour-73dfb
GOOGLE_API_KEY=your_server_restricted_google_places_key
DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/adventour_staging
```

If using the existing App Engine template, you can instead use the Cloud SQL
variables in `Server/app.yaml.example`:

```bash
DB_USER=your_cloud_sql_user
DB_PASSWORD=your_cloud_sql_password
DB_NAME=adventour_staging
DB_CONNECTION_NAME=your-gcp-project:your-region:your-cloud-sql-instance
GOOGLE_API_KEY=your_server_restricted_google_places_key
```

For Google-hosted deployment, prefer Application Default Credentials or a
service account attached to the service. For local Firebase auth testing, use
`FIREBASE_SERVICE_ACCOUNT_PATH`, but do not commit service account files.

## Mobile Staging Environment

The beta app must point to the deployed HTTPS backend, not your PC:

```bash
BACKEND_BASE_URL=https://YOUR_STAGING_BACKEND_URL
API_AUTH_MODE=firebase
DEV_AUTH_EMAIL=
GOOGLE_API_KEY=
GOOGLE_WEB_CLIENT_ID=your_firebase_web_client_id
```

Keep this in a real local file such as:

- `AdventourApp/.env.deployed`
- `AdventourApp/.env.staging`

Commit only the matching `.example` file.

## What Requires A New App Build?

Backend-only changes:

- Recommendation logic.
- Database writes/reads.
- Auth verification.
- Places provider behavior.
- Friend APIs.
- Itinerary APIs.

Deploy the backend and testers can usually keep the same installed app.

Mobile changes:

- React Native screen/UI changes.
- New native packages.
- Firebase client config changes.
- Bundle id/package changes.
- App icon/splash/native config.

Build and distribute a new beta app.

## iPhone Testing Without Publishing

Use TestFlight when you are ready for trusted iPhone testers:

1. Enroll in the Apple Developer Program if you have not already.
2. Register the iOS bundle id: `com.adventour.app`.
3. Add `GoogleService-Info.plist` to the iOS app target.
4. Build the app with the staging env file.
5. Archive/upload from Xcode on a Mac, or use a trusted remote Mac build path.
6. Invite yourself first.
7. Invite trusted friends after the first TestFlight build is approved for
   external testing.

This does not publish Adventour to the App Store. It creates a beta build that
testers install through Apple TestFlight.

## Windows Reality Check

You can keep daily Android development on Windows. For iPhone builds, you still
need one of these:

- A Mac with Xcode.
- A remote Mac build service.
- A later migration to a build system such as EAS if Adventour moves toward
  Expo development builds.

For now, the cleanest path is: Windows for daily backend/Android work, then a
Mac or remote Mac only when cutting iPhone beta builds.

## Cost Controls Before Inviting Friends

Set these before sharing a build:

- Google Cloud budget alert.
- Google Places API quota.
- Server-restricted Google API key for the backend.
- Firebase Authentication enabled only for the providers you are testing.
- A separate staging database so tester data does not mix with future
  production data.
- Max instances or low scaling limits on the backend.

## First Friend-Test Checklist

Backend:

- Deployed backend URL is HTTPS.
- Backend starts with `ADVENTOUR_DEV_AUTH=false`.
- `/user` requests verify Firebase tokens.
- Recommendations work from at least two cities.
- Accept/reject/rating events persist after backend restart.

Mobile:

- Installed beta points at the staging backend URL.
- New account goes through display name, birthdate, and onboarding.
- Existing account skips onboarding without flashing it.
- Profile data is separate between two different Firebase users.
- Friend search returns real users by display name.
- Active Adventour survives app close/reopen.

Operational rhythm:

1. Test locally on Android emulator.
2. Deploy backend to staging.
3. Smoke test against staging from emulator.
4. Build iPhone beta with staging env.
5. Install on your iPhone.
6. Invite one trusted friend.
7. Watch backend logs and Places usage before adding more people.

