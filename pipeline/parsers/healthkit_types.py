"""Mapping from Apple HealthKit identifier strings to our normalized type vocabulary.

Only the types we want to ingest are listed. Everything else is silently dropped
by `normalize_type` returning None.
"""
from typing import Optional

# Curated subset — these are the types worth surfacing on the dashboard.
# Others (e.g., HKQuantityTypeIdentifierDietaryProtein) can be added later.
HEALTHKIT_TYPE_MAP: dict[str, str] = {
    # Cardiovascular
    "HKQuantityTypeIdentifierHeartRate":                 "heart_rate",
    "HKQuantityTypeIdentifierRestingHeartRate":          "heart_rate_resting",
    "HKQuantityTypeIdentifierWalkingHeartRateAverage":   "heart_rate_walking_avg",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":  "hrv_sdnn",
    "HKQuantityTypeIdentifierVO2Max":                    "vo2max",
    "HKQuantityTypeIdentifierBloodPressureSystolic":     "bp_systolic",
    "HKQuantityTypeIdentifierBloodPressureDiastolic":    "bp_diastolic",

    # Body composition
    "HKQuantityTypeIdentifierBodyMass":                  "weight",
    "HKQuantityTypeIdentifierBodyMassIndex":             "bmi",
    "HKQuantityTypeIdentifierBodyFatPercentage":         "body_fat_pct",
    "HKQuantityTypeIdentifierLeanBodyMass":              "lean_body_mass",

    # Activity
    "HKQuantityTypeIdentifierStepCount":                 "steps",
    "HKQuantityTypeIdentifierDistanceWalkingRunning":    "distance_walking_running",
    "HKQuantityTypeIdentifierActiveEnergyBurned":        "active_energy",
    "HKQuantityTypeIdentifierBasalEnergyBurned":         "basal_energy",
    "HKQuantityTypeIdentifierAppleExerciseTime":         "exercise_minutes",
    "HKQuantityTypeIdentifierAppleStandHour":            "stand_hours",
    "HKQuantityTypeIdentifierFlightsClimbed":            "flights_climbed",

    # Respiration / metabolic
    "HKQuantityTypeIdentifierRespiratoryRate":           "respiratory_rate",
    "HKQuantityTypeIdentifierOxygenSaturation":          "spo2",
    "HKQuantityTypeIdentifierBodyTemperature":           "body_temp",
    "HKQuantityTypeIdentifierBloodGlucose":              "blood_glucose",

    # Sleep
    "HKCategoryTypeIdentifierSleepAnalysis":             "sleep_stage",

    # Mindfulness
    "HKCategoryTypeIdentifierMindfulSession":            "mindful_minutes",
}

KNOWN_TYPES = frozenset(HEALTHKIT_TYPE_MAP.values())


def normalize_type(hk_identifier: str) -> Optional[str]:
    """Map an Apple HealthKit type identifier to our normalized name, or None."""
    return HEALTHKIT_TYPE_MAP.get(hk_identifier)
