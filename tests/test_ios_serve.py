"""Tests for pipeline.ios_serve — token management and HTTP endpoints.

Tests spin up an http.server.HTTPServer on a free port (port=0) in a
background thread and make real HTTP calls against it via stdlib
urllib. No external dependencies.
"""
from __future__ import annotations

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


# ─── Log redaction ──────────────────────────────────────────────────────────

def test_full_token_never_appears_in_logs(server, capfd):
    _request(f"{server['url']}/v1/bundle", token=server["token"])
    captured = capfd.readouterr()
    assert server["token"] not in captured.err
    assert server["token"] not in captured.out
