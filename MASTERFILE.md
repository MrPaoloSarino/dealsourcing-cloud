# DealSourcing Cloud — Master File

Full context for any AI assistant or developer picking up this project. Read this first.
Last updated: 2026-11-19.

> **Privacy rule (hard):** this repository is **public**. Never commit client names, buy-box
> criteria, inquiry/pipeline data, or any credentials. Client buy-boxes live only in the
> user's browser (localStorage). Secrets go in GitHub Actions **Secrets**, never in files.

---

## 1. What this is

A **$0, fully cloud deal-sourcing screen** for an M&A / PE analyst (Paolo, Philippines-based
freelancer) who sources small and lower-middle-market businesses for buy-side clients.

- **Source today:** BusinessesForSale.com, US site only (`https://us.businessesforsale.com/us/`).
- **What it does:** scrapes every listing on a schedule, publishes them to a web page where the
  user can search, filter, sort, export CSV, and see each client's matches ("buy-boxes") scored
  with the same SBA underwriting rules as the user's older desktop app.
- **Constraints the user set:** fully cloud (no PC needed), zero cost, a new UI (not the old
  app's UI), start with one source and add more later.

### The older desktop app (separate, still exists)

- Local repo `dealsourcing` (GitHub `MrPaoloSarino/dealsourcing`, private), at
  `C:\Users\Paolo\Documents\GitHub\dealsourcing` on the user's PC.
- FastAPI dashboard + ~53 scrapers (5 need a real Chrome to pass Cloudflare), SQLite `deals.db`,
  `matcher.py` (client matching + SBA underwriting), `buybox.json` (client buy-boxes),
  Excel exports. The user runs it **only via `DealSourcing.exe`**, never `python app.py`.
- A half-built earlier cloud attempt lives in `dealsourcing/dealscout_cloud/`; the user did not
  want its UI. This repo (`dealsourcing-cloud`) replaces that direction.
- `dealsourcing/cloud_mvp/` on the PC is an early copy of this repo's first test. Ignore it.

---

## 2. Architecture (all free)

```
 GitHub Actions (cron)                    GitHub repo (public)                 User's browser
 ─────────────────────                    ───────────────────                  ──────────────
 bfs/scrape_bfs.py  ── plain HTTP ──►  BusinessesForSale search pages
        │  (curl_cffi, Chrome TLS fingerprint, no browser)
        ▼
 out/bfs_listings.csv
        │
 bfs/publish.py  ── merge + first/last seen ──►  docs/data/bfs.json  ──raw.githubusercontent──┐
        │                                                                                      │
 scripts/save_data.sh ── git commit + push (every 50 pages and at the end)                     │
                                                                                               ▼
 Render static site (dealsourcing-cloud.onrender.com) serves docs/index.html  ── loader ──►  docs/app.html
   (tiny loader: fetches docs/app.html from GitHub raw on every visit, falls back to its own copy)     │
                                                                                              renders the
                                                                                              deal screen;
                                                                                              buy-boxes in
                                                                                              localStorage
```

### Why it's built this way (decisions and rejected options)

| Decision | Reason |
|---|---|
| **Plain HTTP, no browser** for BusinessesForSale | Tested from GitHub Actions on 2026-11-18: search pages return HTTP 200, no Cloudflare challenge. Full crawl of 711 pages, 0 blocked. (The old desktop scraper used a visible Chrome; not needed in the cloud.) |
| **GitHub Actions** as the scheduler/runner | Free; the repo is public so minutes are unlimited. |
| **Repo is public** | Claude's GitHub link could only see public repos; also gives unlimited Actions minutes. Only public listing data is stored. |
| **Data in a JSON file in the repo** (no database yet) | One source, ~15k rows, ~2.9 MB. A database is only needed for writable features (pipeline). |
| **Render** static site for hosting | `*.github.io` (GitHub Pages) is **blocked on the user's network** (connection reset, even `pages.github.com`; changing DNS to 1.1.1.1 didn't help). Cloudflare Pages: user believes their account is banned / can't reach the email. Netlify free: ~20 production deploys/month (credit model), too few. Vercel Hobby: non-commercial use only, and this is client work. Render free static sites work on the user's network and allow commercial use. |
| **Self-updating loader** (`docs/index.html` → fetches `docs/app.html` from GitHub raw) | Render auto-deploy ("On Commit") never fired, probably because the service was connected by public repo URL rather than through the GitHub app. With the loader, Render never needs to redeploy again. `raw.githubusercontent.com` works on the user's network. |
| **Data also read from GitHub raw** | Same reason: new data appears on refresh without any host redeploy. Falls back to `data/bfs.json` next to the page. |
| Rejected: paid VPS / residential proxy / scraping APIs | User chose zero cost. Researched for later: Vultr Regular 4 GB $20/mo; residential proxies ~$1–4/GB; Hetzner US became expensive and restricts new customers in 2026. |
| Rejected: Supabase free DB | Pauses projects after 7 days of low activity. Neon free (1 GB, scales to zero) is the preferred DB if one is added. |

