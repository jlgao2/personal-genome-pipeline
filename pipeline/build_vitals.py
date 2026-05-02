"""Query the Parquet store for dashboard-ready Vitals data.

Each Vital is a small dict with:
  - series:  list of [iso-date-string, value] pairs
  - latest:  most recent value
  - trend:   'up' | 'down' | 'flat' | None  (last 30d slope direction)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import duckdb

# Vitals we surface on the dashboard. Each entry is a query that reduces the
# raw samples to one daily value (avg/min/max/sum depending on the metric).
VITAL_QUERIES: dict[str, str] = {
    # Garmin wins on overlapping days; HealthKit fills earlier history.
    "heart_rate_resting": """
        WITH per_day AS (
          SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, source, avg(value) AS v
          FROM   read_parquet('{parquet}/*.parquet', union_by_name=true)
          WHERE  type = 'heart_rate_resting' AND value IS NOT NULL
          GROUP BY d, source
        ),
        ranked AS (
          SELECT d, source, v,
                 row_number() OVER (PARTITION BY d
                                    ORDER BY CASE source WHEN 'garmin' THEN 0 ELSE 1 END) AS rn
          FROM per_day
        )
        SELECT d, v FROM ranked WHERE rn = 1 ORDER BY d
    """,
    "vo2max": """
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, max(value) AS v
        FROM   read_parquet('{parquet}/*.parquet', union_by_name=true)
        WHERE  type = 'vo2max' AND value IS NOT NULL
        GROUP BY d ORDER BY d
    """,
    "weight": """
        WITH per_day AS (
          -- Garmin weight is in grams; convert to lb to match HealthKit's unit.
          SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, source,
                 avg(CASE WHEN source='garmin' THEN value / 453.592 ELSE value END) AS v
          FROM   read_parquet('{parquet}/*.parquet', union_by_name=true)
          WHERE  type = 'weight' AND value IS NOT NULL
          GROUP BY d, source
        ),
        ranked AS (
          SELECT d, source, v,
                 row_number() OVER (PARTITION BY d
                                    ORDER BY CASE source WHEN 'garmin' THEN 0 ELSE 1 END) AS rn
          FROM per_day
        )
        SELECT d, v FROM ranked WHERE rn = 1 ORDER BY d
    """,
    "bp_systolic": """
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, avg(value) AS v
        FROM   read_parquet('{parquet}/*.parquet', union_by_name=true)
        WHERE  type = 'bp_systolic' AND value IS NOT NULL
        GROUP BY d ORDER BY d
    """,
    "bp_diastolic": """
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, avg(value) AS v
        FROM   read_parquet('{parquet}/*.parquet', union_by_name=true)
        WHERE  type = 'bp_diastolic' AND value IS NOT NULL
        GROUP BY d ORDER BY d
    """,
    # Sleep: Garmin gives stage-level seconds; HealthKit gives category records.
    "sleep_minutes": """
        WITH garmin_per_night AS (
          SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d,
                 sum(value) / 60.0 AS v
          FROM   read_parquet('{parquet}/*.parquet', union_by_name=true)
          WHERE  source = 'garmin' AND type IN ('sleep_deep','sleep_light','sleep_rem')
          GROUP BY d
        ),
        healthkit_per_night AS (
          SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d,
                 sum(epoch(ts_end::TIMESTAMP - ts::TIMESTAMP) / 60.0) AS v
          FROM   read_parquet('{parquet}/*.parquet', union_by_name=true)
          WHERE  source = 'healthkit' AND type = 'sleep_stage' AND value IS NULL
          GROUP BY d
        )
        SELECT COALESCE(g.d, h.d) AS d,
               COALESCE(g.v, h.v) AS v
        FROM garmin_per_night g
        FULL OUTER JOIN healthkit_per_night h ON g.d = h.d
        ORDER BY d
    """,
    "exercise_minutes": """
        WITH garmin_per_day AS (
          SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d,
                 sum(value) AS v
          FROM   read_parquet('{parquet}/*.parquet', union_by_name=true)
          WHERE  source = 'garmin'
            AND type IN ('moderate_minutes','vigorous_minutes')
          GROUP BY d
        ),
        healthkit_per_day AS (
          SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, sum(value) AS v
          FROM   read_parquet('{parquet}/*.parquet', union_by_name=true)
          WHERE  source = 'healthkit' AND type = 'exercise_minutes' AND value IS NOT NULL
          GROUP BY d
        )
        SELECT COALESCE(g.d, h.d) AS d,
               COALESCE(g.v, h.v) AS v
        FROM garmin_per_day g
        FULL OUTER JOIN healthkit_per_day h ON g.d = h.d
        ORDER BY d
    """,
}


def _trend_of(series: list) -> Optional[str]:
    """Return 'up'|'down'|'flat'|None based on simple linear slope of last 30 points."""
    if len(series) < 5:
        return None
    tail = series[-30:]
    n = len(tail)
    xs = list(range(n))
    ys = [v for _, v in tail]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return "flat"
    slope = num / den
    range_y = max(ys) - min(ys) or 1
    rel = slope / range_y
    if rel > 0.01:
        return "up"
    if rel < -0.01:
        return "down"
    return "flat"


def build_vitals(parquet_dir: Path) -> dict:
    """Return a dict keyed by vital name, each entry shaped for the dashboard."""
    out: dict = {}
    parquet_str = str(parquet_dir).rstrip("/")
    for name, query in VITAL_QUERIES.items():
        try:
            rows = duckdb.query(query.format(parquet=parquet_str)).fetchall()
        except duckdb.Error:
            continue
        if not rows:
            continue
        series = [[d.isoformat() if hasattr(d, "isoformat") else str(d), float(v)]
                  for d, v in rows]
        out[name] = {
            "series": series,
            "latest": series[-1][1] if series else None,
            "trend":  _trend_of([(d, v) for d, v in series]),
        }
    return out


def write_vitals_js(parquet_dir: Path, out_path: Path) -> None:
    """Build vitals dict and emit as an ES module the dashboard imports."""
    import json as _json
    vitals = build_vitals(parquet_dir)
    payload = _json.dumps(vitals, indent=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "/* AUTO-GENERATED by pipeline/build_vitals.py — do not edit by hand. */\n"
        f"export const VITALS = {payload};\n"
    )


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Build data-vitals.js from Parquet samples.")
    ap.add_argument("--parquet", type=Path, default=Path("data/parquet/samples"))
    ap.add_argument("--out",     type=Path, default=Path("output/web/js/data-vitals.js"))
    args = ap.parse_args()
    write_vitals_js(args.parquet, args.out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    _cli()
