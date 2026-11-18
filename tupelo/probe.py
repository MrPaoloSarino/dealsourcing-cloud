"""One-off probe: fetch Tupelo listing pages from GitHub's servers and describe the HTML."""
import re, sys
from collections import Counter
from bs4 import BeautifulSoup
from curl_cffi import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept-Language": "en-US,en;q=0.9"}
for page in (0, 1):
    url = f"https://www.tupelosmb.com/marketplace/listings?page={page}"
    r = requests.get(url, headers=H, impersonate="chrome", timeout=40)
    html = r.text
    print(f"\n===== page={page} HTTP {r.status_code} len={len(html)} title={re.search(r'<title>(.*?)</title>', html, re.S).group(1)[:80] if '<title>' in html else None}")
    soup = BeautifulSoup(html, "lxml")
    links = [a for a in soup.find_all("a", href=True) if re.search(r"/marketplace/listings/c[a-z0-9]{20,}", a["href"])]
    print("listing links:", len(links), "distinct:", len({a['href'] for a in links}))
    for a in links[:3]:
        chain, node = [], a
        for _ in range(5):
            node = node.parent
            if node is None: break
            chain.append(f"{node.name}.{'.'.join(node.get('class', []))[:40]}")
        print("--", a["href"], "| a.class=", ".".join(a.get("class", []))[:60])
        print("   chain:", " < ".join(chain))
        print("   a text:", a.get_text(" | ", strip=True)[:300])
        print("   parent text:", a.parent.get_text(" | ", strip=True)[:400])
    m = re.search(r"([0-9,]+)\s+vetted businesses", html); print("total:", m.group(1) if m else None)
    pag = sorted({a["href"] for a in soup.find_all("a", href=True) if "page=" in a["href"]})[:10]; print("pagination hrefs:", pag)
    print("has __NEXT_DATA__:", "__NEXT_DATA__" in html, "| RSC pushes:", html.count("self.__next_f.push"))
    sorts = sorted({a["href"] for a in soup.find_all("a", href=True) if "sort" in a["href"].lower()})[:8]; print("sort links:", sorts)
