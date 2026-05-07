"""Unit tests for the adaptive engine. Each rule gets a focused test;
plus an integration test of adapt_today() against a richer Signals.
"""
from pipeline.adaptive import (
    Signals,
    empty_adapted,
    adapt_today,
    rule_rest_day_no_changes,
    rule_very_low_sleep,
    rule_low_sleep,
    rule_elevated_rhr,
    rule_compounding_load,
    rule_peroneal_swap_lunges,
    rule_hip_no_deep_squat,
    rule_slap_no_overhead_barbell,
    rule_elbow_reduce_grip,
    rule_vo2max_drift,
    rule_already_trained_today,
    rule_actn3_anaerobic_emphasis,
    rule_apoe_e4_sleep_priority,
    rule_high_cost_sport_yesterday,
    rule_thursday_caution,
    rule_saturday_peak_load_warning,
    rule_yoga_cadence_friday,
    rule_sleep_gap_to_target,
)

# ─── Helpers ────────────────────────────────────────────────────────────────

def _sig(day: str = "Day 2", **kwargs) -> Signals:
    base = {
        "program_day": day,
        "prescribed_session": {
            "session": "Pull + Lower + core",
            "main": [
                "Suspension trainer rows — 4×10",
                "Hip thrusts — 4×10",
                "Romanian deadlifts (soft knees) — 3×8",
                "Reverse lunges (short step, front foot flat) — 3×8/side",
                "Farmer carries — 3×30 sec",
            ],
        },
    }
    base.update(kwargs)
    return Signals(**base)


# ─── Recovery rules ─────────────────────────────────────────────────────────

def test_rest_day_no_changes():
    sig = _sig(day="Day 7")
    a = empty_adapted(sig)
    rule_rest_day_no_changes(sig, a)
    assert "rest_day_no_changes" in a["rules_fired"]


def test_very_low_sleep_red():
    sig = _sig(sleep_min_last_night=240)
    a = empty_adapted(sig)
    rule_very_low_sleep(sig, a)
    assert a["traffic_light"] == "red"
    assert a["intensity_modifier"] == 0.0


def test_low_sleep_amber():
    sig = _sig(sleep_min_last_night=320)
    a = empty_adapted(sig)
    rule_low_sleep(sig, a)
    assert a["traffic_light"] == "amber"
    assert a["intensity_modifier"] == 0.7


def test_low_sleep_normal_no_change():
    sig = _sig(sleep_min_last_night=480)
    a = empty_adapted(sig)
    rule_low_sleep(sig, a)
    assert a["traffic_light"] == "green"
    assert a["intensity_modifier"] == 1.0


def test_elevated_rhr():
    sig = _sig(rhr_yesterday=58, rhr_baseline_30d=50)
    a = empty_adapted(sig)
    rule_elevated_rhr(sig, a)
    assert "elevated_rhr" in a["rules_fired"]
    assert a["intensity_modifier"] <= 0.8
    assert a["traffic_light"] == "amber"


def test_compounding_load():
    sig = _sig(avg_tl_last_3d=85, avg_tl_last_7d=50)  # 3d/7d > 1.3
    a = empty_adapted(sig)
    rule_compounding_load(sig, a)
    assert "compounding_load" in a["rules_fired"]
    assert a["traffic_light"] == "amber"


def test_compounding_load_quiet_when_3d_low():
    sig = _sig(avg_tl_last_3d=30, avg_tl_last_7d=50)
    a = empty_adapted(sig)
    rule_compounding_load(sig, a)
    assert "compounding_load" not in a["rules_fired"]


# ─── Injury / condition swaps ───────────────────────────────────────────────

def test_peroneal_swap_lunges_on_day_2():
    sig = _sig(day="Day 2", profile={
        "active_conditions": {"lower_extremity": ["Peroneal tendinopathy (R)"]}
    })
    a = empty_adapted(sig)
    rule_peroneal_swap_lunges(sig, a)
    assert any("Reverse lunges" in s["original"] for s in a["swaps"])
    assert "peroneal_swap_lunges" in a["rules_fired"]


