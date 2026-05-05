"""Adaptive programming engine — given today's prescription + recent vitals
+ active conditions, produces a modified session with swaps, intensity
modifier, and traffic-light verdict.

Pure functional. Single laptop pass during refresh.sh. Output lands in
ios_bundle.json + the desktop dashboard's data-vitals.js.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import duckdb


# ─────────────────────────────────────────────────────────────────────────────
# Signals — everything the rules need
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Signals:
    program_day: str                            # 'Day 1' .. 'Day 7'
    prescribed_session: dict                    # rehab/warmup/main/core arrays

    sleep_min_last_night: Optional[float] = None
    rhr_yesterday: Optional[float] = None
    rhr_baseline_30d: Optional[float] = None
    body_battery_today: Optional[float] = None

    avg_tl_last_3d: Optional[float] = None
    avg_tl_last_7d: Optional[float] = None
    sport_spread_last_7d: dict = field(default_factory=dict)

    workouts_today: list = field(default_factory=list)
    workouts_yesterday: list = field(default_factory=list)
    profile: dict = field(default_factory=dict)
    action_loop: list = field(default_factory=list)
    genome: dict = field(default_factory=dict)


def todays_program_day() -> str:
    """Mon=Day 1 .. Sun=Day 7 by ISO weekday convention."""
    iso = _dt.date.today().isoweekday()  # 1=Mon..7=Sun
    return f"Day {iso}"


def compute_signals(parquet_root: Path,
                    profile: dict,
                    action_loop: list,
                    genome: dict) -> Signals:
    """Build a Signals struct from the Parquet spine + curated profile."""
    program_day = todays_program_day()
    prescribed = (profile.get("daily_protocol") or {}).get(program_day, {})

    sig = Signals(
        program_day=program_day,
        prescribed_session=prescribed,
        profile=profile,
        action_loop=action_loop,
        genome=genome,
    )

    samples = parquet_root / "samples"
    events  = parquet_root / "events"

    if samples.exists() and list(samples.glob("*.parquet")):
        s_glob = f"{str(samples).rstrip('/')}/*.parquet"
        # Sleep last night = sum of garmin sleep stages for yesterday's date
        try:
            row = duckdb.query(f"""
                SELECT sum(value) / 60.0 AS v
                FROM read_parquet('{s_glob}', union_by_name=true)
                WHERE source='garmin' AND type IN ('sleep_deep','sleep_light','sleep_rem')
                  AND date_trunc('day', ts::TIMESTAMP)::DATE = current_date - interval '1 day'
            """).fetchone()
            sig.sleep_min_last_night = float(row[0]) if row and row[0] is not None else None
        except duckdb.Error:
            pass

        # RHR yesterday + 30d baseline
        try:
            row = duckdb.query(f"""
                SELECT
                  (SELECT avg(value) FROM read_parquet('{s_glob}', union_by_name=true)
                   WHERE type='heart_rate_resting'
                     AND date_trunc('day', ts::TIMESTAMP)::DATE = current_date - interval '1 day'),
                  (SELECT avg(value) FROM read_parquet('{s_glob}', union_by_name=true)
                   WHERE type='heart_rate_resting'
                     AND ts::TIMESTAMP > current_timestamp - interval '30 days')
            """).fetchone()
            sig.rhr_yesterday    = float(row[0]) if row and row[0] is not None else None
            sig.rhr_baseline_30d = float(row[1]) if row and row[1] is not None else None
        except duckdb.Error:
            pass

    # Training load — average over last 3 / 7 days
    if events.exists() and list(events.glob("garmin-*.parquet")):
        e_glob = f"{str(events).rstrip('/')}/garmin-*.parquet"
        try:
            row = duckdb.query(f"""
                SELECT
                  (SELECT avg(CAST(json_extract(meta, '$.training_load') AS DOUBLE))
                   FROM read_parquet('{e_glob}')
                   WHERE type='workout'
                     AND ts_start::TIMESTAMP > current_timestamp - interval '3 days'),
                  (SELECT avg(CAST(json_extract(meta, '$.training_load') AS DOUBLE))
                   FROM read_parquet('{e_glob}')
                   WHERE type='workout'
                     AND ts_start::TIMESTAMP > current_timestamp - interval '7 days')
            """).fetchone()
            sig.avg_tl_last_3d = float(row[0]) if row and row[0] is not None else None
            sig.avg_tl_last_7d = float(row[1]) if row and row[1] is not None else None
        except duckdb.Error:
            pass

        # Sport spread over last 7 days
        try:
            rows = duckdb.query(f"""
                SELECT json_extract_string(meta, '$.sport') AS sport, count(*)
                FROM read_parquet('{e_glob}')
                WHERE type='workout'
                  AND ts_start::TIMESTAMP > current_timestamp - interval '7 days'
                GROUP BY sport
            """).fetchall()
            sig.sport_spread_last_7d = {r[0]: r[1] for r in rows if r[0]}
        except duckdb.Error:
            pass

        # Today's already-completed workouts
        try:
            rows = duckdb.query(f"""
                SELECT label, json_extract_string(meta, '$.sport') AS sport
                FROM read_parquet('{e_glob}')
                WHERE type='workout'
                  AND date_trunc('day', ts_start::TIMESTAMP)::DATE = current_date
            """).fetchall()
            sig.workouts_today = [{"label": r[0], "sport": r[1]} for r in rows]
        except duckdb.Error:
            pass

        # Yesterday's workouts (drives the high-cost-sport rule)
        try:
            rows = duckdb.query(f"""
                SELECT label, json_extract_string(meta, '$.sport') AS sport,
                       CAST(json_extract(meta, '$.training_load') AS DOUBLE) AS tl
                FROM read_parquet('{e_glob}')
                WHERE type='workout'
                  AND date_trunc('day', ts_start::TIMESTAMP)::DATE = current_date - interval '1 day'
            """).fetchall()
            sig.workouts_yesterday = [
                {"label": r[0], "sport": r[1], "tl": r[2]} for r in rows
            ]
        except duckdb.Error:
            pass

    return sig


# ─────────────────────────────────────────────────────────────────────────────
# Adapted-session structure
# ─────────────────────────────────────────────────────────────────────────────

def empty_adapted(sig: Signals) -> dict:
    return {
        "program_day": sig.program_day,
        "prescribed":  (sig.prescribed_session or {}).get("session"),
        "traffic_light": "green",
        "intensity_modifier": 1.0,
        "intensity_reason": None,
        "swaps":   [],
        "removed": [],
        "added":   [],
        "notes":   [],
        "rules_fired": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Rules — each takes Signals + AdaptedSession dict and mutates the dict
# ─────────────────────────────────────────────────────────────────────────────

def rule_rest_day_no_changes(sig: Signals, adapted: dict) -> None:
    if sig.program_day == "Day 7":
        adapted["notes"].append("Rest day. Walking, mobility, sleep ≥7h.")
        adapted["traffic_light"] = "green"
        adapted["rules_fired"].append("rest_day_no_changes")


def rule_very_low_sleep(sig: Signals, adapted: dict) -> None:
    if sig.sleep_min_last_night is not None and sig.sleep_min_last_night < 300:
        adapted["traffic_light"] = "red"
        adapted["intensity_modifier"] = 0.0
        adapted["intensity_reason"] = f"Sleep {sig.sleep_min_last_night:.0f} min (<5h) — skip training"
        adapted["notes"].append("Replace today with light walking + sleep. Train tomorrow.")
        adapted["rules_fired"].append("very_low_sleep")


def rule_low_sleep(sig: Signals, adapted: dict) -> None:
    if adapted["traffic_light"] == "red":
        return  # already worse
    if sig.sleep_min_last_night is not None and sig.sleep_min_last_night < 360:
        adapted["traffic_light"] = "amber"
        adapted["intensity_modifier"] = min(adapted["intensity_modifier"], 0.7)
        adapted["intensity_reason"] = f"Sleep {sig.sleep_min_last_night:.0f} min (<6h) — reduce intensity 30%"
        adapted["notes"].append("Lighten intensity ~30% or swap to Day 5 yoga.")
        adapted["rules_fired"].append("low_sleep")


def rule_elevated_rhr(sig: Signals, adapted: dict) -> None:
    if sig.rhr_yesterday is None or sig.rhr_baseline_30d is None:
        return
    delta = sig.rhr_yesterday - sig.rhr_baseline_30d
    if delta > 5:
        if adapted["traffic_light"] == "green":
            adapted["traffic_light"] = "amber"
        adapted["intensity_modifier"] = min(adapted["intensity_modifier"], 0.8)
        prev = adapted.get("intensity_reason") or ""
        suffix = f"RHR +{delta:.0f} bpm vs 30d baseline"
        adapted["intensity_reason"] = (prev + " · " + suffix) if prev else suffix
        adapted["notes"].append("Recovery low. Cap target TL <40, prefer zone 2.")
        adapted["rules_fired"].append("elevated_rhr")


def rule_compounding_load(sig: Signals, adapted: dict) -> None:
    if sig.avg_tl_last_3d is None or sig.avg_tl_last_7d is None:
        return
    if sig.avg_tl_last_3d > 70 and sig.avg_tl_last_3d > 1.3 * sig.avg_tl_last_7d:
        if adapted["traffic_light"] == "green":
            adapted["traffic_light"] = "amber"
        adapted["intensity_modifier"] = min(adapted["intensity_modifier"], 0.75)
        adapted["notes"].append(
            f"3d avg TL {sig.avg_tl_last_3d:.0f} >> 7d avg {sig.avg_tl_last_7d:.0f}. "
            "Forced deload — reduce volume 25%."
        )
        adapted["rules_fired"].append("compounding_load")


def rule_low_body_battery(sig: Signals, adapted: dict) -> None:
    if sig.body_battery_today is not None and sig.body_battery_today < 30:
        if adapted["traffic_light"] == "green":
            adapted["traffic_light"] = "amber"
        adapted["intensity_modifier"] = min(adapted["intensity_modifier"], 0.8)
        adapted["notes"].append(
            f"Body battery {sig.body_battery_today:.0f} (<30) — recovery indicator low."
        )
        adapted["rules_fired"].append("low_body_battery")


# ─── Injury / condition swaps ───────────────────────────────────────────────

def _has_condition(profile: dict, side: str, pattern: str) -> bool:
    import re
    conds = (profile.get("active_conditions") or {}).get(side, []) or []
    return any(re.search(pattern, c, re.I) for c in conds)


def rule_peroneal_no_running(sig: Signals, adapted: dict) -> None:
    if _has_condition(sig.profile, "lower_extremity", r"peroneal|tendon"):
        adapted["notes"].append("Cardio modality: bike or rowing only — no running.")
        adapted["rules_fired"].append("peroneal_no_running")


def rule_peroneal_swap_lunges(sig: Signals, adapted: dict) -> None:
    if not _has_condition(sig.profile, "lower_extremity", r"peroneal|tendon"):
        return
    if sig.program_day not in ("Day 2", "Day 4"):
        return
    main = (sig.prescribed_session or {}).get("main") or []
    for item in main:
        if "lunge" in item.lower():
            adapted["swaps"].append({
                "original":    item,
                "replacement": "Stationary bike 12 min, zone 2 (no ankle stress)",
                "reason":      "Peroneal flare risk on dynamic single-leg loading",
            })
            adapted["rules_fired"].append("peroneal_swap_lunges")


def rule_hip_no_deep_squat(sig: Signals, adapted: dict) -> None:
    if not _has_condition(sig.profile, "lower_extremity", r"hip"):
        return
    if sig.program_day not in ("Day 2", "Day 4"):
        return
    import re
    main = (sig.prescribed_session or {}).get("main") or []
    for item in main:
        # Match "deep <anything> squat(s)" — covers "deep barbell squat", "deep squat", etc.
        if re.search(r"\bdeep\b.*\bsquat", item, re.I):
            adapted["removed"].append({
                "item":   item,
                "reason": "Hip impingement — avoid end-range flexion under load",
            })
            adapted["rules_fired"].append("hip_no_deep_squat")
    adapted["notes"].append("Soft knees on RDLs. 90/90 hip switches in warmup.")


def rule_slap_no_overhead_barbell(sig: Signals, adapted: dict) -> None:
    if not _has_condition(sig.profile, "upper_extremity", r"SLAP|shoulder"):
        return
    if sig.program_day not in ("Day 1", "Day 3"):
        return
    main = (sig.prescribed_session or {}).get("main") or []
    for item in main:
        low = item.lower()
        if ("overhead" in low and "barbell" in low) or "military press" in low:
            adapted["swaps"].append({
                "original":    item,
                "replacement": "Half-kneeling landmine press 3×10/side",
                "reason":      "Post-SLAP — favor non-fixed-path overhead",
            })
            adapted["rules_fired"].append("slap_no_overhead_barbell")


def rule_elbow_reduce_grip(sig: Signals, adapted: dict) -> None:
    if not _has_condition(sig.profile, "upper_extremity", r"epicondylitis|elbow"):
        return
    if sig.program_day not in ("Day 2", "Day 4"):
        return
    adapted["notes"].append(
        "Medial epicondylitis — use straps on rows/RDLs. Neutral grip > supinated."
    )
    adapted["rules_fired"].append("elbow_reduce_grip")


# ─── Goal / drift rules ─────────────────────────────────────────────────────

def rule_vo2max_drift(sig: Signals, adapted: dict) -> None:
    """When VO2Max is below target, prescribe zone-2 work — modality biased
    by which sports correlate with positive recovery (bike/swim/row) rather
    than running. The peroneal context already restricts running, but this
    rule generalizes the modality preference per sport_recovery_cost data."""
    for c in sig.action_loop:
        if c.get("sample_type") != "vo2max":
            continue
        actual = c.get("latest_value")
        target = c.get("target_value")
        if actual is None or target is None:
            return
        if actual < target * 0.95:
            # Prefer recovery-positive modalities (cycling, swimming, rowing)
            modality = "cycling/rowing"
            if _has_condition(sig.profile, "lower_extremity", r"peroneal|tendon"):
                modality = "stationary bike or rowing (zero ankle stress)"
            adapted["added"].append({
                "item":   f"10 min zone 2 {modality} after main",
                "reason": "VO2max below target; bike/rowing per recovery-cost data",
            })
            adapted["rules_fired"].append("vo2max_drift")
        return


# Sports that correlated with elevated next-day RHR (>+1.5 bpm) in user's
# historical data. Pulled from pipeline.correlations sport_recovery_cost.
_HIGH_COST_SPORTS = {"ALPINE_SKIING", "HIKING"}


def rule_high_cost_sport_yesterday(sig: Signals, adapted: dict) -> None:
    """If yesterday's session was a high-recovery-cost sport (per the user's
    own correlation data), drop today's intensity and shift to recovery work."""
    yesterday_sports = {(w.get("sport") or "").upper() for w in sig.workouts_yesterday}
    hits = yesterday_sports & _HIGH_COST_SPORTS
    if not hits:
        return
    # Don't override stronger states
    if adapted["traffic_light"] == "green":
        adapted["traffic_light"] = "amber"
    adapted["intensity_modifier"] = min(adapted["intensity_modifier"], 0.75)
    sport_name = next(iter(hits)).replace("_", " ").title()
    suffix = f"{sport_name} yesterday — costs +2-3 bpm next-day RHR per your history"
    prev = adapted.get("intensity_reason") or ""
    adapted["intensity_reason"] = (prev + " · " + suffix) if prev else suffix
    adapted["notes"].append(
        f"Yesterday was {sport_name} — high recovery cost. Cap today's TL <40, "
        "favor cycling / swimming / mobility."
    )
    adapted["rules_fired"].append("high_cost_sport_yesterday")


