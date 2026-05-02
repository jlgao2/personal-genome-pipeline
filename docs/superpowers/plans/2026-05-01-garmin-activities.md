# Garmin Activities → events.parquet (Sub-3 extension)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Parse the 972 activities in `DI_CONNECT/DI-Connect-Fitness/*_summarizedActivities.json` into the `events.parquet` table defined by the architecture spec. Add a Workouts panel to the dashboard showing the last 90 days with HR-zone breakdown + training load.

**Architecture:** Extend `pipeline/parsers/garmin.py` with `iter_activities()`. Write to `data/parquet/events/garmin-YYYY-MM.parquet` partitioned by activity start month. `build_vitals.py` gains `build_workouts()` that queries the events table and emits a separate `WORKOUTS` ESM export. Dashboard renders a `#workouts` section with one card per workout.

**Tech Stack:** Same as Sub-3 — stdlib `json` + `zipfile`, `pyarrow`, vanilla JS rendering.

---

## File structure

```
data/parquet/events/garmin-YYYY-MM.parquet     (new)

pipeline/parsers/garmin.py                     (modify — add iter_activities + writer)
pipeline/build_vitals.py                       (modify — add build_workouts + write_vitals_js extension)

tests/parsers/fixtures/garmin_activities_sample.json (new)
tests/parsers/test_garmin_activities.py        (new)

output/web/index.html                          (modify — add Workouts section)
output/web/js/main.js                          (modify — renderWorkouts)
output/web/css/layout.css                      (modify — workout card styles)
```

---

## Task 1 — Activities parser (TDD)

**Files:**
- Create: `tests/parsers/fixtures/garmin_activities_sample.json`
- Modify: `pipeline/parsers/garmin.py`
- Create: `tests/parsers/test_garmin_activities.py`

- [ ] **Step 1: Author fixture**

Create `tests/parsers/fixtures/garmin_activities_sample.json`:

```json
[{
  "summarizedActivitiesExport": [
    {
      "activityId": 1,
      "activityType": "tennis_v2",
      "sportType": "TENNIS",
      "name": "Chicago Tennis",
      "beginTimestamp": 1776986466000,
      "duration": 2367519,
      "distance": 188393,
      "calories": 2229,
      "avgHr": 140,
      "maxHr": 177,
      "minHr": 70,
      "hrTimeInZone_0": 105313,
      "hrTimeInZone_1": 27996,
      "hrTimeInZone_2": 689237,
      "hrTimeInZone_3": 1392968,
      "hrTimeInZone_4": 148002,
      "hrTimeInZone_5": 4003,
      "activityTrainingLoad": 97.7,
      "aerobicTrainingEffect": 2.9,
      "anaerobicTrainingEffect": 2.4,
      "locationName": "Chicago"
    },
    {
      "activityId": 2,
      "activityType": "running",
      "sportType": "RUNNING",
      "name": "Morning Run",
      "beginTimestamp": 1776900000000,
      "duration": 1800000,
      "distance": 5000,
      "calories": 410,
      "avgHr": 152,
      "maxHr": 168
    }
  ]
}]
```

- [ ] **Step 2: Write failing test**

Create `tests/parsers/test_garmin_activities.py`:

```python
from pathlib import Path

from pipeline.parsers.garmin import iter_activities

FIXTURE = Path(__file__).parent / "fixtures" / "garmin_activities_sample.json"


def test_iter_activities_yields_one_event_per_activity():
    events = list(iter_activities(FIXTURE))
    assert len(events) == 2
    for e in events:
        assert e["source"] == "garmin"
        assert e["type"] == "workout"
        assert "ts_start" in e and "ts_end" in e

    tennis = next(e for e in events if e["label"] == "Chicago Tennis")
    assert tennis["meta"]["sport"] == "TENNIS"
    assert tennis["meta"]["avg_hr"] == 140
    assert tennis["meta"]["calories"] == 2229
    # HR zones bundled into meta
    assert tennis["meta"]["hr_time_in_zone"]["zone_3"] == 1392968


def test_iter_activities_handles_missing_optional_fields():
    events = list(iter_activities(FIXTURE))
    run = next(e for e in events if e["label"] == "Morning Run")
    # No HR zones / training load on this one — meta still populated, missing keys absent
    assert run["meta"]["sport"] == "RUNNING"
    assert "hr_time_in_zone" not in run["meta"] or run["meta"]["hr_time_in_zone"] == {}
    assert run["meta"].get("training_load") is None
```

