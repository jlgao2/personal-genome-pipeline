# Adaptive Programming Engine

> Triggered by: "the app needs to take health updates and organically update workouts"
> Status: design + first implementation in this commit

## What it actually does

A pure function:

```
adapt_today(signals) → adapted_session
```

`signals` is everything we know about the user's last 7 days + genome + active
conditions + today's prescription. `adapted_session` is the prescription
**modified**: swapped exercises, intensity modifier, added cardio, traffic
light verdict, notes.

The engine runs on the **laptop** during `refresh.sh` and emits its output as
part of `ios_bundle.json`. Single source of truth — web + iOS both render the
same adapted session. No logic duplication.

## Inputs (Signals)

```python
@dataclass
class Signals:
    # Recovery
    sleep_min_last_night: float | None     # from samples
    rhr_yesterday: float | None            # from samples
    rhr_baseline_30d: float | None         # rolling avg
    hrv_yesterday: float | None            # garmin sleep_respiration / sdnn
    body_battery_today: float | None       # from garmin meta

    # Recent training load
    avg_tl_last_3d: float | None           # workouts events
    avg_tl_last_7d: float | None
    sport_spread_last_7d: dict             # {RUNNING: 2, CYCLING: 3, ...}

    # Today
    program_day: str                        # 'Day 1' .. 'Day 7'
    prescribed_session: dict                # rehab/warmup/main/core arrays
    workouts_today: list[dict]              # already-done sessions

    # Static profile
    profile: dict
    action_loop: list[dict]                 # for drift detection
    genome: dict                            # for ACTN3, COL, etc.
```

## Output (AdaptedSession)

```python
{
    "program_day": "Day 4",
    "prescribed": "Pull + Lower + core",
    "traffic_light": "amber",   # green | amber | red

    "intensity_modifier": 0.7,  # multiply prescribed sets/reps/weight by this
    "intensity_reason": "Sleep 5h + RHR +7 bpm vs 30d baseline",

    "swaps": [
        {"original": "Reverse lunges (short step)",
         "replacement": "Stationary bike 15 min, zone 2",
         "reason": "Peroneal flare risk on Day 4 lower volume"},
    ],
    "removed": [
        {"item": "Heavy single-arm row",
         "reason": "Medial epicondylitis active"},
    ],
    "added": [
        {"item": "10 min zone 2 cycling",
         "reason": "VO2max drift on Action Loop"},
    ],
    "notes": [
        "Recovery low — cap target TL <40",
        "Cardio modality: bike or rowing only (no running)",
    ],
}
```

`traffic_light`:
- **green** = train as prescribed (or even progress)
- **amber** = train at reduced intensity, follow swaps
- **red** = skip training, prioritize sleep / mobility / Day 5 yoga regardless of calendar day

## Rule architecture

A rule is a function `(Signals, AdaptedSession) → None` that mutates the session in place. Rules run in order; later rules can see earlier rules' output.

```python
RULES: list[Callable[[Signals, dict], None]] = [
    # — Recovery rules (set intensity_modifier + traffic light) —
    rule_low_sleep,                  # <6h sleep → 0.7 intensity, amber
    rule_very_low_sleep,             # <5h → red
    rule_elevated_rhr,               # RHR +5 bpm → amber, cap TL
    rule_compounding_load,           # high TL 3+ days → deload, amber
    rule_low_body_battery,           # <30 → amber

    # — Injury/condition swaps —
    rule_peroneal_no_running,        # always
    rule_peroneal_swap_lunges,       # Day 2/4/6 → swap dynamic single-leg
    rule_hip_no_deep_squat,          # Day 2/4 → remove deep loaded squats
    rule_slap_no_overhead_barbell,   # Day 1/3 → swap to landmines
    rule_elbow_reduce_grip,          # Day 2/4 → straps + neutral grip

    # — Goal/drift rules —
    rule_vo2max_drift,               # Action Loop has vo2max off → add zone 2
    rule_weight_drift,               # current_weight > goal+3kg → bias cardio
    rule_sleep_streak_low,           # 3+ days <7h → push Day 5 sooner

    # — Schedule rules —
    rule_missed_yesterday,           # if Day N-1 was missed and Day N is similar,
                                     # consider swapping
    rule_already_trained_today,      # if Garmin shows session, deduplicate
    rule_rest_day_no_changes,        # Day 7 → no adaptation

    # — Genome-aware (rare, narrow) —
    rule_actn3_anaerobic_emphasis,   # if ACTN3 RR or RX, slight bias to power work
    rule_apoe_e4_sleep_priority,     # if ε4, push Day 5 if sleep <7h

    # — Final synthesis —
    rule_finalize_traffic_light,     # combines all signals into one verdict
]
```

Rules are **declarative** in spirit — each one self-contained, with a clear
condition + effect. Easy to add. Easy to test.

## Rendering the adapted session

**Dashboard:** the existing `renderTodaySession` reads `adapted_session` from
the bundle and:
- Shows the traffic light prominently (large pill: GREEN / AMBER / RED)
- Lists original exercises, with swaps shown as `~~Reverse lunges~~ → Bike 15min`
- Removed items struck through and dimmed
- Added items appended with a `+` indicator
- Intensity modifier rendered as "70% intensity today (recovery low)"

**iOS:** same shape, scaled to the phone — traffic light is the most prominent
element, swaps render as a list of "→" arrows.

## Implementation tasks

1. **`pipeline/adaptive.py`** — Signals dataclass + compute_signals + ~12 rules + adapt_today
2. **Tests** — `tests/test_adaptive.py` covering each rule + integration tests with synthetic Signals fixtures
3. **Wire into `publish_ios_export`** — adapted_session is a top-level key in `ios_bundle.json`
4. **Update web** — `renderTodaySession` consumes the adapted_session structure
5. **iOS** — extend `Bundle.swift` model, add `AdaptedSessionView` (or fold into existing TodaySessionView)

Time: ~3-4 hours for v0 with ~10 rules. Each rule is ~10-20 lines + a test.

## Out of scope (v1)

- **Set/rep/weight progression** — needs a workout logger first (Hevy ingest later)
- **ML-based load prediction** — the current rule set is honest about being heuristic
- **A/B comparing adaptations** — too early, too few data points
- **User-configurable rule weights** — single user; can add later
- **"Why did you change this?" full audit log** — every rule produces a `reason`
  string already; aggregate later if needed

## Decision points (call out if wrong)

1. **Rule output format = mutate-in-place dict** — keeps rules cheap, no schema gymnastics
2. **Single laptop pass** — runs at `refresh.sh` time, not per-page-load. Same data freshness as everything else
3. **Genome rules are narrow** — only ACTN3 + APOE included in v1. The full genome→training mapping is its own deep project
4. **Traffic light is the headline** — green/amber/red is simpler than a numeric score

Reply "go" to start, or redline.