def test_peroneal_swap_quiet_on_day_1():
    sig = _sig(day="Day 1", profile={
        "active_conditions": {"lower_extremity": ["Peroneal tendinopathy (R)"]}
    })
    a = empty_adapted(sig)
    rule_peroneal_swap_lunges(sig, a)
    assert "peroneal_swap_lunges" not in a["rules_fired"]


def test_hip_no_deep_squat():
    sig = _sig(day="Day 2",
               prescribed_session={
                   "session": "Pull + Lower",
                   "main": ["Deep barbell squats — 4×6", "Hip thrusts — 4×10"],
               },
               profile={"active_conditions": {"lower_extremity": ["Hip impingement"]}})
    a = empty_adapted(sig)
    rule_hip_no_deep_squat(sig, a)
    assert any("Deep barbell squats" in r["item"] for r in a["removed"])


def test_slap_swaps_overhead_barbell():
    sig = _sig(day="Day 1",
               prescribed_session={
                   "session": "Push",
                   "main": ["Overhead barbell press — 4×6", "Cable lateral raises — 3×12"],
               },
               profile={"active_conditions": {"upper_extremity": ["Post-SLAP repair shoulder"]}})
    a = empty_adapted(sig)
    rule_slap_no_overhead_barbell(sig, a)
    assert any("Overhead barbell" in s["original"] for s in a["swaps"])


def test_elbow_grip_note_on_day_4():
    sig = _sig(day="Day 4",
               profile={"active_conditions": {"upper_extremity": ["Medial epicondylitis"]}})
    a = empty_adapted(sig)
    rule_elbow_reduce_grip(sig, a)
    assert any("epicondylitis" in n.lower() or "straps" in n.lower() for n in a["notes"])


# ─── Goal / drift ───────────────────────────────────────────────────────────

def test_vo2max_drift_adds_zone2():
    sig = _sig(action_loop=[{
        "sample_type": "vo2max", "latest_value": 30, "target_value": 35,
    }])
    a = empty_adapted(sig)
    rule_vo2max_drift(sig, a)
    assert any("zone 2" in (item["item"].lower()) for item in a["added"])
    assert "vo2max_drift" in a["rules_fired"]


def test_vo2max_on_target_no_add():
    sig = _sig(action_loop=[{
        "sample_type": "vo2max", "latest_value": 50, "target_value": 35,
    }])
    a = empty_adapted(sig)
    rule_vo2max_drift(sig, a)
    assert not a["added"]


def test_already_trained_today_note():
    sig = _sig(workouts_today=[{"label": "Morning Run", "sport": "RUNNING"}])
    a = empty_adapted(sig)
    rule_already_trained_today(sig, a)
    assert any("already trained" in n.lower() for n in a["notes"])


# ─── Genome-aware ───────────────────────────────────────────────────────────

def test_actn3_emphasis_on_push_day():
    sig = _sig(day="Day 1", genome={"by_source": {"imputed_panels": [
        {"gene": "ACTN3", "genotype": "C/C", "rsid": "rs1815739"},
    ]}})
    a = empty_adapted(sig)
    rule_actn3_anaerobic_emphasis(sig, a)
    assert any("ACTN3" in n for n in a["notes"])


def test_apoe_e4_low_sleep():
    sig = _sig(sleep_min_last_night=380, genome={"by_source": {"nutrition_traits": [
        {"gene": "APOE", "genotype": "e3/e4 (T/C)", "rsid": "rs429358"},
    ]}})
    a = empty_adapted(sig)
    rule_apoe_e4_sleep_priority(sig, a)
    assert any("ε4" in n for n in a["notes"])


# ─── Data-driven rules (from correlations) ─────────────────────────────────

def test_high_cost_sport_yesterday_alpine_skiing():
    sig = _sig(day="Day 1",
               workouts_yesterday=[{"label": "Whistler", "sport": "ALPINE_SKIING", "tl": 78}])
    a = empty_adapted(sig)
    rule_high_cost_sport_yesterday(sig, a)
    assert "high_cost_sport_yesterday" in a["rules_fired"]
    assert a["traffic_light"] == "amber"
    assert a["intensity_modifier"] <= 0.75
    assert any("Alpine Skiing" in n for n in a["notes"])


def test_high_cost_sport_yesterday_hiking():
    sig = _sig(day="Day 2",
               workouts_yesterday=[{"label": "Long hike", "sport": "HIKING", "tl": 60}])
    a = empty_adapted(sig)
    rule_high_cost_sport_yesterday(sig, a)
    assert "high_cost_sport_yesterday" in a["rules_fired"]


