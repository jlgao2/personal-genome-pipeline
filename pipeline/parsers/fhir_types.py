"""LOINC code → normalized type vocabulary for FHIR Observation parsing.

Curated subset of the most clinically-actionable labs + vitals. Every entry
is something the dashboard will plot or join against a cross-ref. Add rows
here when MyChart starts emitting LOINC codes you care about.
"""
from typing import Optional

# Mapping: LOINC code → (normalized_type, default_unit_hint)
LOINC_TO_TYPE: dict[str, tuple[str, str]] = {
    # Lipid panel
    "2093-3":   ("cholesterol_total",   "mg/dL"),
    "13457-7":  ("ldl_cholesterol",     "mg/dL"),
    "18262-6":  ("ldl_cholesterol",     "mg/dL"),  # direct LDL
    "2085-9":   ("hdl_cholesterol",     "mg/dL"),
    "2571-8":   ("triglycerides",       "mg/dL"),
    "9830-1":   ("non_hdl_cholesterol", "mg/dL"),

    # Glucose / HbA1c
    "2345-7":   ("glucose_fasting",     "mg/dL"),
    "4548-4":   ("hba1c",               "%"),
    "17856-6":  ("hba1c",               "%"),

    # Renal
    "2160-0":   ("creatinine",          "mg/dL"),
    "33914-3":  ("egfr",                "mL/min"),
    "3094-0":   ("bun",                 "mg/dL"),

    # Liver
    "1742-6":   ("alt",                 "U/L"),
    "1920-8":   ("ast",                 "U/L"),
    "6768-6":   ("alk_phos",            "U/L"),
    "1975-2":   ("bilirubin_total",     "mg/dL"),

    # Iron / B-vitamins (relevant to HFE, MTHFR, FUT2 findings)
    "2498-4":   ("iron",                "µg/dL"),
    "2276-4":   ("ferritin",            "ng/mL"),
    "2284-8":   ("folate_serum",        "ng/mL"),
    "2132-9":   ("b12",                 "pg/mL"),
    "13965-9":  ("homocysteine",        "µmol/L"),

    # Thyroid
    "3016-3":   ("tsh",                 "mIU/L"),
    "3026-2":   ("free_t4",             "ng/dL"),

    # Inflammation
    "30522-7":  ("hs_crp",              "mg/L"),
    "1988-5":   ("crp",                 "mg/L"),

    # Vitamin D
    "62292-8":  ("vitamin_d_25oh",      "ng/mL"),
    "1989-3":   ("vitamin_d_25oh",      "ng/mL"),

    # Vitals (when they come through as Observations rather than HKQuantity)
    "8480-6":   ("bp_systolic",         "mmHg"),
    "8462-4":   ("bp_diastolic",        "mmHg"),
    "8867-4":   ("heart_rate",          "bpm"),
    "29463-7":  ("weight",              "kg"),
    "8302-2":   ("height",              "cm"),
    "39156-5":  ("bmi",                 "kg/m2"),
    "8310-5":   ("body_temp",           "C"),
    "59408-5":  ("spo2",                "%"),
}


def normalize_loinc(code: Optional[str]) -> Optional[str]:
    """Map a LOINC code to our normalized sample-type name, or None if unknown."""
    if not code:
        return None
    mapping = LOINC_TO_TYPE.get(code)
    return mapping[0] if mapping else None
