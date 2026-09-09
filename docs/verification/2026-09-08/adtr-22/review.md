# ADTR-22 independent review

Base: `82a958ee` (`codex-astra`, merged ADTR-25).
PR: https://github.com/Wanyea/Adventour-v2/pull/4

GPT-6 Astra independently reviewed the contract and source, with a separate
GPT-5.6 Terra backend audit. Neither reviewer authored the implementation.

## Initial findings — c08ad7a9

**Medium, blocking — account isolation:** AuthService.updateProfile cached a
response before HomeCityEditor checked whether it had unmounted. A pending save
for account A could overwrite account B's current-user cache after an account
switch; dev-mode authentication could subsequently use A. Required a request
session/identity check before cache publication and a deferred-response test.

**Medium, blocking — navigation:** Profile saving invoked parent setUser while
MainTabs and its tab components were defined inside AppNavigator. Their identities
changed on each parent render, remounting navigation and discarding Home state.
Required stable component identity and runtime confirmation of retained launch.

The independent backend audit found no code blockers in validation, owner
selection, field omission/clearing, serialization or additive migration.

## Corrections and source re-review

`5e9eb983` guards profile response publication by captured session and Firebase
UID, preserves navigator component identity, and suppresses editor callbacks and
alerts after unmount. The reviewer confirmed both source blockers resolved and
independently reran two app suites: seven tests passed.

One test weakness remained: the deferred-response test switched identity before
the request was sent. `0f2e2b14` corrects it to assert axios.put has been called
before changing the account, then checks response rejection and account B's
retained cache/token. The implementation agent reran all seven app checks and
TypeScript successfully after that test-only change.

## Disposition

Final source/test re-review at `0f2e2b14` found no remaining blocking code
findings. The reviewer verified that the corrected test waits until axios.put
has been called before switching accounts and checks the response-stage error.
The reviewer also inspected the Android emulator screenshots showing optional
onboarding, the saved Paris edit on Profile, Seattle manual launch retained,
and the cleared Home base after relaunch. These corroborate the runtime account;
they are not physical-device evidence.

Overall acceptance remains pending: the real-iPhone walkthrough is an unmet
acceptance criterion, with medium blocking severity, until the Mac session
supplies it. Keep the PR draft for that verification. This is not GitHub
approval, a merge, or ticket completion.

The public Windows pilot service was not deployed from this feature branch.
