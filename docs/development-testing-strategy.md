# Adventour Development and Testing Strategy

This workflow is designed to keep local development, phone testing, and deployment from turning into three different apps in a trench coat.

## Mental Model

Keep these separate:

1. Backend API environment: local SQLite, staging Cloud SQL, production.
2. Metro/JavaScript dev server: serves the React Native JS bundle during development.
3. Native build target: Android emulator, Android phone, iOS simulator, iPhone, release build.

Most confusion comes from changing two or three of those at once. Change one layer at a time.

## Recommended Daily Workflow on Windows

Use Android emulator as the main daily device. It is the fastest full-stack loop from this Windows machine.

Terminal 1:

```powershell
cd D:\source\Adventour\Adventour-v2
powershell -ExecutionPolicy Bypass -File .\scripts\dev-backend.ps1 -Install
```

This starts the backend at:

- Windows/browser: `http://localhost:8080`
- Android emulator: `http://10.0.2.2:8080`
- physical phone on same Wi-Fi: `http://<your-lan-ip>:8080`

Terminal 2:

```powershell
cd D:\source\Adventour\Adventour-v2\AdventourApp
npm run android:local:pixel7
```

If your emulator is already running, `npm run android:local` is enough. If you want a different AVD, use npm's argument separator:

```powershell
npm run android:local -- -AvdName Pixel_XL_API_30
```

The Android helper starts Metro only when port `8081` is not already serving a
Metro status response. The app install step uses `--no-packager`, so this flow
should open at most one separate Metro terminal.

The Android emulator uses `AdventourApp/.env.android.local`:

```bash
BACKEND_BASE_URL=http://10.0.2.2:8080
API_AUTH_MODE=dev
DEV_AUTH_EMAIL=dev@adventour.local
```

Why `10.0.2.2`? Android emulators treat that address as the host computer.

## Testing on a Physical Phone

### Android Phone

If you use an Android phone later:

1. Run backend with `dev-backend.ps1`.
2. Run:

```powershell
.\scripts\show-lan-ip.ps1
```

3. Copy one LAN IP into `AdventourApp/.env.phone.local`:

```bash
BACKEND_BASE_URL=http://192.168.x.x:8080
API_AUTH_MODE=dev
DEV_AUTH_EMAIL=dev@adventour.local
```

4. Make sure Windows Firewall allows inbound TCP `8080`.
5. From `AdventourApp`, run:

```powershell
npm run android:phone
```

### iPhone

Important: with this current bare React Native app, Windows cannot build and install the iOS native app directly onto your iPhone. React Native's iOS device flow requires a Mac with Xcode for local builds and signing.

Practical options:

- Best short-term: use Android emulator on Windows for daily development, then periodically test iOS using a Mac/Xcode.
- Best medium-term: use Expo development builds/EAS Build so cloud builds can produce an iOS dev build you install on your iPhone.
- Alternative: use a remote Mac service or Mac mini for iOS builds.

Your iPhone is still valuable for real-device validation, but it should be a scheduled validation lane, not the daily inner loop unless we move to Expo/EAS or add Mac access.

## Environments

### Local Android Emulator

File: `AdventourApp/.env.android.local`

```bash
BACKEND_BASE_URL=http://10.0.2.2:8080
API_AUTH_MODE=dev
DEV_AUTH_EMAIL=dev@adventour.local
GOOGLE_API_KEY=
```

Autocomplete and geocoding are served by the backend. Put the Google Maps key in `Server/.env.local`, not in the mobile app env:

```bash
GOOGLE_API_KEY=your_server_key_here
```

Leaving it blank is fine for local UI work; autocomplete will return no suggestions and geocode will fall back to GPS coordinates.

Create local env files from examples rather than committing real values:

```powershell
cd D:\source\Adventour\Adventour-v2
Copy-Item Server\.env.local.example Server\.env.local
Copy-Item AdventourApp\.env.android.local.example AdventourApp\.env.android.local
```

### Local Physical Phone

File: `AdventourApp/.env.phone.local`

```bash
BACKEND_BASE_URL=http://YOUR_COMPUTER_LAN_IP:8080
API_AUTH_MODE=dev
DEV_AUTH_EMAIL=dev@adventour.local
GOOGLE_API_KEY=
```

### Deployed Backend

File: `AdventourApp/.env.deployed`

```bash
BACKEND_BASE_URL=https://adventour-73dfb.ue.r.appspot.com
API_AUTH_MODE=firebase
DEV_AUTH_EMAIL=
GOOGLE_API_KEY=
```

Keep real keys out of git. Commit only `.example` files.

For multi-account testing with trusted friends, see
`docs/trusted-wild-testing-auth.md`.

## Testing Pyramid

Use a small, repeatable testing ladder:

1. Backend unit/import checks:

```powershell
cd D:\source\Adventour\Adventour-v2
py -3 -m compileall Server\app.py Server\adventour_backend Server\tests
Server\.venv\Scripts\python.exe -m pytest -q Server
```

2. Backend API smoke:

Use Flask test client or curl/Postman against `http://localhost:8080`.

3. Mobile unit tests:

```powershell
cd D:\source\Adventour\Adventour-v2\AdventourApp
npm test
```

4. Android emulator full-stack:

```powershell
npm run android:local
```

5. Physical-device validation:

Use phone LAN config for Android, or Mac/EAS path for iPhone.

6. Deployed smoke:

Build app against `.env.deployed`, then verify login, onboarding, recommendations, feedback, and event recording.

## Release Discipline

Do not deploy directly from a random local state.

Use this rhythm:

1. Run backend locally.
2. Run Android emulator against local backend.
3. Run backend smoke checks.
4. Commit.
5. Deploy backend to staging/production.
6. Point mobile env at deployed backend.
7. Run a smoke pass.

Smoke pass checklist:

- App launches.
- User auth path works, or dev auth works locally.
- Onboarding preferences save.
- `POST /api/recommendations` returns recommendations.
- Accept/reject creates events.
- Rating creates a rating and event.
- Backend logs have no stack traces.

## Platform Recommendation

For the current codebase:

- Stay with bare React Native for this immediate Phase 1 because the project already exists and uses native Firebase packages.
- Use Android emulator as the Windows daily driver.
- Add EAS/Expo development build support later if iPhone-on-Windows becomes important enough to justify the migration.

React Native now recommends using a framework like Expo for new apps, and Expo development builds are specifically designed for production-grade apps with native code. That is probably the direction Adventour should consider after the backend shape settles.

## Backend Project Shape

The backend now has a small package boundary:

- `Server/app.py`: Flask entrypoint and current route registration.
- `Server/adventour_backend/models.py`: SQLAlchemy models.
- `Server/adventour_backend/auth.py`: Firebase/dev auth helpers.
- `Server/adventour_backend/services/`: business logic and external API wrappers.
- `Server/adventour_backend/providers/`: swappable place provider abstraction.
- `Server/adventour_backend/data/`: local Adventour-owned reference data.
- `Server/tests/`: automated tests.
- `Server/recommender_lab.py`: deterministic recommender scenarios.
- `Server/real_place_lab.py`: live Google-backed recommendation lab.
- `Server/app.yaml.example`: App Engine deployment template; the real
  `Server/app.yaml` is ignored because it can contain secrets.

That is enough structure for Phase 1 without hiding the system behind too many layers. If `app.py` keeps growing, the next cleanup is to move routes into blueprints by domain.

## Sources

- React Native environment setup: https://reactnative.dev/docs/environment-setup
- React Native running on device: https://reactnative.dev/docs/running-on-device
- Expo development builds: https://docs.expo.dev/develop/development-builds/introduction/