- [ ] **Step 3: Implement parser**

Append to `pipeline/parsers/garmin.py`:

```python
def _ts_from_ms(ms: int) -> str:
    """Convert epoch milliseconds to ISO-8601 UTC."""
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.isoformat()


def iter_activities(json_path: Path) -> Iterator[dict]:
    """Yield event dicts from one summarizedActivities.json file."""
    with json_path.open() as f:
        outer = json.load(f)
    if not outer:
        return
    activities = outer[0].get("summarizedActivitiesExport") or []
    for a in activities:
        begin_ms = a.get("beginTimestamp")
        if begin_ms is None:
            continue
        try:
            duration_ms = float(a.get("duration") or 0)
        except (TypeError, ValueError):
            duration_ms = 0
        ts_start = _ts_from_ms(begin_ms)
        ts_end   = _ts_from_ms(int(begin_ms + duration_ms))

        zones = {}
        for i in range(6):
            v = a.get(f"hrTimeInZone_{i}")
            if v is not None:
                zones[f"zone_{i}"] = v

        meta = {
            "activity_id":   a.get("activityId"),
            "sport":         a.get("sportType"),
            "activity_type": a.get("activityType"),
            "duration_s":    duration_ms / 1000.0 if duration_ms else None,
            "distance_m":    a.get("distance"),
            "calories":      a.get("calories"),
            "avg_hr":        a.get("avgHr"),
            "max_hr":        a.get("maxHr"),
            "min_hr":        a.get("minHr"),
            "hr_time_in_zone":      zones if zones else None,
            "training_load":        a.get("activityTrainingLoad"),
            "aerobic_te":           a.get("aerobicTrainingEffect"),
            "anaerobic_te":         a.get("anaerobicTrainingEffect"),
            "location":             a.get("locationName"),
        }
        # Drop None values for tighter JSON
        meta = {k: v for k, v in meta.items() if v is not None}

        yield {
            "ts_start": ts_start,
            "ts_end":   ts_end,
            "source":   "garmin",
            "type":     "workout",
            "label":    a.get("name") or a.get("sportType") or "Workout",
            "meta":     meta,
        }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/parsers/test_garmin_activities.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/parsers/garmin.py tests/parsers/test_garmin_activities.py tests/parsers/fixtures/garmin_activities_sample.json
git commit -m "Add Garmin activities → events parser"
```

---

## Task 2 — Events Parquet writer + ZIP integration

**Files:**
- Modify: `pipeline/parsers/garmin.py`
- Modify: `tests/parsers/test_garmin_parquet.py`

The existing `parse_zip_to_parquet` writes only to `samples/`. We extend it to also write `events/garmin-YYYY-MM.parquet` whenever `summarizedActivities.json` is found.

- [ ] **Step 1: Update orchestrator to take separate samples/events outdirs**

Modify `parse_zip_to_parquet` in `pipeline/parsers/garmin.py`:

```python
def parse_zip_to_parquet(zip_path: Path, outdir: Path,
                         events_outdir: Optional[Path] = None) -> int:
    """Parse all known JSON files in a Garmin bulk-export ZIP to Parquet.

    `outdir` receives sample partitions (garmin-YYYY-MM.parquet).
    `events_outdir` (default: outdir.parent / 'events') receives event
    partitions (garmin-YYYY-MM.parquet) for activities.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    if events_outdir is None:
        events_outdir = outdir.parent / "events"
    events_outdir.mkdir(parents=True, exist_ok=True)

    for old in outdir.glob("garmin-*.parquet"):
        old.unlink()
    for old in events_outdir.glob("garmin-*.parquet"):
        old.unlink()

    rows_by_partition: dict[str, list[dict]] = defaultdict(list)
    events_by_partition: dict[str, list[dict]] = defaultdict(list)
    n_total = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.startswith("DI_CONNECT/DI-Connect-Aggregator/UDSFile_") and name.endswith(".json"):
                samples = list(_iter_from_zip_member(zf, name, iter_uds_samples))
                for s in samples:
                    s = {**s, "meta": json.dumps(s["meta"])}
                    rows_by_partition[s["ts"][:7]].append(s)
                    n_total += 1
            elif name.startswith("DI_CONNECT/DI-Connect-Wellness/") and name.endswith("_sleepData.json"):
                samples = list(_iter_from_zip_member(zf, name, iter_sleep_samples))
                for s in samples:
                    s = {**s, "meta": json.dumps(s["meta"])}
                    rows_by_partition[s["ts"][:7]].append(s)
                    n_total += 1
            elif name.endswith("_userBioMetrics.json") and "DI-Connect-Wellness" in name:
                samples = list(_iter_from_zip_member(zf, name, iter_biometric_samples))
                for s in samples:
                    s = {**s, "meta": json.dumps(s["meta"])}
                    rows_by_partition[s["ts"][:7]].append(s)
                    n_total += 1
            elif name.endswith("_summarizedActivities.json") and "DI-Connect-Fitness" in name:
                events = list(_iter_from_zip_member(zf, name, iter_activities))
                for e in events:
                    e = {**e, "meta": json.dumps(e["meta"])}
                    events_by_partition[e["ts_start"][:7]].append(e)
                    n_total += 1

    sample_schema = pa.schema([
        ("ts",     pa.string()),
        ("ts_end", pa.string()),
        ("source", pa.string()),
        ("type",   pa.string()),
        ("value",  pa.float64()),
        ("unit",   pa.string()),
        ("meta",   pa.string()),
    ])
    for partition, samples in rows_by_partition.items():
        table = pa.Table.from_pylist(samples, schema=sample_schema)
        pq.write_table(table, outdir / f"garmin-{partition}.parquet")

    event_schema = pa.schema([
        ("ts_start", pa.string()),
        ("ts_end",   pa.string()),
        ("source",   pa.string()),
        ("type",     pa.string()),
        ("label",    pa.string()),
        ("meta",     pa.string()),
    ])
    for partition, events in events_by_partition.items():
        table = pa.Table.from_pylist(events, schema=event_schema)
        pq.write_table(table, events_outdir / f"garmin-{partition}.parquet")

    return n_total
```

(Add `from typing import Optional` import if not already present.)

- [ ] **Step 2: Update existing test ZIP to include activities + add events test**

Append to `tests/parsers/test_garmin_parquet.py`:

```python
ACT = json.loads((Path(__file__).parent / "fixtures" / "garmin_activities_sample.json").read_text())


def _make_test_zip_with_activities(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("DI_CONNECT/DI-Connect-Aggregator/UDSFile_test.json", json.dumps(UDS))
        zf.writestr("DI_CONNECT/DI-Connect-Fitness/test_summarizedActivities.json", json.dumps(ACT))


def test_parse_zip_writes_events_partitions(tmp_path):
    zip_path = tmp_path / "g.zip"
    samples_out = tmp_path / "samples"
    events_out  = tmp_path / "events"
    _make_test_zip_with_activities(zip_path)
    n = parse_zip_to_parquet(zip_path, samples_out, events_out)
    assert n > 0
    assert list(events_out.glob("garmin-*.parquet")), "events partition was not written"

    rows = duckdb.query(
        f"select label, count(*) from '{events_out}/garmin-*.parquet' group by label"
    ).fetchall()
    labels = {r[0] for r in rows}
    assert "Chicago Tennis" in labels
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/parsers/ -v
```

Expected: all parser tests pass, including 1 new events test.

- [ ] **Step 4: Run on real data**