def rule_thursday_caution(sig: Signals, adapted: dict) -> None:
    """User's day-of-week pattern shows Thursday = lowest sleep + highest TL.
    On Thursdays with already-low sleep, push toward lighter work."""
    if sig.program_day != "Day 4":  # Thursday in the Mon-anchored schema
        return
    if sig.sleep_min_last_night is None or sig.sleep_min_last_night >= 360:
        return
    adapted["notes"].append(
        "Thursday + low sleep is your historically worst combination "
        "(avg 346 min, peak weekly TL). Consider swapping for Day 5 yoga."
    )
    adapted["rules_fired"].append("thursday_caution")


def rule_sleep_streak_low(sig: Signals, adapted: dict) -> None:
    if sig.sleep_min_last_night is not None and sig.sleep_min_last_night < 360:
        # already covered by rule_low_sleep; this rule pushes Day 5 sooner
        if sig.program_day in ("Day 1", "Day 3"):
            adapted["notes"].append(
                "Two intensity days in a row at low sleep is high injury risk. "
                "Consider swapping today for Day 5 yoga."
            )
            adapted["rules_fired"].append("sleep_streak_low")


def rule_already_trained_today(sig: Signals, adapted: dict) -> None:
    if sig.workouts_today:
        labels = ", ".join(w["label"] for w in sig.workouts_today)
        adapted["notes"].append(
            f"Garmin shows you already trained today: {labels}. "
            "Skip duplicate volume."
        )
        adapted["rules_fired"].append("already_trained_today")