Raw-URL gotcha: `raw.githubusercontent.com/<owner>/<repo>/main/...` briefly cached a 404 for a new
file; the `refs/heads/main/...` form worked immediately. The loader uses `refs/heads/main`.

---

## 3. Repository layout

| Path | What it is |
|---|---|
| `bfs/scrape_bfs.py` | Scraper. Walks `/us/search/businesses-for-sale`, `-2`, `-3`… (25 cards/page). Parses each `div.result-header` card: title, URL, kind, location, asking price, revenue, cash flow, EBITDA. Skips franchise ads. Stops on Cloudflare block, or after 2 pages with no new listings / 404. `--pages N` (0 = all), `--checkpoint-every 50 --checkpoint-cmd "..."` saves progress mid-crawl. Writes `out/bfs_listings.csv`, `out/bfs_run.json`, `out/page1.html`. |
| `bfs/publish.py` | Merges a run into `docs/data/bfs.json`: keeps `first_seen` from earlier runs, sets `last_seen` to today, derives US state code from location, keeps a short teaser for M&A Vault cards, **drops listings not seen for 21 days**. Sets `meta.baseline_date` on first ever run (listings first seen after it are "New"). |
| `scripts/save_data.sh` | Runs publish, then commits and pushes `docs/data/bfs.json` as `dealsourcing-bot` (retries with `git pull --rebase`). |
| `.github/workflows/bfs_sweep.yml` | Schedule + manual + push triggers (below). `permissions: contents: write`, `concurrency: bfs-sweep`. |
| `docs/index.html` | Loader page that hosts serve. |
| `docs/app.html` | The deal screen (single file: HTML + CSS + JS, no build step). |
| `docs/data/bfs.json` | Published listings (compact: `{meta, fields, rows:[[...]]}`). |
| `README.md` | Short user-facing summary. |
| `MASTERFILE.md` | This file. |

### `docs/data/bfs.json` format

- `fields`: `path, title, kind, location, state, price, revenue, cash_flow, ebitda, first_seen, last_seen, teaser`
  - `path` = URL minus `https://us.businessesforsale.com/us/`
  - `kind`: `0` regular listing, `1` M&A Vault
  - money fields are integers (USD) or `null`; dates `YYYY-MM-DD`
- `meta`: `source, updated_utc, site_total, tracked, last_run_pages, last_run_new, last_run_dropped, baseline_date, last_full_crawl_utc`

---

## 4. Schedules (GitHub Actions, times in Manila / UTC+8)

| Trigger | Pages | Notes |
|---|---|---|
| Cron `17 */4 * * *` | 20 newest (~500 listings) | Every 4 h: 12:17am, 4:17am, 8:17am, 12:17pm, 4:17pm, 8:17pm. ~1–2 min. |
| Cron `41 18 * * 6` | all (~711) | Sunday 2:41am. ~45–50 min. Progress saved every 50 pages. Also what drops delisted listings (21-day rule). |
| Manual: Actions → *BusinessesForSale sweep* → Run workflow | input `pages` (0 = all) | |
| Push to `bfs/**`, `scripts/**`, `.github/workflows/**` | 3 pages, or all if the commit message contains `[full]` | |

