# Prefrontal Cortex Rename + LAN HTTP Transport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the Frontal Lobe → Prefrontal Cortex rename (already partially staged), then replace the dead iCloud Drive transport with a LAN HTTP server on the laptop and a `URLSession` client on the phone, with bearer-token auth.

**Architecture:** Two repos, two commits per repo. Pipeline (`/Users/georgegao/snp_gene_analysis/`) gains `pipeline/ios_serve.py` (stdlib http.server, ~150 lines) and `tests/test_ios_serve.py`. iOS app (`/Users/georgegao/personal-data-ios/`) gains a `Transport/` module (Keychain helper, settings store, URLSession client) and a settings sheet UI; `DataLoader` and `SampleExporter` are rewritten to use the new client.

**Tech Stack:**
- **Server:** Python 3 stdlib only (`http.server`, `secrets`, `urllib.request` for tests). Already-pinned deps in `requirements.txt` are unchanged.
- **iOS:** Swift 5.10 / iOS 17, SwiftUI, `URLSession`, `Security` framework (Keychain), `ObservableObject` + `@Published` (matches existing codebase — do **not** introduce `@Observable` macro).
- **Build:** xcodegen → xcodebuild for simulator.

**Spec:** `docs/superpowers/specs/2026-05-06-lan-http-transport.md`

**Working directories:**
- Pipeline: `/Users/georgegao/snp_gene_analysis/`
- iOS: `/Users/georgegao/personal-data-ios/`

---

## File Structure

### Pipeline repo

| Path | Action | Purpose |
|---|---|---|
| `pipeline/ios_serve.py` | Create | Stdlib HTTP server: `/v1/health`, `/v1/bundle`, `/v1/samples`. Token loading + CLI. |
| `pipeline/ios_serve.sh` | Create | Convenience wrapper: `python3 -m pipeline.ios_serve "$@"` from repo root. |
| `tests/test_ios_serve.py` | Create | Pytest suite — token logic + endpoint behaviors via real localhost socket. |
| `README.md` | Modify | Add an "iOS sync" section describing how to start the server and pair the phone. |

### iOS repo

| Path | Action | Purpose |
|---|---|---|
| `PrefrontalCortex/Transport/Keychain.swift` | Create | Static helper around `Security.framework` for password items. |
| `PrefrontalCortex/Transport/TransportSettings.swift` | Create | `ObservableObject` holding serverURL (UserDefaults via App Group) + token (Keychain). Singleton `.shared`. |
| `PrefrontalCortex/Transport/TransportClient.swift` | Create | `URLSession` wrappers for the three endpoints. Maps HTTP errors → typed `TransportError`. |
| `PrefrontalCortex/Views/TransportSettingsView.swift` | Create | SwiftUI sheet: serverURL + token fields, "Test connection" button, save action. |
| `PrefrontalCortex/Views/TransportStatusPill.swift` | Create | Tiny pill shown in `TodayHeaderView` reflecting current transport state. Tappable → opens settings sheet. |
| `PrefrontalCortex/DataLoader.swift` | Modify (rewrite body) | Drop `containerID` / `iCloudURL()`. New `loadBundle()` uses `TransportClient.fetchBundle()`, caches to `Documents/last_bundle.json`. |
| `PrefrontalCortex/HealthKit/SampleExporter.swift` | Modify (rewrite body) | Drop `containerID`. New `uploadDaily()` posts to `/v1/samples`. |
| `PrefrontalCortex/Views/TodayHeaderView.swift` | Modify | Embed `TransportStatusPill` top-right. |
| `PrefrontalCortex/ContentView.swift` | Modify | Change toolbar icon from `icloud.and.arrow.up` to `arrow.up.circle`; add Profile-tab toolbar gear that opens `TransportSettingsView`. |
| `PrefrontalCortex/AppStore.swift` | Modify | Wire `TransportSettings.shared` into bootstrap; surface transport-error states for the pill to read. |
| `PrefrontalCortex/Resources/Info.plist` | Modify (via `project.yml`) | Add `NSAppTransportSecurity → NSAllowsLocalNetworking: true` and `NSLocalNetworkUsageDescription`. |
| `project.yml` | Modify | Embed the two new Info.plist keys in the `info.properties` block. |
| `README.md` | Modify | New title, build commands, source layout, architecture diagram showing LAN HTTP. |

---

## Phase 1 — Land the rename (iOS repo)

The working tree already has the file moves, project.yml updates, new entitlements, and a regenerated `PrefrontalCortex.xcodeproj/`. This phase commits that work after fixing the README and verifying the build still passes. **Do not modify Swift files in this phase** — the iCloud-fossil constants stay (commit 2 removes them).

### Task 1: Update `README.md` to reflect the rename

**Files:**
- Modify: `/Users/georgegao/personal-data-ios/README.md`

- [ ] **Step 1: Replace `PersonalData` references and adjust the architecture section**

The README currently has 5 stale `PersonalData` references and an iCloud-based architecture diagram. Replace with the content below. Note: the architecture diagram is *removed* in this commit — Phase 4 re-adds a LAN-HTTP version.

Open `/Users/georgegao/personal-data-ios/README.md` and replace its full contents with:

````markdown
# Prefrontal Cortex — iOS Companion