```bash
python3 -m pipeline.parsers.garmin data/raw/garmin/garmin_export.zip --outdir data/parquet/samples
python3 -c "
import duckdb
n = duckdb.query(\"select count(*) from 'data/parquet/events/garmin-*.parquet'\").fetchone()[0]
print(f'  total events: {n}')
rows = duckdb.query(\"select json_extract_string(meta, '\$.sport') as sport, count(*) as n from 'data/parquet/events/garmin-*.parquet' group by sport order by n desc limit 10\").fetchall()
for s, n in rows: print(f'  {s:20s}  {n:>4d}')
"
```

Expected: ~972 events; sport distribution led by RUNNING / TENNIS / CYCLING / etc.

- [ ] **Step 5: Commit**

```bash
git add pipeline/parsers/garmin.py tests/parsers/test_garmin_parquet.py
git commit -m "Garmin: write activities to events.parquet alongside samples"
```

---

## Task 3 — Workouts query layer + JS module

**Files:**
- Modify: `pipeline/build_vitals.py` (add `build_workouts` + extend `write_vitals_js`)

- [ ] **Step 1: Add build_workouts function**

Append to `pipeline/build_vitals.py`:

```python
WORKOUTS_QUERY = """
    SELECT ts_start, ts_end, label,
           json_extract_string(meta, '$.sport')         AS sport,
           CAST(json_extract(meta, '$.duration_s')         AS DOUBLE) AS duration_s,
           CAST(json_extract(meta, '$.distance_m')         AS DOUBLE) AS distance_m,
           CAST(json_extract(meta, '$.calories')           AS DOUBLE) AS calories,
           CAST(json_extract(meta, '$.avg_hr')             AS DOUBLE) AS avg_hr,
           CAST(json_extract(meta, '$.max_hr')             AS DOUBLE) AS max_hr,
           CAST(json_extract(meta, '$.training_load')      AS DOUBLE) AS training_load,
           CAST(json_extract(meta, '$.aerobic_te')         AS DOUBLE) AS aerobic_te,
           json_extract(meta, '$.hr_time_in_zone')          AS hr_zones_json
    FROM   read_parquet('{events}/garmin-*.parquet', union_by_name=true)
    WHERE  type = 'workout'
    ORDER BY ts_start DESC
    LIMIT 90
"""


def build_workouts(events_dir: Path) -> list[dict]:
    """Return the most recent 90 workouts as plain dicts."""
    if not events_dir.exists() or not list(events_dir.glob("garmin-*.parquet")):
        return []
    rows = duckdb.query(WORKOUTS_QUERY.format(events=str(events_dir).rstrip("/"))).fetchall()
    cols = ["ts_start", "ts_end", "label", "sport", "duration_s", "distance_m",
            "calories", "avg_hr", "max_hr", "training_load", "aerobic_te", "hr_zones_json"]
    out = []
    for row in rows:
        d = dict(zip(cols, row))
        # hr_zones_json comes back as a JSON string — re-parse to dict for the dashboard
        zj = d.pop("hr_zones_json")
        try:
            d["hr_zones"] = json.loads(zj) if zj else None
        except (TypeError, ValueError):
            d["hr_zones"] = None
        out.append(d)
    return out
```

(Add `import json` at the top of the file if not present.)

- [ ] **Step 2: Extend `write_vitals_js` to also emit WORKOUTS**

Replace the `write_vitals_js` function body:

```python
def write_vitals_js(parquet_dir: Path, out_path: Path,
                    events_dir: Optional[Path] = None) -> None:
    """Build vitals + workouts and emit as one ES module."""
    import json as _json
    if events_dir is None:
        events_dir = parquet_dir.parent / "events"
    vitals = build_vitals(parquet_dir)
    workouts = build_workouts(events_dir)
    vitals_payload = _json.dumps(vitals, indent=2)
    workouts_payload = _json.dumps(workouts, indent=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "/* AUTO-GENERATED by pipeline/build_vitals.py — do not edit by hand. */\n"
        f"export const VITALS = {vitals_payload};\n"
        f"export const WORKOUTS = {workouts_payload};\n"
    )
```

(Add `from typing import Optional` if not already imported.)

- [ ] **Step 3: Run tests + regenerate**

```bash
pytest tests/test_build_vitals_js.py -v
python3 -m pipeline.build_vitals --parquet data/parquet/samples --out output/web/js/data-vitals.js
grep -c "WORKOUTS" output/web/js/data-vitals.js
```

