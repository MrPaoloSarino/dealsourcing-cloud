"""Tupelo (tupelosmb.com) marketplace scraper — plain HTTP, no browser.

Walks the public listing pages:
    https://www.tupelosmb.com/marketplace/listings?page=1 … ?page=N   (10 cards each)
(robots.txt only disallows /api/ and /auth/.)

Each card is an <a href="/marketplace/listings/<id>"> holding: industry badges,
an <h3> title, two location lines (long and short), a short description <p>, and
value/label pairs: "$250,000" + "Asking Price", "$709,000" + "Revenue", "$110,000" + "Cash Flow".

Writes the same CSV columns as the BusinessesForSale scraper (plus `category`)
so bfs/publish.py can merge it:
    out_tupelo/listings.csv, out_tupelo/run.json, out_tupelo/page1.html

Usage:
    python tupelo/scrape_tupelo.py --pages 3     # quick
    python tupelo/scrape_tupelo.py --pages 0     # every page
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
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as http
    IMPERSONATE = {"impersonate": "chrome"}
except ImportError:  # pragma: no cover
    import requests as http
    IMPERSONATE = {}

BASE = "https://www.tupelosmb.com"
LIST_URL = BASE + "/marketplace/listings?page={n}"
CARD_HREF = re.compile(r"/marketplace/listings/(c[a-z0-9]{20,})$")
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
BLOCK_MARKERS = ("just a moment", "cf-chl", "attention required", "access denied", "captcha")
FIELDS = ["source", "kind", "url", "title", "asking_price", "cash_flow", "ebitda", "revenue",
          "location", "category", "page", "card_text"]
MONEY = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(m|mm|million|k|thousand)?\b", re.I)


def amount(text: str) -> int | None:
    m = MONEY.search(text or "")
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    s = (m.group(2) or "").lower()
    v *= 1e6 if s in ("m", "mm", "million") else 1e3 if s in ("k", "thousand") else 1
    v = int(v)
    return v if 1_000 <= v <= 1_000_000_000 else None


def is_blocked(status: int, html: str) -> bool:
    head = (html or "")[:6000].lower()
    return status in (403, 429, 503) or any(mk in head for mk in BLOCK_MARKERS)


def parse_cards(html: str, page_no: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0].split("#")[0]
        if not CARD_HREF.search(href):
            continue
        url = urljoin(BASE, href)
        if url in seen:
            continue
        seen.add(url)

        h3 = a.find("h3")
        title = h3.get_text(" ", strip=True) if h3 else ""
        if not title:
            continue

        # industry badges (deduplicated, skip "+ 2" style overflow counters)
        cats = []
        for b in a.select("div.inline-flex"):
            t = b.get_text(" ", strip=True)
            if t and not t.startswith("+") and t not in cats:
                cats.append(t)

        # location: two spans, long ("…, Florida, United States") then short ("…, FL, US")
        locs = [s.get_text(" ", strip=True) for s in a.select("span.line-clamp-1")]
        short = next((l for l in locs if re.search(r",\s*[A-Z]{2},\s*US$", l)), "")
        loc = short[:-4] if short.endswith(", US") else (locs[-1] if locs else "")
        if loc.lower() == "confidential":
            loc = ""

        desc_el = a.find("p")
        desc = desc_el.get_text(" ", strip=True) if desc_el else ""

        # figures: each label span follows its value span
        figs = {}
        for lab in a.find_all("span"):
            name = lab.get_text(" ", strip=True).lower()
            if name in ("asking price", "revenue", "cash flow", "ebitda"):
                val = lab.find_previous_sibling("span") or lab.find_previous("span")
                figs[name] = amount(val.get_text(" ", strip=True)) if val else None

        rows.append({
            "source": "Tupelo",
            "kind": "listing",
            "url": url,
            "title": title,
            "asking_price": figs.get("asking price"),
            "cash_flow": figs.get("cash flow"),
            "ebitda": figs.get("ebitda"),
            "revenue": figs.get("revenue"),
            "location": loc,
            "category": " / ".join(cats[:3]),
            "page": page_no,
            "card_text": desc[:400],
        })
    return rows


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
        except Exception as e:
            last = (0, f"ERROR: {e}")
        time.sleep(5 * (i + 1))
    return last


def write_outputs(out_dir: str, rows: dict, summary: dict) -> None:
    vals = list(rows.values())
    summary.update({
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "listings": len(vals),
        "with_price": sum(1 for r in vals if r["asking_price"]),
        "with_cash_flow": sum(1 for r in vals if r["cash_flow"]),
    })
    with open(os.path.join(out_dir, "listings.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(vals)
    with open(os.path.join(out_dir, "run.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=3, help="pages to fetch; 0 = all")
    ap.add_argument("--delay", type=float, default=2.5)
    ap.add_argument("--out", default="out_tupelo")
    ap.add_argument("--checkpoint-every", type=int, default=0)
    ap.add_argument("--checkpoint-cmd", default="")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    session = http.Session()
    summary = {"started_utc": datetime.now(timezone.utc).isoformat(), "pages": [], "blocked": False,
               "site_total": None}
    rows: dict[str, dict] = {}
    max_pages = args.pages if args.pages > 0 else 1000
    empty_streak = 0

    for n in range(1, max_pages + 1):
        status, html = fetch(session, LIST_URL.format(n=n))
        blocked = is_blocked(status, html) if html else True
        cards = [] if blocked else parse_cards(html, n)
        if n == 1:
            with open(os.path.join(args.out, "page1.html"), "w", encoding="utf-8") as f:
                f.write(html)
            m = re.search(r"([0-9][0-9,]*)\s+vetted businesses", html or "")
            summary["site_total"] = int(m.group(1).replace(",", "")) if m else None
        new = 0
        for r in cards:
            if r["url"] not in rows:
                rows[r["url"]] = r
                new += 1
        summary["pages"].append({"page": n, "status": status, "blocked": blocked, "cards": len(cards), "new": new})
        print(f"page {n:4d}  HTTP {status}  blocked={blocked}  cards={len(cards)}  new={new}", flush=True)
        if blocked:
            summary["blocked"] = True
            print("!! Blocked / challenge page detected — stopping.", flush=True)
            break
        empty_streak = empty_streak + 1 if new == 0 else 0
        if empty_streak >= 2:
            print("No new listings on 2 pages in a row — end of results.", flush=True)
            break
        if args.checkpoint_every and n % args.checkpoint_every == 0 and rows:
            write_outputs(args.out, rows, summary)
            if args.checkpoint_cmd:
                print(f"-- checkpoint at page {n}: {len(rows)} listings so far", flush=True)
                subprocess.run(args.checkpoint_cmd, shell=True)
        time.sleep(args.delay + random.uniform(0, 1.5))

    write_outputs(args.out, rows, summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "pages"}, indent=2))
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a", encoding="utf-8") as f:
            f.write("## Tupelo sweep\n\n")
            f.write(f"- Blocked: **{summary['blocked']}**\n- Pages fetched: **{len(summary['pages'])}**\n")
            f.write(f"- Listings: **{summary['listings']}** (price: {summary['with_price']}, "
                    f"cash flow: {summary['with_cash_flow']})\n")
    return 1 if summary["blocked"] or not rows else 0


if __name__ == "__main__":
    sys.exit(main())
