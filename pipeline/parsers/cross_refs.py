"""Build cross_refs.parquet from a hand-curated YAML mapping.

Each entry pairs a finding_id (matches findings.parquet.id) with a sample
type from samples.parquet and a clinical takeaway. The YAML lives at
output/cross_refs.yaml (gitignored — contains personal context) and is
hand-edited as analysis grows.
"""
from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import yaml


def parse_cross_refs_yaml(yaml_path: Path, out_path: Path) -> int:
    """Read a YAML list of cross-ref dicts; write to a single Parquet file."""
    with yaml_path.open() as f:
        entries = yaml.safe_load(f) or []
    schema = pa.schema([
        ("finding_id",         pa.string()),
        ("sample_type",        pa.string()),
        ("expected_direction", pa.string()),
        ("target_value",       pa.float64()),
        ("takeaway",           pa.string()),
    ])
    rows = [
        {
            "finding_id":         e["finding_id"],
            "sample_type":        e["sample_type"],
            "expected_direction": e.get("expected_direction"),
            "target_value":       e.get("target_value"),
            "takeaway":           e.get("takeaway"),
        }
        for e in entries
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, out_path)
    return len(rows)


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Build cross_refs.parquet from YAML.")
    ap.add_argument("--yaml", type=Path, default=Path("output/cross_refs.yaml"))
    ap.add_argument("--out",  type=Path,
                    default=Path("data/parquet/cross_refs/cross_refs.parquet"))
    args = ap.parse_args()
    n = parse_cross_refs_yaml(args.yaml, args.out)
    print(f"Wrote {n} cross-refs to {args.out}")


if __name__ == "__main__":
    _cli()
