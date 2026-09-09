# ADTR-22 Android runtime packet

Runtime verification used the existing `emulator-5554` Android emulator and the
already-installed `com.adventourapp` debug build. This is emulator evidence;
no physical Android device or iPhone was tested.

Verified application source: `0f2e2b14`.

## Isolated environment

- Backend: the ADTR-22 worktree on `127.0.0.1:8082`, launched with the original
  private `Server/.env.ingest-check` configuration. A separate import check
  reported the SQLAlchemy dialect as `postgresql`.
- Metro: the ADTR-22 worktree served on port 8081. The installed debug client
  requested `10.0.2.2:8081`; its worktree bundle initially needed a temporary
  Metro resolver configuration pointing at the existing original-repository
  `node_modules`. No application source was changed for this setup.
- Feature requests used only port 8082. The primary agent checked public-service
  localhost health endpoints: `/healthz` returned 200 and `/readyz` reported
  `database=ok`. Its identified `remote_service` process remained distinct from
  the local 8082 process. No feature deployment or participant request was made.

### Runtime process record

The managed backend session was `61238`, running
`python -m flask --app app run --host 127.0.0.1 --port 8082` from the ADTR-22
`Server` directory after `ENV_FILE` was set to the original private
`Server/.env.ingest-check` path. At capture, port 8082 belonged to Python PID
31024. Metro session `69330` ran `react-native start --port 8081 --reset-cache`
with temporary configuration
`C:\Users\wanye\AppData\Local\Temp\adtr22-metro.config.js`; port 8081 belonged
to Node PID 41860. `adb reverse` was `tcp:8081 -> tcp:8081`.

## Observed Android behavior

- [Home with no launch point](home-no-launch.png) shows the existing no-location
  guard: empty launch field, disabled "Waiting for a place" action, and no
  local-events section.
- The fresh local 8082 access output for app opens contains user and Adventour
  history/active calls, but no `/api/local-events` request. This corroborates
  the guard; it does not claim a new event prompt (that is outside ADTR-22).
- [Profile Home base](profile-home-base-not-set.png) is from the worktree bundle.
  It shows the new `HOME BASE` section in the existing Profile screen with the
  `Not set` state and `Edit` affordance.
- A fresh synthetic dev account completed Profile Setup with a birthdate, a home
  locality, and the existing mood selection. [Onboarding Home city](onboarding-home.png)
  records the optional Home city field; [saved Profile](profile-onboarding-saved.png)
  records the resulting Home base value in Profile.
- After force-closing and relaunching, [Profile after relaunch](profile-relaunch.png)
  still displayed that saved Home base value.
- The existing manual launch selection was set to Seattle. Editing Home base to a
  different locality stayed on Profile ([edited Profile](profile-edited.png));
  returning Home retained the Seattle manual launch
  ([manual launch retained](manual-launch-retained.png)).
- Clearing the editor draft and choosing Cancel left the saved Home base intact.
  Choosing Clear then Save displayed `Not set`.
- [Cleared Profile after relaunch](profile-cleared-relaunch.png) shows that
  `Not set` persisted after force-close/relaunch.
  [Home after cleared relaunch](home-cleared-relaunch.png) shows the blank-launch
  guard again.
- The bounded server access output from this final relaunch contained only the
  profile/Adventour calls expected on startup; it did not contain a
  `/api/local-events` request. Earlier `/api/local-events` calls were made only
  while Seattle was intentionally selected for the manual-launch retention check.

## Isolated API persistence corroboration

Two designated synthetic dev identities were used only against the private
ingest-check database. The following focused calls completed successfully:

| Check | Observed result |
|---|---|
| `PUT /user/profile` with whitespace-padded locality | `200`; returned trimmed locality |
| Authenticated `GET /user/:id` by the same identity | returned that locality |
| Authenticated `GET /user/:id` by the second identity | `403` |
| `PUT /user/profile` with `home_city: null` | `200`; returned `null` |

The test cleared the synthetic account's locality before completion. No public
participant or owner account was read, changed, or reset.

## Remaining device checkpoint

The screenshot packet records the no-location Home guard, initial Profile state,
a completed fresh-account onboarding save, persistence after relaunch, edit,
cancel, clear, and clear persistence after relaunch. It does not claim
physical-iPhone verification. That requires the Mac walkthrough in
`docs/adtr-22-mac-handoff.md`.
