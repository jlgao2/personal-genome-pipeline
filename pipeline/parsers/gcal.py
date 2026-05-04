"""Google Calendar integration — OAuth (Installed-App flow) + read/write.

One-time setup (you do this once):
  1. https://console.cloud.google.com → create a project
  2. APIs & Services → enable "Google Calendar API"
  3. Credentials → "Create Credentials" → OAuth client ID → Desktop app
  4. Download the JSON → save to ~/.config/personal-data/google_credentials.json
  5. Run: python3 -m pipeline.parsers.gcal auth
     Browser opens → grant access → token cached to
     ~/.config/personal-data/google_token.json

After that, normal `refresh.sh` will read upcoming events automatically.

The token has a refresh_token so it self-renews without re-auth.
Personal data: tokens never leave your laptop, calendar events flow
into the spine via the same Parquet pipeline as everything else.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Optional

CREDS_DIR    = Path.home() / ".config" / "personal-data"
CREDS_PATH   = CREDS_DIR / "google_credentials.json"
TOKEN_PATH   = CREDS_DIR / "google_token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _build_service():
    """Return an authenticated Google Calendar service object, or None if
    credentials/tokens missing."""
    if not CREDS_PATH.exists():
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("Install: pip3 install google-auth google-auth-oauthlib google-api-python-client",
              file=sys.stderr)
        return None

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        CREDS_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
        os.chmod(TOKEN_PATH, 0o600)

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def auth_now() -> bool:
    """Force the OAuth flow (interactive). Idempotent thereafter."""
    svc = _build_service()
    if svc is None:
        print(f"Missing credentials at {CREDS_PATH}. See module docstring.", file=sys.stderr)
        return False
    print(f"Calendar OAuth complete. Token at {TOKEN_PATH}.")
    return True


def upcoming_events(days: int = 14, calendar_id: str = "primary") -> list[dict]:
    """Return the next N days of events in a compact dict shape suitable for
    the dashboard bundle. Fails silently with [] if not authed."""
    svc = _build_service()
    if svc is None:
        return []
    now = _dt.datetime.utcnow().isoformat() + "Z"
    end = (_dt.datetime.utcnow() + _dt.timedelta(days=days)).isoformat() + "Z"
    try:
        resp = svc.events().list(
            calendarId=calendar_id,
            timeMin=now,
            timeMax=end,
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        ).execute()
    except Exception as e:
        print(f"gcal list failed: {e}", file=sys.stderr)
        return []
    rows = []
    for e in resp.get("items", []):
        start = (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date")
        end_t = (e.get("end")   or {}).get("dateTime") or (e.get("end")   or {}).get("date")
        rows.append({
            "id":       e.get("id"),
            "summary":  e.get("summary") or "(no title)",
            "start":    start,
            "end":      end_t,
            "all_day":  bool((e.get("start") or {}).get("date")),
            "location": e.get("location"),
            "url":      e.get("htmlLink"),
        })
    return rows


_TAG = "personal-data-pipeline:v1"


def _existing_tagged_ids(svc, calendar_id: str = "primary") -> set[str]:
    """Find events we've previously created (by extendedProperties.private.tag)."""
    out: set[str] = set()
    try:
        page = None
        while True:
            req = svc.events().list(
                calendarId=calendar_id,
                privateExtendedProperty=f"tag={_TAG}",
                pageToken=page,
                singleEvents=True,
                maxResults=250,
            ).execute()
            for e in req.get("items", []):
                # Match by external id stored in our private extended property.
                eid = (e.get("extendedProperties", {}).get("private", {}) or {}).get("ext_id")
                if eid:
                    out.add(eid)
            page = req.get("nextPageToken")
            if not page:
                break
    except Exception as e:
        print(f"gcal list (tagged) failed: {e}", file=sys.stderr)
    return out


def upsert_birthdays(birthdays: list[dict],
                     calendar_id: str = "primary") -> int:
    """Idempotently create all-day birthday events on the user's calendar.
    Each event is tagged with our pipeline marker so we don't duplicate.
    Returns the number of events created."""
    svc = _build_service()
    if svc is None:
        return 0
    existing = _existing_tagged_ids(svc, calendar_id)
    n_created = 0
    today = _dt.date.today()
    for b in birthdays:
        m, d = b.get("month"), b.get("day")
        if not (m and d):
            continue
        # Determine this year's date — if past, use next year.
        try:
            this_year = _dt.date(today.year, m, d)
            target = this_year if this_year >= today else _dt.date(today.year + 1, m, d)
        except ValueError:
            continue
        ext_id = f"birthday:{b.get('id')}:{target.isoformat()}"
        if ext_id in existing:
            continue
        body = {
            "summary": f"🎂 {b.get('name') or 'Friend'}",
            "start":   {"date": target.isoformat()},
            "end":     {"date": (target + _dt.timedelta(days=1)).isoformat()},
            "description": "Reminder from personal-data-pipeline · social-media-graph",
            "extendedProperties": {"private": {"tag": _TAG, "ext_id": ext_id}},
            "transparency": "transparent",
        }
        try:
            svc.events().insert(calendarId=calendar_id, body=body).execute()
            n_created += 1
        except Exception as e:
            print(f"insert failed for {b.get('name')}: {e}", file=sys.stderr)
    return n_created


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Google Calendar OAuth + sync.")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("auth", help="Run/refresh the OAuth flow.")

    p_list = sub.add_parser("list", help="Print upcoming events.")
    p_list.add_argument("--days", type=int, default=14)

    p_sync = sub.add_parser("sync-birthdays",
                            help="Create birthday events from social-media-graph.")
    p_sync.add_argument("--bundle", type=Path,
                        default=Path("output/ios_export/ios_bundle.json"))

    args = ap.parse_args()
    if args.cmd == "auth":
        auth_now()
    elif args.cmd == "list":
        rows = upcoming_events(days=args.days)
        for r in rows:
            print(f"  {r['start'][:10]:10s}  {r['summary'][:60]}")
        print(f"--- {len(rows)} events in next {args.days} days")
    elif args.cmd == "sync-birthdays":
        if not args.bundle.exists():
            print(f"Run refresh.sh first to produce {args.bundle}", file=sys.stderr)
            sys.exit(1)
        bundle = json.loads(args.bundle.read_text())
        bdays = (bundle.get("social") or {}).get("birthdays") or []
        n = upsert_birthdays(bdays)
        print(f"Created {n} new birthday events ({len(bdays)} candidates).")
    else:
        ap.print_help()


if __name__ == "__main__":
    _cli()
