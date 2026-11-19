# Implementation report

Date: 2026-11-20 (Australia/Sydney)
Implementer: Codex. Branch: `main`. No push, GitHub repository creation or deployment was performed.
Authority: [PROJECT_CHARTER.md](../PROJECT_CHARTER.md) and [SPEC.md](../spec/SPEC.md), both read in full before implementation.

## Objective and result

Implement spec sections 1–13: a polished Chinese OzBargain monitoring page, plus a reusable source → snapshot → score → page core demonstrated by Hacker News. This is a side project intended to save attention during the family trip; the workflow stops scheduled refreshes from 2027-01-01 Sydney time.

**Implemented and locally verified; ready for independent review.** Both live sources succeeded, all 25 offline Python tests pass, fixture output is served successfully, and JS rendering/interactions pass the browser-free smoke checks. This report records implementation evidence, not architect approval or operational acceptance. The charter assigns review/acceptance to Claude and product/publication decisions to Tracy.

## What was built

| Spec | Implementation |
| --- | --- |
| 1–2 | Python standard library only; source-neutral `Item`, source protocol, RSS utilities, atomic state, configurable scoring, optional summaries, generic build and CLI. Vanilla frontend with no external script/style resources. |
| 3 | Both official OzBargain feeds, namespaces, UTC dates, plain descriptions, direct merchant URLs, images, metrics, categories/tags/events, creator, expiry/starting, flags, free detection, front-page membership and max-metric deduplication. No item/merchant pages fetched. |
| 4 | Per-monitor `state.json`, first/last seen, per-seen-item snapshots, 7-day retention, bounded/thinned 96-point history, nearest eligible 20–90-minute comparison and self-relative bursts. No-history burst is null. |
| 5 | Configured log scoring and component breakdown, tiers, watch/block matching, expired ordering and Top 3 exclusion. |
| 6 | GitHub Models JSON requests, configured model/fallbacks, validated Chinese length limits, cached item summaries, candidate cap, rate-limit/auth degradation, Top 3-set digest cache and at most one digest call per run. No-token and fixture modes make no AI calls. |
| 7 | Per-monitor site JSON, complete statistics/feed health, public config, summaries, <=24-point trends, bounded output size and stale-data timestamps. |
| 8 | Shared Chinese OzBargain/HN app: warm cards, orange accents, mobile grid, dark mode, Top 3, all specified filters/search/sorts, local favourites/hidden/settings, sparkline, expandable score breakdown, expiry/flags, AI labels, source attribution, monitor navigation and timed JSON refresh. |
| 9 | Guarded schedule/manual/main-code-push workflow, required permissions, serial concurrency, main + orphan state worktree, offline tests, both monitors, last-publication fallback, single amended state commit, Pages artifact and deployment steps. |
| 10 | Offline unittest fixtures, malformed inputs, merge, score/tier/keyword/burst/store checks, mocked AI success/failure/429/token/limits/fallback/cache, output/CLI, source failure isolation, frontend assets/IDs, guard and actual state-branch shell integration. |
| 11 | Chinese-first README with scoring table and English section; worked HN adapter/template guide in `docs/NEW_MONITOR.md`. |
| 12 | Scope kept to the specified feed-based static product. |
| 13 | Reproducible commands and evidence below; remaining acceptance boundaries listed explicitly. |

Implementation commits:

- `380e82f` — reusable pipeline and initial tests.
- `5680445` — responsive Chinese interface and static checks.
- `1a99b1c` — failure isolation, browser-free JS smoke checks and served-site checker.
- `dab8b5b` — guarded workflow, recovery, documentation and timezone validation.
- This report is committed separately after implementation verification. All implementation/report commit messages include the requested Codex co-author trailer.

## Deviations / decisions

