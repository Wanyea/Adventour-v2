# iPhone friends pilot distribution checklist

This is the bounded distribution workstream for the approved Phase 2 friends
pilot. It is a checklist for the Mac/Xcode owner; no iOS build or TestFlight
release has been performed from this Windows workspace.

## External prerequisites

- Apple Developer membership with access to the App ID `com.adventour.app`.
- A Mac with Xcode and CocoaPods, or an equivalent macOS build service.
- Access to the Firebase project used by the pilot, including the iOS app
  registration and its `GoogleService-Info.plist`.
- A reachable HTTPS Flask endpoint backed by the pilot Postgres database. Keep
  Postgres private; do not expose port 5432.
- A real Firebase account for each tester. Do not use the local dev-auth bypass.

## Configure the pilot build

1. Copy `AdventourApp/.env.ios.pilot.example` to
   `AdventourApp/.env.ios.pilot.local` and set the actual HTTPS backend URL.
   Keep the local file uncommitted.
2. Add the Firebase iOS configuration to the `AdventourApp` target. Confirm
   its bundle ID is `com.adventour.app` and that the Firebase project matches
   the backend's token verifier. The repository intentionally does not contain
   this environment-specific plist.
3. Open `AdventourApp/ios/AdventourApp.xcworkspace` in Xcode. Select the
   `AdventourApp` target, choose the Apple Developer team, and enable the
   signing profile for the pilot App ID. Do not commit a team ID or certificate
   material to the repository.
4. Confirm the Release configuration receives the pilot env file through
   `react-native-config` before archiving. The pilot build must set exactly
   `APP_VARIANT=pilot`, plus nonempty `PILOT_ID` and `APP_BUILD_ID`, for pilot
   feedback controls and study capture. A standard build must set
   `APP_VARIANT=standard` or leave the variant unset.
5. Verify the archive has bundle ID `com.adventour.app`, a new
   `CFBundleVersion`, and the intended marketing version before uploading.

Example Mac commands from `AdventourApp/`:

```sh
cp .env.ios.pilot.example .env.ios.pilot.local
cd ios && bundle exec pod install && cd ..
# Release simulator smoke check
ENVFILE=.env.ios.pilot.local npx react-native run-ios --mode Release --simulator "iPhone 15"
# Registered-device smoke check (replace with the actual device name)
ENVFILE=.env.ios.pilot.local npx react-native run-ios --mode Release --device "Owner's iPhone"
```

The first command only creates a template copy; the URL and Firebase values
must be supplied locally. The `run-ios` commands are simulator/device smoke
checks; they do not produce the signed distribution artifact. Use Xcode's
Product → Archive flow for the archive, then inspect its bundle ID, build
number, signing, and embedded pilot environment before uploading it.

## Device and TestFlight gates

Distribution is gated by the dependency chain P2-06 → P2-07 → P2-08 → P2-09 →
P2-10. Complete and retain the reporting/rehearsal, unseeded-region,
remote-service, iOS-build, and physical-iPhone evidence for those tickets
before treating P2-11/TestFlight preparation as ready. Run these gates in order
and record the result with the build ID:

1. Install the signed build on one registered iPhone. Confirm real Firebase
   sign-in creates/loads that user's own profile and preferences.
2. Deny location, confirm the app remains usable, then grant foreground
   location and confirm the selected coordinates reach the backend. Test a
   location outside the seeded metros.
3. With the PC backend reachable over cellular data, request a deck and local
   events. Verify the response region follows the phone's launch location and
   that no Orlando fallback appears for another region.
4. Complete one pilot place question and one event question. Confirm the
   response is associated with the signed-in participant, survives a temporary
   network loss, and appears once in the private export.
5. Verify a standard build separately: no pilot controls, no extra pilot
   network writes, and no reuse of a stale pilot card ID.
6. Upload the Release archive to App Store Connect and complete the required
   privacy/export declarations. Internal TestFlight distribution still waits
   for the previous checks and the server enrollment/build allowlist. External
   friends additionally require Apple's external TestFlight review/approval
   before invitations can be sent.

TestFlight distribution does not enroll a person automatically. The operator
must create the Firebase account, explain consent/retention, enroll the backend
user with `pilot_admin`, and then send the invitation. Keep the private export
and any location-bearing logs on the agreed PC storage.

## Evidence to retain

Record the Xcode/archive version, build ID, device iOS version, Firebase project
identifier, backend release, location permission result, one place request and
one event request ID, and the matching export/replay check. Do not commit
tester accounts, Firebase plist files, certificates, private exports, or
location-bearing screenshots.

The remaining blockers include external Apple/Mac access, Firebase iOS
configuration, reachable HTTPS operation, and a real-device/TestFlight smoke
pass. Internal implementation gaps also remain: native Firebase AppDelegate
initialization and archive environment wiring have not been demonstrated, and
the full instrumentation, regional acquisition, and remote-service path is
incomplete. The pilot must use exactly `APP_VARIANT=pilot`. External friends
also require Apple's external TestFlight review/approval. This checklist does
not claim any of these gates is complete.
