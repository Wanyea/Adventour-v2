# Google Places API Cost Control

## Recommendation

Use Places API (New) for now, but only through the Adventour backend.

Do not call Google Places directly from the mobile app for Adventour v2 local/dev work. Backend calls let us:

- keep the API key out of the app bundle
- cache repeated autocomplete searches
- enforce minimum query length
- add rate limits and per-user quotas later
- switch providers later without rewriting screens

## APIs To Enable

In Google Cloud Console, enable:

- Places API

For the current code, put the key in:

```bash
Adventour-v2/Server/.env.local
```

```bash
GOOGLE_API_KEY=your_server_key_here
```

Then restart the backend.

The main provider path uses these Places API (New) endpoints:

- `places:autocomplete`
- `places:searchNearby`
- `places:searchText`

The GPS reverse-label endpoint can optionally use Geocoding API to turn raw
coordinates into `City, State`. If Geocoding API is not enabled, Adventour falls
back to the coordinates and recommendations can still run.

## Spend Controls

Do these before using the key:

- Restrict the key to Places API, and optionally Geocoding API if you want GPS reverse labels.
- Use a separate key for local backend development.
- Set a low daily quota for Places API during development.
- Set a budget alert in Google Cloud Billing.
- Do not put the server key in `AdventourApp/.env.*`.

Google's security guidance says API keys should be restricted, separate keys should be used per app, and unused services should be disabled. It also warns that you are financially responsible for unauthorized usage if keys are unrestricted.

## Autocomplete Pricing Notes

Google recommends using Autocomplete sessions. A session starts with the first autocomplete request containing a session token and ends with a Place Details or Address Validation request using the same token.

For our first local implementation, we are not yet using session tokens because the current UI only needs suggestion text and then resolves the chosen text through `places:searchText`. We reduce cost by:

- requiring at least 3 characters
- debouncing input by 350ms
- caching backend autocomplete results
- returning an empty list when no key is configured

Next improvement: when the user selects a suggestion, preserve its `place_id`, start/use a session token during autocomplete, and terminate with a minimal Place Details Essentials request for coordinates.

## Sources

- Google Autocomplete session pricing: https://developers.google.com/maps/documentation/places/web-service/session-pricing
- Google Places API Nearby Search (New): https://developers.google.com/maps/documentation/places/web-service/nearby-search
- Google Places API Autocomplete (New): https://developers.google.com/maps/documentation/places/web-service/place-autocomplete
- Google Maps API security best practices: https://developers.google.com/maps/api-security-best-practices
