# DealSourcing Cloud — Master File

Full context for any AI assistant or developer picking up this project. Read this first.
Last updated: 2026-11-23 (after adding Baton).

> **Privacy rule (hard):** this repository is **public**. Never commit client names, buy-box
> criteria, inquiry/pipeline data, or any credentials. Client buy-boxes live only in the
> user's browser (localStorage). Secrets go in GitHub Actions **Secrets**, never in files.

---

## 1. What this is

A **$0, fully cloud deal-sourcing screen** for an M&A / PE analyst (Paolo, Philippines-based
freelancer) who sources small and lower-middle-market businesses for buy-side clients.

- **Sources:** BusinessesForSale.com, US site (`https://us.businessesforsale.com/us/`), **Tupelo** (`https://www.tupelosmb.com/marketplace/listings`, added 2026-11-19), and **Baton** (`https://www.baton.com/market/businesses-for-sale`, added 2026-11-23). Each source has its own scraper, schedule and data file; the screen merges them.
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
| **Self-updating loader** (`docs/index.html` → fetches `docs/app.html` from GitHub raw) | Added when Render's auto-deploy wasn't firing (the repo had been added as a Public Git Repository). Kept as a safety net: the screen and data update from GitHub even if Render doesn't redeploy. `raw.githubusercontent.com` works on the user's network. Render auto-deploy now works too (see below). |
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
| `tupelo/scrape_tupelo.py` | Tupelo scraper, plain HTTP. Walks `/marketplace/listings?page=1…N` (10 cards/page, ~175 pages; `page=0` and `page=1` are the same first page). Each card is an `<a href="/marketplace/listings/<cuid>">` with industry badges (`div.inline-flex`), `<h3>` title, two `span.line-clamp-1` location lines (long + short `City, County, ST, US`), a description `<p>`, and value/label span pairs (Asking Price, Revenue, Cash Flow; `-` = not given). robots.txt only disallows `/api/` and `/auth/`. Writes `out_tupelo/listings.csv` + `run.json`. |
| `baton/scrape_baton.py` | Baton scraper, plain HTTP (robots.txt allows all). Pages are Remix server-rendered; listing data is read from the JSON in `window.__remixContext` (no HTML parsing). Reads `/market/sitemap.xml` (all listing URLs + state pages `category/businesses-in-<state>`), walks each state page `?page=N` (14 listings each, `searchBusinesses.results[].listing`: name, asking_price, financials.adjusted_free_cash_flow / gross_revenue, locations, industries, status, display_region), then opens listing pages for sitemap listings no state page showed (`--max-details`, default 150). Status LIVE / PRIVATE / UNDER_CONTRACT goes into `teaser` ("Private listing", "Under contract", else the region). Writes `out_baton/listings.csv` + `run.json` (`full: true` on a full crawl). |
| `bfs/publish.py` | Generic publisher (default BusinessesForSale; Tupelo passes `--data docs/data/tupelo.json --prefix https://www.tupelosmb.com/marketplace/listings/ --label Tupelo`). Merges a run into the source's data file: keeps `first_seen` from earlier runs, sets `last_seen` to today, derives US state code from location, keeps a short teaser for M&A Vault cards, **drops listings not seen for 21 days**. Row order in the file = the site's order (newest first): this run's listings in site order, then the rest in their previous order, stable-sorted by `first_seen` desc. Sets `meta.baseline_date` on first ever run (listings first seen after it are "New"). |
| `scripts/save_data.sh` | `save_data.sh "<commit msg>" [publish args…]`: runs publish, then commits and pushes `docs/data/*.json` as `dealsourcing-bot` (retries with `git pull --rebase`). |
| `.github/workflows/tupelo_sweep.yml` | Tupelo schedule (below). |
| `.github/workflows/baton_sweep.yml` | Baton schedule (below). |
| `.github/workflows/bfs_sweep.yml` | Schedule + manual + push triggers (below). `permissions: contents: write`, `concurrency: bfs-sweep`. |
| `docs/index.html` | Loader page that hosts serve. |
| `docs/app.html` | The deal screen (single file: HTML + CSS + JS, no build step). |
| `docs/data/bfs.json`, `docs/data/tupelo.json`, `docs/data/baton.json` | Published listings per source (compact: `{meta, fields, rows:[[...]]}`). |
| `README.md` | Short user-facing summary. |
| `MASTERFILE.md` | This file. |