1. **Request-budget ambiguity:** “two feed requests per run” takes precedence over the separate “one retry” instruction. A shared two-attempt budget includes retries. If the first OzBargain feed consumes both attempts, the second reports a budget error and previous records remain. Redirects are rejected to avoid hidden extra requests or disallowed routes. The normal successful path fetches both feeds once.
2. **Burst baseline:** average rate uses the entire observed snapshot span, including the current comparison window, because the spec does not define another baseline. With only two points, window rate equals average and normally cannot satisfy the 2× requirement. The score still uses measured `burst_raw` whenever a valid comparison exists; the rising tier's burst rule requires `is_burst`.
3. **History thinning:** retain the newest 64 points densely, evenly sample older points into 32 slots, and preserve the earliest/latest endpoints. Published trends evenly sample the resulting history to 24 points; the SVG uses elapsed time for the horizontal axis.
4. **Staleness:** `generated_at` records the last run with at least one successful feed. Added `checked_at` and item `last_seen` clarify attempted refresh versus observed data. Unseen items keep their metrics, receive no snapshot and do not retain a current burst badge. Expiry timestamps additionally mark elapsed deals expired even when an RSS flag is absent.
5. **Settings defaults:** watch/block lists start empty. Expired posts are visible at the end by default, matching the sorting requirement; blocked/hidden posts are hidden by default. Settings reset preserves favourites/hidden lists. Stats and the AI digest describe the overall server sample; list chips/search/sort affect the list, while Top 3 uses basic visibility/settings and score.
6. **Totals and HN:** `total_votes` is the sum of net votes. HN points map to positive votes; negative votes/clicks are zero. HN retains the reference weights, so absent clicks contribute zero. It has discussion and original-article links, with no merchant button.
7. **AI failure handling:** fallback models apply to item summaries; 401/403/429 stop enrichment for that run to avoid repeated rejected calls. Digest generation has one request at most, without a second-model retry. A digest for a different Top 3 set is retained in state but not published as current.
8. **Recovery and output size:** previous published JSON is stored on the state branch as well as in the state file. Unexpected CLI failure annotates the previous publication; a first-ever failure emits an explicit empty error document. If output approaches 1.5 MB, reduce trend detail first; if still too large, preserve last-good output rather than silently truncate records. Unreadable state files are not overwritten.
9. **Offline safety:** default fixture/live histories are separate; fixture mode disables AI even when a token exists. Generated `site/data/` and local history are ignored by Git. Each monitor requires its own explicit state directory.
10. **Workflow guard structure:** a first guard job prevents the entire publish job after the scheduled stop date. A state-branch lookup transport failure aborts instead of being mistaken for a missing branch. The state shell was tested for first-run empty monitor directories as well as subsequent amendment.
11. **Verification boundary:** no browser was used, as instructed. Static responsive/dark-style checks, served-resource checks and executed JS against a small DOM stub provide useful evidence but do not establish visual layout or real browser behaviour. Local `python3` is 3.14.8; Python 3.12 is configured in Actions but was not installed locally. Production code uses only standard-library APIs available in 3.12.
12. **Repository scope:** no Shared Context/memory/outbox writes were made because this task explicitly forbids touching outside this repository (apart from the requested temporary live outputs and test scratch files). Durable handoff is this report and Git. No owner-level fact needs promotion to long-term memory.

## Exact verification commands and results

Run from the repository root unless noted. Earlier test iterations corrected fixture-count expectations (actual counts: 30 new, 20 front, 48 unique merged) and added regression coverage; results below are the final checks.

### Offline suite

```sh
python3 -m unittest discover -s tests
```

**PASS: 25 tests, OK.** Deliberately malformed items, unavailable feeds and simulated AI failures log expected warnings. All source/API calls in tests are fixtures/mocks; the Git integration test uses a temporary local bare remote, not GitHub. The suite also executes the workflow's actual stop-guard Python for stopped/future/manual/push cases, and actual state checkout/amend/push shell for two cycles, asserting one state commit and unchanged main content.

```sh
node --check site/app.js
node tests/frontend_smoke.js site
```

**PASS:** JS syntax; four smoke scenarios (both monitors × storage available/denied). Checks include rendering, source-specific buttons, search-empty state, favourites, hidden/show-hidden, keyword settings/reset, escaping/unsafe URLs, refresh timers and retention of displayed data after fetch failure. Node is a development check only, not a product dependency.

### Fixture runs and local HTTP

```sh
python3 scripts/run.py --monitor ozbargain --fixtures
python3 scripts/run.py --monitor hackernews --fixtures
python3 -m http.server 8000 --bind 127.0.0.1 --directory site
```

