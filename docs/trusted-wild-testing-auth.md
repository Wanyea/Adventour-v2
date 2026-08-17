# Trusted Wild Testing Auth Setup

This is the path for testing Adventour with separate real accounts on Android emulator, a physical iPhone, and a few trusted friends before any app store launch.

## Target Shape

- Firebase Authentication owns user identity.
- Adventour Flask backend verifies Firebase ID tokens.
- Adventour database is shared and reachable by all testers.
- Mobile apps point at one deployed backend URL.
- Local dev auth remains available only for fast emulator work.

## Firebase Setup

1. In Firebase Console, enable Email/Password sign-in.
2. Add app clients for the platforms you will test:
   - Android package: `com.adventourapp`
   - iOS bundle id: `com.adventour.app`
3. Download client config files:
   - Android: `google-services.json` into `AdventourApp/android/app/google-services.json`.
   - iOS: `GoogleService-Info.plist` into the iOS app target.
4. Generate a Firebase Admin service account JSON for the backend.
5. Keep all real credential files out of git.

## Backend Environment

For local Firebase auth testing:

```bash
ADVENTOUR_DEV_AUTH=false
DATABASE_URL=sqlite:///adventour_dev.db
FIREBASE_SERVICE_ACCOUNT_PATH=D:\path\to\firebase-service-account.json
GOOGLE_API_KEY=your_server_key
```

For trusted friends outside your Wi-Fi, deploy the backend and use a shared database. Do not use local SQLite for distributed testing because each machine/deployment would have its own isolated data.

Recommended next backend step:

- App Engine or Cloud Run for Flask.
- Cloud SQL Postgres or MySQL for shared data.
- Secret Manager or deployed env vars for `GOOGLE_API_KEY` and Firebase Admin credentials.

For the end-to-end staging plan, including iPhone distribution and the
local-vs-staging workflow, see `docs/wild-testing-staging.md`.

## Mobile Environments

For Android emulator local dev:

```bash
BACKEND_BASE_URL=http://10.0.2.2:8080
API_AUTH_MODE=dev
DEV_AUTH_EMAIL=dev@adventour.local
```

For real multi-account testing:

```bash
BACKEND_BASE_URL=https://YOUR_DEPLOYED_BACKEND_URL
API_AUTH_MODE=firebase
DEV_AUTH_EMAIL=
```

## Tester Flow

1. Install the app build configured with `API_AUTH_MODE=firebase`.
2. Create a new account with email/password.
3. Complete onboarding.
4. Search for another tester by display name or username in Friends & Trips.
5. Send and accept friend requests.
6. Run Adventours in different cities and confirm each account has separate Passport data.

## iPhone From Windows

The current bare React Native app still needs a Mac/Xcode path for iOS signing. For trusted iPhone testing, use one of:

- A Mac with Xcode and TestFlight/internal distribution.
- EAS Build/development builds if Adventour moves toward Expo tooling later.
- A remote Mac build service.
