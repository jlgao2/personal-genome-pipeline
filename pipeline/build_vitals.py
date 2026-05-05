"""Query the Parquet store for dashboard-ready Vitals data.

Each Vital is a small dict with:
  - series:  list of [iso-date-string, value] pairs
  - latest:  most recent value
  - trend:   'up' | 'down' | 'flat' | None  (last 30d slope direction)
"""
from __future__ import annotations

import json
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


WORKOUTS_QUERY = """
    SELECT ts_start, ts_end, label,
           json_extract_string(meta, '$.sport')                    AS sport,
           CAST(json_extract(meta, '$.duration_s')    AS DOUBLE)   AS duration_s,
           CAST(json_extract(meta, '$.distance_m')    AS DOUBLE)   AS distance_m,
           CAST(json_extract(meta, '$.calories')      AS DOUBLE)   AS calories,
           CAST(json_extract(meta, '$.avg_hr')        AS DOUBLE)   AS avg_hr,
           CAST(json_extract(meta, '$.max_hr')        AS DOUBLE)   AS max_hr,
           CAST(json_extract(meta, '$.training_load') AS DOUBLE)   AS training_load,
           CAST(json_extract(meta, '$.aerobic_te')    AS DOUBLE)   AS aerobic_te,
           json_extract(meta, '$.hr_time_in_zone')                 AS hr_zones_json
    FROM   read_parquet('{events}/garmin-*.parquet', union_by_name=true)
    WHERE  type = 'workout'
    ORDER BY ts_start DESC
    LIMIT 90
"""


def build_workouts(events_dir: Path) -> list[dict]:
    """Return the most recent 90 workouts as plain dicts."""
    if not events_dir.exists() or not list(events_dir.glob("garmin-*.parquet")):
        return []
    rows = duckdb.query(WORKOUTS_QUERY.format(events=str(events_dir).rstrip("/"))).fetchall()
    cols = ["ts_start", "ts_end", "label", "sport", "duration_s", "distance_m",
            "calories", "avg_hr", "max_hr", "training_load", "aerobic_te", "hr_zones_json"]
    out = []
    for row in rows:
        d = dict(zip(cols, row))
        zj = d.pop("hr_zones_json")
        try:
            d["hr_zones"] = json.loads(zj) if zj else None
        except (TypeError, ValueError):
            d["hr_zones"] = None
        out.append(d)
    return out


ACTION_LOOP_QUERY = """
WITH latest_per_type AS (
  SELECT type,
         max(ts::TIMESTAMP) AS latest_ts,
         arg_max(value, ts::TIMESTAMP) FILTER (WHERE value IS NOT NULL) AS latest_value
  FROM   read_parquet('{samples}/*.parquet', union_by_name=true)
  WHERE  value IS NOT NULL
  GROUP BY type
),
recent_avg AS (
  SELECT type, avg(value) AS v
  FROM   read_parquet('{samples}/*.parquet', union_by_name=true)
  WHERE  value IS NOT NULL
    AND  ts::TIMESTAMP > current_timestamp - interval '90 days'
  GROUP BY type
),
sleep_min AS (
  SELECT 'sleep_minutes' AS type,
         max(d) AS latest_ts,
         (SELECT v FROM (
            SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, sum(value)/60.0 AS v
            FROM read_parquet('{samples}/*.parquet', union_by_name=true)
            WHERE source='garmin' AND type IN ('sleep_deep','sleep_light','sleep_rem')
            GROUP BY d ORDER BY d DESC LIMIT 1) ) AS latest_value
  FROM (
    SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, sum(value)/60.0 AS v
    FROM read_parquet('{samples}/*.parquet', union_by_name=true)
    WHERE source='garmin' AND type IN ('sleep_deep','sleep_light','sleep_rem')
    GROUP BY d
  )
)
SELECT
  c.finding_id,
  f.gene,
  f.summary                         AS finding_summary,
  f.tier                            AS finding_tier,
  c.sample_type,
  c.expected_direction,
  c.target_value,
  c.takeaway,
  COALESCE(s.latest_value, sm.latest_value) AS latest_value,
  COALESCE(s.latest_ts,    sm.latest_ts)    AS latest_ts,
  r.v                                       AS avg_90d
FROM   read_parquet('{cross_refs}/cross_refs.parquet') c
LEFT   JOIN read_parquet('{findings}/findings-*.parquet', union_by_name=true) f
       ON   f.id = c.finding_id
LEFT   JOIN latest_per_type s ON s.type = c.sample_type
LEFT   JOIN recent_avg     r  ON r.type = c.sample_type
LEFT   JOIN sleep_min      sm ON sm.type = c.sample_type
"""


