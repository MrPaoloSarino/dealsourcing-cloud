"""One-off: print the structure of every listing-ish link on a saved results page."""
import re
import sys
from collections import Counter

from bs4 import BeautifulSoup

html = open(sys.argv[1], encoding="utf-8").read()
soup = BeautifulSoup(html, "lxml")
print("html_len", len(html))
hrefs = Counter()
for a in soup.find_all("a", href=True):
    h = a["href"]
    if "aspx" in h or "/us/" in h:
        hrefs[h] += 1
print("distinct candidate hrefs:", len(hrefs))
for h, c in hrefs.most_common(200):
    a = soup.find("a", href=h)
    txt = a.get_text(" ", strip=True)[:50]
    chain = []
    node = a
    for _ in range(4):
        node = node.parent
        if node is None:
            break
        chain.append(f"{node.name}.{'.'.join(node.get('class', []))[:30]}")
    print(f"{c}x | {h[:110]} | text={txt!r} | {' < '.join(chain)}")

# containers that look like result cards
cls = Counter()
for el in soup.find_all(class_=True):
    for c in el.get("class", []):
        if re.search(r"result|listing|card|item", c, re.I):
            cls[f"{el.name}.{c}"] += 1
print("card-like classes:", cls.most_common(25))
