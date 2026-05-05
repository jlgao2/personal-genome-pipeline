"""Media log parser — reads output/media.yaml, emits a structured array
suitable for the dashboard bundle.

This is the consumption side of the Frontal Lobe tool: what you've
chosen to read / listen to / watch. Non-consumption (abstinences) lives
in health_profile.json under `abstinences[]` and is tracked daily via
localStorage on the dashboard.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def load_media(yaml_path: Path) -> Optional[list[dict]]:
    """Return the parsed list, or None if missing/invalid.
    Date values are coerced to ISO strings for JSON-serializability."""
    if not yaml_path.exists():
        return None
    try:
        import yaml
    except ImportError:
        return None
    try:
        data = yaml.safe_load(yaml_path.read_text())
    except yaml.YAMLError:
        return None
    if not isinstance(data, list):
        return None
    import datetime as _dt
    out = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        clean = {}
        for k, v in entry.items():
            if isinstance(v, (_dt.date, _dt.datetime)):
                clean[k] = v.isoformat()
            else:
                clean[k] = v
        out.append(clean)
    return out
