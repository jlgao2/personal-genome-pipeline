"""Cross-source correlation engine — uses the spine that's been
accumulating to surface honest patterns.

Each function returns a small dict shaped for the dashboard:
  {name, n, r (or comparison), trend, summary, actionable}

We intentionally cap to a few questions the user can act on. More
correlations is more noise — fewer is more signal.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import duckdb


def _samples_glob(parquet_root: Path) -> str:
    return f"{str(parquet_root).rstrip('/')}/samples/*.parquet"


def _events_glob(parquet_root: Path) -> str:
    return f"{str(parquet_root).rstrip('/')}/events/garmin-*.parquet"


# ── Daily features view (CTE we reuse) ──────────────────────────────────────

def _daily_cte(parquet_root: Path) -> str:
    s_glob = _samples_glob(parquet_root)
    e_glob = _events_glob(parquet_root)
    return f"""
    WITH
    sleep_min AS (
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d,
               sum(value) / 60.0 AS sleep_minutes
        FROM   read_parquet('{s_glob}', union_by_name=true)
        WHERE  source='garmin' AND type IN ('sleep_deep','sleep_light','sleep_rem')
        GROUP BY d
    ),
    rhr AS (
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d,
               avg(value) AS rhr
        FROM   read_parquet('{s_glob}', union_by_name=true)
        WHERE  type = 'heart_rate_resting' AND value IS NOT NULL
        GROUP BY d
    ),
    workouts AS (
        SELECT date_trunc('day', ts_start::TIMESTAMP)::DATE AS d,
               count(*) AS workout_count,
               sum(coalesce(CAST(json_extract(meta, '$.training_load') AS DOUBLE), 0)) AS tl_total
        FROM   read_parquet('{e_glob}')
        WHERE  type = 'workout'
        GROUP BY d
    ),
    daily AS (
        SELECT
            COALESCE(s.d, r.d, w.d) AS d,
            s.sleep_minutes,
            r.rhr,
            COALESCE(w.workout_count, 0) AS workout_count,
            COALESCE(w.tl_total, 0)      AS tl_total
        FROM        sleep_min s
        FULL JOIN   rhr      r ON r.d = s.d
        FULL JOIN   workouts w ON w.d = COALESCE(s.d, r.d)
    )
    """


# ── Correlations ────────────────────────────────────────────────────────────

def workout_to_next_night_sleep(parquet_root: Path) -> Optional[dict]:
    """Days you trained vs that night's sleep. Compares means."""
    sql = _daily_cte(parquet_root) + """
    , paired AS (
        SELECT
            d.workout_count > 0 AS trained,
            n.sleep_minutes
        FROM daily d
        JOIN daily n ON n.d = d.d + INTERVAL 1 DAY
        WHERE n.sleep_minutes IS NOT NULL
    )
    SELECT trained, avg(sleep_minutes) AS s, count(*) AS n
    FROM paired
    GROUP BY trained
    """
    try:
        rows = duckdb.query(sql).fetchall()
    except duckdb.Error:
        return None
    by_trained = {bool(r[0]): (r[1], r[2]) for r in rows}
    if True not in by_trained or False not in by_trained:
        return None
    trained_avg, n_trained = by_trained[True]
    rest_avg, n_rest = by_trained[False]
    if trained_avg is None or rest_avg is None:
        return None
    delta = trained_avg - rest_avg
    direction = "more" if delta > 0 else "less"
    trend = "positive" if abs(delta) > 5 and delta > 0 else \
            "negative" if abs(delta) > 5 and delta < 0 else "neutral"
    return {
        "name":       "Training days → next-night sleep",
        "n":          int(n_trained + n_rest),
        "trend":      trend,
        "summary":    (f"Trained: {trained_avg:.0f} min sleep that night · "
                       f"rest day: {rest_avg:.0f} min (n={n_trained + n_rest})"),
        "actionable": (
            f"You sleep ~{abs(delta):.0f} min {direction} the night after training. "
            + ("Training is supporting recovery." if delta > 5
               else "Training is degrading sleep — likely too late or too high TL."
               if delta < -5
               else "Effect is small — not a key lever for you.")
        ),
        "metric_a":   round(trained_avg, 1),
        "metric_b":   round(rest_avg, 1),
        "metric_a_label": "after training",
        "metric_b_label": "rest day",
        "unit":       "min",
    }


