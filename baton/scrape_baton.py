"""Baton (baton.com) marketplace scraper — plain HTTP, no browser.

robots.txt allows everything. Baton's pages are server-rendered (Remix) and carry the
listing data as JSON in `window.__remixContext`, so no HTML layout parsing is needed.

How it walks the site:
  1. /market/sitemap.xml lists every listing URL and every state page
     (/market/businesses-for-sale/category/businesses-in-<state>).
  2. Each state page (?page=1, 2, …; 14 listings each) holds full listing records:
     name, asking price, adjusted cash flow, gross revenue, city/state, industries, status.
  3. Listings in the sitemap that no state page showed are opened one by one
     (up to --max-details per run) to read the same fields from the listing page.

Writes the same CSV columns as the other scrapers so bfs/publish.py can merge it:
    out_baton/listings.csv, out_baton/run.json
Usage:
    python baton/scrape_baton.py              # full crawl (~130 pages, ~8 min)
    python baton/scrape_baton.py --states 3   # quick test: first 3 states only
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    from curl_cffi import requests as http
    IMPERSONATE = {"impersonate": "chrome"}
except ImportError:  # pragma: no cover
    import requests as http
    IMPERSONATE = {}

BASE = "https://www.baton.com/market/businesses-for-sale/"
SITEMAP = "https://www.baton.com/market/sitemap.xml"
HEADERS = {"Accept-Language": "en-US,en;q=0.9"}
BLOCK_MARKERS = ("just a moment", "cf-chl", "attention required", "access denied", "captcha")
FIELDS = ["source", "kind", "url", "title", "asking_price", "cash_flow", "ebitda", "revenue",
          "location", "category", "page", "card_text", "status"]
LISTING_URL = re.compile(r"/market/businesses-for-sale/([a-z0-9-]+)/([0-9a-f-]{36})$")
STATE_URL = re.compile(r"/market/businesses-for-sale/category/(businesses-in-[a-z-]+)$")
CTX = re.compile(r"window\.__remixContext = (\{.*?\});\s*(?:__remixContext|</script>)", re.S)
# Deal stage, as Baton's cards show it. LIVE + an accepted-offer tag = under LOI;
# PRIVATE = the seller is only exploring interest (financials not released yet).
STAGE = {"LIVE": "for_sale", "PRIVATE": "exploring", "UNDER_CONTRACT": "under_contract",
         "SOLD": "sold", "PAUSED": "paused"}
STAGE_LABEL = {"for_sale": "", "loi": "Under LOI", "exploring": "Exploring interest",
               "under_contract": "Under contract", "sold": "Sold", "paused": "Paused"}
LOI_TAGS = {"ACCEPTED_OFFER", "UNDER_LOI", "LOI", "LOI_SIGNED", "OFFER_ACCEPTED"}
TAG_KEYS = ("status_tags", "statusTags", "listing_status_tags", "tags")


def tags_of(L: dict) -> list[str]:
    for k in TAG_KEYS:
        v = L.get(k)
        if isinstance(v, list):
            return [str(t.get("name") or t.get("value") or t) if isinstance(t, dict) else str(t) for t in v]
    return []


def is_blocked(status: int, html: str) -> bool:
    head = (html or "")[:6000].lower()
    return status in (403, 429, 503) or any(mk in head for mk in BLOCK_MARKERS)


def fetch(session, url: str, tries: int = 3) -> tuple[int, str]:
    last = (0, "")
    for i in range(tries):
        try:
            r = session.get(url, headers=HEADERS, timeout=40, **IMPERSONATE)
            last = (r.status_code, r.text)
            if (r.status_code == 200 and not is_blocked(200, r.text)) or r.status_code == 404:
                return last
        except Exception as e:
            last = (0, f"ERROR: {e}")
        time.sleep(5 * (i + 1))
    return last


def context(html: str) -> dict:
    m = CTX.search(html or "")
    return json.loads(m.group(1)) if m else {}


def money(v) -> int | None:
    try:
        v = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def to_row(L: dict, page: int) -> dict | None:
    slug, bid = L.get("slug"), L.get("business_id")
    if not slug or not bid or not L.get("name"):
        return None
    fin = L.get("financials") or {}
    locs = L.get("locations") or []
    loc = next((x for x in locs if x.get("is_primary_location")), locs[0] if locs else {})
    addr = (loc or {}).get("address") or {}
    city, st = (addr.get("city") or "").strip(), (addr.get("state") or "").strip()
    if city.lower().startswith("undisclosed"):
        city = ""
    location = ", ".join(p for p in (city, st) if p)
    cats = []
    for i in L.get("industries") or []:
        c = (i.get("category") or "").strip()
        if c and c not in cats:
            cats.append(c)
    status = (L.get("status") or "").upper()
    tags = [t.upper() for t in tags_of(L)]
    stage = STAGE.get(status, status.lower())
    if stage == "for_sale" and any(t in LOI_TAGS for t in tags):
        stage = "loi"
    note = STAGE_LABEL.get(stage, status.replace("_", " ").title())
    region = (L.get("display_region") or "").strip()
    return {
        "source": "Baton",
        "kind": "listing",
        "url": f"{BASE}{slug}/{bid}",
        "title": L["name"].strip(),
        "asking_price": None if L.get("asking_price_withheld") else money(L.get("asking_price")),
        "cash_flow": money(fin.get("adjusted_free_cash_flow")),
        "ebitda": None,
        "revenue": money(fin.get("gross_revenue")),
        "location": location,
        "category": " / ".join(cats[:3]),
        "page": page,
        "card_text": " · ".join(p for p in (note, region) if p),
        "status": stage,
        "_status": status,
        "_tags": tags,
        "_keys": sorted(L.keys()),
    }


def state_page_rows(html: str, page: int) -> tuple[list[dict], int | None]:
    seo = (context(html).get("state", {}).get("loaderData", {}) or {}).get("features/search/SearchSEO") or {}
    rows, total = [], seo.get("seoTotalCount")
    for q in (seo.get("dehydratedState") or {}).get("queries", []):
        sb = ((q.get("state") or {}).get("data") or {}).get("searchBusinesses")
        if not sb:
            continue
        total = sb.get("totalCount", total)
        for r in sb.get("results") or []:
            row = to_row(r.get("listing") or {}, page)
            if row:
                rows.append(row)
    return rows, total


def detail_row(html: str) -> dict | None:
    d = (context(html).get("state", {}).get("loaderData", {}) or {}).get("features/search/listing/Listing") or {}
    for q in (d.get("dehydratedState") or {}).get("queries", []):
        L = ((q.get("state") or {}).get("data") or {}).get("listing")
        if L:
            return to_row(L, 0)
    return None


def write_outputs(out_dir: str, rows: dict, summary: dict) -> None:
    vals = list(rows.values())
    summary.update({
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "listings": len(vals),
        "with_price": sum(1 for r in vals if r["asking_price"]),
        "with_cash_flow": sum(1 for r in vals if r["cash_flow"]),
        "by_status": {s: sum(1 for r in vals if r["_status"] == s) for s in sorted({r["_status"] for r in vals})},
        "by_stage": {s: sum(1 for r in vals if r["status"] == s) for s in sorted({r["status"] for r in vals})},
        "tags_seen": sorted({t for r in vals for t in r["_tags"]}),
        "listing_keys": vals[0]["_keys"] if vals else [],
    })
    with open(os.path.join(out_dir, "listings.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(vals)
    with open(os.path.join(out_dir, "run.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", type=int, default=0, help="states to crawl; 0 = all")
    ap.add_argument("--max-details", type=int, default=150, help="listing pages to open for listings no state page showed")
    ap.add_argument("--delay", type=float, default=2.5)
    ap.add_argument("--out", default="out_baton")
    ap.add_argument("--checkpoint-every", type=int, default=0)
    ap.add_argument("--checkpoint-cmd", default="")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    session = http.Session()
    summary = {"started_utc": datetime.now(timezone.utc).isoformat(), "pages": [], "blocked": False,
               "site_total": None, "full": args.states == 0}
    rows: dict[str, dict] = {}

    status, xml = fetch(session, SITEMAP)
    if status != 200 or is_blocked(status, xml):
        print(f"!! Sitemap failed: HTTP {status}", flush=True)
        summary["blocked"] = True
        write_outputs(args.out, rows, summary)
        return 1
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    listing_urls = {u for u in locs if LISTING_URL.search(u)}
    states = sorted({m.group(1) for u in locs if (m := STATE_URL.search(u))})
    summary["site_total"] = len(listing_urls)
    print(f"sitemap: {len(listing_urls)} listings, {len(states)} state pages", flush=True)
    if args.states:
        states = states[: args.states]

    fetched = 0

    def pause():
        time.sleep(args.delay + random.uniform(0, 1.5))

    for st in states:
        for n in range(1, 80):
            time.sleep(0)
            url = f"{BASE}category/{st}" + (f"?page={n}" if n > 1 else "")
            pause()
            status, html = fetch(session, url)
            fetched += 1
            blocked = is_blocked(status, html) if html else True
            got, total = ([], None) if blocked else state_page_rows(html, n)
            new = 0
            for r in got:
                if r["url"] not in rows:
                    rows[r["url"]] = r
                    new += 1
            summary["pages"].append({"page": url[len(BASE):], "status": status, "blocked": blocked,
                                     "cards": len(got), "new": new})
            print(f"{st:40s} p{n:<3d} HTTP {status} blocked={blocked} cards={len(got)} new={new} total={total}", flush=True)
            if blocked:
                summary["blocked"] = True
                break
            if not got or (total is not None and n * 14 >= total):
                break
            if args.checkpoint_every and fetched % args.checkpoint_every == 0 and rows:
                write_outputs(args.out, rows, summary)
                if args.checkpoint_cmd:
                    subprocess.run(args.checkpoint_cmd, shell=True)
        if summary["blocked"]:
            print("!! Blocked / challenge page detected — stopping.", flush=True)
            break

    # Listings no state page showed (e.g. no state on file): open them directly.
    missing = sorted(listing_urls - set(rows)) if summary["full"] and not summary["blocked"] else []
    summary["missing_after_states"] = len(missing)
    opened = 0
    for url in missing[: args.max_details]:
        pause()
        status, html = fetch(session, url)
        opened += 1
        if is_blocked(status, html):
            summary["blocked"] = True
            print("!! Blocked on a listing page — stopping.", flush=True)
            break
        r = detail_row(html) if status == 200 else None
        if r:
            rows.setdefault(r["url"], r)
        print(f"detail HTTP {status} {'ok' if r else 'no data'} {url[len(BASE):]}", flush=True)
    summary["details_opened"] = opened

    write_outputs(args.out, rows, summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "pages"}, indent=2))
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a", encoding="utf-8") as f:
            f.write("## Baton sweep\n\n")
            f.write(f"- Blocked: **{summary['blocked']}**\n- Pages fetched: **{len(summary['pages'])}** + {opened} listing pages\n")
            f.write(f"- Listings: **{summary['listings']}** of {summary['site_total']} in the sitemap "
                    f"(price: {summary['with_price']}, cash flow: {summary['with_cash_flow']})\n")
            f.write(f"- By status: {summary['by_status']}\n")
            f.write(f"- By deal stage: {summary['by_stage']}\n- Status tags seen: {summary['tags_seen']}\n")
            f.write(f"- Listing fields: {', '.join(summary['listing_keys'])}\n")
    return 1 if summary["blocked"] or not rows else 0


if __name__ == "__main__":
    sys.exit(main())
