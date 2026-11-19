# Add a monitor in under an hour

The reusable pattern is public structured source → `Item` records → persistent snapshots → scores → shared static UI. Read [PROJECT_CHARTER.md](PROJECT_CHARTER.md) and [spec/SPEC.md](spec/SPEC.md) before extending scope.

## 1. Choose an appropriate source (5 minutes)

Use a public RSS feed or public JSON endpoint with stable IDs, timestamps and numeric engagement metrics. Follow the source's published access rules and request limits. Never add a login, secret credential, robots-disallowed scraping or HTML-page crawler to v1. A Super/ETF comparison requiring research, financial judgement and different data semantics does not fit this engagement monitor.

## 2. Copy the HN adapter (10 minutes)

Create `monitors/example/__init__.py`, `adapter.py`, and `config.json`. `Source(fixture_dir=None)` must implement `fetch() -> list[Item]` and expose `feeds: dict[str, str]` health after fetching. `scripts/run.py` discovers config directories automatically. Do not edit `monitor_core` for source-specific parsing.

HN's worked example is [adapter.py](../monitors/hackernews/adapter.py):

- Feed: `https://hnrss.org/frontpage`, loaded with shared `read_feeds`.
- Stable ID: `id` query parameter of the discussion URL.
- `url`: discussion, `item_url`: original article. No merchant button on the HN page.
- `posted_at`: timezone-aware RSS pubDate converted to UTC.
- `metrics`: `votes_pos` = Points, `votes_neg` = 0, `comments` = # Comments, `clicks` = 0.
- Missing metrics default to 0. Malformed individual items log a warning and are skipped.
- `extra`: plain `description` ≤300 characters, `category`, `events`, `on_front_page`, `is_free`; optionally `expiry`, `starting`, `creator`.
- `tags` and `flags` are lists; `expired` is the shared expiry flag.

A JSON source can return the same `Item` objects without using RSS helpers. Keep HTTP requests bounded and handle feed errors independently. Pass fixture files when `fixture_dir` is provided; fixture mode must never use network or AI.

## 3. Configure scoring (5 minutes)

Copy [HN config](../monitors/hackernews/config.json). Set `monitor` and Chinese `title`, weights, caps, tier thresholds, burst window/minimum/ratio, watch/block keywords, retention and summary model/fallbacks. Weights should sum to 100, all caps must be positive. Core metrics have stable names; sources without clicks can set that weight to 0 and redistribute it. The bundled HN example retains the reference scoring weights to show the same scoring pipeline; missing clicks contribute zero.

Each record is stored in `STATE_DIR/state.json`; use **separate state directories for each monitor**. Disappearing items retain their last data until retention elapses, without inventing samples. The complete observed history defines average burst rate. Snapshots retain the newest 64 densely and sample the older history into 32 slots (max 96); published trend is sampled across time to ≤24 points.

## 4. Add a page (10 minutes)

Copy `site/hn.html` to `site/example.html`. Set `body data-monitor="example"`, title, source attribution, navigation and config link. It reads `data/example.json`. All pages use the same `app.js` and `style.css`, without external script/style URLs. The existing app provides generic post links, metrics, filters, settings and summaries. Only the OzBargain page has a merchant action. Add the monitor to the workflow loop and state `git add` list. Add a nav link if useful.

## 5. Test offline, then once live (10–20 minutes)

Save a public sample in `tests/fixtures/`. Add parsing assertions for known IDs, counts, metrics and missing / malformed fields. Run:

```sh
python3 -m unittest discover -s tests
python3 scripts/run.py --monitor example --fixtures --state-dir .state/fixtures/example --out site
python3 -m http.server 8000 --directory site
```

Check that `http://localhost:8000/data/example.json` loads and that every JS element ID exists on the new page (the included frontend test does this). Verify 375 px layout, keyboard navigation, light/dark mode, empty/error/stale states, and absent localStorage. Run one polite live sample after checking the source request policy. Record exact results in the implementation report; do not claim visual QA or deployment from static checks alone.

## 6. Deployment

Actions checks out main and a separate orphan `state` worktree. It preserves each monitor's `state.json` and previous published JSON, runs offline tests and both pipelines, then amends and force-pushes a **single state commit** before publishing Pages. Feed failures retain previous records and expose health in the JSON. Unexpected pipeline failures use `scripts/fallback.py` to annotate the previous publication or emit an explicit empty first-run error document.

Use only built-in `GITHUB_TOKEN`; no new credentials or paid services. The Sydney `STOP_DATE` guard applies to scheduled runs only. Extending the schedule or publishing beyond this repository requires the Owner's decision under the charter.
