#!/usr/bin/env python3
"""Fetch Playtomic padel availability for the next 7 days for configured venues."""

import json
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
VENUES_FILE = BASE_DIR / "config" / "venues.json"
OUTPUT_FILE = BASE_DIR / "data" / "padel_morning_cache.json"

PLAYTOMIC_API = "https://playtomic.io/api/v1"
SPORT_ID = "PADEL"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def api_get(path: str, params: dict) -> list | dict:
    url = f"{PLAYTOMIC_API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def resolve_tenant_id(slug: str, name: str) -> tuple[str | None, str | None]:
    """Try to resolve a Playtomic tenant ID from the club URL slug.
    Returns (tenant_id, error_message).
    """
    last_err = None
    for search_term in [slug, name]:
        try:
            results = api_get("tenants", {
                "user_id": "me",
                "tenant_name": search_term,
                "playtomic_status": "ACTIVE",
                "with_properties": "SPORT",
                "size": 10,
            })
            for r in results:
                r_slug = (r.get("slug") or "").lower()
                r_name = (r.get("tenant_name") or "").lower()
                if slug.lower() in r_slug or slug.lower() in r_name:
                    return r["tenant_id"], None
            if len(results) == 1:
                return results[0]["tenant_id"], None
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read(256).decode("utf-8", errors="replace")
            except Exception:
                pass
            last_err = f"http_{exc.code}: {body.strip()}" if body else f"http_{exc.code}"
        except urllib.error.URLError as exc:
            last_err = f"url_error: {exc.reason}"
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
    return None, last_err or "no_results"


def fetch_availability(tenant_id: str, date_str: str) -> list:
    """Return available slots for a tenant on a given date (YYYY-MM-DD)."""
    return api_get("availability", {
        "user_id": "me",
        "tenant_id": tenant_id,
        "sport_id": SPORT_ID,
        "local_start_min": f"{date_str}T00:00:00",
        "local_start_max": f"{date_str}T23:59:59",
    })


def main():
    fetched_at = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).date()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(7)]

    with open(VENUES_FILE) as f:
        config = json.load(f)

    results = []
    for venue in config["venues"]:
        name = venue["name"]
        url = venue["url"]
        slug = url.rstrip("/").split("/")[-1]

        venue_result = {
            "name": name,
            "url": url,
            "slug": slug,
            "tenant_id": None,
            "availability": {},
            "error": None,
        }

        print(f"Resolving tenant ID for {name} ({slug})…", file=sys.stderr)
        tenant_id, err = resolve_tenant_id(slug, name)

        if not tenant_id:
            venue_result["error"] = f"tenant_lookup_failed: {err}"
            results.append(venue_result)
            print(f"  ERROR: {err}", file=sys.stderr)
            continue

        venue_result["tenant_id"] = tenant_id
        print(f"  tenant_id={tenant_id}", file=sys.stderr)

        for date in dates:
            print(f"  Fetching {date}…", file=sys.stderr)
            try:
                slots = fetch_availability(tenant_id, date)
                venue_result["availability"][date] = slots
            except urllib.error.HTTPError as exc:
                venue_result["availability"][date] = {"error": f"http_{exc.code}"}
            except Exception as exc:
                venue_result["availability"][date] = {"error": str(exc)}

        results.append(venue_result)

    output = {
        "fetched_at": fetched_at,
        "sport": SPORT_ID,
        "dates": dates,
        "venues": results,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved → {OUTPUT_FILE}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
