# LAN HTTP Transport — Replacing iCloud Drive

> **Status:** PROPOSAL · awaiting redline
> **Triggered by:** Prefrontal Cortex rename (2026-05-06) stripped iCloud entitlements (personal Apple team can't sign them). The existing `DataLoader` / `SampleExporter` paths now silently fall back to bundled sample data because `forUbiquityContainerIdentifier` returns `nil` without the entitlement.

## Why LAN HTTP, not iCloud

Three forces:

1. **Personal-team constraint.** iCloud entitlements require the paid Apple Developer Program ($99/yr). George's team is `Jia Lin Gao` (personal); per `feedback_ios_personal_team.md` we already stripped these entitlements — adding them back breaks the build.
2. **Privacy posture.** `output/ios_bundle.json` carries aggregated genome findings + vitals + meds. The project's stated privacy boundary is local-first, with only TOPMed/ClinVar/PGS/myvariant as external. iCloud Drive — even with Advanced Data Protection on — routes that bundle through Apple infrastructure. A LAN transport keeps it on-prem.
3. **Architectural fit.** Laptop is the source of truth, phone is the consumer. Direct LAN fetch has lower latency than NSMetadataQuery polling, simpler failure modes, and no third-party dependency for the most common case (laptop and phone on same Wi-Fi).

Paying $99 separately to remove the 7-day re-sign treadmill is a defensible call later — it's about ergonomics, not about iCloud.

## Architecture

```
┌────────────────────┐                       ┌──────────────────────┐
│  laptop            │   GET /v1/bundle      │  iOS app             │
│  pipeline/         │ ────────────────────▶ │  PrefrontalCortex    │
│  ios_serve.py      │                       │                      │
│  :8787             │   POST /v1/samples    │  DataLoader          │
│                    │ ◀──────────────────── │  SampleExporter      │
│  reads/writes      │                       │  TransportSettings   │
│  output/ios_export │                       │  (URL + token)       │
└────────────────────┘                       └──────────────────────┘
       same Wi-Fi LAN, bearer-token auth
```

## Server side — `pipeline/ios_serve.py`

Stdlib only (`http.server`, `json`, `secrets`, `pathlib`). No new dependencies in `requirements.txt`.

**Endpoints:**

| Method | Path | Behavior |
|---|---|---|
| `GET`  | `/v1/bundle`  | Returns `output/ios_export/ios_bundle.json` as `application/json`. 404 if absent. `Last-Modified` header from file mtime. |
| `POST` | `/v1/samples` | Body: JSON array of sample dicts. Writes to `output/ios_export/samples_YYYY-MM-DD.json` (today's date on the laptop). If file exists, merges by appending and de-duping on `(ts, type)`. Returns `{"written": <count>, "path": "..."}`. |
| `GET`  | `/v1/health` | Liveness probe. Returns `{"ok": true, "bundle_mtime": "..."}`. **Does not require auth** — used by the iOS app to detect "laptop is reachable but bundle is missing" vs "laptop is offline". |

**Auth:**
- `Authorization: Bearer <token>` on all endpoints except `/v1/health`.
- Token loaded from `~/.snp_gene_analysis/ios_token` (chmod 600).
- First run generates a token via `secrets.token_urlsafe(32)` and prints it; subsequent runs read the existing one.
- `--rotate-token` flag regenerates and prints. Manual sync to phone via Settings sheet.
- Override via `SNP_IOS_TOKEN` env var for testing.

**Bind address:**
- Defaults to `0.0.0.0:8787` (all interfaces, LAN-reachable).
- `--bind 127.0.0.1` flag for laptop-only testing.
- Logs each request as `[ios_serve] <ip> <method> <path> <status> token=<first6>...`. Token prefix only — never the full token.

**Operation:**
- Foreground process; user runs `pipeline/ios_serve.sh` (which `exec`s the Python module) when they want sync. Not a daemon. Matches existing shell-script convention (`refresh.sh`, `00_run_phase1.sh`, etc.).
- README documents the laptop's LAN IP discovery: `ipconfig getifaddr en0` on macOS.

## iOS side

**New: `PrefrontalCortex/Transport/TransportSettings.swift`**
- Stores `serverURL: URL?` (e.g. `http://192.168.1.42:8787`) and `token: String?`.
- URL persisted in `UserDefaults` (App Group), token in **Keychain** (service `com.jlgao.PrefrontalCortex.transport`, account `bearer`).
- Published as an `@Observable` so views can react to "transport configured" state.

**New: `PrefrontalCortex/Views/TransportSettingsView.swift`**
- Sheet accessible from a gear icon on the Profile tab (or settings entrypoint).
- Two fields: laptop URL, bearer token.
- "Test connection" button → calls `/v1/health`, shows green check / red error.
- "Save" persists; "Rotate" prompts for a new token (after running `--rotate-token` on laptop).

**Rewrite: `PrefrontalCortex/DataLoader.swift`**
- Drop `containerID`, `iCloudURL()`, `enum DataError.noICloud`.
- New error: `enum DataError { case transportNotConfigured, transportUnreachable(String), badAuth, bundleMissing, decodingFailed(Error) }`.
- `loadBundle()`:
  - If `TransportSettings.serverURL` and `token` present → `URLSession` `GET /v1/bundle` with header. Decode, cache to `Documents/last_bundle.json`, return.
  - If 401 → `.badAuth`, return last cached bundle if present.
  - If 404 → `.bundleMissing`, return last cached bundle if present.
  - If unreachable → `.transportUnreachable(localizedError)`, return last cached bundle if present.
  - If transport not configured → bundled `sample_bundle.json`. The "Setup → Settings" pill is the loud cue to configure; we don't track a separate "ever-configured" state.

**Rewrite: `PrefrontalCortex/HealthKit/SampleExporter.swift`**
- Drop `containerID` and the iCloud upload code path.
- `uploadDaily()`:
  - Build sample rows (unchanged).
  - If transport configured → `URLSession` `POST /v1/samples` with header and JSON body. Return parsed response.
  - If not configured → no-op with structured log; surface a banner the next time the user opens Settings.

**App Transport Security:**
- `Info.plist` adds `NSAppTransportSecurity → NSAllowsLocalNetworking: true`. This is a documented narrow exception that allows plain HTTP only to RFC1918 / link-local addresses, not arbitrary HTTP. No global ATS bypass.
- iOS 14+ also requires the Local Network usage prompt for any LAN connection. Add `NSLocalNetworkUsageDescription` in `Info.plist`: "Connect to your laptop on the same Wi-Fi to sync the daily bundle."

## Error states (UI)

The Now header gets a thin status pill (right-aligned, dim):

| State | Pill text | Bundle behavior |
|---|---|---|
| Transport configured, healthy, fresh | *(no pill)* | Live bundle |
| Configured, fresh but >24h old | "Bundle 1d old" | Live bundle, warning |
| Configured, laptop offline | "Laptop offline" | Last cached bundle if present, else sample |
| Configured, 401 | "Auth error — Settings" | Last cached bundle if present, else sample |
| Configured, bundle missing on laptop (404) | "Run refresh.sh" | Last cached bundle if present, else sample |
| Not configured | "Setup → Settings" | Sample bundle |

DataLoader caches the last successful response in `Documents/last_bundle.json` so the offline path renders something real instead of the long-stale dev sample.

## What's deleted

- `DataLoader.iCloudURL()` and the `containerID` constant.
- `SampleExporter.containerID` and the iCloud upload code.
- `enum DataError.noICloud`.
- README architecture diagram's iCloud arrows.

## Testing

`tests/test_ios_serve.py`:
- Spin server on a random port using `http.server.HTTPServer` in a thread; tear down in `addfinalizer`.
- `test_bundle_get_with_token` — fixture writes a tiny bundle, asserts 200 + body.
- `test_bundle_get_no_token` — asserts 401.
- `test_bundle_get_bad_token` — asserts 401, no token leak in response body.
- `test_bundle_get_missing_file` — asserts 404.
- `test_samples_post_creates_file` — POST array, asserts file written, asserts merge semantics on second POST same day.
- `test_samples_post_invalid_body` — non-array body returns 400.
- `test_health_no_auth` — `/v1/health` works without token.
- `test_log_redacts_token` — capture stdout, assert full token never appears.

iOS-side tests are out of scope (the project has no iOS test target today; not adding one as part of this).

## Out of scope for v1

- **TLS / HTTPS.** LAN-only, behind a router, single trusted network. Add later if George ever wants to sync from outside the home (which probably means a tailscale-style overlay, not a self-signed cert).
- **Bonjour / mDNS auto-discovery.** Manual URL entry once is fine; the laptop's LAN IP rarely changes on a home network with a DHCP lease.
- **Multi-device / multi-user.** Single phone, single laptop assumption.
- **Background sync.** v1 fetches on app foreground (`onAppear`) and on pull-to-refresh. `BGAppRefreshTask` registration is a follow-up.
- **WebSocket / push.** No server→phone wake-ups in v1. Local notifications already cover the executive-function alerts that matter.

## Migration / first-run

1. Land rename commit (separate, see plan).
2. Land transport commit:
   - Server runs once → prints a token.
   - User opens phone, builds new "Prefrontal Cortex" app (note: bundle ID changed, so it's a fresh install — the old "Frontal Lobe" app stays alongside until manually deleted).
   - Phone shows "Setup → Settings" pill.
   - User opens Settings sheet, enters laptop URL (e.g. `http://192.168.1.42:8787`) and the token printed by the server.
   - "Test connection" button confirms `/v1/health` is reachable.
   - Save. Now the app fetches real data on next foreground.
3. Delete the old "Frontal Lobe" app icon when ready (optional; the new one works fine alongside).

## Commit plan

Two commits, in order:

1. **`Rename: Frontal Lobe → Prefrontal Cortex; remove iCloud transport`**
   - All staged renames + project.yml changes + new entitlements + xcodeproj.
   - Removes dead `containerID` / `iCloudURL` / `enum DataError.noICloud`. `DataLoader` and `SampleExporter` temporarily stub-fail (returns `transportNotConfigured`).
   - README updated: title, build commands, source layout. Architecture diagram removed for now (re-added in commit 2).

2. **`iOS: LAN HTTP transport (laptop ↔ phone)`**
   - `pipeline/ios_serve.py` + `tests/test_ios_serve.py`.
   - `Transport/TransportSettings.swift`, `Views/TransportSettingsView.swift`.
   - `DataLoader` and `SampleExporter` rewritten against URLSession.
   - `Info.plist`: `NSAllowsLocalNetworking`, `NSLocalNetworkUsageDescription`.
   - README: new architecture diagram + transport setup section.
   - `make ios-serve` recipe (or short shell script).
