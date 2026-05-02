# Unified Personal Data Architecture

> Design doc · 2026-05-01
> Brainstormed via `superpowers:brainstorming`
> Status: approved by user, ready for implementation planning

## Context

The `personal-genome-pipeline` repo currently turns one input (a 23andMe v5 raw genotype) into one output (an interactive dashboard). This works, but the user wants to extend it into a **holistic personal-data system** that:

1. Maximizes the value of the genome data already in hand.
2. Ingests other longitudinal sources (Apple HealthKit XML, Garmin Connect bulk export, derived signals from the user's separate `social-media-graph` repo).
3. Self-iterates — new data drops in, dashboard regenerates.
4. Stays exportable / forkable so other people can run it on their own data.
5. Optionally surfaces correlations between physiological state and social/mental signals.

A 24 MB Apple Health export is already on disk (`data/raw/healthkit/export.zip`). Garmin bulk export is pending request. The `social-media-graph` repo already produces analytical outputs and is local-only.

This spec defines the architecture once. Each subsystem then gets its own design+plan cycle. Tonight we are NOT designing per-subsystem visuals or data formats beyond the shared schema — those happen in follow-up brainstorms.

## Decisions made during brainstorm

| # | Decision | Rationale |
|---|---|---|
| 1 | High-level architecture first, drill into one subsystem at a time after | Avoids designing in the abstract; each subsystem benefits from concrete predecessor patterns |
| 2 | **Parquet + DuckDB** as the unified data spine (not SQLite, not plain JSON) | Better at multi-GB time-series, columnar, lingua franca for analytics, anyone can `duckdb 'select … from "file.parquet"'` without setup |
| 3 | Social/mental linkage uses **derived signals only** — no raw contact data crosses into the genome dashboard | Genome dashboard is for self-state vs. self-genotype, not a CRM. Raw contact-level work stays inside `social-media-graph`'s own UI |
| 4 | Iteration model: **manual `refresh.sh` locally + GitHub Actions CI on synthetic-only public template** | Manual matches the actual cadence (HealthKit export every few weeks); CI catches parser regressions without exposing personal data |
| 5 | One repo, not split. `data/` gitignored. Public `docs/` keeps Eunjung Kim synthetic demo | Already proven model; extends cleanly to all five subsystems |
| 6 | Future work: `fswatch`-driven live refresh (option B). User wants to be prompted to revisit once 2+ parsers are running for a few weeks | Avoids over-engineering the iteration model before we feel its friction |

## The unifying spine

DuckDB-backed Parquet store. All five subsystems are **parsers** that emit Parquet files; all views (dashboard, future PDF, future iOS app) are **readers** that query via DuckDB SQL.

### Directory layout

```
data/
  raw/                              # gitignored — original exports
    healthkit/export.xml
    garmin/{wellness,activities,sleep}/
    social/                          # aggregate exports from social-media-graph
    genome/                          # 23andMe zip, imputed VCF
    labs/                            # clinical lab PDFs/CSVs
  parquet/                          # gitignored — normalized store
    samples/                         # partitioned by source
      healthkit-{yyyy-mm}.parquet
      garmin-{yyyy-mm}.parquet
      social-{yyyy-mm}.parquet
      lab-{yyyy-mm}.parquet
    events/
      workouts-{yyyy-mm}.parquet
      conversations-{yyyy-mm}.parquet
    findings.parquet                 # mostly static — current data.js content
    cross_refs.parquet               # genotype ↔ measurement pairings
```

### Schema

Intentionally flat and source-tagged so adding a new wearable / lab / source = writing a parser, no schema migration.

```sql
samples(
  ts          TIMESTAMP,
  source      VARCHAR,    -- 'healthkit' | 'garmin' | 'social' | 'lab' | 'genome'
  type        VARCHAR,    -- 'heart_rate_resting' | 'sleep_duration' | 'social_volume_per_day' | …
  value       DOUBLE,
  unit        VARCHAR,    -- 'bpm' | 'minutes' | 'count' | 'mg/dL' | …
  meta        JSON        -- arbitrary source-specific extras (e.g., GPX route geometry)
)

events(
  ts_start    TIMESTAMP,
  ts_end      TIMESTAMP,
  source      VARCHAR,
  type        VARCHAR,    -- 'workout' | 'conversation' | 'lab_visit' | 'supplement_change' | …
  label       VARCHAR,
  meta        JSON
)

findings(
  id          VARCHAR,    -- e.g., 'cyp2c19'
  gene        VARCHAR,
  rsid        VARCHAR,
  genotype    VARCHAR,
  tier        VARCHAR,    -- 'A' | 'B' | 'C'
  summary     VARCHAR,
  meta        JSON
)

cross_refs(
  finding_id          VARCHAR,
  sample_type         VARCHAR,    -- which sample type this finding predicts
  expected_direction  VARCHAR,    -- 'increase' | 'decrease' | 'stable'
  target_value        DOUBLE,     -- what to aim for
  takeaway            VARCHAR
)
```

### Three properties this gives us

1. **Time-aware joins are trivial.** "Show HRV alongside isolation_streak" is one SQL query; the dashboard just reads the result.
2. **Sources are independent.** Garmin can land before or after HealthKit; the dashboard never breaks.
3. **Anyone can fork & run.** Drop their own raw exports, run the parsers, get their own Parquet — same downstream views work unchanged.

## Sub-systems

### 1 · Genome (already built)

- **Parser**: existing scripts in `pipeline/01-12_*.py`. Refactor to write `findings.parquet` + `cross_refs.parquet` instead of the current TSV+hand-curated `data.js`.
- **View**: existing dashboard sections (Drugs, Cardio, Carrier, Nutrition, Lifestyle, PRS, X-ref, Reassuring, Limits). Unchanged behaviorally.
- **Effort**: small — refactor only.

### 2 · HealthKit longitudinal

- **Parser** `parse_healthkit.py`:
  - Stream-parses `export.xml` with `xml.etree.iterparse` (must — 427 MB is too big for DOM).
  - Maps Apple's record types to our normalized vocabulary (`HKQuantityTypeIdentifierHeartRate` → `heart_rate`, `HKCategoryTypeIdentifierSleepAnalysis` → `sleep_stage`, etc.).
  - Writes `samples/healthkit-{yyyy-mm}.parquet`.
  - Workout routes (GPX files in zip) become `events` of type `workout` with `route_geometry` in `meta`.
- **View**: new "Vitals" dashboard section.
  - Line charts: resting HR trend, VO2max trajectory, sleep duration consistency, weight, BP.
  - Each chart annotated with genotype-driven targets: 9p21 → BP <120/80 overlay; APOE ε4 → ≥7h sleep band; FADS1 → omega-3 status; etc.
- **Cross-refs**: predicted-vs-actual cards alongside existing genetic-clinical correlations.
- **Effort**: medium — main next implementation target.

### 3 · Garmin (when bulk-export arrives)

- **Parser** `parse_garmin.py`:
  - Walks the bulk-export ZIP.
  - `fitparse` for `.fit` activities → `events`.
  - JSON wellness/sleep/HRV → `samples` with `source='garmin'`.
- **View**: integrates into the same Vitals section.
  - Where overlaps with HealthKit exist (HR, sleep), prefer Garmin (higher resolution); HealthKit becomes fallback.
  - Confidence indicator on each chart shows which source is being plotted.
  - Cross-source agreement raises confidence; disagreement flags amber.
- **Effort**: medium — gated on the user receiving the bulk-export email (24-48h after request).

### 4 · Social/mental linkage (derived only)

- **Parser** `parse_social.py`:
  - Lightweight wrapper. Reads aggregate exports produced by the existing `social-media-graph` repo (the user adds a new export step to that repo separately).
  - Aggregates flow as `samples`: `social_volume_per_day`, `contact_diversity_index`, `isolation_streak_days`, `avg_message_sentiment`.
  - Raw contact data **never enters** the genome pipeline's Parquet store.
- **View**: new "Social Vitals" panel in the dashboard.
  - Mini-time-series of the four aggregate signals.
  - Auto-detected correlations card: e.g., "HRV drops correlate with isolation_streak ≥ 3 days (r = −0.42 over last 90d)".
- **Effort**: small once the social-media-graph repo exposes its aggregates. The cross-correlation surfacing is the interesting code.

### 5 · Self-iteration & exportable framework

Two operational components:

- **`refresh.sh`** orchestrator:
  - Detects which raw inputs changed since last run (`mtime` vs. `data/parquet/.last_refresh`).
  - Runs only the relevant parsers; each parser is idempotent (`DELETE WHERE source=X partition=Y` then re-INSERT).
  - Regenerates `docs/web/js/data.js` (or the private rendered dashboard in `output/`) by running DuckDB queries via `build_dashboard.py`.
  - Writes a snapshot timestamp to a `refresh_log` table; dashboard footer shows "last updated: 3 hours ago".
- **GitHub Actions CI**:
  - Runs `refresh.sh --demo` on synthetic data (`docs/data/parquet-demo/`) nightly.
  - Fails build if any parser regresses or the demo dashboard fails to render.
  - Personal data never reaches CI.
- **Bring-Your-Own-Data convention**:
  - `data/raw/<source>/` directory naming matches parser names.
  - README documents which sources are supported and what file structure each parser expects.
  - Each parser is a standalone Python module with a clear `parse(input_path) -> Iterator[Sample | Event]` signature so people can contribute new ones (Oura, Whoop, Levels CGM) via PR.

## What this spec does NOT design

These are deferred to follow-up brainstorms:

1. **Visual design of "Vitals" and "Social Vitals" dashboard sections.** Will use the visual companion when we get there — UI-shaped questions benefit from mockups.
2. **The exact aggregation logic for social signals.** Belongs in `social-media-graph` repo's own design cycle. We import whatever it exports.
3. **Live API ingestion** (Garmin Connect API polling, Apple Shortcuts → webhook). Only in scope after the manual file-drop workflow is solid for a few weeks.
4. **The fswatch-driven live refresh** (iteration option B). User asked to be prompted to revisit after the manual model has settled.
5. **Lab data parser.** Likely a small `parse_labs.py` that ingests CSV exports (LabCorp / Quest / clinical PDFs after OCR). Important but not blocking.

## Implementation order

1. **Sub-1 refactor (genome → Parquet)** — small, derisks the spine.
2. **Sub-2 (HealthKit)** — biggest concrete value tonight. Data is already on disk.
3. **Sub-5 operational layer** — `refresh.sh` + CI. Easier to write once you've felt the friction of running parsers manually.
4. **Sub-4 (social linkage)** — gated on the user adding an aggregate-export step to `social-media-graph`.
5. **Sub-3 (Garmin)** — gated on receiving the bulk-export email.

Each step gets its own brainstorm → writing-plans → executing-plans cycle. Tonight, the next concrete step is the writing-plans pass for **Sub-2 (HealthKit)** since the data is on disk and Sub-1 refactor is conceptually trivial.

## Acceptance criteria for the architecture as a whole

The architecture is "done" when:

- [ ] All five subsystems have parsers that read from `data/raw/<source>/` and write to `data/parquet/`.
- [ ] `bash refresh.sh` regenerates the dashboard in <60 seconds for a typical data load (one Apple Health export + one Garmin export + last month of social aggregates).
- [ ] CI on the public template passes nightly without intervention for 30+ days.
- [ ] A friend can fork the repo, drop their own 23andMe + HealthKit exports, run `refresh.sh`, and see their own dashboard.
- [ ] No personal data has ever entered the public repo's git history.
