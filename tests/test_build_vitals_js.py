import json
import re
import tempfile
from pathlib import Path

from pipeline.parsers.healthkit import parse_to_parquet
from pipeline.build_vitals import write_vitals_js

FIXTURE = Path(__file__).parent / "parsers" / "fixtures" / "healthkit_sample.xml"


def test_write_vitals_js_emits_valid_es_module():
    with tempfile.TemporaryDirectory() as td:
        parquet_dir = Path(td) / "parquet"
        out_js = Path(td) / "data-vitals.js"
        parse_to_parquet(FIXTURE, parquet_dir)
        write_vitals_js(parquet_dir, out_js)

        content = out_js.read_text()
        assert content.startswith("/* AUTO-GENERATED")
        assert "export const VITALS" in content

        # Extract the JSON literal after `=` and verify it parses.
        match = re.search(r"export const VITALS\s*=\s*(\{.*\});", content, re.S)
        assert match
        data = json.loads(match.group(1))
        assert "heart_rate_resting" in data
