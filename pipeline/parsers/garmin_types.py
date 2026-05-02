"""Mapping from Garmin Connect bulk-export field names to our normalized vocab.

UDS rollups are daily summary objects; sleep is per-night; biometrics are sparse.
Each entry: garmin_field → (normalized_type, unit).
"""
from typing import Optional

UDS_FIELD_MAP: dict[str, tuple[str, str]] = {
    "minHeartRate":               ("heart_rate_min_daily",  "bpm"),
    "maxHeartRate":               ("heart_rate_max_daily",  "bpm"),
    "minAvgHeartRate":            ("heart_rate_resting",    "bpm"),
    "moderateIntensityMinutes":   ("moderate_minutes",      "min"),
    "vigorousIntensityMinutes":   ("vigorous_minutes",      "min"),
    "totalKilocalories":          ("kcal_total",            "kcal"),
    "activeKilocalories":         ("kcal_active",           "kcal"),
}

SLEEP_FIELD_MAP: dict[str, tuple[str, str]] = {
    "deepSleepSeconds":   ("sleep_deep",   "s"),
    "lightSleepSeconds":  ("sleep_light",  "s"),
    "remSleepSeconds":    ("sleep_rem",    "s"),
    "awakeSleepSeconds":  ("sleep_awake",  "s"),
    "averageRespiration": ("sleep_respiration_avg", "breaths/min"),
    "avgSleepStress":     ("sleep_stress_avg",      "score"),
}

BIOMETRIC_FIELD_MAP: dict[str, tuple[str, str]] = {
    "vo2MaxRunning": ("vo2max",       "mL/min·kg"),
    "vo2MaxCycling": ("vo2max_cycle", "mL/min·kg"),
    "weight":        ("weight",       "g"),
    "height":        ("height",       "cm"),
    "bodyFat":       ("body_fat_pct", "%"),
}


def normalize_uds(field: str) -> Optional[tuple[str, str]]:
    return UDS_FIELD_MAP.get(field)


def normalize_sleep(field: str) -> Optional[tuple[str, str]]:
    return SLEEP_FIELD_MAP.get(field)


def normalize_biometric(field: str) -> Optional[tuple[str, str]]:
    return BIOMETRIC_FIELD_MAP.get(field)
