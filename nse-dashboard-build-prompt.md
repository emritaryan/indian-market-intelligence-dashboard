# Build Prompt: Personal NSE Market & Stock Research Dashboard

*One honest note before this goes anywhere: the reference link (7shescfoerzyo.ok.kimi.link) is a client-side-rendered SPA — I could only retrieve its page title ("TAPE · US Market Watch"), not the actual layout, since it renders via JS my fetch tool can't execute. I've marked it below as an unverified inspirational reference rather than describing a layout I didn't actually see. Open it yourself before handing this to the code model, and add 2-3 lines describing what you want copied from it if anything.*

---

Copy everything below the line into Claude Code (or Codex).

---

## Objective

Build a personal, two-page NSE market and stock research dashboard for daily trading decision support (buy / sell / no-action calls on swing positions). This is a solo-user tool, not a product — optimize for "I check this every morning before market open and once at close," not for concurrent users or uptime SLAs.

**Optional reference for visual inspiration only, not a spec:** https://7shescfoerzyo.ok.kimi.link/ — this is a US-market dashboard example, JS-rendered so treat any description of its layout as unverified. Don't assume feature parity with it; the requirements below are the actual spec.

## Non-negotiable architecture decision — read this before choosing a stack

Do **not** default to a Streamlit/Dash app requiring a persistently running Python server. Free hosting for that (Streamlit Community Cloud, Render free tier, PythonAnywhere) comes with sleep/cold-start behavior, RAM ceilings, or outbound-network whitelisting that breaks live API calls. Use this architecture instead:

- **Data layer:** Python script(s) run on a **schedule via GitHub Actions** (free — 2,000 min/month on a private repo, unlimited on public). Script(s) pull market data, compute derived metrics and indicators, and write the results as **static JSON files** committed back to the repo (or pushed to a data branch).
- **Frontend:** A static site (React + TypeScript + Vite, or plain HTML/JS if you want to keep it simpler) that fetches the static JSON and renders charts client-side. Use a proper charting library — Apache ECharts or TradingView's lightweight-charts for candlesticks — not hand-rolled SVG.
- **Hosting:** Cloudflare Pages. Free, unlimited bandwidth, no commercial-use restriction, git-push-to-deploy.
- **Refresh cadence:** Schedule the GitHub Action for after NSE market close (e.g. 16:00 IST) and optionally once pre-open (09:00 IST). This is not a live tick-by-tick terminal — don't build it like one.

