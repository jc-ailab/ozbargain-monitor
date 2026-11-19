# SPEC: OzBargain 热帖监控（ozbargain-monitor）v1

Owner: Tracy (PO). Architect and reviewer: Claude Opus 5.5. Implementer: Codex.
Date: 2026-11-20. Read `docs/PROJECT_CHARTER.md` first.

## 0. Product in one line

A public, phone-friendly web page that shows which OzBargain deals are hot right now, and which are suddenly blowing up, refreshed every 30 minutes. It is free to run: GitHub Actions + GitHub Pages, no server, no paid API.

UI language: Simplified Chinese (product and deal titles stay in English). Code, comments, docs for developers: English.

## 1. Hard constraints

1. **Python 3.12 standard library only** for the pipeline (urllib, xml.etree, json, unittest, etc.). No pip dependencies. Frontend: vanilla HTML/CSS/JS, no build step, no framework, no CDN.
2. **Data source = official RSS only**: `https://www.ozbargain.com.au/deals/feed` (new) and `https://www.ozbargain.com.au/feed` (front page). Never fetch `/api/`, `/goto/`, `/search/`, `/comment/`, `/ozbapi/` (robots.txt). At most 2 feed requests per run. User-Agent: `ozbargain-monitor/1.0 (+https://github.com/jc-ailab/ozbargain-monitor)`. Timeout 20 s, one retry.
3. The page links to the deal's OzBargain node page and to the merchant URL from `ozb:meta url` (not the /goto/ link).
4. No secrets. The only token used is the workflow's built-in `GITHUB_TOKEN`.
5. All tests run offline from fixtures in `tests/fixtures/`: `python -m unittest discover -s tests` must pass.
6. Never crash the whole run because one item, one feed or the AI summary fails. Degrade, log a warning, keep the last good data.

## 2. Architecture (generic core + adapters; this is "step 4")

```
monitor_core/          # reusable, knows nothing about OzBargain
  model.py             # Item dataclass: id, source, title, url, item_url, image, posted_at,
                       #   metrics: dict[str,float], tags, extra: dict, status flags
  source.py            # Source protocol: fetch() -> list[Item]
  store.py             # snapshot history: load/save state JSON, append snapshot, prune
  scoring.py           # config-driven weighted score + burst + tiers
  summarize.py         # optional AI summary via GitHub Models, cached by item id
  build.py             # run pipeline for one monitor config -> writes site data JSON
  rss.py               # small shared RSS helpers
monitors/
  ozbargain/
    adapter.py         # OzBargain Source (both feeds, merge, dedupe)
    config.json        # weights, thresholds, keywords, summary settings
  hackernews/          # second adapter, proves the core is reusable
    adapter.py         # hnrss.org/frontpage: points + comments from description
    config.json
site/                  # static frontend, one shared app reading a per-monitor JSON
  index.html           # OzBargain page (main product)
  hn.html              # same app, HN config (small, may share app.js)
  app.js, style.css
scripts/run.py         # CLI: python scripts/run.py --monitor ozbargain --state-dir STATE --out OUT
tests/
docs/
  spec/SPEC.md
  NEW_MONITOR.md       # how to add a new monitor in < 1 hour (template guide)
.github/workflows/monitor.yml
```

## 3. OzBargain adapter

Parse each `<item>`:
- id: node number from `<link>` (`/node/984332` -> `984332`).
- title, link (node URL), description (strip HTML to plain text, max 300 chars), image (`ozb:meta image`), merchant url (`ozb:meta url`), pubDate -> posted_at (timezone aware, store ISO UTC), categories (domain contains `/cat/` -> category, `/tag/` -> tags, `/event/` -> events), `dc:creator` if present.
- metrics from `ozb:meta`: `votes_pos`, `votes_neg`, `comments`, `clicks`. Missing attribute -> 0.
- `expiry`, `starting` attributes -> stored.
- `ozb:title-msg type` (seen: `expired`, `upcoming`, `targeted`, likely also `out-of-stock`) -> `flags` list.
- `on_front_page`: true if the item appears in `/feed`.
- Free deal detection: title matches `\bfree\b` or `\$0\b` (case-insensitive) or category `freebies`.
- Merge both feeds by id; if in both, take the higher metric values.

## 4. History, state, and burst detection

