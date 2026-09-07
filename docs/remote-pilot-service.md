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