The server ran in a separate tool session while the following command executed:

```sh
python3 scripts/check_site.py
```

**PASS:** `index.html` and `hn.html`, their local CSS/JS, and both data files returned HTTP 200. Every one of the 28 literal element IDs used by JS exists in each HTML page. No duplicate IDs or external script/style references. Fixture results: OzBargain 48 items, feeds `deals=ok, front=ok`; HN 20 items, `front=ok`. Final checked fixture JSON sizes: 66,022 and 24,338 bytes, well below 1.5 MB. Data remains locally under ignored `site/data/` for preview. Server stopped after verification.

### Live runs

```sh
python3 scripts/run.py --monitor ozbargain --state-dir /tmp/ozb-state --out /tmp/ozb-out
python3 scripts/run.py --monitor hackernews --state-dir /tmp/hn-state --out /tmp/hn-out
```

**PASS, confirmed from the JSON health fields, not just process exit codes:**

| Monitor | Result | Live requests | JSON evidence |
| --- | --- | ---: | --- |
| OzBargain | 48 merged items; both feeds `ok` | **2 total during this entire session**, no retry | `/tmp/ozb-out/data/ozbargain.json`, 64,261 bytes, `generated_at=2026-11-19T20:26:23.351786Z` |
| Hacker News | 20 items; front feed `ok` | 2 attempts: first logged `URLError`, one retry succeeded | `/tmp/hn-out/data/hackernews.json`, 22,956 bytes, `generated_at=2026-11-19T20:26:23.351782Z` |

AI logged `GITHUB_TOKEN absent` and skipped calls. No additional OzBargain checks were made; fixture/offline checks made no live feed requests.

### YAML and repository hygiene

```sh
ruby -e 'require "yaml"; workflow=YAML.load_file(".github/workflows/monitor.yml"); abort "missing triggers" unless workflow.fetch("on").keys.sort == %w[push schedule workflow_dispatch]; abort "bad jobs" unless workflow.fetch("jobs").keys.sort == %w[guard publish]; puts "PASS valid YAML; triggers, jobs and permissions parsed"'
git diff --check
python3 --version
```

**PASS:** valid YAML, expected trigger/job structure, required permissions present; no whitespace errors. Local Python: **3.14.8**. Ruby is only used for local YAML validation; neither pipeline nor tests require it. GitHub's hosted workflow validator/execution was not run. All commits are local to the existing branch and use the requested trailer; no push was performed.

## Known gaps and acceptance handoff

- No rendered-browser visual inspection at 375 px, screenshot, or real-browser accessibility/localStorage test. The CSS has a three-column wrapping mobile stats grid, single-column deal cards, wrapping controls, safe text wrapping, >=36 px buttons, dark variables, focus outlines and reduced-motion support; actual visual acceptance remains for the reviewer.
- Real GitHub Models calls were not attempted because no built-in workflow token is available locally. JSON validation, fallback/cap/cache behaviour and failures are verified with mocks.
- Python 3.12 execution, the hosted schedule, repository permissions, remote state push and Pages deployment remain unverified in GitHub. YAML and executable guard/state logic are locally verified.
- First-run live data cannot prove sustained burst detection or scheduled refresh reliability. Synthetic histories cover burst rules; operational evidence requires later scheduled samples.

No product decision is needed to review this implementation. Recommended next steps, in order:

1. Claude reviews against the charter/spec and performs real 375 px light/dark and keyboard checks; this supplies independent acceptance and catches visual issues the permitted local checks cannot see.
2. After review and Owner-authorised publication, enable Pages via GitHub Actions and run one manual workflow. Verify Python 3.12 tests, built-in token/model access, single-commit state branch and published JSON without adding credentials.
3. Observe scheduled samples before claiming operational readiness. Keep the existing stop date; consider weight tuning only after enough real data, as suggested by the charter.

Session handoff: built and locally verified the complete specified scope; new evidence is two successful live sources plus 25 offline tests; decisions are recorded above; remaining issues are independent visual/hosted/AI acceptance; next action belongs to the reviewer. Long-term memory proposal: none; retain project facts in this report and Git.