- State lives in `STATE_DIR/state.json` (one file per monitor): for each known item: latest item data + list of snapshots `[ts, votes_pos, votes_neg, comments, clicks]`, plus `first_seen`, `last_seen`, cached `summary`.
- Each run appends one snapshot per item seen. Items not seen this run keep their data and get no new snapshot.
- Prune: drop items whose `last_seen` is older than `retention_days` (default 7). Keep at most 96 snapshots per item (2 days at 30 min); thin older ones.
- Burst (per item): compare the latest snapshot with the snapshot closest to `burst_window_minutes` (default 30) ago, but at least 20 and at most 90 minutes old. `delta_votes = Δvotes_pos`, `delta_comments = Δcomments`, `burst_raw = delta_votes + 0.7 * delta_comments`. Burst requires `burst_raw >= burst_min` (default 5) AND per-hour rate ≥ the item's own average rate × `burst_ratio` (default 2). If there is no suitable earlier snapshot, burst = null (not 0) and the UI says "采样中".
- First run has no history: score still works, burst component = 0.

## 5. Score (0–100) and tiers

Configurable in `config.json`. Defaults match the Muse reference:

| component | weight | raw value | normalise |
|---|---|---|---|
| votes | 30 | votes_pos − votes_neg | log-scale: `min(1, log1p(max(v,0))/log1p(v_cap))`, v_cap 300 |
| comments | 25 | comments | log-scale, cap 150 |
| velocity | 25 | net votes per hour since posted (hours floor 0.5) | log-scale, cap 60/h |
| clicks | 10 | clicks | log-scale, cap 5000 |
| burst | 10 | burst_raw | log-scale, cap 40 |

Score = round(sum(weight × normalised)), integer 0–100. Store the per-component breakdown so the UI can explain the score.

Tiers (config):
- `爆火` (viral): score ≥ 70 OR net votes ≥ `viral_votes` (200)
- `热门` (hot): score ≥ 50 OR net votes ≥ `hot_votes` (60)
- `升温` (rising): burst true OR score ≥ 35
- else none.
Expired items: keep in data, flagged, sorted after active ones by default, and never in Top 3.

Watch keywords: item matches if title/tags contain any (case-insensitive) -> `watch_hit: [keywords]`. Block keywords: item gets `blocked: true` (hidden by default in UI, toggle to show). Keyword defaults live in config; the UI lets the viewer override them in localStorage.

## 6. AI summary (GitHub Models, free)

- Endpoint `https://models.github.ai/inference/chat/completions`, auth `Bearer $GITHUB_TOKEN`, workflow permission `models: read`. Model id from config, default `openai/gpt-4.1-mini`; fallback list in config.
- Only for items that (a) have no cached summary, (b) are tier 爆火/热门/升温 or watch hits, (c) at most `summary_max_per_run` (default 8) per run, highest score first.
- Prompt input: title, plain description, price-like strings, categories, merchant domain, net votes, comments. Output JSON: `{"one_liner": "<=40 Chinese characters: what it is and why people like it", "caveat": "<=30 chars, conditions/limits like membership, C&C, minimum spend, or empty"}`. Temperature 0.2. Validate JSON and lengths; on failure store nothing and retry next run.
- If `GITHUB_TOKEN` is absent (local runs, tests) or the API errors/rate-limits, skip silently with a log line. Tests mock the HTTP call.
- Also produce a run-level **"本期速览"** (digest): one call per run at most, max 120 Chinese characters, summarising the Top 3 and any bursts. Cached and only regenerated when the Top 3 set changes.
- The UI marks AI text with a small "AI 摘要" label.

## 7. Output JSON (site data)

`OUT/data/<monitor>.json`:
```json
{
  "monitor": "ozbargain", "title": "...", "generated_at": "ISO UTC",
  "stats": {"total": 44, "viral": 0, "hot": 3, "rising": 5, "free": 4, "bursting": 2,
            "avg_score": 39.6, "total_votes": 1201, "total_comments": 583,
            "feeds": {"deals": "ok", "front": "ok"}},
  "digest": {"text": "...", "ai": true} | null,
  "config_public": {"weights": {}, "thresholds": {}, "watch": [], "block": []},
  "items": [ { id, title, url, item_url, image, posted_at, first_seen, category, tags, events,
               flags, on_front_page, is_free, metrics, score, breakdown, tier, burst,
               watch_hit, blocked, summary, trend: [[ts, net_votes, comments], ...] } ]
}
```
Trend is downsampled to ≤ 24 points. Keep the file < 1.5 MB.

## 8. Frontend (site/)

Reference look: Muse screenshot (warm off-white cards, orange accent, rank badge, score on the right). Must work well at 375 px width (Tracy mostly uses a phone), and in light + dark mode (CSS variables, `prefers-color-scheme`).