def build_action_loop(parquet_root: Path) -> list[dict]:
    """Return one row per cross-ref, joined with the latest sample value.

    Each row is shaped for the 'Action Loop' dashboard panel:
      - finding_id, gene, finding_summary, finding_tier
      - sample_type, expected_direction, target_value, takeaway
      - latest_value, latest_ts, avg_90d
    """
    samples_dir   = parquet_root / "samples"
    findings_dir  = parquet_root / "findings"
    crossrefs_dir = parquet_root / "cross_refs"
    if not (crossrefs_dir / "cross_refs.parquet").exists():
        return []
    if not list(findings_dir.glob("findings-*.parquet")):
        return []
    rows = duckdb.query(ACTION_LOOP_QUERY.format(
        samples=str(samples_dir).rstrip("/"),
        findings=str(findings_dir).rstrip("/"),
        cross_refs=str(crossrefs_dir).rstrip("/"),
    )).fetchall()
    cols = ["finding_id", "gene", "finding_summary", "finding_tier",
            "sample_type", "expected_direction", "target_value", "takeaway",
            "latest_value", "latest_ts", "avg_90d"]
    out = []
    for row in rows:
        d = dict(zip(cols, row))
        if d["latest_ts"] is not None:
            d["latest_ts"] = str(d["latest_ts"])
        out.append(d)
    return out


def load_health_profile(profile_path: Path) -> Optional[dict]:
    """Load the user's health-profile JSON if present (else None)."""
    if not profile_path.exists():
        return None
    with profile_path.open() as f:
        return json.load(f)