# ─── Genome-aware (narrow v1) ───────────────────────────────────────────────

def _has_genotype(genome: dict, gene: str, pattern: str) -> bool:
    """Search by_source for a gene match. Pattern is regex over genotype field."""
    import re
    by_src = (genome or {}).get("by_source") or {}
    for rows in by_src.values():
        for r in rows or []:
            if r.get("gene") == gene and r.get("genotype"):
                if re.search(pattern, r["genotype"]):
                    return True
    return False


def rule_actn3_anaerobic_emphasis(sig: Signals, adapted: dict) -> None:
    if not _has_genotype(sig.genome, "ACTN3", r"^C/C|^CC"):
        return
    if sig.program_day in ("Day 1", "Day 3"):
        adapted["notes"].append(
            "ACTN3 R/R — fast-twitch favored. Bias to slightly heavier sets, "
            "longer rest (90s+), fewer reps per set."
        )
        adapted["rules_fired"].append("actn3_anaerobic_emphasis")


def rule_apoe_e4_sleep_priority(sig: Signals, adapted: dict) -> None:
    if not _has_genotype(sig.genome, "APOE", r"e4|ε4|/4"):
        return
    if sig.sleep_min_last_night is not None and sig.sleep_min_last_night < 420:
        adapted["notes"].append(
            "APOE ε4 carrier — sleep <7h is a hard amber. Prioritize early bed tonight."
        )
        adapted["rules_fired"].append("apoe_e4_sleep_priority")


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