1. Header: title "OzBargain 超值 Deal 监控", last refresh time in Sydney time ("x 分钟前"), stale warning if > 90 minutes old.
2. Stats bar (wraps on phone, no truncation): total, 爆火, 热门, 升温, 免费, 正在爆发, 平均分, 总票数, 总评论.
3. Digest box (if any).
4. **爆火榜 Top 3**: rank badge, image, title, tier chips, score, votes/comments/clicks, burst delta, AI one-liner, buttons: 去商家, 看帖子.
5. Filter chips: 全部 / 爆火 / 热门 / 升温 / 正在爆发 / 免费 / 首页 / 收藏 / 关注词命中; search box (title + tags); sort select (热度分, 最新, 票数, 评论, 爆发增量).
6. Deal list cards: as Top 3 plus posted time ("3 小时前"), category, expiry, flags (过期 / 即将开始 / 仅限部分用户), sparkline (inline SVG) of net votes, expandable score breakdown, ☆ 收藏, 隐藏.
7. Favourites and hidden: localStorage, wrapped in try/catch; page works if storage is unavailable. "已隐藏 N 条 · 显示" control.
8. Settings drawer: watch keywords, block keywords, 只看首页 toggle, show expired toggle, reset. Stored in localStorage; defaults from `config_public`. Explain in one line that thresholds/weights are set in `config.json` on GitHub (link).
9. Footer: data from OzBargain public RSS, not affiliated with OzBargain; AI summaries may be wrong; link to repo.
10. Auto reload the JSON every 10 minutes while the page is open; no full page reload.
11. Accessibility: buttons are real buttons, tap targets ≥ 36 px, no horizontal scroll at 375 px.
12. `hn.html`: same app pointed at `data/hackernews.json`, title "Hacker News 热帖监控", no merchant button.
13. A tiny `site/index.html` nav link between monitors is enough; OzBargain is the default page.

## 9. Workflow (.github/workflows/monitor.yml)

- Triggers: `schedule: cron "7,37 * * * *"` (avoid :00 congestion), `workflow_dispatch`, and `push` to main touching code/site.
- permissions: `contents: write`, `pages: write`, `id-token: write`, `models: read`.
- concurrency group `monitor`, cancel-in-progress false.
- **Auto-stop guard**: first step computes Sydney date; if `>= STOP_DATE` (repo variable `STOP_DATE`, default `2027-01-01` in the workflow file), scheduled runs exit early with a notice (manual dispatch still runs). Remove/extend by editing one line.
- Steps: checkout main; checkout the `state` branch into `./state` (create orphan branch on first run if missing); run tests (`python -m unittest`); run both monitors; copy `site/` + generated `data/` into `_site`; commit `state/` to the `state` branch as a single amended commit and force-push (avoids history bloat); upload pages artifact; deploy pages.
- If a monitor fails, the job still deploys with the previous state and the stats `feeds` field shows the error.

## 10. Tests (unittest, offline)

At least: RSS parsing on both OzBargain fixtures (count, id, metrics, flags, merchant url, free detection), merge/dedupe, score bounds and monotonicity, tier rules, burst with synthetic snapshots (no history -> null; real jump -> true; slow steady growth -> false), prune, keyword watch/block, summary module with mocked HTTP (success, bad JSON, HTTP 429, no token), output JSON schema keys, HN adapter on its fixture, end-to-end run of `scripts/run.py` against fixtures via a `--fixtures` flag (no network). Frontend: a Python test that `site/*.html` reference existing files and contain no external `http` script/style URLs.

## 11. Docs

- `README.md` (Chinese first, short English section): what it is, live link, how the score works (table), how bursts work, how to change settings, how to add a monitor, disclaimer.
- `docs/NEW_MONITOR.md`: step-by-step template guide to add a monitor (adapter + config + page), using HN as the worked example; note which kinds of sources fit (public feed/JSON with numeric engagement metrics) and which do not (sites needing login, scraping against robots.txt, data that needs agent research like the Super/ETF page).

## 12. Out of scope (v1)

Push notifications, accounts, server-side favourites, scraping HTML, comments content, paid APIs, any Muse-specific service.

## 13. Definition of done

1. `python -m unittest discover -s tests` passes offline.
2. `python scripts/run.py --monitor ozbargain --fixtures` and the HN equivalent produce valid JSON; opening `site/index.html` via a local static server shows the full UI with that data.
3. A live run (network) against the real feeds works locally.
4. Workflow file is valid YAML and matches §9.
5. Implementation report in `docs/reports/IMPL_REPORT.md`: what was built, deviations from spec with reasons, known gaps, exact commands run and their results.