GitHub may start scheduled runs 5–30 min late. Listing order on the site is newest first (matches the
site's RSS feed `/us/search/businesses-for-sale.rss`, 25 newest items with pubDate; not used yet).

---

## 5. The deal screen (`docs/app.html`)

- **Filters:** search (title, location, teaser), state, type (all / listings / M&A Vault), asking
  min/max, cash flow min/max (type `500k`, `2.5m`), highest multiple, first seen (new / 24h / 7d / 30d),
  only with cash flow. Filters persist in localStorage (`bfs-filters`).
- **Sorting:** click column headers (▲/▼, `aria-sort`) or the Sort menu; every column both ways;
  empty values always last. First click direction: asking ↑, revenue ↓, cash flow ↓, multiple ↑,
  first seen ↓, name ↑.
- **Multiple** = asking ÷ cash flow, drawn as a gauge (≤3× green, 3–5× gold, >5× red).
- **Data-quality flag:** seller-typed cash flow is shown greyed with "?" and excluded from sorting and
  the multiple when: cash flow ≥ revenue, = asking price, > 2× asking price, or > $50M (~430 listings).
  Listings under ~$15K asking are mostly space/lease listings, not businesses (not filtered by default).
- **New tag:** `first_seen > meta.baseline_date` (baseline 2026-11-18, so the first crawl isn't "new").
- **Export CSV** of the current filtered view (adds buy-box columns when a buy-box is active).
- Responsive (table stacks on mobile), keyboard focus visible.
- Design tokens: paper `#F4F6F3`, ink `#1B2420`, pine `#23513F`, brass `#A87A1E`, rust `#A2513C`,
  line `#D6DED8`; fonts Bricolage Grotesque (headings) + Public Sans (body, tabular numbers).

### Buy-boxes (client matching)

Stored **only in the browser** (`localStorage` keys `dealscreen-buyboxes`, `dealscreen-active-box`).
Import from the desktop app's `buybox.json` (active `clients` only; `archived_clients` ignored) or from
a Back up file. Add / edit / delete in a dialog. Each browser/device needs its own import.

Buy-box fields: `name, states[] (codes), places[], industry[], exclude[], minEbitda, maxPrice,
freeCash, managerSalary (default 100000), maxMultiple, allowTbd, skipFoodLegal`.
Import mapping from desktop schema: `target_states`→codes, `location_keywords` + city names from
`target_cities`→`places`, `industry_keywords`, `exclude_keywords`, `min_ebitda`, `max_price`,
`target_free_cash`, `manager_salary` (missing → 100000, same as the desktop default),
`max_multiple`, `allow_tbd_financials`.

Matching mirrors desktop `matcher.py`:
1. Skip if title matches food/restaurant/bar/law-firm list (when `skipFoodLegal`), or any exclude keyword.
2. Geography: state in `states`; or a `places` keyword (word-bounded) in the location; or, if places
   include Online/Remote/Relocatable, those words in the location or title. No geo constraints = anywhere.
   **Not implemented:** radius-from-city (`target_radius`); places are matched by name instead.
3. Industry: any keyword in title + teaser. Alphabetic keywords of 4+ letters match as prefixes
   (`plumb` → plumbing); `word*` forces prefix; short ones are exact words. Empty = any industry.
   **Limitation:** only title/teaser are available (no description or category yet).
4. Profit: EBITDA if present (no deduction), else cash flow (treated as SDE) minus `managerSalary`.
   Missing profit → only kept if `allowTbd` (revenue ≥ min, asking between 2× min and max) → "Figures missing".
5. SBA underwriting: debt-service factor = 80% SBA @ 10.5%/10y + 10% seller note @ 8%/5y (≈0.1539 per $ of price).
   Gates: price ≤ max price; DSCR ≥ 2.4 (lender floor 1.5 × safety 1.6); cash left after debt ≥ target;
   price ÷ adjusted profit ≤ max multiple. Missing price → "Price not listed" with max supportable price.
6. Stress test: haircut h ~ Triangular(0, 0.35, mode 0.10); confidence = P(profit survives the haircut
   and still meets min profit, 1.5× lender floor, target free cash, max multiple). ≥85 Fast-track,
   ≥70 Pursue, ≥40 Conditional, else excluded.
Rule of thumb from these settings: asking price must be under ~2.7× (cash flow − manager salary).
Rows show the decision tag and "Matched "keyword", supports up to $X, $Y left after debt".

---

## 6. Current numbers (first full crawl, 2026-11-18)

- Site total ~17,750; tracked **14,663** (gap is mostly franchise ads, skipped on purpose).
- With asking price 98%, with cash flow 74%, with a US state 90%, M&A Vault cards 31.
- Full crawl: 711 pages + 2 trailing 404s, 0 blocked, ~50 min.

---

## 7. Operating guide

- **See the screen:** https://dealsourcing-cloud.onrender.com (refresh; Ctrl+F5 if stale).
  https://mrpaolosarino.github.io/dealsourcing-cloud/ also works but is blocked on the user's network.
- **Run a sweep now:** GitHub → Actions → *BusinessesForSale sweep* → Run workflow → pages (0 = all).
- **If the screen looks stale:** check the latest Actions run; data file is `docs/data/bfs.json`
  (`meta.updated_utc`). Raw GitHub can cache up to ~5 min.
- **If Render shows an old page:** Render → Manual Deploy → Deploy latest commit (should only be needed
  if `docs/index.html` itself changes).
- **Failure signals:** a failed run (GitHub emails the account), `blocked=True` lines in the run log,
  or a sudden drop in `tracked`.
- Commits by the bot are `dealsourcing-bot`; code commits use the user's name with a
  `Co-Authored-By: Claude …` trailer.

---

## 8. Known gaps / roadmap (agreed priority)

1. **Industry / category per listing** — crawl the site's category search pages (e.g.
   `/us/search/services-businesses-for-sale`) and tag listings; improves buy-box matching.
2. ~~Client buy-boxes as saved views~~ — **done** (2026-11-19).
3. **Daily email digest of new matches** — GitHub Actions + Gmail app password as an Actions secret.
   Note: buy-boxes are browser-only, so the digest needs its own private copy of criteria (e.g. an
   encrypted secret), never a file in this public repo.
4. **M&A Vault section crawl** — `/us/m-and-a-vault` pages show revenue + profitability % (and
   sometimes growth/leverage); derive estimated profit = revenue × margin. Vault deals require buyer
   verification/NDA on the site; usually no asking price.
5. **Detail pages for new listings only** — fill missing cash flow (~26%) and descriptions.
6. **More sources** — next by volume in the old app: Transworld, BBMS, BusinessBroker, Tupelo, Sunbelt.
   Test each from Actions first; merge duplicates across sources (one listing, many sources).
7. **Pipeline tracking** (Inquired → NDA → CIM → LOI) — needs private writable storage (Neon free
   Postgres or similar); can't live in this public repo.
8. Housekeeping: alert when a sweep returns far fewer listings than usual (layout change); radius
   matching (needs a US cities lat/long table, the old app has `uscities.csv`).

---

## 9. Notes for an AI assistant

- The user is an analyst, not a full-time developer: explain in plain language, give exact click paths,
  prefer doing the work over describing it. Keep everything $0 unless the user agrees to spend.
- The user's network blocks `*.github.io`; test reachability from their side before suggesting a host.
- Don't add client data, buy-box contents, or secrets to this repo. Don't change the repo to private
  without checking Actions minutes and the Claude GitHub App access.
- Respect the site: sequential requests, 2.5–4 s between pages, robots.txt only disallows
  `/us/search?` query URLs (these paths have none). Marketplace terms may restrict automated access;
  saved-search email alerts are the fallback if scraping is ever blocked.
- When changing `docs/app.html`, test with real data (`docs/data/bfs.json`) in a headless browser:
  load, sort each column, filters, buy-box import, and check for JS errors.