def tl_to_next_day_rhr(parquet_root: Path) -> Optional[dict]:
    """3-day rolling TL vs next-day RHR. Pearson r."""
    sql = _daily_cte(parquet_root) + """
    , windowed AS (
        SELECT d, rhr,
               avg(tl_total) OVER (ORDER BY d ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS tl_3d
        FROM daily
        WHERE rhr IS NOT NULL OR tl_total IS NOT NULL
    ),
    next_day AS (
        SELECT a.tl_3d, b.rhr
        FROM windowed a
        JOIN windowed b ON b.d = a.d + INTERVAL 1 DAY
        WHERE a.tl_3d IS NOT NULL AND b.rhr IS NOT NULL
    )
    SELECT corr(tl_3d, rhr) AS r, count(*) AS n,
           avg(rhr) AS rhr_avg
    FROM next_day
    """
    try:
        row = duckdb.query(sql).fetchone()
    except duckdb.Error:
        return None
    if not row or row[0] is None or row[1] is None:
        return None
    r, n, rhr_avg = row
    if abs(r) < 0.10:
        trend = "neutral"
        actionable = "TL → RHR signal is weak. Recovery isn't strongly load-driven for you."
    elif r > 0:
        trend = "positive"
        actionable = (f"Higher 3-day TL → higher next-day RHR (r={r:+.2f}, n={n}). "
                      "Real recovery cost — respect deload weeks.")
    else:
        trend = "negative"
        actionable = (f"Higher 3-day TL → LOWER next-day RHR (r={r:+.2f}, n={n}). "
                      "Unusual: training might be regulating rather than depleting.")
    return {
        "name":       "3-day training load → next-day RHR",
        "n":          int(n),
        "trend":      trend,
        "summary":    f"r = {r:+.2f} across {n} day-pairs (RHR baseline {rhr_avg:.0f})",
        "actionable": actionable,
        "r":          round(r, 2),
    }


def day_of_week_summary(parquet_root: Path) -> Optional[list[dict]]:
    """Per-DOW averages — sleep, RHR, workout count, TL."""
    sql = _daily_cte(parquet_root) + """
    SELECT
        date_part('isodow', d) AS dow,        -- 1=Mon..7=Sun
        avg(sleep_minutes) AS sleep_avg,
        avg(rhr)           AS rhr_avg,
        avg(tl_total)      AS tl_avg,
        sum(workout_count) AS workouts,
        count(*) AS n
    FROM daily
    GROUP BY dow
    ORDER BY dow
    """
    try:
        rows = duckdb.query(sql).fetchall()
    except duckdb.Error:
        return None
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out = []
    for r in rows:
        dow, sleep_avg, rhr_avg, tl_avg, workouts, n = r
        if not (1 <= int(dow) <= 7):
            continue
        out.append({
            "dow":      names[int(dow) - 1],
            "sleep":    round(sleep_avg, 0) if sleep_avg is not None else None,
            "rhr":      round(rhr_avg, 1)   if rhr_avg   is not None else None,
            "tl":       round(tl_avg, 1)    if tl_avg    is not None else None,
            "workouts": int(workouts) if workouts is not None else 0,
            "n":        int(n),
        })
    return out


def social_to_training(parquet_root: Path) -> Optional[dict]:
    """Did you train more or less in weeks with more social check-in events?"""
    s_glob = _samples_glob(parquet_root)
    e_glob = _events_glob(parquet_root)
    social_glob = f"{str(parquet_root).rstrip('/')}/events/social-*.parquet"
    sql = f"""
    WITH
    weekly_workouts AS (
        SELECT date_trunc('week', ts_start::TIMESTAMP)::DATE AS wk,
               count(*) AS workouts
        FROM read_parquet('{e_glob}')
        WHERE type='workout'
        GROUP BY wk
    ),
    weekly_social AS (
        SELECT date_trunc('week', ts_start::TIMESTAMP)::DATE AS wk,
               count(*) AS social_events
        FROM read_parquet('{social_glob}')
        WHERE type IN ('checkin_anchor','checkin_first_contact','checkin_last_contact')
        GROUP BY wk
    )
    SELECT corr(workouts, social_events) AS r,
           count(*) AS n,
           avg(workouts) AS workouts_avg,
           avg(social_events) AS social_avg
    FROM weekly_workouts w
    JOIN weekly_social s ON s.wk = w.wk
    """
    try:
        row = duckdb.query(sql).fetchone()
    except duckdb.Error:
        return None
    if not row or row[0] is None or row[1] is None or row[1] < 5:
        return None
    r, n, workouts_avg, social_avg = row
    if abs(r) < 0.15:
        trend = "neutral"
        actionable = "Training and social activity are decoupled in your data."
    elif r > 0:
        trend = "positive"
        actionable = "Weeks you trained more were also weeks you connected more. Habits cluster."
    else:
        trend = "negative"
        actionable = "Trade-off detected — weeks of high training came with less social contact."
    return {
        "name":       "Weekly workouts ↔ social check-in events",
        "n":          int(n),
        "trend":      trend,
        "summary":    f"r = {r:+.2f} across {int(n)} weeks (workouts {workouts_avg:.1f}/wk · social {social_avg:.1f}/wk)",
        "actionable": actionable,
        "r":          round(r, 2),
    }


# ── Top-level builder ───────────────────────────────────────────────────────

def build_correlations(parquet_root: Path) -> dict:
    """Compute all correlations. Skip ones that fail or have too few samples."""
    out_corrs = []
    for fn in (workout_to_next_night_sleep,
               tl_to_next_day_rhr,
               social_to_training):
        try:
            v = fn(parquet_root)
        except Exception:
            v = None
        if v is not None:
            out_corrs.append(v)
    return {
        "correlations": out_corrs,
        "day_of_week":  day_of_week_summary(parquet_root) or [],
    }


def _cli() -> None:
    import argparse, json
    ap = argparse.ArgumentParser(description="Compute cross-source correlations.")
    ap.add_argument("--parquet-root", type=Path, default=Path("data/parquet"))
    args = ap.parse_args()
    print(json.dumps(build_correlations(args.parquet_root), indent=2))


if __name__ == "__main__":
    _cli()