### Data file format (`docs/data/<source>.json`)

- `fields`: `path, title, kind, location, state, price, revenue, cash_flow, ebitda, first_seen, last_seen, teaser, category`
  - `category` = industry (Tupelo badges, e.g. "Heavy Construction / Other Building & Construction"); empty for BusinessesForSale
  - `teaser` = M&A Vault pitch (BFS) or the card description (Tupelo, up to 240 chars)
  - `path` = listing URL minus the source's base URL (`meta.base`)
  - `kind`: `0` regular listing, `1` M&A Vault
  - money fields are integers (USD) or `null`; dates `YYYY-MM-DD`
- `meta`: `source, base, updated_utc, site_total, tracked, last_run_pages, last_run_new, last_run_dropped, baseline_date, last_full_crawl_utc`

---

## 4. Schedules (GitHub Actions, times in Manila / UTC+8)

| Trigger | Pages | Notes |
|---|---|---|
| Cron `17 */4 * * *` | 20 newest (~500 listings) | Every 4 h: 12:17am, 4:17am, 8:17am, 12:17pm, 4:17pm, 8:17pm. ~1–2 min. |
| Cron `41 18 * * 6` | all (~711) | Sunday 2:41am. ~45–50 min. Progress saved every 50 pages. Also what drops delisted listings (21-day rule). |
| Manual: Actions → *BusinessesForSale sweep* → Run workflow | input `pages` (0 = all) | |
| Push to `bfs/**`, `scripts/**`, `.github/workflows/**` | 3 pages, or all if the commit message contains `[full]` | |

**Tupelo** (`tupelo_sweep.yml`): every 4 h at :37 (12:37am/4:37/8:37 am/pm Manila) newest 10 pages; daily 03:53 Manila full crawl (~175 pages, ~10 min); push to `tupelo/**` runs a full crawl; manual dispatch with `pages`.

**Baton** (`baton_sweep.yml`): full crawl every 6 h at :07 (8:07am/2:07pm/8:07pm/2:07am Manila), ~140 pages + a few listing pages, ~9 min; push to `baton/**` runs it; manual dispatch with `states` (0 = full, N = first N states for a quick test).

