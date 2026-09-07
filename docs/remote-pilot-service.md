# Remote pilot service

The Windows PC service is deliberately split from the Flask module. Run
`Server/start_remote_service.ps1` with a private `.env.remote` file. The
wrapper loads that file, runs preflight, and only then imports the application.
It refuses to start when dev auth is enabled, Firebase credentials are absent,
Postgres is not local, or the listener is not loopback-only.

Copy `Server/.env.remote.example` to `Server/.env.remote`, fill in the local
Postgres and Firebase service-account values, then run:

```powershell
Set-Location Server
PowerShell -ExecutionPolicy Bypass -File .\start_remote_service.ps1
```

The service uses Waitress and listens on `127.0.0.1:8080` by default. Put the
TLS tunnel or reverse proxy in front of that loopback listener; do not expose
Postgres or bind the app to `0.0.0.0`. The public endpoint must use the real
Firebase project and must not use `ADVENTOUR_DEV_AUTH`.

## Tailscale Funnel pilot route

The approved pilot route is Tailscale Funnel on the Windows PC. Install the
current Tailscale client on that PC, sign it into the owner's tailnet, and
confirm that the device has a stable `*.ts.net` hostname. Friends' iPhones do
not need the Tailscale app because Funnel is public HTTPS; Firebase remains the
application authentication layer.

After the local service has passed preflight and is listening on loopback, run
the following in an elevated PowerShell window on the Windows PC:

```powershell
tailscale funnel --bg http://127.0.0.1:8080
tailscale funnel status
```

The status output is the source of truth for the public HTTPS URL. Use that
exact URL as `BACKEND_BASE_URL` in the Mac-only pilot env file. Do not use
`tailscale serve` for the friends pilot: Serve is restricted to the tailnet and
will not work for iPhones outside it. `tailscale serve` may be used separately
for private operator diagnostics, but never as the public route.

Keep Funnel configured on the same device and use `--bg` so it resumes after a
Tailscale restart or Windows reboot. After every service restart, verify the
local health/readiness/version endpoints first, then verify the public health
URL and make the authenticated pilot request. If the local service is stopped,
Funnel must not be treated as a healthy backend even if its public listener
still responds.

To remove the public route after the pilot, run:

```powershell
tailscale funnel reset
```

Do not record auth keys, private tailnet policy, or Tailscale account details in
the repository or in the public verification packet.

Before an off-network pilot check, verify locally:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/healthz
Invoke-RestMethod http://127.0.0.1:8080/readyz
Invoke-RestMethod http://127.0.0.1:8080/version
```

Then use the HTTPS endpoint from a network outside the PC, sign in with a real
Firebase account, submit one recommendation feedback response, and confirm the
joined pilot export locally. Record the endpoint, service version, Firebase
project, database host, restart time, and request/export IDs in the private
verification packet. Never commit the env file, service account, or participant
export.

## Stop, restart, and reboot check

Keep the service in its operator PowerShell window. Press `Ctrl+C` to stop it;
the process should exit and a local request should fail:

```powershell
Invoke-WebRequest http://127.0.0.1:8080/healthz -TimeoutSec 3
```

Start it again with the same command. The script must report successful
preflight before Waitress starts. Recheck `/healthz`, `/readyz`, and `/version`,
then make one authenticated pilot request before resuming testing. Restart the
HTTPS tunnel separately and verify its public health URL after the local checks.

For a reboot rehearsal, stop the service and tunnel first, restart Windows
using the normal Windows restart action, sign in, and rerun
`start_remote_service.ps1 -EnvFile .env.remote`. This service is intentionally
operator-started; no unattended startup task is claimed. Record the stop,
restart, reboot, health, and authenticated-request timestamps in the private
verification packet. If preflight fails after reboot, keep the endpoint offline
until the selected env file and local Postgres/Firebase checks pass.