def test_high_cost_sport_yesterday_quiet_for_cycling():
    sig = _sig(day="Day 1",
               workouts_yesterday=[{"label": "Easy spin", "sport": "CYCLING", "tl": 30}])
    a = empty_adapted(sig)
    rule_high_cost_sport_yesterday(sig, a)
    assert "high_cost_sport_yesterday" not in a["rules_fired"]


def test_thursday_caution_fires_on_low_sleep():
    sig = _sig(day="Day 4", sleep_min_last_night=320)
    a = empty_adapted(sig)
    rule_thursday_caution(sig, a)
    assert "thursday_caution" in a["rules_fired"]
    assert any("Thursday" in n for n in a["notes"])


def test_thursday_caution_quiet_with_normal_sleep():
    sig = _sig(day="Day 4", sleep_min_last_night=480)
    a = empty_adapted(sig)
    rule_thursday_caution(sig, a)
    assert "thursday_caution" not in a["rules_fired"]


def test_thursday_caution_quiet_other_day():
    sig = _sig(day="Day 1", sleep_min_last_night=320)
    a = empty_adapted(sig)
    rule_thursday_caution(sig, a)
    assert "thursday_caution" not in a["rules_fired"]


def test_vo2max_modality_prefers_bike_when_peroneal_active():
    sig = _sig(profile={"active_conditions": {"lower_extremity": ["Peroneal tendinopathy"]}},
               action_loop=[{"sample_type": "vo2max", "latest_value": 30, "target_value": 35}])
    a = empty_adapted(sig)
    rule_vo2max_drift(sig, a)
    assert any("bike" in item["item"].lower() or "rowing" in item["item"].lower()
               for item in a["added"])


def test_apoe_quiet_when_sleep_normal():
    sig = _sig(sleep_min_last_night=480, genome={"by_source": {"nutrition_traits": [
        {"gene": "APOE", "genotype": "e3/e4", "rsid": "rs429358"},
    ]}})
    a = empty_adapted(sig)
    rule_apoe_e4_sleep_priority(sig, a)
    assert "apoe_e4_sleep_priority" not in a["rules_fired"]


# ─── Integration ────────────────────────────────────────────────────────────

def test_adapt_today_integration_amber():
    """Realistic case: low sleep + RHR drift + peroneal on Day 2 → amber with swaps."""
    sig = _sig(
        day="Day 2",
        sleep_min_last_night=320,
        rhr_yesterday=58, rhr_baseline_30d=50,
        profile={"active_conditions": {"lower_extremity": ["Peroneal tendinopathy (R)"]}},
        action_loop=[{"sample_type": "vo2max", "latest_value": 28, "target_value": 35}],
    )
    a = adapt_today(sig)
    assert a["traffic_light"] == "amber"
    assert a["intensity_modifier"] <= 0.7
    assert any(s["original"].lower().startswith("reverse lunges") for s in a["swaps"])
    assert any("zone 2" in item["item"].lower() for item in a["added"])
    assert "low_sleep" in a["rules_fired"]
    assert "elevated_rhr" in a["rules_fired"]
    assert "peroneal_swap_lunges" in a["rules_fired"]
    assert "vo2max_drift" in a["rules_fired"]


def test_adapt_today_red_overrides():
    """Very low sleep should force red regardless of program day."""
    sig = _sig(day="Day 1", sleep_min_last_night=180)
    a = adapt_today(sig)
    assert a["traffic_light"] == "red"
    assert a["intensity_modifier"] == 0.0


def test_adapt_today_green_when_clean():
    sig = _sig(day="Day 2", sleep_min_last_night=480,
               rhr_yesterday=50, rhr_baseline_30d=51,
               avg_tl_last_3d=40, avg_tl_last_7d=45)
    a = adapt_today(sig)
    assert a["traffic_light"] == "green"
    assert a["intensity_modifier"] == 1.0


# ─── Saturday peak-load warning (data-driven, day_of_week) ──────────────────