RULES: list[Callable[[Signals, dict], None]] = [
    rule_rest_day_no_changes,
    rule_very_low_sleep,
    rule_low_sleep,
    rule_elevated_rhr,
    rule_compounding_load,
    rule_low_body_battery,
    rule_high_cost_sport_yesterday,   # data-driven (sport_recovery_cost)
    rule_thursday_caution,             # data-driven (day_of_week)
    rule_peroneal_no_running,
    rule_peroneal_swap_lunges,
    rule_hip_no_deep_squat,
    rule_slap_no_overhead_barbell,
    rule_elbow_reduce_grip,
    rule_vo2max_drift,
    rule_sleep_streak_low,
    rule_already_trained_today,
    rule_actn3_anaerobic_emphasis,
    rule_apoe_e4_sleep_priority,
]


def adapt_today(sig: Signals) -> dict:
    """Run all rules in order, returning the adapted session dict."""
    adapted = empty_adapted(sig)
    for rule in RULES:
        rule(sig, adapted)
    return adapted


def build_adapted_session(parquet_root: Path,
                          profile: Optional[dict],
                          action_loop: list,
                          genome: dict) -> Optional[dict]:
    """Top-level helper called by publish_ios_export / build_vitals."""
    if not profile:
        return None
    sig = compute_signals(parquet_root, profile, action_loop, genome)
    return adapt_today(sig)