Expected: tests pass; grep returns ≥1.

- [ ] **Step 4: Commit**

```bash
git add pipeline/build_vitals.py
git commit -m "Add build_workouts; data-vitals.js exports VITALS + WORKOUTS"
```

---

## Task 4 — Dashboard Workouts panel

**Files:**
- Modify: `output/web/index.html`
- Modify: `output/web/js/main.js`
- Modify: `output/web/css/layout.css`

- [ ] **Step 1: Add Workouts section to HTML**

Edit `output/web/index.html`. Add a nav entry after the Vitals one:

```html
<li><button class="nav-btn" data-section="workouts"  data-num="07b">Workouts</button></li>
```

After the closing `</section>` of the Vitals section, insert:

```html
<!-- Workouts (Garmin activities) -->
<section class="section" id="workouts">
  <p class="section-kicker">Garmin · last 90 activities</p>
  <h2 class="section-title">Workouts</h2>
  <p class="section-lead">
    Recent training. HR-zone bars show time spent in each zone — wide right
    bars = aerobic threshold and above. Training load is Garmin's per-activity
    score; aerobic-TE 3.0+ is a strong session.
  </p>
  <div class="workouts-list" id="workouts-list"></div>
</section>
```

- [ ] **Step 2: Add CSS for workout cards**

Append to `output/web/css/layout.css`:

```css
/* ── Workouts list ── */
.workouts-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  margin-bottom: 1.5rem;
}
.workout-card {
  background: var(--bg-card);
  padding: 0.85rem 1.1rem;
  display: grid;
  grid-template-columns: 100px 1fr auto;
  gap: 1rem;
  align-items: center;
}
.workout-date {
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--fg-dim);
}
.workout-label {
  font-family: var(--font-display);
  font-size: 1rem;
  font-style: italic;
  color: var(--fg);
}
.workout-sport {
  font-family: var(--font-mono);
  font-size: 0.5rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--fg-mute);
  margin-left: 0.4rem;
}
.workout-stats {
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--fg-dim);
  text-align: right;
}
.hr-zones {
  display: flex;
  height: 6px;
  width: 100%;
  margin-top: 0.4rem;
  background: var(--bg-tint);
  border-radius: 1px;
  overflow: hidden;
}
.hr-zone {
  height: 100%;
}
.hr-zone[data-z="0"] { background: rgba(232, 238, 245, 0.2); }
.hr-zone[data-z="1"] { background: var(--tier-c); }
.hr-zone[data-z="2"] { background: var(--accent-deep); }
.hr-zone[data-z="3"] { background: var(--accent); }
.hr-zone[data-z="4"] { background: var(--rune); }
.hr-zone[data-z="5"] { background: var(--warn); }
```

- [ ] **Step 3: Add renderWorkouts to main.js**

Edit `output/web/js/main.js`. At the import, change:

```js
import { VITALS } from './data-vitals.js';
```

to:

```js
import { VITALS, WORKOUTS } from './data-vitals.js';
```

Add the render function above `renderCrossRef`:

```js
function renderWorkouts() {
  const root = document.getElementById('workouts-list');
  if (!root) return;
  if (!WORKOUTS || WORKOUTS.length === 0) {
    root.innerHTML = '<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--fg-dim);">No workouts yet — drop a Garmin export in <code>data/raw/garmin/</code> and run <code>refresh.sh</code>.</p>';
    return;
  }
  const formatDate = ts => new Date(ts).toLocaleDateString('en-US', {month:'short', day:'numeric', year:'2-digit'});
  const formatDuration = s => {
    if (s == null) return '';
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  };
  const zoneBar = zones => {
    if (!zones) return '';
    const total = Object.values(zones).reduce((a, b) => a + b, 0) || 1;
    return '<div class="hr-zones">' + [0,1,2,3,4,5].map(z => {
      const v = zones[`zone_${z}`] || 0;
      return v > 0 ? `<div class="hr-zone" data-z="${z}" style="width:${(100 * v / total).toFixed(1)}%"></div>` : '';
    }).join('') + '</div>';
  };
  root.innerHTML = WORKOUTS.map(w => `
    <article class="workout-card">
      <div class="workout-date">${formatDate(w.ts_start)}</div>
      <div>
        <span class="workout-label">${w.label}</span>
        <span class="workout-sport">${w.sport || ''}</span>
        ${zoneBar(w.hr_zones)}
      </div>
      <div class="workout-stats">
        ${formatDuration(w.duration_s)} ·
        ${w.avg_hr ? Math.round(w.avg_hr) + ' bpm avg' : ''}
        ${w.training_load ? ` · TL ${Math.round(w.training_load)}` : ''}
      </div>
    </article>
  `).join('');
}
```

