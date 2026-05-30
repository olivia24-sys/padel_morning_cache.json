#!/usr/bin/env python3
"""Fetch Playtomic availability for all venues across the next 7 days."""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

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


def fetch_venue_day(tenant_id: str, date: str):
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
    now = datetime.now(timezone.utc)
    fetched_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now.date()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(7)]

    result = {
        "fetched_at": fetched_at,
        "date_range": {"start": dates[0], "end": dates[-1]},
        "venues": {},
    }

    for v in VENUES:
        venue_days = {}
        for date in dates:
            slots, err = fetch_venue_day(v["tenant_id"], date)
            venue_days[date] = {
                "fetch_status": "ok" if slots is not None else "error",
                "error": err,
                "slots": slots,
            }
            status = "ok" if slots is not None else f"error: {err}"
            print(f"  {v['id']:12s} {date}  {status}")
        result["venues"][v["id"]] = {
            "name": v["name"],
            "days": venue_days,
        }

    os.makedirs("data", exist_ok=True)
    out_path = "data/padel_morning_cache.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nfetched_at: {fetched_at}")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
