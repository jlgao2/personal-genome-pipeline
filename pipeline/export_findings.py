"""Emit the public artifact this repo hands off to downstream consumers
(Prefrontal Cortex health pipeline today; potentially others later).

Reads `output/raw_findings/*.tsv` via the same per-TSV parsers
`pipeline.parsers.genome` already uses for the parquet build, and writes
a single `output/findings/genomic_findings.json` carrying:

  - schema_version (int)
  - exported_at (ISO 8601 UTC)
  - source_pipeline_commit (git short-sha; "unknown" if not in a repo)
  - rows: list of canonical findings dicts (12 columns each)

The shape mirrors `pipeline.parsers.genome.FINDINGS_COLUMNS` so the health
repo's reader can drop these straight into its parquet spine.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
from pathlib import Path

from pipeline.parsers.genome import FINDINGS_COLUMNS, TSV_PARSERS

SCHEMA_VERSION = 1


def _git_short_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unknown"


def collect_rows(raw_dir: Path) -> list[dict]:
    """Walk the registered TSV parsers and return a flat list of rows.

    Skips TSVs that don't exist on disk (this is the genome pipeline's
    historical behavior — partial outputs are normal during dev).
    """
    rows: list[dict] = []
    for filename, parser_fn in TSV_PARSERS:
        path = raw_dir / filename
        if not path.exists():
            continue
        rows.extend(parser_fn(path))
    return rows


def build_payload(raw_dir: Path) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "source_pipeline_commit": _git_short_sha(),
        "rows": collect_rows(raw_dir),
    }


def write_findings(raw_dir: Path, out_path: Path) -> int:
    payload = build_payload(raw_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    return len(payload["rows"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("output/raw_findings"),
                        help="Directory containing the per-source TSVs.")
    parser.add_argument("--out", type=Path,
                        default=Path("output/findings/genomic_findings.json"),
                        help="Output JSON path.")
    args = parser.parse_args()

    n = write_findings(args.raw, args.out)
    print(f"[export_findings] wrote {n} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
