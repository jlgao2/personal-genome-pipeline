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
        def log_message(self, fmt: str, *args) -> None:
            ip = self.client_address[0]
            sys.stderr.write(f"[ios_serve] {ip} {fmt % args}\n")

        def _check_auth(self) -> bool:
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return False
            return header.removeprefix("Bearer ").strip() == token

        def do_GET(self):
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

        def do_POST(self):
            if not self._check_auth():
                _send_json(self, 401, {"error": "unauthorized"})
                return
            if self.path == "/v1/samples":
                self._handle_samples_post()
                return
            _send_json(self, 404, {"error": "not found"})

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