Only deviate from this if a specific feature genuinely requires live server-side computation per request (it shouldn't, for anything in this spec — everything below can be precomputed on schedule and rendered statically).

## Development process — work through these phases explicitly, don't jump straight to code

1. **Plan:** Propose the repo structure (data pipeline folder, frontend folder, GitHub Actions workflow file, config file location) before writing anything. Confirm the tech stack choices above or flag if you think a specific piece genuinely needs to differ, with a reason.
2. **Requirements & data sources:** For every metric/indicator listed below, state explicitly which data source will supply it (see Data Sources section) and what happens if that source is unavailable for a given stock (e.g., missing fundamental data for an illiquid name). Flag any metric you can't source cleanly rather than silently faking it with placeholder data.
3. **Design:** Before building, produce a short written UI/UX outline — page layout, navigation between the two pages, how the stock selector works, how color-coding is applied — for review.
4. **Build:** Implement the data pipeline, the config-driven section system, and both pages.
5. **Deploy:** Provide the exact steps to stand up GitHub Actions (including required secrets) and connect the repo to Cloudflare Pages.

Do not skip straight to Build — surface the Plan and Design outputs first so they can be reviewed before code is written.

## Data sources — use these, not scraping

- **NSE cash-segment stock data (price, volume, delivery %):** A free broker API — Angel One SmartAPI, Upstox API, or DhanHQ (pick one; all are free with an account and provide licensed, ToS-clean data). Do **not** scrape nseindia.com or moneycontrol — both explicitly prohibit automated data collection in their Terms of Use.
- **Nifty 50, Nifty Bank, sector indices, India VIX, crude oil, gold, silver, USD/INR:** `yfinance` is acceptable here — this is index/commodity/FX data, not licensed exchange data, and yfinance is fine for personal use. Relevant tickers: `^NSEI`, `^NSEBANK`, `^CNXIT`, `^CNXPHARMA`, `^CNXAUTO`, `^INDIAVIX`, `CL=F` (crude), `GC=F` (gold), `SI=F` (silver), `USDINR=X`.
- **Fundamentals (PE, D/E, promoter holding, quarterly YoY revenue/PAT):** Pull from the broker API if it exposes fundamentals; otherwise NSE's official corporate-disclosure filings (quarterly results, shareholding pattern) are public disclosures, not scraped market data — flag this distinction in code comments since it's a different legal category than live price data.
- **Market holiday calendar (for the open/closed indicator):** Maintain a static JSON list of NSE trading holidays for the current year (source it from NSE's official published holiday circular once, store it in the repo, and add a config reminder to update it each January) plus standard trading hours (09:15–15:30 IST, Mon–Fri).
- **FII/DII daily flow (optional, if you want it on Page 1):** NSE publishes this officially at `nseindia.com/reports/fii-dii` — check and enter manually or fetch once daily at low frequency, not as a polling scraper.

## Page 1: Market Trends

- **NIFTY trend:** Line/candlestick chart of Nifty 50, with a toggle for daily/weekly view.
- **Category-wise stock buckets:** Group your watchlist stocks by sector (define the watchlist and sector mapping in the config file, not hardcoded). For each bucket, show each stock's daily/weekly % change color-coded green (positive) / red (negative), sized or ordered by magnitude, so money flow by sector is visible at a glance.
- **Commodity & currency trend charts:** Separate small trend charts for Crude Oil, USD/INR, Gold, Silver (each pulling from the yfinance tickers above).
- **Market status indicator:** A simple badge — "Market Open" / "Market Closed" / "Holiday: [name]" — computed from the current IST time against trading hours and the holiday list.

## Page 2: Stock-Specific Analysis

- **Stock selector:** Dropdown or search, scoped to your configured watchlist (not all of NSE — keep the precomputed data set bounded).
- **Price trend chart:** Candlestick chart for the selected stock with a timeframe toggle (daily / weekly / monthly).
- **Key metrics panel:**
  - Volume Delivery % (trend, not just current value)
  - P/E ratio
  - Debt-to-Equity ratio
  - Promoter holding trend — visually flag rising holding as positive and any pledged-share increase as a red-flag indicator
  - Quarterly YoY revenue growth
  - Quarterly YoY PAT growth
- **Technical indicator panel** — implement using these specific parameters (already calibrated for NSE volatility, don't substitute generic textbook defaults):
  - EMA 20/50 for trend direction
  - RSI(14), with regime-adjusted bands: 40/80 in a confirmed uptrend, 20/60 in a downtrend, rather than static 30/70
  - MACD(12,26,9) as a confirmation signal, not a standalone trigger
  - Volume relative to its own 20-day average, flagging >1.5x as a breakout-volume signal
  - Surface **Momentum Breakout**, **Pullback-to-Support**, and **MA Crossover** as three distinct labeled signals (badges or annotations on the chart), each independently flagged true/false for the selected stock on the most recent session — don't collapse them into a single opaque "score" without showing which conditions fired.

## Customization mechanism (required, not optional)

Drive the dashboard from a single config file (JSON or YAML) covering:
- The watchlist (list of stock tickers + sector/category assignment)
- Which sections/widgets appear on each page, in what order
- The commodity/FX tickers shown

Adding, removing, or reordering a section should mean editing this config, not touching component code. Structure the frontend as independent components per widget/section that read their presence and order from this config at build or load time. Document this config file's schema clearly in a README.

## Output expected from you (the code-generation model)

1. The Plan and Design write-ups (per the phases above), before code.
2. Repo scaffold: GitHub Actions workflow, Python data-pipeline scripts, frontend project structure, and the config file schema.
3. Working initial implementation of both pages against the static JSON (placeholder/sample data is fine for first pass if live API keys aren't provided yet — but label it clearly as placeholder and show exactly where real API calls plug in).
4. A README covering: how to add a broker API key as a GitHub Actions secret, how the config file works, and the exact steps to deploy to Cloudflare Pages.
5. Inline comments at every data-fetching integration point marking exactly where each metric's source is called, so gaps are easy to spot later.
