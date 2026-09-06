# App Engine Deployment

`Server/app.yaml` is used only when deploying the backend to Google App Engine.
When you run this from `Adventour-v2/Server`:

```powershell
gcloud app deploy
```

Google Cloud reads `app.yaml` to decide the Python runtime, Gunicorn entrypoint,
scaling settings, and deployed environment variables.

## Why The Real File Is Ignored

The backend reads configuration through environment variables:

- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `DB_CONNECTION_NAME`
- `GOOGLE_API_KEY`

For local development those come from `Server/.env.local`. For App Engine, they
come from `Server/app.yaml` unless we later move them into Secret Manager.

Because `app.yaml` can contain secrets, the repository now commits only:

```text
Server/app.yaml.example
```

and ignores:

```text
Server/app.yaml
```

## Deploy Flow

Create the local deploy manifest:

```powershell
cd D:\source\Adventour\Adventour-v2\Server
Copy-Item app.yaml.example app.yaml
```

Edit `app.yaml` with your real Cloud SQL settings and server-side Google Maps
key, then deploy:

```powershell
gcloud app deploy
```

## Important Key Safety

Use a server-restricted Google Maps key for `GOOGLE_API_KEY`. Restrict it in
Google Cloud by API and, where possible, by backend/service usage. Do not put
this key in the mobile app env files.

The safer future version is to store `DB_PASSWORD` and `GOOGLE_API_KEY` in
Google Secret Manager and have the backend load them at startup. The current
template keeps Phase 1 simpler while preventing secrets from being committed.
