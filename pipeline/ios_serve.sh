#!/usr/bin/env bash
# Convenience wrapper to run the LAN sync server from the repo root.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m pipeline.ios_serve "$@"
