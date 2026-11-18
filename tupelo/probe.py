"""One-off probe #2: card internals + structured data in the Next.js payload."""
import re, json
from bs4 import BeautifulSoup
from curl_cffi import requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
html = requests.get("https://www.tupelosmb.com/marketplace/listings?page=2", headers=H, impersonate="chrome", timeout=40).text
soup = BeautifulSoup(html, "lxml")
cards = [a for a in soup.find_all("a", href=True) if re.search(r"/marketplace/listings/c[a-z0-9]{20,}", a["href"])]
for a in cards[:2]:
    print("\n#### CARD", a["href"])
    for el in a.find_all(True):
        own = "".join(t for t in el.find_all(string=True, recursive=False)).strip()
        if own:
            print(f"  <{el.name} class='{' '.join(el.get('class', []))[:70]}'> {own[:120]!r}")
print("\n#### keys in page:")
for k in ["askingPrice", "asking_price", "cashFlow", "cash_flow", "revenue", "grossRevenue", "ebitda", "sde", "industry", "createdAt", "publishedAt", "listedAt", "city", "state"]:
    print(f"  {k}: {html.count(chr(92)+chr(34)+k+chr(92)+chr(34))} escaped / {html.count(chr(34)+k+chr(34))} plain")
i = html.find('askingPrice')
print("\n#### context around first askingPrice:\n", html[max(0,i-1500):i+1500].replace("\\\"", "\"")[:3000] if i >= 0 else "none")
