from pipeline.parsers.healthkit_types import normalize_type, KNOWN_TYPES


def test_known_types_normalize():
    assert normalize_type("HKQuantityTypeIdentifierHeartRate") == "heart_rate"
    assert normalize_type("HKQuantityTypeIdentifierRestingHeartRate") == "heart_rate_resting"
    assert normalize_type("HKQuantityTypeIdentifierVO2Max") == "vo2max"
    assert normalize_type("HKQuantityTypeIdentifierBodyMass") == "weight"
    assert normalize_type("HKCategoryTypeIdentifierSleepAnalysis") == "sleep_stage"


def test_unknown_type_returns_none():
    assert normalize_type("HKQuantityTypeIdentifierUnknownSomething") is None


def test_known_types_set_nonempty():
    assert len(KNOWN_TYPES) > 15
