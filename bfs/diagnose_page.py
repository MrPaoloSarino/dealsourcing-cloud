"""One-off: show sample card texts per kind, and probe the RSS feed."""
import csv, sys
from collections import defaultdict
from curl_cffi import requests

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
by = defaultdict(list)
for r in rows:
    by[r["kind"]].append(r)
for kind, rs in by.items():
    print(f"== {kind}: {len(rs)} rows, price {sum(1 for r in rs if r['asking_price'])}, "
          f"cash flow {sum(1 for r in rs if r['cash_flow'])}, location {sum(1 for r in rs if r['location'])}")
    for r in rs[:3]:
        print("   ", r["title"][:60], "|", r["card_text"][:420])

r = requests.get("https://us.businessesforsale.com/us/search/businesses-for-sale.rss", impersonate="chrome", timeout=40)
print("RSS status", r.status_code, "len", len(r.text), "items", r.text.count("<item>"))
i = r.text.find("<item>")
print(r.text[i:i+1200] if i >= 0 else r.text[:600])