def build_genomics_from_parquet(findings_dir: Path) -> dict:
    """Pull all findings rows from findings.parquet, grouped by source_tsv.
    Returns a dict ready for the iOS app to render — no data.js dependency.
    """
    if not findings_dir.exists() or not list(findings_dir.glob("findings-*.parquet")):
        return {}
    rows = duckdb.query(
        f"SELECT id, source_tsv, gene, rsid, chrom, pos, ref, alt, "
        f"       genotype, tier, summary, meta "
        f"FROM read_parquet('{str(findings_dir).rstrip('/')}/findings-*.parquet') "
        f"ORDER BY source_tsv, gene"
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        d = {
            "id":         r[0],
            "source_tsv": r[1],
            "gene":       r[2],
            "rsid":       r[3],
            "chrom":      r[4],
            "pos":        r[5],
            "ref":        r[6],
            "alt":        r[7],
            "genotype":   r[8],
            "tier":       r[9],
            "summary":    r[10],
        }
        # Parse meta JSON if present
        try:
            d["meta"] = json.loads(r[11]) if r[11] else None
        except (TypeError, ValueError):
            d["meta"] = None
        out.setdefault(d["source_tsv"], []).append(d)
    # Summary stats for the app
    return {
        "by_source": out,
        "tier_counts": dict(duckdb.query(
            f"SELECT tier, count(*) FROM read_parquet('{str(findings_dir).rstrip('/')}/findings-*.parquet') "
            f"GROUP BY tier ORDER BY tier"
        ).fetchall()),
        "total": sum(len(v) for v in out.values()),
    }


def write_vitals_js(parquet_dir: Path, out_path: Path,
                    events_dir: Optional[Path] = None,
                    parquet_root: Optional[Path] = None,
                    profile_path: Optional[Path] = None) -> None:
    """Build vitals + workouts + action_loop + health_profile + med_alerts;
    emit one ES module the dashboard imports."""
    if events_dir is None:
        events_dir = parquet_dir.parent / "events"
    if parquet_root is None:
        parquet_root = parquet_dir.parent
    if profile_path is None:
        profile_path = Path("output/health_profile.json")
    from pipeline.adaptive import build_adapted_session
    vitals = build_vitals(parquet_dir)
    workouts = build_workouts(events_dir)
    action_loop = build_action_loop(parquet_root)
    health_profile = load_health_profile(profile_path)
    med_alerts = build_med_alerts(events_dir, health_profile)
    genomics = build_genomics_from_parquet(parquet_root / "findings")
    adapted = build_adapted_session(parquet_root, health_profile, action_loop, genomics)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    social = _load_social_summary(parquet_root)
    calendar = _load_calendar()
    media = _load_media()
    out_path.write_text(
        "/* AUTO-GENERATED by pipeline/build_vitals.py — do not edit by hand. */\n"
        f"export const VITALS = {json.dumps(vitals, indent=2)};\n"
        f"export const WORKOUTS = {json.dumps(workouts, indent=2)};\n"
        f"export const ACTION_LOOP = {json.dumps(action_loop, indent=2)};\n"
        f"export const HEALTH_PROFILE = {json.dumps(health_profile, indent=2)};\n"
        f"export const MED_ALERTS = {json.dumps(med_alerts, indent=2)};\n"
        f"export const ADAPTED_SESSION = {json.dumps(adapted, indent=2)};\n"
        f"export const SOCIAL = {json.dumps(social, indent=2)};\n"
        f"export const CALENDAR = {json.dumps(calendar, indent=2)};\n"
        f"export const MEDIA = {json.dumps(media, indent=2)};\n"
    )


def build_med_alerts(events_dir: Path, profile: Optional[dict]) -> list[dict]:
    """Cross MyChart medication events (from FHIR) against the user's
    medications_to_avoid list. Returns one alert dict per matching prescription.

    Each alert: {medication, fhir_status, started, reason, severity}
    """
    if not profile or not profile.get("medications_to_avoid"):
        return []
    if not events_dir.exists() or not list(events_dir.glob("fhir-*.parquet")):
        return []
    rows = duckdb.query(
        f"SELECT ts_start, ts_end, label, meta "
        f"FROM read_parquet('{str(events_dir).rstrip('/')}/fhir-*.parquet') "
        f"WHERE type = 'medication'"
    ).fetchall()
    if not rows:
        return []

    avoid_terms: dict[str, dict] = {}
    for entry in profile["medications_to_avoid"]:
        cls = (entry.get("class") or "").lower()
        if "fluoroquinolone" in cls:
            avoid_terms.update({t: entry for t in
                ["cipro", "levaquin", "levofloxacin", "ciprofloxacin",
                 "moxifloxacin", "ofloxacin", "norfloxacin"]})
        if "statin" in cls:
            avoid_terms.update({t: entry for t in
                ["atorvastatin", "rosuvastatin", "simvastatin", "pravastatin",
                 "lovastatin", "fluvastatin", "pitavastatin"]})
        if "corticosteroid" in cls:
            avoid_terms.update({t: entry for t in
                ["prednisone", "prednisolone", "dexamethasone",
                 "methylprednisolone", "hydrocortisone"]})
        if "nsaid" in cls:
            avoid_terms.update({t: entry for t in
                ["ibuprofen", "naproxen", "diclofenac", "celecoxib",
                 "meloxicam", "ketorolac"]})

    alerts: list[dict] = []
    for ts_start, _ts_end, label, meta_json in rows:
        if not label:
            continue
        lower = label.lower()
        for term, entry in avoid_terms.items():
            if term in lower:
                try:
                    meta = json.loads(meta_json or "{}")
                except (TypeError, ValueError):
                    meta = {}
                alerts.append({
                    "medication": label,
                    "drug_class": entry.get("class"),
                    "reason":     entry.get("reason"),
                    "fhir_status": meta.get("status"),
                    "started":    str(ts_start) if ts_start else None,
                    "severity":   "high",
                })
                break
    return alerts


def _load_social_summary(parquet_root: Path) -> Optional[dict]:
    p = parquet_root / "social_summary.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _load_calendar() -> list:
    """Pull next 14 days from Google Calendar if OAuth is configured."""
    try:
        from pipeline.parsers.gcal import upcoming_events
        return upcoming_events(days=14)
    except Exception:
        return []


def _load_media() -> Optional[list]:
    try:
        from pipeline.parsers.media import load_media
        return load_media(Path("output/media.yaml"))
    except Exception:
        return None


def publish_ios_export(parquet_dir: Path,
                       events_dir: Optional[Path] = None,
                       parquet_root: Optional[Path] = None,
                       profile_path: Optional[Path] = None,
                       outdir: Optional[Path] = None) -> None:
    """Emit a single ios_bundle.json the iOS app reads via iCloud Drive."""
    import datetime as _dt
    from pipeline.adaptive import build_adapted_session
    if events_dir is None:    events_dir = parquet_dir.parent / "events"
    if parquet_root is None:  parquet_root = parquet_dir.parent
    if profile_path is None:  profile_path = Path("output/health_profile.json")
    if outdir is None:        outdir = Path("output/ios_export")
    outdir.mkdir(parents=True, exist_ok=True)
    profile = load_health_profile(profile_path)
    action_loop = build_action_loop(parquet_root)
    genomics = build_genomics_from_parquet(parquet_root / "findings")
    bundle = {
        "exported_at": _dt.datetime.utcnow().isoformat() + "Z",
        "vitals":      build_vitals(parquet_dir),
        "workouts":    build_workouts(events_dir),
        "action_loop": action_loop,
        "profile":     profile,
        "genomics":    genomics,
        "med_alerts":  build_med_alerts(events_dir, profile),
        "adapted_session": build_adapted_session(parquet_root, profile, action_loop, genomics),
        "social":      _load_social_summary(parquet_root),
        "calendar":    _load_calendar(),
        "media":       _load_media(),
    }
    (outdir / "ios_bundle.json").write_text(json.dumps(bundle, indent=2))


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