def test_saturday_peak_load_fires_on_day_6():
    sig = _sig(day="Day 6")
    a = empty_adapted(sig)
    rule_saturday_peak_load_warning(sig, a)
    assert "saturday_peak_load_warning" in a["rules_fired"]
    assert "Saturday" in a["notes"][0]


def test_saturday_peak_load_quiet_on_other_days():
    for day in ("Day 1", "Day 5", "Day 7"):
        sig = _sig(day=day)
        a = empty_adapted(sig)
        rule_saturday_peak_load_warning(sig, a)
        assert "saturday_peak_load_warning" not in a["rules_fired"], f"fired on {day}"


# ─── Yoga cadence Friday (goal-driven, weekly compliance) ────────────────────

def test_yoga_cadence_friday_fires_when_zero_yoga_in_7d():
    sig = _sig(day="Day 5", sport_spread_last_7d={"CYCLING": 3, "RUNNING": 1})
    a = empty_adapted(sig)
    rule_yoga_cadence_friday(sig, a)
    assert "yoga_cadence_friday" in a["rules_fired"]


def test_yoga_cadence_friday_quiet_when_yoga_already_done():
    sig = _sig(day="Day 5", sport_spread_last_7d={"YOGA": 1, "CYCLING": 3})
    a = empty_adapted(sig)
    rule_yoga_cadence_friday(sig, a)
    assert "yoga_cadence_friday" not in a["rules_fired"]


def test_yoga_cadence_friday_case_insensitive():
    sig = _sig(day="Day 5", sport_spread_last_7d={"yoga_flow": 1})
    a = empty_adapted(sig)
    rule_yoga_cadence_friday(sig, a)
    assert "yoga_cadence_friday" not in a["rules_fired"]


def test_yoga_cadence_friday_quiet_on_non_friday():
    sig = _sig(day="Day 1", sport_spread_last_7d={})
    a = empty_adapted(sig)
    rule_yoga_cadence_friday(sig, a)
    assert "yoga_cadence_friday" not in a["rules_fired"]


# ─── Sleep gap to target (goal-driven) ───────────────────────────────────────

_SLEEP_GOAL = {
    "goals": [{
        "name": "Sleep average (7d rolling)",
        "target": 7.5,
        "units": "hours",
        "direction": "increase",
        "category": "recovery",
    }],
}


def test_sleep_gap_fires_when_behind_target():
    sig = _sig(sleep_min_last_night=300, profile=_SLEEP_GOAL)
    a = empty_adapted(sig)
    rule_sleep_gap_to_target(sig, a)
    assert "sleep_gap_to_target" in a["rules_fired"]
    msg = a["notes"][0]
    assert "150 min behind" in msg
    assert "450" in msg  # target rendered in minutes


def test_sleep_gap_quiet_when_at_target():
    sig = _sig(sleep_min_last_night=460, profile=_SLEEP_GOAL)
    a = empty_adapted(sig)
    rule_sleep_gap_to_target(sig, a)
    assert "sleep_gap_to_target" not in a["rules_fired"]


def test_sleep_gap_quiet_when_within_30min():
    sig = _sig(sleep_min_last_night=425, profile=_SLEEP_GOAL)  # 25 min behind
    a = empty_adapted(sig)
    rule_sleep_gap_to_target(sig, a)
    assert "sleep_gap_to_target" not in a["rules_fired"]


def test_sleep_gap_quiet_with_no_goal():
    sig = _sig(sleep_min_last_night=300, profile={"goals": []})
    a = empty_adapted(sig)
    rule_sleep_gap_to_target(sig, a)
    assert "sleep_gap_to_target" not in a["rules_fired"]


def test_sleep_gap_quiet_when_no_sleep_data():
    sig = _sig(profile=_SLEEP_GOAL)  # no sleep_min_last_night
    a = empty_adapted(sig)
    rule_sleep_gap_to_target(sig, a)
    assert "sleep_gap_to_target" not in a["rules_fired"]


def test_sleep_gap_handles_minutes_units():
    profile = {"goals": [{
        "name": "Sleep avg", "target": 450, "units": "min",
        "category": "recovery",
    }]}
    sig = _sig(sleep_min_last_night=300, profile=profile)
    a = empty_adapted(sig)
    rule_sleep_gap_to_target(sig, a)
    assert "sleep_gap_to_target" in a["rules_fired"]
