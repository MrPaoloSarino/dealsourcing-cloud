"""BusinessesForSale.com (US) cloud scraper — plain HTTP, no browser.

Walks the public search pages:
    https://us.businessesforsale.com/us/search/businesses-for-sale        (page 1)
    https://us.businessesforsale.com/us/search/businesses-for-sale-2      (page 2) ...
(robots.txt only disallows /us/search? with query strings; these paths have none.)

Outputs (in ./out):
    bfs_listings.csv   one row per listing card
    bfs_run.json       run summary: pages fetched, HTTP statuses, blocks, counts
    page1.html         raw HTML of page 1 (for tuning the parser)

Usage:
    python bfs/scrape_bfs.py --pages 5          # quick test
    python bfs/scrape_bfs.py --pages 0          # all pages (stops when a page is empty)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:  # curl_cffi mimics Chrome's TLS fingerprint; fall back to requests if missing
    from curl_cffi import requests as http
    IMPERSONATE = {"impersonate": "chrome"}
except ImportError:  # pragma: no cover
    import requests as http
    IMPERSONATE = {}

BASE = "https://us.businessesforsale.com"
FIRST_PAGE = f"{BASE}/us/search/businesses-for-sale"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
SKIP_LINK_WORDS = ("emailalerts", "contact", "login", "register", "members", "advertise", "franchise")

MONEY = r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(m|mm|million|k|thousand)?\b"
LABELS = {
    "asking_price": r"(?:asking\s+price|price)",
    "cash_flow": r"(?:cash\s*flow|sde|seller'?s\s+discretionary\s+earnings)",
    "ebitda": r"ebitda",
    "revenue": r"(?:revenue|sales\s+revenue|turnover|gross\s+revenue)",
}
TOTAL_RX = re.compile(r"of\s+([0-9][0-9,]*)", re.I)
BLOCK_MARKERS = ("just a moment", "cf-chl", "attention required", "challenge-platform", "access denied")


def page_url(n: int) -> str:
    return FIRST_PAGE if n == 1 else f"{FIRST_PAGE}-{n}"


def to_int(num: str, suffix: str | None) -> int | None:
    try:
        v = float(num.replace(",", ""))
    except ValueError:
        return None
    s = (suffix or "").lower()
    if s in ("m", "mm", "million"):
        v *= 1_000_000
    elif s in ("k", "thousand"):
        v *= 1_000
    v = int(v)
    return v if 1_000 <= v <= 1_000_000_000 else None


def labeled_amount(text: str, label_rx: str) -> int | None:
    m = re.search(label_rx + r"[^$\n]{0,40}" + MONEY, text, re.I)
    return to_int(m.group(1), m.group(2)) if m else None


def is_blocked(status: int, html: str) -> bool:
    head = html[:5000].lower()
    return status in (403, 429, 503) or any(mk in head for mk in BLOCK_MARKERS)


def card_for(a) -> object:
    """Climb from the listing link to the smallest ancestor that holds the price text."""
    node = a
    for _ in range(8):
        parent = node.parent
        if parent is None or parent.name in ("body", "html"):
            break
        node = parent
        txt = node.get_text(" ", strip=True)
        if re.search(r"asking\s+price|cash\s*flow|revenue", txt, re.I):
            # stop before swallowing several listings
            links = {x.get("href") for x in node.find_all("a", href=True) if ".aspx" in x["href"]}
            if len(links) <= 3:
                return node
            return a.parent or a
    return a.parent or a


def parse_listings(html: str, page_no: int) -> tuple[list[dict], int | None]:
    soup = BeautifulSoup(html, "lxml")
    total = None
    m = TOTAL_RX.search(soup.get_text(" ", strip=True)[:20000])
    if m:
        total = int(m.group(1).replace(",", ""))

    seen, rows = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE, a["href"].split("#")[0])
        if not href.endswith(".aspx") or "/us/" not in href:
            continue
        if any(w in href.lower() for w in SKIP_LINK_WORDS) or href in seen:
            continue
        title = a.get_text(" ", strip=True)
        if len(title) < 6:  # image / "more" links — keep looking for the titled link
            continue
        seen.add(href)
        card = card_for(a)
        text = card.get_text(" ", strip=True)
        loc_el = card.find(class_=re.compile("location|region|area", re.I)) if hasattr(card, "find") else None
        rows.append({
            "source": "BusinessesForSale",
            "url": href,
            "title": title,
            "asking_price": labeled_amount(text, LABELS["asking_price"]),
            "cash_flow": labeled_amount(text, LABELS["cash_flow"]),
            "ebitda": labeled_amount(text, LABELS["ebitda"]),
            "revenue": labeled_amount(text, LABELS["revenue"]),
            "location": loc_el.get_text(" ", strip=True)[:120] if loc_el else "",
            "card_text": text[:600],
            "page": page_no,
        })
    return rows, total


def fetch(session, url: str, tries: int = 3) -> tuple[int, str]:
    last = (0, "")
    for i in range(tries):
        try:
            r = session.get(url, headers=HEADERS, timeout=40, **IMPERSONATE)
            last = (r.status_code, r.text)
            if r.status_code == 200 and not is_blocked(200, r.text):
                return last
            if r.status_code == 404:
                return last
        except Exception as e:  # network hiccup
            last = (0, f"ERROR: {e}")
        time.sleep(5 * (i + 1))
    return last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=5, help="pages to fetch; 0 = all")
    ap.add_argument("--delay", type=float, default=2.5, help="base seconds between pages")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    session = http.Session()
    started = datetime.now(timezone.utc)
    summary = {"started_utc": started.isoformat(), "pages": [], "blocked": False,
               "site_total": None, "listings": 0, "with_price": 0, "with_cash_flow": 0}
    all_rows: dict[str, dict] = {}
    max_pages = args.pages if args.pages > 0 else 10_000
    empty_streak = 0

    for n in range(1, max_pages + 1):
        url = page_url(n)
        status, html = fetch(session, url)
        blocked = is_blocked(status, html) if html else True
        rows, total = ([], None) if blocked else parse_listings(html, n)
        if n == 1:
            with open(os.path.join(args.out, "page1.html"), "w", encoding="utf-8") as f:
                f.write(html)
            summary["site_total"] = total
        new = 0
        for r in rows:
            if r["url"] not in all_rows:
                all_rows[r["url"]] = r
                new += 1
        summary["pages"].append({"page": n, "status": status, "blocked": blocked,
                                 "cards": len(rows), "new": new})
        print(f"page {n:4d}  HTTP {status}  blocked={blocked}  cards={len(rows)}  new={new}", flush=True)

        if blocked:
            summary["blocked"] = True
            print("!! Blocked / challenge page detected — stopping.", flush=True)
            break
        empty_streak = empty_streak + 1 if new == 0 else 0
        if empty_streak >= 2:
            print("No new listings on 2 pages in a row — end of results.", flush=True)
            break
        time.sleep(args.delay + random.uniform(0, 1.5))

    rows = list(all_rows.values())
    summary.update({
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "listings": len(rows),
        "with_price": sum(1 for r in rows if r["asking_price"]),
        "with_cash_flow": sum(1 for r in rows if r["cash_flow"]),
    })
    fields = ["source", "url", "title", "asking_price", "cash_flow", "ebitda", "revenue",
              "location", "page", "card_text"]
    with open(os.path.join(args.out, "bfs_listings.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(args.out, "bfs_run.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps({k: v for k, v in summary.items() if k != "pages"}, indent=2))
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a", encoding="utf-8") as f:
            f.write("## BusinessesForSale cloud test\n\n")
            f.write(f"- Blocked by Cloudflare: **{summary['blocked']}**\n")
            f.write(f"- Site says total listings: **{summary['site_total']}**\n")
            f.write(f"- Pages fetched: **{len(summary['pages'])}**\n")
            f.write(f"- Listings parsed: **{summary['listings']}** "
                    f"(price: {summary['with_price']}, cash flow: {summary['with_cash_flow']})\n")
    return 1 if summary["blocked"] or not rows else 0


if __name__ == "__main__":
    sys.exit(main())
