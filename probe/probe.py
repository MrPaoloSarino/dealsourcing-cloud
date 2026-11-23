import re, json, time, os
from curl_cffi import requests as http
s = http.Session()
H = {"Accept-Language": "en-US,en;q=0.9"}
out = {}
def get(u, name):
    try:
        r = s.get(u, headers=H, timeout=40, impersonate="chrome")
        out[name] = {"url": u, "status": r.status_code, "len": len(r.text)}
        open(f"probe/{name}", "w", encoding="utf-8").write(r.text)
        return r.text
    except Exception as e:
        out[name] = {"url": u, "error": str(e)}; return ""
sm = get("https://www.baton.com/market/sitemap.xml", "sitemap.xml")
locs = re.findall(r"<loc>([^<]+)</loc>", sm)
lst = [l for l in locs if re.search(r"/businesses-for-sale/[^/]+/[0-9a-f-]{36}$", l)]
out["sitemap_locs"] = len(locs); out["sitemap_listings"] = len(lst)
time.sleep(3)
get("https://www.baton.com/market/businesses-for-sale", "search.html"); time.sleep(3)
get("https://www.baton.com/market/businesses-for-sale/category/businesses-in-texas", "cat_tx.html"); time.sleep(3)
get("https://www.baton.com/market/businesses-for-sale?page=2", "search_p2.html"); time.sleep(3)
for i, u in enumerate(lst[:3] + lst[-2:]):
    get(u, f"listing{i}.html"); time.sleep(3)
json.dump(out, open("probe/summary.json", "w"), indent=2)
print(json.dumps(out, indent=2))
