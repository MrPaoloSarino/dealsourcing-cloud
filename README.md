# DealSourcing Cloud

A $0, fully cloud deal screen. First source: **BusinessesForSale.com (US)**.

- **Deal screen:** GitHub Pages serves `docs/index.html`. Search, filter by state / price / cash flow / multiple, sort, export CSV.
- **Data:** `docs/data/bfs.json`, refreshed by GitHub Actions (`.github/workflows/bfs_sweep.yml`):
  - daily 06:17 Manila: newest 20 pages (~500 listings)
  - weekly, Sunday 02:41 Manila: full crawl of every page (~45–50 min)
  - manual: Actions → BusinessesForSale sweep → Run workflow (pages, 0 = all)
- **Scraper:** `bfs/scrape_bfs.py`, plain HTTP, no browser. `bfs/publish.py` merges each run and tracks first seen / last seen; listings not seen for 21 days are dropped.

Listings in the very first crawl count as already on the market; anything that appears after that is tagged **New**.
