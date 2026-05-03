"""Ingest aggregate exports from the social-media-graph repo.

The neighboring repo (~/Social Media Graph/) produces:
  pipeline/output/checkins.json — top N people with attention_score,
                                  days_since_last, birthday, etc.
  pipeline/output/timeline.json — events list (first_contact, anchor,
                                  last_contact, birthday)

We ingest these into our spine without crossing the privacy boundary —
canonical IDs only, never raw chat content beyond the curated excerpts
the source repo already chose to expose.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

import pyarrow as pa
import pyarrow.parquet as pq


def load_checkins(checkins_path: Path) -> Optional[dict]:
    """Return the parsed checkins.json or None if not present."""
    if not checkins_path.exists():
        return None
    return json.loads(checkins_path.read_text())


def build_social_summary(checkins_path: Path, top_n: int = 12) -> Optional[dict]:
    """Return a compact summary suitable for the dashboard bundle.
    Includes top-N reach-out list and upcoming birthdays.
    """
    data = load_checkins(checkins_path)
    if not data:
        return None
    people = data.get("people") or []
    # Top by attention_score (already sorted in source, but enforce).
    reach_out = sorted(people, key=lambda p: -(p.get("attention_score") or 0))[:top_n]

    # Upcoming birthdays (next 60 days).
    birthdays = [p for p in people
                 if p.get("days_until_birthday") is not None
                 and p["days_until_birthday"] <= 60]
    birthdays.sort(key=lambda p: p["days_until_birthday"])

    return {
        "generated":   data.get("generated"),
        "today":       data.get("today"),
        "total_people": data.get("count"),
        "reach_out":   [_compact_person(p) for p in reach_out],
        "birthdays":   [_compact_birthday(p) for p in birthdays],
    }


def _compact_person(p: dict) -> dict:
    """Trim a person dict to the keys the dashboard renders."""
    return {
        "id":              p.get("canonical_id"),
        "name":            p.get("display_name"),
        "attention_score": p.get("attention_score"),
        "days_since_last": p.get("days_since_last"),
        "last_msg_from":   p.get("last_msg_from"),
        "last_excerpt":    p.get("last_msg_excerpt"),
        "about_what":      p.get("about_what"),
        "sources":         p.get("sources"),
        "msg_count":       p.get("msg_count"),
        "has_portrait":    p.get("has_portrait"),
    }


def _compact_birthday(p: dict) -> dict:
    bd = p.get("birthday") or {}
    return {
        "id":           p.get("canonical_id"),
        "name":         p.get("display_name"),
        "month":        bd.get("month"),
        "day":          bd.get("day"),
        "days_until":   p.get("days_until_birthday"),
        "year_known":   bd.get("year_known"),
    }


def parse_timeline_to_parquet(timeline_path: Path, outdir: Path) -> int:
    """Parse timeline.json into events.parquet rows.

    Each entry becomes an event with type ∈ {checkin_first, checkin_last,
    checkin_anchor, birthday}, source='social', label=person name.
    Idempotent: clears existing social-*.parquet first.
    """
    if not timeline_path.exists():
        return 0
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("social-*.parquet"):
        old.unlink()

    data = json.loads(timeline_path.read_text())
    entries = data.get("entries") or []
    if not entries:
        return 0

    by_partition: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        date = e.get("date")
        if not date:
            continue
        kind = e.get("kind") or "anchor"
        ts = f"{date}T12:00:00+00:00"
        meta = {
            "canonical_id": e.get("canonical_id"),
            "person":       e.get("person"),
            "summary":      e.get("summary"),
            "kind":         kind,
            "source":       e.get("source"),
        }
        row = {
            "ts_start": ts,
            "ts_end":   ts,
            "source":   "social",
            "type":     f"checkin_{kind}" if kind != "birthday" else "birthday",
            "label":    e.get("person") or "—",
            "meta":     json.dumps(meta),
        }
        by_partition[date[:7]].append(row)

    schema = pa.schema([
        ("ts_start", pa.string()),
        ("ts_end",   pa.string()),
        ("source",   pa.string()),
        ("type",     pa.string()),
        ("label",    pa.string()),
        ("meta",     pa.string()),
    ])
    n_total = 0
    for partition, rows in by_partition.items():
        table = pa.Table.from_pylist(rows, schema=schema)
        pq.write_table(table, outdir / f"social-{partition}.parquet")
        n_total += len(rows)
    return n_total


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Ingest social-media-graph exports.")
    ap.add_argument("--checkins", type=Path,
                    default=Path("/Users/georgegao/Social Media Graph/pipeline/output/checkins.json"))
    ap.add_argument("--timeline", type=Path,
                    default=Path("/Users/georgegao/Social Media Graph/pipeline/output/timeline.json"))
    ap.add_argument("--events-outdir", type=Path,
                    default=Path("data/parquet/events"))
    ap.add_argument("--summary-out", type=Path,
                    default=Path("data/parquet/social_summary.json"))
    args = ap.parse_args()

    n = parse_timeline_to_parquet(args.timeline, args.events_outdir)
    summary = build_social_summary(args.checkins)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    if summary:
        args.summary_out.write_text(json.dumps(summary, indent=2))
        print(f"Wrote {args.summary_out} (top {len(summary['reach_out'])} reach-out, "
              f"{len(summary['birthdays'])} upcoming birthdays)")
    print(f"Wrote {n:,} timeline events to {args.events_outdir}/social-*.parquet")


if __name__ == "__main__":
    _cli()