In the `DOMContentLoaded` handler, add `renderWorkouts();` after `renderVitals();`.

- [ ] **Step 4: Visual verify**

```bash
python3 -m http.server 8732 -d output/web &
sleep 1
curl -sI http://localhost:8732/ | head -1
kill %1
```

Open `http://localhost:8732/`, scroll to the new **Workouts** section. Confirm cards render with dates, labels, HR-zone bars, training load.

- [ ] **Step 5: Commit**

```bash
git add output/web/index.html output/web/js/main.js output/web/css/layout.css
git commit -m "Add Workouts dashboard panel with HR-zone bars"
```

---

## Task 5 — refresh.sh + final check

**Files:**
- Modify: `pipeline/refresh.sh` (no changes needed — events outdir is auto-derived)

- [ ] **Step 1: Re-run refresh end-to-end**

```bash
rm -f data/parquet/.last_refresh
bash pipeline/refresh.sh
```

Expected: HealthKit + Garmin (samples + events) + genome + cross_refs + vitals JS in <90s.

- [ ] **Step 2: Cross-source SQL — workouts vs sleep**

```bash
python3 <<'PY'
import duckdb
print("=== Recent workouts ⨝ sleep next-night ===")
rows = duckdb.query("""
SELECT
  date_trunc('day', e.ts_start::TIMESTAMP)::DATE AS workout_day,
  e.label,
  CAST(json_extract(e.meta, '$.training_load') AS DOUBLE) AS tl,
  s.sleep_min_next
FROM 'data/parquet/events/garmin-*.parquet' e
LEFT JOIN (
  SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d,
         sum(value) / 60.0 AS sleep_min_next
  FROM 'data/parquet/samples/*.parquet'
  WHERE source='garmin' AND type IN ('sleep_deep','sleep_light','sleep_rem')
  GROUP BY d
) s ON s.d = date_trunc('day', e.ts_start::TIMESTAMP)::DATE + 1
WHERE e.type = 'workout'
ORDER BY e.ts_start DESC LIMIT 8
""").fetchall()
for r in rows: print(' ', r)
PY
```

Expected: a list of recent workouts with the next night's sleep duration alongside. This is the kind of cross-source join the spine was built for.

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass, including new Garmin-activities tests.

- [ ] **Step 4: Final commit (if any tweaks)**

```bash
git status
# If nothing — done.
```

---

## Acceptance criteria

- [ ] `data/parquet/events/garmin-*.parquet` exists with ~972 rows for the user's bulk export.
- [ ] Dashboard `#workouts` section renders the most recent 90 activities with HR-zone bars.
- [ ] Cross-source query workouts ⨝ next-night sleep returns at least 8 valid rows.
- [ ] `pytest tests/` passes; ≥3 new tests added.
- [ ] CI still green on the synthetic data path (the test ZIP doesn't include activities, but that's fine — events_outdir is just empty).

## What this plan does NOT do

- **HR-time-series during a workout.** Only summary stats. The full per-second HR trace lives in `.fit` files, which Garmin's bulk export doesn't include — only the activity summaries.
- **GPS route rendering on a map.** `startLatitude`/`endLatitude` are present but no full polyline. Map polylines are deferred (would need `.fit` files or the Garmin Connect API).
- **Workout filters / search / pagination.** v1 just shows the last 90.
- **Personal-record (PR) badges, kudos, comparisons.** Future polish.
