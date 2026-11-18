# DealSourcing Cloud — MVP (step 0: BusinessesForSale test)

Fully cloud, $0. This first step only answers one question:
**can GitHub's servers read BusinessesForSale.com without a browser?**

## What's here
- `bfs/scrape_bfs.py` — plain-HTTP scraper for the US search pages (`/us/search/businesses-for-sale`, `-2`, `-3`, ...). No Chrome needed.
- `.github/workflows/bfs_test.yml` — runs it on GitHub Actions and saves the results.

## How to run the test
1. Create a **private** GitHub repo, e.g. `dealsourcing-cloud` (no README).
2. Upload `README.md`, `requirements.txt` and the `bfs` folder to the repo root (Add file → Upload files, drag them in, Commit).
3. Add the workflow: **Add file → Create new file**, name it `.github/workflows/bfs_test.yml`,
   paste the contents of `bfs_test.yml` from this folder, and Commit.
   Then open the repo's **Actions** tab. The run starts automatically (5 pages = ~125 listings).
   To run again: **BusinessesForSale cloud test → Run workflow**, set pages (0 = all ~700 pages, ~30–40 min).
4. Open the finished run:
   - The **Summary** shows: blocked yes/no, site total, listings parsed, how many had price / cash flow.
   - **Artifacts → bfs-results** has `bfs_listings.csv`, `bfs_run.json` and `page1.html`.

## Run it locally (optional)
```
pip install -r requirements.txt
python bfs/scrape_bfs.py --pages 2
```

## Next steps (after the test passes)
1. Neon Postgres + import of existing listings
2. Daily scheduled run writing to the database
3. New dashboard (Render Free) with login
