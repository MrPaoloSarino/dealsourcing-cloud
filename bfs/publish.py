"""Merge a scrape run into a published data file (one per source).

Defaults are BusinessesForSale: out/bfs_listings.csv -> docs/data/bfs.json.
Other sources pass their own paths, e.g. Tupelo:
    python bfs/publish.py out_tupelo/listings.csv --data docs/data/tupelo.json \
        --prefix https://www.tupelosmb.com/marketplace/listings/ --label Tupelo

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
          "cash_flow", "ebitda", "first_seen", "last_seen", "teaser", "category"]

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


CODES = set(STATES.values())


def state_of(location: str) -> str:
    parts = [p.strip() for p in (location or "").split(",") if p.strip()]
    for p in reversed(parts):
        code = STATES.get(p.lower()) or (p.upper() if p.upper() in CODES and len(p) == 2 else None)
        if code:
            return code
    return ""


def to_int(v: str):
    try:
        return int(float(v)) if v not in ("", None) else None
    except ValueError:
        return None


def teaser_of(row: dict) -> str:
    """M&A Vault cards carry no dollar figures; keep their one-line pitch instead.
    Sources with a short description on every card (Tupelo) keep it for all rows."""
    if row.get("source") == "Tupelo":
        return " ".join((row.get("card_text") or "").split())[:240]
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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("run_csv", nargs="?", default="out/bfs_listings.csv")
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--prefix", default=PREFIX)
    ap.add_argument("--label", default="BusinessesForSale.com (US)")
    a = ap.parse_args()
    run_csv, data_path, prefix = a.run_csv, a.data, a.prefix
    run_dir = os.path.dirname(run_csv)
    run_json = next((os.path.join(run_dir, n) for n in ("bfs_run.json", "run.json")
                     if os.path.exists(os.path.join(run_dir, n))), os.path.join(run_dir, "run.json"))
    today = date.today().isoformat()

    existing: dict[str, dict] = {}
    meta = {}
    if os.path.exists(data_path):
        with open(data_path, encoding="utf-8") as f:
            blob = json.load(f)
        meta = blob.get("meta", {})
        for r in blob.get("rows", []):
            rec = {k: None for k in FIELDS}
            rec.update(dict(zip(blob["fields"], r)))
            existing[rec["path"]] = rec

    with open(run_csv, encoding="utf-8") as f:
        scraped = list(csv.DictReader(f))
    run = json.load(open(run_json, encoding="utf-8")) if os.path.exists(run_json) else {}

    added = 0
    for row in scraped:
        path = row["url"].replace(prefix, "")
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
            "category": (row.get("category") or "").strip(),
        }
        if not prev:
            added += 1
        existing[path] = rec

    cutoff = (date.today() - timedelta(days=DROP_AFTER_DAYS)).isoformat()
    # Order = the site's own order (newest first): listings from this run in the order the
    # site showed them, then everything else in its previous order. The screen uses this
    # order to break ties, so "Newest first" matches the site.
    run_paths = [row["url"].replace(prefix, "") for row in scraped]
    seen_now = set(run_paths)
    ordered = [existing[p] for p in dict.fromkeys(run_paths)] + \
              [r for p, r in existing.items() if p not in seen_now]
    kept = [r for r in ordered if r["last_seen"] >= cutoff]
    dropped = len(existing) - len(kept)
    kept.sort(key=lambda r: r["first_seen"], reverse=True)   # stable: keeps site order within a day

    full = len(run.get("pages", [])) > 100
    # Everything in the very first crawl is "already on the market", not new.
    meta.setdefault("baseline_date", today)
    meta.update({
        "source": a.label,
        "base": prefix,
        "updated_utc": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "site_total": run.get("site_total") or meta.get("site_total"),
        "tracked": len(kept),
        "last_run_pages": len(run.get("pages", [])),
        "last_run_new": added,
        "last_run_dropped": dropped,
    })
    if full:
        meta["last_full_crawl_utc"] = meta["updated_utc"]

    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "fields": FIELDS,
                   "rows": [[r[k] for k in FIELDS] for r in kept]},
                  f, separators=(",", ":"), ensure_ascii=False)
    print(f"published {len(kept)} listings ({added} new, {dropped} dropped) -> {data_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
