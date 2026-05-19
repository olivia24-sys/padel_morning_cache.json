#!/usr/bin/env python3
"""
Fetch today's Playtomic availability for all 6 padel venues.

Usage: python3 fetch_padel.py <label>
  label — human-readable snapshot label, e.g. "06:50 snapshot"

Output:
  Writes data/snapshots/YYYY-MM-DD_HHMM.json  (this snapshot)
  Writes data/padel_morning_cache.json          (latest, overwritten each run)

JSON format (keyed by venue ID so the dashboard can look up directly):
{
  "fetched_at": "2026-05-19T06:52:11Z",
  "label": "06:50 snapshot",
  "date":  "2026-05-19",
  "venues": {
    "corsham": {
      "name": "Padel People — Corsham",
      "fetch_status": "ok" | "error",
      "error": null | "<message>",
      "slots": [ ...raw Playtomic availability array... ] | null
    },
    ...
  }
}

The "slots" array is the raw response from:
  GET api.playtomic.io/v1/availability?tenant_id=...&sport_id=PADEL&...
Each element: { resource_id, start_date, slots: [{start_time, duration, price}] }
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

VENUES = [
    {"id": "corsham",     "name": "Padel People — Corsham",        "tenant_id": "2d7685dc-cbb2-40ae-8fb9-13d4e73b2e00"},
    {"id": "boston",      "name": "Padel People — Boston",         "tenant_id": "ae1d9547-c095-4932-8a0a-2c097946cae9"},
    {"id": "basingstoke", "name": "Padel People — Basingstoke",    "tenant_id": "ec4aa02a-15a6-4dad-b49b-dd75178f2eec"},
    {"id": "shepton",     "name": "Padel People — Shepton Mallet", "tenant_id": "18d99acc-7bad-46c8-a52f-2ac911db3854"},
    {"id": "atc",         "name": "ATC Padel — Andover",           "tenant_id": "4feb9af7-79ce-4a44-b34e-f1b20336abac"},
    {"id": "worldham",    "name": "Worldham Padel — Alton",        "tenant_id": "e6ec5602-4b8e-4758-99b6-b16b119ae894"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; padel-cache-bot/1.0)",
    "Accept": "application/json",
}


def fetch_venue(tenant_id: str, date: str):
    """Returns the raw API array, or None on failure."""
    url = (
        f"https://api.playtomic.io/v1/availability"
        f"?tenant_id={tenant_id}&sport_id=PADEL"
        f"&start_min={date}T00:00:00&start_max={date}T23:59:59"
    )
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return None, f"Network error: {e.reason}"
    except Exception as e:
        return None, str(e)


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "manual fetch"

    now       = datetime.now(timezone.utc)
    date      = now.strftime("%Y-%m-%d")
    hhmm      = now.strftime("%H%M")
    fetched_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    result = {
        "fetched_at": fetched_at,
        "label":      label,
        "date":       date,
        "venues":     {},
    }

    ok_count = 0
    for v in VENUES:
        slots, err = fetch_venue(v["tenant_id"], date)
        if slots is not None:
            ok_count += 1
        result["venues"][v["id"]] = {
            "name":         v["name"],
            "fetch_status": "ok" if slots is not None else "error",
            "error":        err,
            "slots":        slots,
        }
        status = "ok" if slots is not None else f"error: {err}"
        print(f"  {v['id']:12s} {status}")

    print(f"\nFetched {ok_count}/{len(VENUES)} venues for {date} at {fetched_at}")

    # Write snapshot file
    os.makedirs("data/snapshots", exist_ok=True)
    snapshot_path = f"data/snapshots/{date}_{hhmm}.json"
    with open(snapshot_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Written: {snapshot_path}")

    # Overwrite latest
    latest_path = "data/padel_morning_cache.json"
    with open(latest_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Updated: {latest_path}")


if __name__ == "__main__":
    main()
