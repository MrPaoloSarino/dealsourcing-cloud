"""Merge a scrape run (out/bfs_listings.csv) into the published data file docs/data/bfs.json.

Tracks first_seen / last_seen per listing so the screen can show what's new,
and drops listings nobody has seen for DROP_AFTER_DAYS (sold or delisted).

Compact format (keeps the file small for the browser):
    {"meta": {...}, "fields": [...], "rows": [[...], ...]}
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

PREFIX = "https://us.businessesforsale.com/us/"
DATA = os.path.join("docs", "data", "bfs.json")
DROP_AFTER_DAYS = 21
FIELDS = ["path", "title", "kind", "location", "state", "price", "revenue",
          "cash_flow", "ebitda", "first_seen", "last_seen", "teaser"]

STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "puerto rico": "PR",
}


def state_of(location: str) -> str:
    parts = [p.strip() for p in (location or "").split(",") if p.strip()]
    for p in reversed(parts):
        code = STATES.get(p.lower())
        if code:
            return code
    return ""


def to_int(v: str):
    try:
        return int(float(v)) if v not in ("", None) else None
    except ValueError:
        return None


def teaser_of(row: dict) -> str:
    """M&A Vault cards carry no dollar figures; keep their one-line pitch instead."""
    if row.get("kind") != "mna_vault":
        return ""
    text = row.get("card_text", "")
    title = row.get("title", "")
    if text.startswith(title):
        text = text[len(title):]
    for cut in ("More details", "Learn more"):
        text = text.split(cut)[0]
    return text.replace("United States", "").replace("High Value", "").strip()[:220]


def main() -> int:
    run_csv = sys.argv[1] if len(sys.argv) > 1 else "out/bfs_listings.csv"
    run_json = os.path.join(os.path.dirname(run_csv), "bfs_run.json")
    today = date.today().isoformat()

    existing: dict[str, dict] = {}
    meta = {}
    if os.path.exists(DATA):
        with open(DATA, encoding="utf-8") as f:
            blob = json.load(f)
        meta = blob.get("meta", {})
        for r in blob.get("rows", []):
            rec = dict(zip(blob["fields"], r))
            existing[rec["path"]] = rec

    with open(run_csv, encoding="utf-8") as f:
        scraped = list(csv.DictReader(f))
    run = json.load(open(run_json, encoding="utf-8")) if os.path.exists(run_json) else {}

    added = 0
    for row in scraped:
        path = row["url"].replace(PREFIX, "")
        prev = existing.get(path)
        rec = {
            "path": path,
            "title": row["title"],
            "kind": 1 if row["kind"] == "mna_vault" else 0,
            "location": row["location"],
            "state": state_of(row["location"]),
            "price": to_int(row["asking_price"]),
            "revenue": to_int(row["revenue"]),
            "cash_flow": to_int(row["cash_flow"]),
            "ebitda": to_int(row["ebitda"]),
            "first_seen": prev["first_seen"] if prev else today,
            "last_seen": today,
            "teaser": teaser_of(row),
        }
        if not prev:
            added += 1
        existing[path] = rec

    cutoff = (date.today() - timedelta(days=DROP_AFTER_DAYS)).isoformat()
    kept = [r for r in existing.values() if r["last_seen"] >= cutoff]
    dropped = len(existing) - len(kept)
    kept.sort(key=lambda r: (r["first_seen"], r["last_seen"]), reverse=True)

    full = len(run.get("pages", [])) > 100
    # Everything in the very first crawl is "already on the market", not new.
    meta.setdefault("baseline_date", today)
    meta.update({
        "source": "BusinessesForSale.com (US)",
        "updated_utc": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "site_total": run.get("site_total") or meta.get("site_total"),
        "tracked": len(kept),
        "last_run_pages": len(run.get("pages", [])),
        "last_run_new": added,
        "last_run_dropped": dropped,
    })
    if full:
        meta["last_full_crawl_utc"] = meta["updated_utc"]

    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "fields": FIELDS,
                   "rows": [[r[k] for k in FIELDS] for r in kept]},
                  f, separators=(",", ":"), ensure_ascii=False)
    print(f"published {len(kept)} listings ({added} new, {dropped} dropped) -> {DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