GitHub may start scheduled runs 5–30 min late. Listing order on the site is newest first (matches the
site's RSS feed `/us/search/businesses-for-sale.rss`, 25 newest items with pubDate; not used yet).

---

## 5. The deal screen (`docs/app.html`)

- **Sources:** `SOURCES` list in the script (key, label, data file, base URL). All files load in parallel from GitHub raw (fallback `data/<file>`); rows get `src`, `key` (`src:path`, used for buy-box results), `url`, and a search haystack (title + location + industry + teaser). Source filter + chip; each row shows the source name, and the industry on its own line. App bar shows the most recent update (tooltip lists each source; dot turns gold if any source is >8 h old) and the combined site totals. CSV export includes Source and Industry.

- **Two tabs under the masthead (added 2026-11-25):** **1 Deal Sourcing** (mandates ribbon, filters, listings on the left,
  IC tearsheet on the right; unchanged) and **2 Client Buy Box**: every buy-box as a card with matches, new, accepted and
  axed counts, a Fast-track / Pursue / Conditional / Price not listed / Figures missing bar, the criteria in plain words,
  the SBA max price at the minimum profit, "View N deals" (opens that mandate in tab 1) and Edit. Search box, + New Buy-Box.
  Keys 1 / 2 switch tabs; the open tab is remembered (localStorage `dealscreen-view`). With a profile lock only that
  client's card shows.
- **Layout ("Private Equity Origination Desk", designed by the user 2026-11-19, phone fixes by Claude):**
  dark racing-green masthead (`--pe #0B3D2E`, gold accent `--gold-bright #E4C162`, Newsreader serif + Public Sans)
  with freshness dot, site totals, Import Buy-Boxes / Back up / Export CSV; a **Mandates** ribbon (buy-boxes as tabs,
  "+ New Buy-Box", a **Deciding for** client picker, ✓ Accepted and Hide axed toggles with counts); one-line filter bar (search, source, state,
  asking min/max, cash flow min/max, multiple, first seen, type, has cash flow; collapses to "Search & Filters" on
  phones); results header with count and medians; filter chips incl. the active mandate (Edit / ×); table with a ✓ / ✕ (Accept / Axe) column; **IC tearsheet panel** on the right (slide-over drawer below 1120px) for the selected row: mandate verdict
  and confidence, description, figures, **target offer slider** ("Snap to SBA Max", manager-salary selector),
  10% equity / year-1 cash-on-cash / SBA DSCR, the 80/10/10 capital stack and annual cash flow, a private analyst
  note, a "Decisions on this deal" list (every client), Accept / Axe for the current client, Open listing.
  Keys: `/` search, J/K move, A accept, X axe, O open. Below 820px: header scrolls away (not sticky), mandate
  tabs and triage buttons on their own rows, rows become two-column cards, selected card highlighted evenly.
- **Accept / Axe per client** (added 2026-11-19, replaces the global Shortlist / Pass). Accepted = sourced or
  inquired for that client; Axed = rejected for that client. The client is the open mandate tab, or the
  "Deciding for" picker when "All listings" is open (changing the picker while a mandate is open switches the tab).
  Pressing the same button again undoes it. Rows show an Accepted/Axed tag for the current client and
  "Also: Client A ✓, Client B ✕" for other clients. CSV export adds Decision, Decided on, Other clients' decisions.
  Stored in the browser only: localStorage `dealscreen-decisions` =
  `{"<client name>": {"<source:path>" (Baton: "baton:<listing id>"): {"s": "accepted"|"axed", "d": "YYYY-MM-DD"}}}`, plus
  `dealscreen-decide-for`. Keyed by client name on purpose so it maps to the cloud inquiries table later
  (accepted → Inquired, axed → Axed). Back up / Import include it.
- **Cloud sign-in (added 2026-11-19).** Masthead "Sign in" → email + password (the user types them; Claude never
  does). Talks to Supabase directly with `fetch` (no library): `/auth/v1/token` (password + refresh), `/rest/v1/...`.
  Session in localStorage `dealscreen-sb-session`. On sign-in: checks `app_admins`, loads active `clients` and all
  `inquiries` with a `listing_key` (paged by 1,000), adds missing buy-boxes from `clients.buybox`, uploads any
  browser-only decisions for cloud clients once (then deletes them locally), and shows "● Synced".
  Signed in, Accept = upsert inquiry status **Inquired**, Axe = **Axed** (on conflict `client_id,link`); row tags show
  the real status and date ("NDA sent Oct 1"). Undo only reverts what the screen did (`dealscreen-cloud-undo`:
  delete a row it created, or restore the status it changed); older inquiries are never deleted from the screen.
  Clients that aren't in the cloud keep browser-only decisions. Statuses Axed/Passed count as axed, all others as accepted.
- **Profile lock (added 2026-11-19).** With a mandate open, "🔓 Lock profile to <client>" stores
  localStorage `dealscreen-lock`. Locked: only "All listings" + that client's tab show, "+ New Buy-Box" and the
  "Deciding for" picker are disabled, and every Accept / Axe applies to that client. Unlock = type the client's
  name. **Cross-inquiry check** (locked or not): accepting a deal another client already has asks for confirmation.
- **Notes** stay in localStorage `dealscreen-triage` (`{starred, passed, notes:{key:text}}`); the old
  starred/passed sets are no longer shown but are kept and still included in Back up.

- **Filters:** search (title, location, teaser), state, type (all / listings / M&A Vault), asking
  min/max, cash flow min/max (type `500k`, `2.5m`), highest multiple, first seen (new / 24h / 7d / 30d),
  only with cash flow. Filters persist in localStorage (`bfs-filters`).
- **Sorting:** click column headers (▲/▼, `aria-sort`) or the Sort menu; every column both ways;
  empty values always last; ties keep the site's order (file order), so "Newest first" matches the site. First click direction: asking ↑, revenue ↓, cash flow ↓, multiple ↑,
  first seen ↓, name ↑.
- **Multiple** = asking ÷ cash flow, drawn as a gauge (≤3× green, 3–5× gold, >5× red).
- **Data-quality flag:** seller-typed cash flow is shown greyed with "?" and excluded from sorting and
  the multiple when: cash flow ≥ revenue, = asking price, > 2× asking price, or > $50M (~430 listings).
  Listings under ~$15K asking are mostly space/lease listings, not businesses (not filtered by default).
- **New tag:** `first_seen > meta.baseline_date` (baseline 2026-11-18, so the first crawl isn't "new").
- **Export CSV** of the current filtered view (adds buy-box columns when a buy-box is active).
- Responsive: below 900px the side panel collapses into "Buy-boxes and filters" and rows become two-column cards; above 900px the panel is always open (also when a narrow window is widened). Keyboard focus visible.
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
3. Industry: any keyword in title + industry (category) + teaser. Alphabetic keywords of 4+ letters match as prefixes
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

## 6. Current numbers (BFS/Tupelo as of 2026-11-19; Baton as of 2026-11-23)

| | BusinessesForSale | Tupelo |
|---|---|---|
| Listings tracked | 14,671 (site shows ~17,750; gap is mostly franchise ads, skipped on purpose) | 1,747 (matches the site's "1,746 vetted businesses") |
| With asking price | 97% | 90% |
| With cash flow | 73% | 57% |
| With a US state | 89% | 89% |
| With an industry | 0% (not on search cards) | 100% |
| Tagged New since baseline (2026-11-18) | 5 | 1 |
| First full crawl | 2026-11-18: 711 pages + 2 trailing 404s, 0 blocked, ~50 min | 2026-11-18: 175 pages + 2 empty, 0 blocked, ~10 min |

- BusinessesForSale M&A Vault cards: ~31 (no dollar figures on search cards).
- Tupelo top industries: American Restaurants 110, Other Building & Construction 88, Auto Repair 69,
  HVAC Businesses 60; top states CA 433, FL 172, IL 141, TX 89.
- Tupelo's site total isn't parsed (`meta.site_total` is null); the screen counts Tupelo by `tracked`.
- **Baton (2026-11-23):** 1,613 of 1,615 sitemap listings; 1,445 "Private listing", 143 live, 25 under contract; 99.8% with
  asking price, 100% with cash flow (adjusted free cash flow) and revenue; industry on every row; first full crawl ~9 min, 0 blocked.
  The user's 49 past Baton inquiry links (some in `…/businesses-for-sale/<id>` form, no name part) use the same listing ID;
  32 were still on the site. Baton keys are therefore `baton:<listing id>`, not the full path.
- Scheduled sweeps for all sources are running and succeeding. GitHub starts them a few to ~15 minutes
  after the cron time.

---

## 7. Operating guide

- **See the screen:** https://dealsourcing-cloud.onrender.com (refresh; Ctrl+F5 if stale).
  https://mrpaolosarino.github.io/dealsourcing-cloud/ also works but is blocked on the user's network.
- **Run a sweep now:** GitHub → Actions → *BusinessesForSale sweep*, *Tupelo sweep* or *Baton sweep* → Run workflow → pages (0 = all).
- **If the screen looks stale:** hover "Updated…" in the app bar to see each source's last update, then check that
  source's latest Actions run; data files are `docs/data/bfs.json`, `docs/data/tupelo.json` and `docs/data/baton.json` (`meta.updated_utc`). Raw GitHub can cache up to ~5 min.
- **Render deploys automatically** on every push to `main` (Render's GitHub app has access to `dealsourcing-cloud`;
  linked 2026-11-19, first automatic deploy 4:07pm Manila). If it ever stops: Render → Manual Deploy → Deploy latest commit.
- **Failure signals:** a failed run (GitHub emails the account), `blocked=True` lines in the run log,
  or a sudden drop in `tracked`.
- Commits by the bot are `dealsourcing-bot`; code commits use the user's name with a
  `Co-Authored-By: Claude …` trailer.

---

## 8. Known gaps / roadmap

**Waiting on the user**
- Import buy-boxes (`buybox.json`) in the browser the user actually uses; each browser/device is separate.

**Next to build (priority order)**
1. **Industry for BusinessesForSale** — crawl the site's category search pages (e.g.
   `/us/search/services-businesses-for-sale`) and fill `category`. Tupelo already has it.
2. **Detail pages for new listings only** — fill missing cash flow (BFS ~27%, Tupelo ~43%) and descriptions,
   so keyword matching sees full text like the old desktop app.
3. **Cross-source duplicates** — the same business can be on BFS and Tupelo; merge by normalized title +
   location + asking price, show both sources on one row.
4. **Daily email digest of new matches** — GitHub Actions + Gmail app password as an Actions secret. Buy-boxes
   are browser-only, so the digest needs its own private copy of criteria (e.g. an encrypted secret), never a
   file in this public repo.
5. **M&A Vault section crawl** — `/us/m-and-a-vault` shows revenue + profitability %; derive estimated profit.
6. **More sources** — next by volume in the old app: Transworld, BBMS, BusinessBroker, Sunbelt. Probe each from
   Actions first (one-off probe workflow, then delete it), reuse `bfs/publish.py` + `scripts/save_data.sh`,
   add a `SOURCES` entry in `docs/app.html`.
7. **Clients & inquiries in the cloud** — DONE: database + import + deal-screen sign-in + Deal Capture extension
   (see section 11). Next: inquiry tracker/pipeline view, nightly backup to a private
   repo (also keeps the free project from pausing), switch-over from the desktop app.
8. Housekeeping: alert when a sweep returns far fewer listings than usual (layout change); radius matching
   (needs a US cities lat/long table, the old app has `uscities.csv`); parse Tupelo's site total.

---

## 11. Cloud database (Supabase, private)

- Project `bfuczktomibpbzexkyah` (Singapore, free plan), URL `https://bfuczktomibpbzexkyah.supabase.co`,
  publishable key in `docs/app.html` (public by design). The service/secret key and DB password are never in chat
  or files; secrets go in GitHub Actions Secrets.
- Tables: `app_admins(user_id)`, `clients(id, name unique, active, buybox jsonb)`, `inquiries(id, client_id, link,
  listing_key, title, inquiry_date, price, sde, revenue, ebitda, location, status, notes, source_site, legacy_id,
  created_at, updated_at; unique(client_id, link))`. Status check: Inquired, NDA sent, Info received, Reviewing, LOI,
  Under contract, Passed, Axed, Closed.
- Security: RLS on all tables; policies allow only users in `app_admins` (via `is_admin()`); anon revoked; public
  sign-ups turned off. Only the user's account is an admin.
- Clients: the user's five active clients (names kept out of this public repo). Imported
  2026-11-19 from desktop `deals.db`: 2,324 inquiries (two duplicate Tupelo links merged); 784 have a deal-screen
  `listing_key` (BFS + Tupelo). `06_baton_listing_keys.sql` (2026-11-23) fills `baton:<id>` keys for past Baton inquiries. Setup SQL lives only on the user's PC in `dealsourcing/backups/cloud_setup/`
  (git-ignored). The cloud workspace and the user's PC VM can't reach `*.supabase.co`; SQL is run by the user in the
  Supabase SQL Editor, and the browser talks to Supabase directly.

### Deal Capture extension (switched to the cloud 2026-11-19)
- Lives on the user's PC: `dealsourcing/capture_extension/` (not in this repo). Pre-cloud copy kept in
  `dealsourcing/backups/capture_extension_pre_cloud/`.
- v2.0: `background.js` is the only part that talks to the tracker. It now calls Supabase (same publishable key)
  and returns the old local server's response shapes (`CHECK`, `CLIENTS`, `INQUIRIES`, `SAVE`, `AUTOFILL`), so
  `content.js` (overlay + company-portal auto-submit) and `popup.js` barely changed. New messages: `AUTH_STATUS`,
  `SIGNIN`, `SIGNOUT`, `SET_PROFILE_CLIENT`, `OPEN_TRACKER` (opens the deal screen).
- Sign-in once per Chrome profile (session in `chrome.storage.local.sbSession`); popup shows "This profile is for
  <client>" (`profileClient`, falls back to `lastClient`). Unknown client names are refused.
- Save = upsert on (client, link): matches the raw or canonical link (port of `core/normalize.canonicalize_link`,
  plus `inquirySuccess` stripped) and Transworld slugs (`transworld_dedupe_key`); updates only fields provided;
  sets `listing_key` for BFS/Tupelo/Baton (v2.2, 2026-11-23) so the deal screen shows the status. "Already inquired" checks link, canonical
  link, listing_key and Transworld slug, across all clients.
- v2.1 lock: "Lock this profile to <client>" (`profileClient`) makes the client field read-only in the popup,
  overlay and portal tab, and `background.js` refuses saves for any other client. Changing it = type the name.
- Each save is also mirrored best-effort to the desktop app (`127.0.0.1:8050/api/inquiries`) when it's running, so
  `deals.db` and the Excel export keep up during the switch-over.

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

---

## 10. Change log

| Date (Manila) | Change |
|---|---|
| 2026-11-19 | Repo `dealsourcing-cloud` created (public). BusinessesForSale plain-HTTP scraper tested from GitHub Actions: not blocked. |
| 2026-11-19 | First full BFS crawl (14,663 listings). Deal screen on GitHub Pages; GitHub Pages blocked on the user's network, moved to Render. |
| 2026-11-19 | Data and screen loaded from GitHub raw via a loader page, so the host never needs redeploys. |
| 2026-11-19 | Progress saves every 50 pages; sweeps every 4 h + weekly full crawl. |
| 2026-11-19 | Column-header sorting; flag impossible seller-entered cash flow. |
| 2026-11-19 | Buy-boxes (browser-only) with the desktop matcher's rules and SBA underwriting; import from `buybox.json`. |
| 2026-11-19 | UI redesign: app bar with freshness dot, side panel sections, medians summary, filter chips, sticky header, clickable rows. Fixed empty side panel after widening; "Newest first" follows site order. |
| 2026-11-19 | Render Deploy Hook workflow added (inactive until the secret exists). |
| 2026-11-19 | **Tupelo added** as second source (1,746 listings, industry on every card); generic publish/save scripts; Source filter; industry used in buy-box matching. |
| 2026-11-19 | User linked Render to GitHub (Render's GitHub app now has the repo): auto-deploy on commit works. Deploy Hook workflow removed. |
| 2026-11-19 | User's redesign published as `docs/app.html`: masthead, Mandates ribbon, one-line filters, IC tearsheet with offer slider and capital stack, shortlist/pass/notes triage. Claude fixed three phone issues (sticky header too tall, patchy selected-row highlight, triage buttons covering buy-box tabs). |
| 2026-11-19 | **Accept / Axe per client** replaces Shortlist / Pass on the deal screen (browser storage `dealscreen-decisions`, keyed by client name; A/X shortcuts; tearsheet shows decisions for every client; CSV and backup include them). |
| 2026-11-19 | **Cloud database live** (Supabase, RLS, admin-only): 5 clients and their inquiries imported; deal screen sign-in syncs Accept/Axe as Inquired/Axed and shows each deal's inquiry status per client. |
| 2026-11-19 | **Deal Capture extension v2.0 writes to the cloud** (per-profile sign-in and client, duplicate check across link variants, best-effort mirror to the desktop app). |
| 2026-11-19 | **Profile lock**: deal screen and Deal Capture extension (v2.1) can be locked to one client per Chrome profile; cross-inquiry confirmation on the deal screen. |
| 2026-11-23 | **Baton added** as third source (1,613 listings, data read from page JSON; full crawl every 6 h). Deal Capture extension v2.2 keys Baton links by listing ID; SQL `06_baton_listing_keys.sql` links past Baton inquiries. |
| 2026-11-25 | **Tabs on the deal screen:** 1 Deal Sourcing (as before) and 2 Client Buy Box (all buy-boxes as cards with match counts, criteria and View deals / Edit). Keys 1 / 2. |