SwiftUI app that mirrors the [`personal-genome-pipeline`](https://github.com/jlgao2/personal-genome-pipeline)
desktop dashboard's daily executive-function surface on iPhone, with **live HealthKit reads**
overriding cached values from the laptop bundle.

## Status

- ✅ Builds (`Debug` for `iphonesimulator`, Xcode 26.3)
- ✅ Renders Now (Today timeline + Adapted Session), Plan, Social, Profile
- ✅ Widgets: Hero, Session, Reach Out (Lock + Home screen)
- ⚠ HealthKit reads work on real device only (simulator has no Health data)
- ⚠ Laptop ↔ phone transport: see follow-up commit

## Build

```bash
xcodegen generate                 # if you've changed project.yml
open PrefrontalCortex.xcodeproj
# or from CLI:
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -project PrefrontalCortex.xcodeproj \
  -scheme PrefrontalCortex \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build
```

## Source layout

```
PrefrontalCortex/
├── App.swift                       Entry point + bootstrap
├── AppStore.swift                  Observable state container
├── ContentView.swift               TabView root (Now / Plan / Social / Profile)
├── DataLoader.swift                Bundle loader
├── Models/Bundle.swift             Codable models matching laptop JSON
├── HealthKit/HealthStore.swift     HKHealthStore wrapper
├── HealthKit/SampleExporter.swift  Pushes daily HK samples back to laptop
├── EventKit/CalendarStore.swift    Read calendar + write reminders/events
├── Notifications.swift             Local notification scheduler
├── Views/
│   ├── TodayHeaderView.swift
│   ├── TimelineView.swift          ← unified Today timeline
│   ├── AdaptedSessionView.swift
│   ├── ActionLoopView.swift        (Plan tab)
│   ├── PlanTabView.swift
│   ├── SocialView.swift
│   ├── HealthProfileView.swift
│   ├── GenomicsView.swift
│   └── …
└── Resources/
    ├── Info.plist                       (generated by xcodegen)
    ├── PrefrontalCortex.entitlements
    └── sample_bundle.json               (gitignored — dev placeholder)
```

## Bundle IDs / signing

- App: `com.jlgao.PrefrontalCortex`
- Widget: `com.jlgao.PrefrontalCortex.PrefrontalCortexWidget`
- App Group: `group.com.jlgao.PrefrontalCortex`
- Signed with personal Apple Developer team (`Jia Lin Gao`). iCloud, health-records,
  Associated Domains and full APNs are unavailable on this team and are intentionally
  not in the entitlements.
````

- [ ] **Step 2: Verify the README has no stale references**

Run: `grep -n "PersonalData\|FrontalLobe\|frontal_lobe" /Users/georgegao/personal-data-ios/README.md`
Expected: no output (zero matches).

### Task 2: Verify the build still works after the rename

**Files:** none modified — verification only.

- [ ] **Step 1: Regenerate the project from `project.yml`**

Run from `/Users/georgegao/personal-data-ios/`:

```bash
xcodegen generate
```

Expected: `Created project at /Users/georgegao/personal-data-ios/PrefrontalCortex.xcodeproj`

If `xcodegen` is missing: `brew install xcodegen`.

- [ ] **Step 2: Build for simulator**

Run from `/Users/georgegao/personal-data-ios/`:

```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -project PrefrontalCortex.xcodeproj \
  -scheme PrefrontalCortex \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build 2>&1 | tail -20
```

Expected: ends with `** BUILD SUCCEEDED **`.

If "destination is not valid", list available simulators with
`xcrun simctl list devices available | grep iPhone` and substitute a present model.

### Task 3: Stage and commit the rename

**Files:** none new — git plumbing only.

- [ ] **Step 1: Stage everything (renames, deletions, new files)**

Run from `/Users/georgegao/personal-data-ios/`:

```bash
git add -A
git status --short | head -40
```

Expected: a mix of `R` (renames) and `A` (new files like `PrefrontalCortex/Resources/PrefrontalCortex.entitlements`, `PrefrontalCortexWidget/PrefrontalCortexWidget.entitlements`, `PrefrontalCortexWidget/PrefrontalCortexWidgetBundle.swift`, the README, the new `.xcodeproj/`); plus deletes for `PersonalData.xcodeproj/`, the old `PersonalData.entitlements`, `FrontalLobeWidget.entitlements`, `FrontalLobeWidgetBundle.swift`. No `??` (untracked) lines remain except `.DS_Store` if any.

- [ ] **Step 2: Sanity-check no `PersonalData` strings survive in tracked content**

Run from `/Users/georgegao/personal-data-ios/`:

```bash
git grep -n "PersonalData\|FrontalLobeWidget" -- ':!*.pbxproj' ':!*.xcworkspace*'
```

Expected: no output. (The `.pbxproj` is gitignored or handled below; `xcworkspace` is excluded for the same reason.) If `.pbxproj` is *not* in `.gitignore`, the new generated one is fine because xcodegen produces strings that all reference `PrefrontalCortex`. If you see surviving `PersonalData` matches in the pbxproj, run `xcodegen generate` again — those should all be cleared.

- [ ] **Step 3: Commit**

Run from `/Users/georgegao/personal-data-ios/`:

```bash
git commit -m "$(cat <<'EOF'
Rename: Frontal Lobe → Prefrontal Cortex

Folder renames (PersonalData → PrefrontalCortex; FrontalLobeWidget →
PrefrontalCortexWidget), bundle IDs (com.jlgao.PrefrontalCortex[.Widget]),
App Group (group.com.jlgao.PrefrontalCortex), display name, widget kind
strings, entitlements file paths.

Drop iCloud + health-records entitlements — personal Apple team can't
sign them. App Group + basic HealthKit only. README and project.yml
updated to match. xcodeproj regenerated from project.yml via xcodegen.

The dead iCloud constants in DataLoader.swift and SampleExporter.swift
move with the rename and are removed in the next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: `[main <hash>] Rename: Frontal Lobe → Prefrontal Cortex` followed by a stat summary.

- [ ] **Step 4: Sanity check the resulting tree**

Run from `/Users/georgegao/personal-data-ios/`:

```bash
git log -1 --stat | tail -10
git status
```

Expected: working tree clean. Last commit shows ~38 files changed.

---

## Phase 2 — Pipeline-side LAN HTTP server

TDD style. Write the test, run it, see it fail, write the minimum code, see it pass, repeat. End the phase with one commit covering the server + tests + shell wrapper.

### Task 4: Token management — failing tests first

**Files:**
- Create: `/Users/georgegao/snp_gene_analysis/tests/test_ios_serve.py`

- [ ] **Step 1: Create the test file with three token tests**

Create `/Users/georgegao/snp_gene_analysis/tests/test_ios_serve.py` with:

```python
"""Tests for pipeline.ios_serve — token management and HTTP endpoints.

Tests spin up an http.server.HTTPServer on a free port (port=0) in a
background thread and make real HTTP calls against it via stdlib
urllib. No external dependencies.
"""
import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest


# ─── Token management ───────────────────────────────────────────────────────

def test_token_loaded_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SNP_IOS_TOKEN", raising=False)
    f = tmp_path / "tok"
    f.write_text("file-token\n")
    from pipeline.ios_serve import load_or_create_token
    assert load_or_create_token(f) == "file-token"


def test_token_generated_on_first_run(tmp_path, monkeypatch):
    monkeypatch.delenv("SNP_IOS_TOKEN", raising=False)
    f = tmp_path / "subdir" / "tok"
    from pipeline.ios_serve import load_or_create_token
    t = load_or_create_token(f)
    assert len(t) >= 32  # secrets.token_urlsafe(32) yields ≥43 chars
    assert f.read_text().strip() == t
    # chmod 600 — owner read/write only
    assert (f.stat().st_mode & 0o777) == 0o600


def test_token_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SNP_IOS_TOKEN", "env-token")
    f = tmp_path / "tok"
    f.write_text("file-token\n")
    from pipeline.ios_serve import load_or_create_token
    assert load_or_create_token(f) == "env-token"
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `/Users/georgegao/snp_gene_analysis/`:

```bash
pytest tests/test_ios_serve.py -v 2>&1 | tail -20
```

Expected: all three tests fail with `ModuleNotFoundError: No module named 'pipeline.ios_serve'` (collection error is fine — it confirms the module is missing).

### Task 5: Implement token management to make those three tests pass

**Files:**
- Create: `/Users/georgegao/snp_gene_analysis/pipeline/ios_serve.py`

- [ ] **Step 1: Create `pipeline/ios_serve.py` with the token helper**

```python
"""LAN HTTP server for laptop ↔ Prefrontal Cortex iOS app sync.

Endpoints (Authorization: Bearer <token> required except /v1/health):
  GET  /v1/health   → liveness; reports bundle mtime
  GET  /v1/bundle   → returns output/ios_export/ios_bundle.json
  POST /v1/samples  → array of sample dicts → samples_<today>.json (merged)

Run: python3 -m pipeline.ios_serve [--port 8787] [--bind 0.0.0.0]
     pipeline/ios_serve.sh [...]   (convenience wrapper)
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import date, datetime, timezone
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Type

DEFAULT_PORT = 8787
DEFAULT_TOKEN_FILE = Path.home() / ".snp_gene_analysis" / "ios_token"
DEFAULT_EXPORT_DIR = Path("output") / "ios_export"


def load_or_create_token(token_path: Path = DEFAULT_TOKEN_FILE) -> str:
    """Return the bearer token. Env var > file > newly generated.

    On first run, generates secrets.token_urlsafe(32), writes chmod 600.
    """
    env = os.environ.get("SNP_IOS_TOKEN")
    if env:
        return env
    if token_path.exists():
        return token_path.read_text().strip()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    token_path.write_text(token + "\n")
    token_path.chmod(0o600)
    return token
```

- [ ] **Step 2: Run the token tests to verify they pass**

Run from `/Users/georgegao/snp_gene_analysis/`:

```bash
pytest tests/test_ios_serve.py -v 2>&1 | tail -10
```

Expected: 3 passed (other tests don't exist yet).

### Task 6: `/v1/health` — failing test first

- [ ] **Step 1: Append the server fixture and `/v1/health` test to `tests/test_ios_serve.py`**

Append to `/Users/georgegao/snp_gene_analysis/tests/test_ios_serve.py`:

```python
# ─── Server fixture ─────────────────────────────────────────────────────────

@pytest.fixture
def server(tmp_path):
    """Spin a server on a random port; tear down after the test."""
    from pipeline.ios_serve import make_handler
    export_dir = tmp_path / "ios_export"
    export_dir.mkdir()
    token = "test-token-abcdef0123456789"
    handler_cls = make_handler(token=token, export_dir=export_dir)
    httpd = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "url": f"http://127.0.0.1:{port}",
            "token": token,
            "export_dir": export_dir,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _request(url: str, *, token: str | None = None, method: str = "GET",
             body: object = None) -> tuple[int, dict]:
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=2) as resp:
            payload = resp.read()
            return resp.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        body_bytes = e.read()
        try:
            return e.code, json.loads(body_bytes)
        except json.JSONDecodeError:
            return e.code, {"raw": body_bytes.decode(errors="replace")}


# ─── /v1/health ─────────────────────────────────────────────────────────────

def test_health_no_auth_required(server):
    status, body = _request(f"{server['url']}/v1/health")
    assert status == 200
    assert body["ok"] is True
    assert "bundle_mtime" in body
    assert body["bundle_mtime"] is None  # no bundle written


def test_health_reports_bundle_mtime(server):
    bundle = server["export_dir"] / "ios_bundle.json"
    bundle.write_text("{}")
    status, body = _request(f"{server['url']}/v1/health")
    assert status == 200
    assert body["bundle_mtime"] is not None
```

- [ ] **Step 2: Run health tests to confirm they fail**

```bash
pytest tests/test_ios_serve.py::test_health_no_auth_required tests/test_ios_serve.py::test_health_reports_bundle_mtime -v 2>&1 | tail -10
```

Expected: both fail with `ImportError: cannot import name 'make_handler' from 'pipeline.ios_serve'`.

### Task 7: Implement `make_handler` + `/v1/health`

- [ ] **Step 1: Append the handler factory to `pipeline/ios_serve.py`**

Append to `/Users/georgegao/snp_gene_analysis/pipeline/ios_serve.py`:

```python
def _send_json(handler: BaseHTTPRequestHandler, status: int, body: dict) -> None:
    payload = json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def make_handler(token: str, export_dir: Path) -> Type[BaseHTTPRequestHandler]:
    """Return a BaseHTTPRequestHandler subclass with token + export_dir bound."""

    class Handler(BaseHTTPRequestHandler):
        # Suppress default access logging — we have a custom redacted log below.
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            ip = self.client_address[0]
            sys.stderr.write(f"[ios_serve] {ip} {fmt % args}\n")

        # ── Auth helper ────────────────────────────────────────────────────
        def _check_auth(self) -> bool:
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return False
            return header.removeprefix("Bearer ").strip() == token

        # ── Routes ─────────────────────────────────────────────────────────
        def do_GET(self):  # noqa: N802 (stdlib API)
            if self.path == "/v1/health":
                self._handle_health()
                return
            if not self._check_auth():
                _send_json(self, 401, {"error": "unauthorized"})
                return
            if self.path == "/v1/bundle":
                self._handle_bundle_get()
                return
            _send_json(self, 404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if not self._check_auth():
                _send_json(self, 401, {"error": "unauthorized"})
                return
            if self.path == "/v1/samples":
                self._handle_samples_post()
                return
            _send_json(self, 404, {"error": "not found"})

        # ── Handlers ───────────────────────────────────────────────────────
        def _handle_health(self):
            bundle_path = export_dir / "ios_bundle.json"
            mtime_iso: str | None = None
            if bundle_path.exists():
                mtime_iso = datetime.fromtimestamp(
                    bundle_path.stat().st_mtime, tz=timezone.utc
                ).isoformat()
            _send_json(self, 200, {"ok": True, "bundle_mtime": mtime_iso})

        def _handle_bundle_get(self):
            bundle_path = export_dir / "ios_bundle.json"
            if not bundle_path.exists():
                _send_json(self, 404, {"error": "bundle not found"})
                return
            data = bundle_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header(
                "Last-Modified",
                formatdate(bundle_path.stat().st_mtime, usegmt=True),
            )
            self.end_headers()
            self.wfile.write(data)

        def _handle_samples_post(self):
            length = int(self.headers.get("Content-Length", "0") or "0")
            try:
                body = json.loads(self.rfile.read(length) or b"null")
            except json.JSONDecodeError:
                _send_json(self, 400, {"error": "invalid json"})
                return
            if not isinstance(body, list):
                _send_json(self, 400, {"error": "expected json array"})
                return
            export_dir.mkdir(parents=True, exist_ok=True)
            f = export_dir / f"samples_{date.today().isoformat()}.json"
            existing = []
            if f.exists():
                try:
                    existing = json.loads(f.read_text())
                except json.JSONDecodeError:
                    existing = []
                if not isinstance(existing, list):
                    existing = []
            seen = {(r.get("ts"), r.get("type")) for r in existing}
            new_rows = [r for r in body if (r.get("ts"), r.get("type")) not in seen]
            merged = existing + new_rows
            f.write_text(json.dumps(merged, indent=2))
            _send_json(self, 200, {"written": len(new_rows), "path": str(f)})

    return Handler
```

- [ ] **Step 2: Run health tests to verify they pass**

```bash
pytest tests/test_ios_serve.py -v 2>&1 | tail -15
```

Expected: 5 passed (token x3 + health x2). The bundle/samples tests don't exist yet; that's fine.

### Task 8: `/v1/bundle` — failing tests first

- [ ] **Step 1: Append bundle tests to `tests/test_ios_serve.py`**

Append:

```python
# ─── /v1/bundle ─────────────────────────────────────────────────────────────

def test_bundle_get_with_token(server):
    bundle = {"hello": "world", "exported_at": "2026-05-06T10:00:00Z"}
    (server["export_dir"] / "ios_bundle.json").write_text(json.dumps(bundle))
    status, body = _request(f"{server['url']}/v1/bundle", token=server["token"])
    assert status == 200
    assert body == bundle


def test_bundle_get_no_token_returns_401(server):
    status, body = _request(f"{server['url']}/v1/bundle")
    assert status == 401


def test_bundle_get_wrong_token_returns_401(server):
    status, body = _request(f"{server['url']}/v1/bundle", token="wrong-token")
    assert status == 401


def test_bundle_get_missing_returns_404(server):
    status, body = _request(f"{server['url']}/v1/bundle", token=server["token"])
    assert status == 404
```

- [ ] **Step 2: Run them; expect all four to pass**

The handler factory already implements `/v1/bundle` (we wrote it ahead in Task 7's diff because the four route handlers naturally cluster in one file). So this batch is a verification, not an implementation, step.

```bash
pytest tests/test_ios_serve.py -v 2>&1 | tail -15
```

Expected: 9 passed.

### Task 9: `/v1/samples` — failing tests first

- [ ] **Step 1: Append samples tests**

Append:

```python
# ─── /v1/samples ────────────────────────────────────────────────────────────

def test_samples_post_writes_file(server):
    rows = [
        {"ts": "2026-05-06T10:00:00Z", "ts_end": "2026-05-06T10:00:00Z",
         "source": "healthkit", "type": "heart_rate_resting",
         "value": 44, "unit": "bpm", "meta": "{\"via\":\"ios_app\"}"},
    ]
    status, body = _request(
        f"{server['url']}/v1/samples", token=server["token"],
        method="POST", body=rows,
    )
    assert status == 200
    assert body["written"] == 1
    files = sorted(server["export_dir"].glob("samples_*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text()) == rows


def test_samples_post_merges_and_dedupes(server):
    base = {"ts_end": "2026-05-06T10:00:00Z", "source": "healthkit",
            "value": 44, "unit": "bpm", "meta": "{}"}
    first = [{**base, "ts": "2026-05-06T10:00:00Z", "type": "heart_rate_resting"}]
    second = [
        {**base, "ts": "2026-05-06T10:00:00Z", "type": "heart_rate_resting"},  # dupe
        {**base, "ts": "2026-05-06T11:00:00Z", "type": "vo2max",
         "value": 51.2, "unit": "mL/min·kg"},
    ]
    _request(f"{server['url']}/v1/samples", token=server["token"],
             method="POST", body=first)
    status, body = _request(f"{server['url']}/v1/samples", token=server["token"],
                            method="POST", body=second)
    assert status == 200
    assert body["written"] == 1
    files = sorted(server["export_dir"].glob("samples_*.json"))
    merged = json.loads(files[0].read_text())
    assert len(merged) == 2


def test_samples_post_rejects_non_array(server):
    status, body = _request(
        f"{server['url']}/v1/samples", token=server["token"],
        method="POST", body={"not": "an array"},
    )
    assert status == 400


def test_samples_post_rejects_unauthorized(server):
    status, body = _request(
        f"{server['url']}/v1/samples", method="POST", body=[],
    )
    assert status == 401
```

- [ ] **Step 2: Run; expect all four to pass**

```bash
pytest tests/test_ios_serve.py -v 2>&1 | tail -20
```

Expected: 13 passed.

### Task 10: CLI args, shell wrapper, log redaction

**Files:**
- Modify: `/Users/georgegao/snp_gene_analysis/pipeline/ios_serve.py`
- Create: `/Users/georgegao/snp_gene_analysis/pipeline/ios_serve.sh`

- [ ] **Step 1: Add log-redaction test**

Append to `tests/test_ios_serve.py`:

```python
# ─── Log redaction ──────────────────────────────────────────────────────────

def test_full_token_never_appears_in_logs(server, capfd):
    # Make a real authenticated request, then read everything written to stderr.
    _request(f"{server['url']}/v1/bundle", token=server["token"])
    captured = capfd.readouterr()
    assert server["token"] not in captured.err
    assert server["token"] not in captured.out
```

- [ ] **Step 2: Run it; expect it to pass already**

The current `log_message` implementation writes only the request line (no headers), so the token never enters the log stream. Verify:

```bash
pytest tests/test_ios_serve.py::test_full_token_never_appears_in_logs -v 2>&1 | tail -5
```

Expected: passed.

- [ ] **Step 3: Add CLI entrypoint to `pipeline/ios_serve.py`**

Append:

```python
# ─── CLI ────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LAN sync server for Prefrontal Cortex iOS.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--bind", default="0.0.0.0",
                        help="Interface to bind. Default 0.0.0.0 (LAN). Use 127.0.0.1 for laptop-only.")
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR,
                        help="Directory containing ios_bundle.json (default: output/ios_export).")
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--rotate-token", action="store_true",
                        help="Generate a new token, print it, and exit.")
    args = parser.parse_args(argv)

    if args.rotate_token:
        args.token_file.unlink(missing_ok=True)
        token = load_or_create_token(args.token_file)
        print(f"New token: {token}", flush=True)
        return 0

    token = load_or_create_token(args.token_file)
    handler_cls = make_handler(token=token, export_dir=args.export_dir)
    httpd = HTTPServer((args.bind, args.port), handler_cls)
    print(f"[ios_serve] token (first 6): {token[:6]}…  full token in {args.token_file}",
          file=sys.stderr, flush=True)
    print(f"[ios_serve] listening on http://{args.bind}:{args.port}",
          file=sys.stderr, flush=True)
    print(f"[ios_serve] serving exports from {args.export_dir.resolve()}",
          file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[ios_serve] stopped", file=sys.stderr)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Create the shell wrapper**

Create `/Users/georgegao/snp_gene_analysis/pipeline/ios_serve.sh` with:

```bash
#!/usr/bin/env bash
# Convenience wrapper to run the LAN sync server from the repo root.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m pipeline.ios_serve "$@"
```

Then make it executable:

```bash
chmod +x pipeline/ios_serve.sh
```

- [ ] **Step 5: Smoke-test the CLI**

Run from `/Users/georgegao/snp_gene_analysis/`:

```bash
SNP_IOS_TOKEN=smoke-token timeout 1 python3 -m pipeline.ios_serve --port 18787 --bind 127.0.0.1 --export-dir /tmp 2>&1 | head -5
```

Expected output (the `timeout 1` exits the server after a second; that's intentional):

```
[ios_serve] token (first 6): smoke-…  full token in /Users/georgegao/.snp_gene_analysis/ios_token
[ios_serve] listening on http://127.0.0.1:18787
[ios_serve] serving exports from /tmp
```

(The token file path may differ but the first 6 chars of the env-token will match `smoke-`.)

- [ ] **Step 6: Run the full test suite to ensure nothing else regressed**

```bash
pytest tests/ -q 2>&1 | tail -5
```

Expected: `86 passed` (72 baseline + 14 new tests). Adjust if the test count differs by a couple — list count above is a guide, not a contract.

### Task 11: Commit pipeline-side server

- [ ] **Step 1: Stage and commit**

Run from `/Users/georgegao/snp_gene_analysis/`:

```bash
git add pipeline/ios_serve.py pipeline/ios_serve.sh tests/test_ios_serve.py
git status --short
```

Expected: 3 added files (`A`).

```bash
git commit -m "$(cat <<'EOF'
iOS sync: add LAN HTTP server (pipeline.ios_serve)

Stdlib http.server with bearer-token auth, three endpoints:
  GET  /v1/health    no auth, reports bundle mtime
  GET  /v1/bundle    returns output/ios_export/ios_bundle.json
  POST /v1/samples   merges into samples_<today>.json, dedupes by (ts,type)

Token persisted at ~/.snp_gene_analysis/ios_token (chmod 600), env-var
override SNP_IOS_TOKEN, --rotate-token to regenerate. Defaults to bind
0.0.0.0:8787. Log line redacts token. 14 tests run real loopback HTTP.

iOS app side comes next.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit success.

---

## Phase 3 — iOS-side transport (iOS repo)

The pipeline server is shipped. Now wire the phone to it. **Working directory: `/Users/georgegao/personal-data-ios/`** for all of Phase 3.

### Task 12: Keychain helper

**Files:**
- Create: `PrefrontalCortex/Transport/Keychain.swift`

- [ ] **Step 1: Create the Keychain helper**

Create `PrefrontalCortex/Transport/Keychain.swift` with:

```swift
import Foundation
import Security

/// Minimal Keychain wrapper for `kSecClassGenericPassword` items.
/// We only store the bearer token here — URLs go in UserDefaults (App Group).
enum Keychain {
    enum Error: Swift.Error { case unhandled(OSStatus) }

    static func set(_ value: String, account: String, service: String) throws {
        let data = Data(value.utf8)
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        // Idempotent: delete then add.
        SecItemDelete(query as CFDictionary)
        var item = query
        item[kSecValueData as String] = data
        // ThisDeviceOnly: never backed up via iCloud Keychain. Matches the
        // local-first posture for this token.
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(item as CFDictionary, nil)
        guard status == errSecSuccess else { throw Error.unhandled(status) }
    }

    static func get(account: String, service: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String:  true,
            kSecMatchLimit as String:  kSecMatchLimitOne,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data,
              let s = String(data: data, encoding: .utf8) else { return nil }
        return s
    }

    static func delete(account: String, service: String) {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
```

- [ ] **Step 2: No build yet — keep moving (TransportSettings depends on this)**

### Task 13: TransportSettings

**Files:**
- Create: `PrefrontalCortex/Transport/TransportSettings.swift`

- [ ] **Step 1: Create the settings store**

Create `PrefrontalCortex/Transport/TransportSettings.swift` with:

```swift
import Foundation

/// Source of truth for transport configuration.
/// - serverURLString lives in App-Group UserDefaults so the widget can read it.
/// - token lives in Keychain (never UserDefaults, never the App Group).
@MainActor
final class TransportSettings: ObservableObject {
    static let shared = TransportSettings()

    private static let appGroup = "group.com.jlgao.PrefrontalCortex"
    private static let urlKey   = "transport.serverURL"
    private static let kcService = "com.jlgao.PrefrontalCortex.transport"
    private static let kcAccount = "bearer"

    private let defaults: UserDefaults

    @Published private(set) var serverURLString: String?
    @Published private(set) var token: String?

    private init() {
        let d = UserDefaults(suiteName: Self.appGroup) ?? .standard
        self.defaults = d
        self.serverURLString = d.string(forKey: Self.urlKey)
        self.token = Keychain.get(account: Self.kcAccount, service: Self.kcService)
    }

    var isConfigured: Bool {
        guard let s = serverURLString, URL(string: s) != nil,
              let t = token, !t.isEmpty else { return false }
        return true
    }

    var serverURL: URL? {
        guard let s = serverURLString else { return nil }
        return URL(string: s)
    }

    func update(serverURLString: String?, token: String?) throws {
        // Trim and normalize the URL.
        let trimmedURL = serverURLString?.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedToken = token?.trimmingCharacters(in: .whitespacesAndNewlines)

        if let u = trimmedURL, !u.isEmpty {
            defaults.set(u, forKey: Self.urlKey)
            self.serverURLString = u
        } else {
            defaults.removeObject(forKey: Self.urlKey)
            self.serverURLString = nil
        }

        if let t = trimmedToken, !t.isEmpty {
            try Keychain.set(t, account: Self.kcAccount, service: Self.kcService)
            self.token = t
        } else {
            Keychain.delete(account: Self.kcAccount, service: Self.kcService)
            self.token = nil
        }
    }
}
```

- [ ] **Step 2: No build yet**

### Task 14: TransportClient

**Files:**
- Create: `PrefrontalCortex/Transport/TransportClient.swift`

- [ ] **Step 1: Create the URLSession client**

Create `PrefrontalCortex/Transport/TransportClient.swift` with:

```swift
import Foundation

enum TransportError: Error, LocalizedError {
    case notConfigured
    case unreachable(String)
    case unauthorized
    case bundleMissing
    case serverError(Int, String)
    case decodingFailed(Error)

    var errorDescription: String? {
        switch self {
        case .notConfigured:        return "Transport not configured"
        case .unreachable(let s):   return "Laptop offline: \(s)"
        case .unauthorized:         return "Auth error — check token in Settings"
        case .bundleMissing:        return "Bundle missing on laptop — run refresh.sh"
        case .serverError(let c, let m): return "Server error \(c): \(m)"
        case .decodingFailed(let e): return "Bundle decode failed: \(e.localizedDescription)"
        }
    }
}

struct HealthResponse: Decodable { let ok: Bool; let bundle_mtime: String? }
struct SamplesUploadResponse: Decodable { let written: Int; let path: String }

final class TransportClient {
    static let shared = TransportClient()

    private let session: URLSession
    init(session: URLSession = .shared) { self.session = session }

    func health() async throws -> HealthResponse {
        let url = try await resolveURL(path: "v1/health")
        let token = await TransportSettings.shared.token
        var req = URLRequest(url: url)
        req.timeoutInterval = 5
        if let token, !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, resp) = try await session.data(for: req)
        try Self.assertOK(resp)
        return try Self.decode(HealthResponse.self, from: data)
    }

    func fetchBundle() async throws -> Data {
        let req = try await makeAuthedRequest(path: "v1/bundle", method: "GET", body: nil)
        let (data, resp) = try await session.data(for: req)
        try Self.assertOK(resp)
        return data
    }

    func uploadSamples(_ rows: [[String: Any]]) async throws -> SamplesUploadResponse {
        let body = try JSONSerialization.data(withJSONObject: rows, options: [])
        let req = try await makeAuthedRequest(path: "v1/samples", method: "POST", body: body)
        let (data, resp) = try await session.data(for: req)
        try Self.assertOK(resp)
        return try Self.decode(SamplesUploadResponse.self, from: data)
    }

    // ── Helpers ────────────────────────────────────────────────────────────
    private func resolveURL(path: String) async throws -> URL {
        guard let base = await TransportSettings.shared.serverURL else {
            throw TransportError.notConfigured
        }
        return base.appendingPathComponent(path)
    }

    private func makeAuthedRequest(path: String, method: String, body: Data?) async throws -> URLRequest {
        let url = try await resolveURL(path: path)
        guard let token = await TransportSettings.shared.token, !token.isEmpty else {
            throw TransportError.notConfigured
        }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.timeoutInterval = 5
        if let body {
            req.httpBody = body
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return req
    }

    private static func assertOK(_ resp: URLResponse) throws {
        guard let http = resp as? HTTPURLResponse else {
            throw TransportError.unreachable("non-HTTP response")
        }
        switch http.statusCode {
        case 200...299: return
        case 401:       throw TransportError.unauthorized
        case 404:       throw TransportError.bundleMissing
        default:        throw TransportError.serverError(http.statusCode, "")
        }
    }

    private static func decode<T: Decodable>(_ t: T.Type, from data: Data) throws -> T {
        do { return try JSONDecoder().decode(t, from: data) }
        catch { throw TransportError.decodingFailed(error) }
    }
}

extension TransportClient {
    /// Map any error into our TransportError taxonomy. Pass-through if already
    /// a TransportError; recognize DecodingError (bad bundle); URLError-or-other
    /// → unreachable with the localized description.
    static func wrap(_ error: Error) -> TransportError {
        if let t = error as? TransportError { return t }
        if error is DecodingError { return .decodingFailed(error) }
        if let u = error as? URLError { return .unreachable(u.localizedDescription) }
        return .unreachable(error.localizedDescription)
    }
}
```

- [ ] **Step 2: First build checkpoint**

Run from `/Users/georgegao/personal-data-ios/`:

```bash
xcodegen generate
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -project PrefrontalCortex.xcodeproj \
  -scheme PrefrontalCortex \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build 2>&1 | tail -15
```

Expected: `** BUILD SUCCEEDED **`. The new transport files have no consumers yet — only "unused" warnings are acceptable.

### Task 15: Info.plist — ATS exception + Local Network usage description

**Files:**
- Modify: `/Users/georgegao/personal-data-ios/project.yml`

- [ ] **Step 1: Add the two keys to the `info.properties` block of the `PrefrontalCortex` target**

Open `project.yml`. Find the `info.properties:` block under `targets.PrefrontalCortex` (currently contains `CFBundleDisplayName`, `UILaunchScreen`, `NSHealthShareUsageDescription`, etc.).

Add the following two keys to that properties dictionary (anywhere within `properties:`):

```yaml
        NSAppTransportSecurity:
          NSAllowsLocalNetworking: true
        NSLocalNetworkUsageDescription: Connect to your laptop on the same Wi-Fi to sync the daily bundle.
```

- [ ] **Step 2: Regenerate the Xcode project and verify Info.plist has the keys**

```bash
xcodegen generate
plutil -p PrefrontalCortex/Resources/Info.plist | grep -E "NSAllowsLocalNetworking|NSLocalNetworkUsageDescription"
```

Expected: both keys are present and have the expected values. (`xcodegen` writes them to `Info.plist`.)

### Task 16: Rewrite `DataLoader`

**Files:**
- Modify: `/Users/georgegao/personal-data-ios/PrefrontalCortex/DataLoader.swift`

- [ ] **Step 1: Replace the file contents**

Replace the full contents of `PrefrontalCortex/DataLoader.swift` with:

```swift
import Foundation

final class DataLoader {
    static let shared = DataLoader()

    private var cacheURL: URL? {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
        return docs?.appendingPathComponent("last_bundle.json")
    }

    /// Load the latest bundle from the laptop, falling back to last cache,
    /// then to the bundled sample. Throws on configured-but-failing transport.
    func loadBundle() async throws -> IOSBundle {
        let settings = TransportSettings.shared
        if await settings.isConfigured {
            do {
                let data = try await TransportClient.shared.fetchBundle()
                let bundle = try JSONDecoder().decode(IOSBundle.self, from: data)
                if let url = cacheURL { try? data.write(to: url, options: .atomic) }
                return bundle
            } catch {
                // Try cache, else fall through to sample
                if let url = cacheURL,
                   let data = try? Data(contentsOf: url),
                   let cached = try? JSONDecoder().decode(IOSBundle.self, from: data) {
                    return cached
                }
                throw TransportClient.wrap(error)
            }
        }

        // Not configured → bundled sample (dev fallback).
        if let sample = Bundle.main.url(forResource: "sample_bundle", withExtension: "json") {
            let data = try Data(contentsOf: sample)
            return try JSONDecoder().decode(IOSBundle.self, from: data)
        }
        throw TransportError.notConfigured
    }
}
```

- [ ] **Step 2: Verify nothing references the old `DataError` enum**

Run from `/Users/georgegao/personal-data-ios/`:

```bash
git grep -n "DataError" -- PrefrontalCortex/
```

Expected: no output (we removed the enum; nothing imported it elsewhere). If anything matches, fix it.

### Task 17: Rewrite `SampleExporter`

**Files:**
- Modify: `/Users/georgegao/personal-data-ios/PrefrontalCortex/HealthKit/SampleExporter.swift`

- [ ] **Step 1: Replace the file contents**

Replace `PrefrontalCortex/HealthKit/SampleExporter.swift` with:

```swift
import Foundation
import HealthKit

/// Reads recent HealthKit samples and POSTs them to the laptop's LAN sync server.
struct SampleExporter {
    /// Pull the latest reading for each sample type the laptop spine cares about.
    static func dailySamples() async -> [[String: Any]] {
        let store = HealthStore.shared
        let bpm = HKUnit.count().unitDivided(by: .minute())
        var rows: [[String: Any]] = []

        func add(_ type: String, _ value: Double, unit: String) {
            let now = ISO8601DateFormatter().string(from: Date())
            rows.append([
                "ts":     now,
                "ts_end": now,
                "source": "healthkit",
                "type":   type,
                "value":  value,
                "unit":   unit,
                "meta":   "{\"via\":\"ios_app\"}",
            ])
        }
        if let v = await store.latest(.restingHeartRate, unit: bpm, hours: 30) {
            add("heart_rate_resting", v, unit: "bpm")
        }
        if let v = await store.latest(.vo2Max, unit: HKUnit(from: "ml/(kg*min)"), hours: 24*60) {
            add("vo2max", v, unit: "mL/min·kg")
        }
        if let v = await store.latest(.bodyMass, unit: .pound(), hours: 24*30) {
            add("weight", v, unit: "lb")
        }
        if let v = await store.latest(.bloodPressureSystolic, unit: .millimeterOfMercury(), hours: 24*60) {
            add("bp_systolic", v, unit: "mmHg")
        }
        if let v = await store.latest(.bloodPressureDiastolic, unit: .millimeterOfMercury(), hours: 24*60) {
            add("bp_diastolic", v, unit: "mmHg")
        }
        if let v = await store.sleepMinutes(hours: 36) {
            add("sleep_minutes", v, unit: "min")
        }
        return rows
    }

    /// Returns a human-readable status string. nil means "transport not configured;
    /// nothing happened" — caller should treat that distinctly from a real failure.
    @discardableResult
    static func uploadDaily() async -> String? {
        let rows = await dailySamples()
        guard !rows.isEmpty else { return "No samples to upload" }
        guard await TransportSettings.shared.isConfigured else {
            return nil  // signals "set up transport in Settings first"
        }
        do {
            let resp = try await TransportClient.shared.uploadSamples(rows)
            return "Uploaded \(resp.written) of \(rows.count) sample\(rows.count == 1 ? "" : "s")"
        } catch {
            return "Upload failed: \(TransportClient.wrap(error).localizedDescription)"
        }
    }
}
```

- [ ] **Step 2: Update `AppStore.uploadTodaySamples()` to consume the new return type**

Open `/Users/georgegao/personal-data-ios/PrefrontalCortex/AppStore.swift`. The current implementation reads:

```swift
    func uploadTodaySamples() async {
        if let url = await SampleExporter.uploadDaily() {
            lastUploadResult = "Uploaded \(url.lastPathComponent)"
        } else {
            lastUploadResult = "No samples uploaded (no HK auth or no recent data)"
        }
    }
```

Replace those 6 lines with:

```swift
    func uploadTodaySamples() async {
        if let msg = await SampleExporter.uploadDaily() {
            lastUploadResult = msg
        } else {
            lastUploadResult = "Set laptop URL + token in Settings first"
        }
    }
```

- [ ] **Step 3: Second build checkpoint**

```bash
xcodegen generate
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -project PrefrontalCortex.xcodeproj \
  -scheme PrefrontalCortex \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build 2>&1 | tail -10
```

Expected: `** BUILD SUCCEEDED **`. The whole transport pipeline should compile end-to-end now.

### Task 18: Settings sheet view

**Files:**
- Create: `/Users/georgegao/personal-data-ios/PrefrontalCortex/Views/TransportSettingsView.swift`

- [ ] **Step 1: Create the sheet**

Create `PrefrontalCortex/Views/TransportSettingsView.swift` with:

```swift
import SwiftUI

struct TransportSettingsView: View {
    @ObservedObject var settings: TransportSettings = .shared
    @Environment(\.dismiss) private var dismiss

    @State private var urlInput: String = ""
    @State private var tokenInput: String = ""
    @State private var testStatus: TestStatus = .idle
    @State private var saveError: String?

    enum TestStatus { case idle, testing, ok(String), fail(String) }

    var body: some View {
        NavigationStack {
            Form {
                Section("Laptop URL") {
                    TextField("http://192.168.1.42:8787", text: $urlInput)
                        .keyboardType(.URL)
                        .autocapitalization(.none)
                        .textInputAutocapitalization(.never)
                        .disableAutocorrection(true)
                    Text("Find with `ipconfig getifaddr en0` on the laptop. Same Wi-Fi only.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Section("Bearer token") {
                    TextField("Run `pipeline/ios_serve.sh` to print it", text: $tokenInput)
                        .autocapitalization(.none)
                        .textInputAutocapitalization(.never)
                        .disableAutocorrection(true)
                        .font(.caption.monospaced())
                }
                Section {
                    Button("Test connection") { Task { await runTest() } }
                        .disabled(URL(string: urlInput) == nil)
                    statusRow
                }
                if let saveError {
                    Section { Text(saveError).foregroundStyle(.red) }
                }
            }
            .navigationTitle("Laptop sync")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { save() } }
            }
            .onAppear {
                urlInput = settings.serverURLString ?? ""
                tokenInput = settings.token ?? ""
            }
        }
    }

    @ViewBuilder
    private var statusRow: some View {
        switch testStatus {
        case .idle:        EmptyView()
        case .testing:     HStack { ProgressView(); Text("Testing…") }
        case .ok(let info): Label(info, systemImage: "checkmark.seal").foregroundStyle(.green)
        case .fail(let msg): Label(msg, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
        }
    }

    private func runTest() async {
        testStatus = .testing
        // Probe the in-memory inputs directly — do NOT mutate TransportSettings.
        // (A failed test shouldn't accidentally persist a bad URL.)
        guard let baseURL = URL(string: urlInput.trimmingCharacters(in: .whitespaces)) else {
            testStatus = .fail("Invalid URL")
            return
        }
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/health"))
        req.timeoutInterval = 5
        let trimmedToken = tokenInput.trimmingCharacters(in: .whitespaces)
        if !trimmedToken.isEmpty {
            req.setValue("Bearer \(trimmedToken)", forHTTPHeaderField: "Authorization")
        }
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse else {
                testStatus = .fail("Non-HTTP response"); return
            }
            guard http.statusCode == 200 else {
                testStatus = .fail("HTTP \(http.statusCode)"); return
            }
            let h = try JSONDecoder().decode(HealthResponse.self, from: data)
            testStatus = .ok("OK — bundle: \(h.bundle_mtime ?? "none yet")")
        } catch {
            testStatus = .fail(error.localizedDescription)
        }
    }

    private func save() {
        do {
            try settings.update(serverURLString: urlInput, token: tokenInput)
            dismiss()
        } catch {
            saveError = error.localizedDescription
        }
    }
}
```

### Task 19: Status pill on the Now tab

**Files:**
- Create: `/Users/georgegao/personal-data-ios/PrefrontalCortex/Views/TransportStatusPill.swift`
- Modify: `/Users/georgegao/personal-data-ios/PrefrontalCortex/Views/TodayHeaderView.swift`
- Modify: `/Users/georgegao/personal-data-ios/PrefrontalCortex/AppStore.swift`

- [ ] **Step 1: Add a `lastTransportError` field to `AppStore`**

Open `PrefrontalCortex/AppStore.swift`. Find the `@Published` block at the top (currently contains `bundle`, `liveValues`, `loading`, `lastError`, `lastUploadResult`). Add one line:

```swift
    @Published var lastTransportError: TransportError?
```

Then in `bootstrap()`, replace the `do { bundle = try await DataLoader.shared.loadBundle() } catch { … }` block with:

```swift
        do {
            bundle = try await DataLoader.shared.loadBundle()
            lastTransportError = nil
        } catch let e as TransportError {
            lastTransportError = e
            lastError = e.localizedDescription
        } catch {
            lastError = "Bundle load failed: \(error.localizedDescription)"
        }
```

- [ ] **Step 2: Create the pill view**

Create `PrefrontalCortex/Views/TransportStatusPill.swift`:

```swift
import SwiftUI

struct TransportStatusPill: View {
    @ObservedObject var settings: TransportSettings = .shared
    let lastError: TransportError?
    @Binding var presentSettings: Bool

    var body: some View {
        if let label, let color {
            Button {
                presentSettings = true
            } label: {
                Text(label)
                    .font(.caption2.monospaced())
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(color.opacity(0.2))
                    .foregroundStyle(color)
                    .cornerRadius(8)
            }
            .buttonStyle(.plain)
        }
    }

    private var label: String? {
        if !settings.isConfigured { return "Setup → Settings" }
        switch lastError {
        case .none:                   return nil
        case .unauthorized:           return "Auth error"
        case .bundleMissing:          return "Run refresh.sh"
        case .unreachable:            return "Laptop offline"
        case .notConfigured:          return "Setup → Settings"
        case .serverError(let c, _):  return "Server \(c)"
        case .decodingFailed:         return "Bad bundle"
        }
    }

    private var color: Color? {
        if !settings.isConfigured { return .yellow }
        switch lastError {
        case .none:           return nil
        case .unauthorized:   return .orange
        case .bundleMissing:  return .yellow
        case .unreachable:    return .gray
        case .notConfigured:  return .yellow
        case .serverError:    return .orange
        case .decodingFailed: return .orange
        }
    }
}
```

- [ ] **Step 3: Embed the pill in `TodayHeaderView`**

Open `PrefrontalCortex/Views/TodayHeaderView.swift`. Currently the body is a `VStack` with three `Text` views, ending with `.frame(maxWidth: .infinity, alignment: .leading)`.

Replace the struct's body and add a small surrounding state hook:

```swift
struct TodayHeaderView: View {
    let bundle: IOSBundle
    @EnvironmentObject var store: AppStore
    @State private var showSettings = false

    var dayKey: String {
        let dow = Calendar.current.component(.weekday, from: Date())
        let dayNum = ((dow + 5) % 7) + 1
        return "Day \(dayNum)"
    }

    var todaySession: String {
        bundle.profile?.daily_protocol?[dayKey]?.session ?? "—"
    }

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text(dayKey.uppercased())
                    .font(.caption2.monospaced())
                    .foregroundStyle(.cyan)
                    .tracking(2)
                Text(todaySession)
                    .font(.title2.italic())
                    .foregroundStyle(.white)
                Text("Last refreshed \(prettyDate(bundle.exported_at))")
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
            }
            Spacer()
            TransportStatusPill(
                lastError: store.lastTransportError,
                presentSettings: $showSettings
            )
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .sheet(isPresented: $showSettings) {
            TransportSettingsView()
        }
    }

    private func prettyDate(_ iso: String) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = f.date(from: iso) ?? ISO8601DateFormatter().date(from: iso) else {
            return iso.prefix(16).description
        }
        let rel = RelativeDateTimeFormatter()
        rel.unitsStyle = .abbreviated
        return rel.localizedString(for: date, relativeTo: Date())
    }
}
```

### Task 20: Profile-tab gear → Settings sheet

**Files:**
- Modify: `/Users/georgegao/personal-data-ios/PrefrontalCortex/ContentView.swift`

- [ ] **Step 1: Add a settings-sheet state and a gear toolbar item to `profileTab`**

Open `ContentView.swift`. The `ContentView` struct has:

```swift
@State private var selectedTab: Tab = .interventions
```

Add:

```swift
@State private var showTransportSettings = false
```

Find the `profileTab` view (currently ends with `.toolbarBackground(Color.black, for: .navigationBar)`). Add a `.toolbar` modifier and a `.sheet` modifier just below it:

```swift
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showTransportSettings = true } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $showTransportSettings) {
                TransportSettingsView()
            }
```

- [ ] **Step 2: Swap the now-misleading upload icon on the Now tab**

In the same file, find `uploadToolbar`:

```swift
    private var uploadToolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Button {
                Task { await store.uploadTodaySamples() }
            } label: {
                Image(systemName: "icloud.and.arrow.up")
            }
        }
    }
```

Change `"icloud.and.arrow.up"` → `"arrow.up.circle"`.

### Task 21: Final iOS build + commit

**Files:** none new — verification + commit.

- [ ] **Step 1: Regenerate and build**

```bash
cd /Users/georgegao/personal-data-ios
xcodegen generate
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -project PrefrontalCortex.xcodeproj \
  -scheme PrefrontalCortex \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build 2>&1 | tail -15
```

Expected: `** BUILD SUCCEEDED **`. Warnings about new types being unused are fine if you've added scaffolding without consumers; at this point everything should be consumed.

- [ ] **Step 2: Stage and commit**

```bash
cd /Users/georgegao/personal-data-ios
git add -A
git status --short
```

Expected new/modified: 5 new files (`Transport/Keychain.swift`, `Transport/TransportSettings.swift`, `Transport/TransportClient.swift`, `Views/TransportSettingsView.swift`, `Views/TransportStatusPill.swift`); modified: `DataLoader.swift`, `HealthKit/SampleExporter.swift`, `AppStore.swift`, `ContentView.swift`, `Views/TodayHeaderView.swift`, `project.yml`, `Resources/Info.plist`, regenerated `PrefrontalCortex.xcodeproj/`.

```bash
git commit -m "$(cat <<'EOF'
iOS: LAN HTTP transport — replace iCloud Drive

DataLoader and SampleExporter now talk to the laptop's pipeline.ios_serve
over the LAN. New Transport/ module:

  - Keychain.swift          minimal kSecClassGenericPassword wrapper
  - TransportSettings.swift @Published settings; URL in App-Group
                            UserDefaults, token in Keychain (singleton)
  - TransportClient.swift   URLSession async client for the three endpoints
                            with a typed TransportError taxonomy

UI:
  - TransportSettingsView (sheet, Form): URL + token + "Test connection"
    that pings /v1/health and reports bundle mtime; Save persists
  - TransportStatusPill on Now header — labels: Setup→Settings,
    Laptop offline, Auth error, Run refresh.sh; tap opens settings sheet
  - Profile tab gets a gear toolbar item that also opens the sheet

Info.plist:
  - NSAppTransportSecurity → NSAllowsLocalNetworking: true
    (narrow exception that allows plain HTTP only to RFC1918 / link-local)
  - NSLocalNetworkUsageDescription for iOS 14+ permission prompt

DataLoader caches the last successful bundle to Documents/last_bundle.json
so the offline path renders real data, not the bundled dev sample.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds. `git status` clean.

---

## Phase 4 — Documentation

### Task 22: Pipeline-side README — add an "iOS sync" section

**Files:**
- Modify: `/Users/georgegao/snp_gene_analysis/README.md`

- [ ] **Step 1: Add an "iOS sync" section before "Privacy" or wherever sections cluster**

Open `/Users/georgegao/snp_gene_analysis/README.md`. Find a natural insertion point (somewhere after the pipeline-stages overview, before the privacy/repo section). Insert:

````markdown
## iOS sync (Prefrontal Cortex companion app)

The companion app at [`personal-data-ios`](https://github.com/jlgao2/personal-data-ios)
fetches `output/ios_export/ios_bundle.json` from this laptop over the LAN
and POSTs HealthKit samples back. Run the server when you want to sync:

```bash
pipeline/ios_serve.sh
# or
python3 -m pipeline.ios_serve --port 8787 --bind 0.0.0.0
```

First run prints the bearer token (also persisted at `~/.snp_gene_analysis/ios_token`).
Find the laptop's LAN IP with `ipconfig getifaddr en0` (macOS). On the phone,
open Prefrontal Cortex → Profile → ⚙ → enter `http://<laptop>:8787` and the
token, tap "Test connection", Save.

Endpoints (bearer-token auth except `/v1/health`):

| Method | Path | Behavior |
|---|---|---|
| `GET`  | `/v1/health`  | Liveness probe; reports bundle mtime. |
| `GET`  | `/v1/bundle`  | Returns `output/ios_export/ios_bundle.json`. |
| `POST` | `/v1/samples` | Merges array of sample dicts into `samples_<today>.json`. |

To rotate the token: `python3 -m pipeline.ios_serve --rotate-token`.
The phone needs its bearer-token field updated to match.

iCloud Drive sync is **not** used — the companion app is signed with a
personal Apple Developer team that can't enable iCloud entitlements,
and a LAN transport keeps health data off Apple's infrastructure.
````

### Task 23: iOS-side README — re-add the architecture diagram for LAN HTTP

**Files:**
- Modify: `/Users/georgegao/personal-data-ios/README.md`

- [ ] **Step 1: Add an "Architecture" section between "Status" and "Build"**

Open `/Users/georgegao/personal-data-ios/README.md`. Insert a new section above `## Build`:

````markdown
## Architecture

```
┌───────────────────────┐                    ┌──────────────────────────┐
│  laptop pipeline      │  GET /v1/bundle    │  Prefrontal Cortex (iOS) │
│  pipeline/ios_serve   │ ─────────────────▶ │  DataLoader              │
│  :8787 (bearer auth)  │                    │  + Documents/last_bundle │
│                       │  POST /v1/samples  │                          │
│  output/ios_export/   │ ◀───────────────── │  SampleExporter          │
│   ├ ios_bundle.json   │                    │  HealthStore (live HK)   │
│   └ samples_*.json    │                    └──────────────────────────┘
└───────────────────────┘
        same Wi-Fi LAN
```

Pair the phone with the laptop in **Profile → ⚙ → Laptop sync**:
enter `http://<laptop-LAN-IP>:8787` and the bearer token printed by
`pipeline/ios_serve.sh` on the laptop. Tap **Test connection** then **Save**.

The pipeline repo's [README "iOS sync" section](https://github.com/jlgao2/personal-genome-pipeline#ios-sync-prefrontal-cortex-companion-app)
covers the laptop side.
````

### Task 24: Final docs commit (one per repo)

**Files:** none new.

- [ ] **Step 1: Pipeline-repo commit**

```bash
cd /Users/georgegao/snp_gene_analysis
git add README.md
git commit -m "$(cat <<'EOF'
docs: README — add iOS sync section for pipeline.ios_serve

Covers starting the server, pairing the phone, the three endpoints,
token rotation, and a one-liner explaining why iCloud isn't used.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: iOS-repo commit**

```bash
cd /Users/georgegao/personal-data-ios
git add README.md
git commit -m "$(cat <<'EOF'
docs: README — re-add architecture diagram (LAN HTTP)

Replaces the old iCloud diagram dropped during the rename. Points
back to pipeline-repo README for the laptop-side server.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Final tree check (both repos)**

```bash
cd /Users/georgegao/personal-data-ios && git log --oneline -5 && git status --short
echo "---"
cd /Users/georgegao/snp_gene_analysis && git log --oneline -5 && git status --short
```

Expected:
- iOS repo: 3 new commits on top of `08a594f` (rename / transport / docs); clean working tree.
- Pipeline repo: 3 new commits on top of `eee63e1` (spec / server / docs); `output/ios_export/` may still appear as untracked (it's the runtime output dir — fine).

---

## Out-of-band: on-device verification (manual, optional)

Once the plan is complete, install on phone:

1. Plug phone into Mac. Trust this computer if prompted.
2. Open `PrefrontalCortex.xcodeproj` in Xcode 26.3.
3. Pick the phone as the run destination. Set the team to **Jia Lin Gao** (personal).
4. Run. The new app installs alongside the old "Frontal Lobe" app (different bundle ID). Delete the old one when ready.
5. On the laptop: `pipeline/ios_serve.sh`. Note the printed token and laptop URL.
6. On the phone: open Prefrontal Cortex → Profile → ⚙. Enter `http://<laptop>:8787` and the token. Tap **Test connection** — green "OK — bundle: <mtime>". **Save.**
7. iOS will show a "Local Network" permission prompt. Allow.
8. Pull-to-refresh on Now. Real bundle should load.
9. Tap upload arrow on Now toolbar. Banner: "Uploaded N of M samples".
10. On laptop, `ls output/ios_export/samples_*.json` — today's file should exist with N rows.

If 7-day re-sign expiry becomes a recurring annoyance, that's the moment to revisit the $99 Apple Developer Program decision — but it's an ergonomics call, not a transport one.

---

## Self-Review

- **Spec coverage:** Every spec section has a task. Endpoints (Tasks 7/9), auth (5/8), token storage and rotation (5/10), iOS Transport module (12/13/14), Settings UI (18), status pill states (19), DataLoader fall-through to cache then sample (16), SampleExporter (17), Info.plist ATS exception (15), README architecture (22/23). ✓
- **Placeholder scan:** No "TBD" / "implement later" / "add error handling" placeholders. Every code block is the actual code to paste. ✓
- **Type consistency:** `TransportError` cases match across `TransportClient`, `DataLoader`, `AppStore`, and `TransportStatusPill`. `make_handler(token:, export_dir:)` signature matches between the implementation and the test fixture. `TransportSettings.shared` is the only entry point used by `DataLoader`, `SampleExporter`, and `TransportSettingsView`. ✓
- **Commit cadence:** 5 commits — rename / server / iOS transport / pipeline-docs / iOS-docs. Each is reviewable on its own. ✓

---

## Execution choice

Plan complete. Recommended execution path: **Inline Execution** (executing-plans skill). The tasks are tightly chained (each commit depends on the prior compiling) and span two repos with shared knowledge of conventions — fewer agent handoffs, less re-priming cost, and the build/test signal is fast (1.4s pytest, ~30s xcodebuild).

If a task gets long or the user wants finer-grained review, switching to subagent-driven mid-stream is fine.
