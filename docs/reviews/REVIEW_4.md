# Review 4: first live run (Claude Opus 5.5, 2026-11-20)

Run https://github.com/jc-ailab/ozbargain-monitor/actions/runs/44621060409 (workflow_dispatch).
- OK: guard, tests, both monitors (OzBargain 45 items, feeds ok), state branch created, artifact `github-pages` uploaded (31 KB).
- FAIL: Deploy Pages: "No artifacts named github-pages were found". upload-pages-artifact@v3 + deploy-pages@v4 are mismatched with the current artifact backend.
- FAIL: every AI call -> JSONDecodeError. Cause (architect's error in SPEC §6): **GitHub Models was retired on 2026-07-30**; models.github.ai now returns a text/plain placeholder. Each run also wasted ~33 calls because a non-JSON response does not stop the loop.

## Required

R8. Upgrade workflow actions to current majors: actions/checkout@v7, actions/setup-python@v7 (latest releases: v7.0.1 and v7.1.0), actions/upload-pages-artifact@v5, actions/deploy-pages@v5 (check each action's README for changed inputs). This should also clear the Node 20 deprecation warnings.

R9. AI provider becomes pluggable and **off by default**:
- config `summary.provider`: `"none"` (default) or `"gemini"`. Gemini uses the official REST `generateContent` endpoint with an API key read from env `GEMINI_API_KEY` (workflow passes `secrets.GEMINI_API_KEY`), model id from config (default `gemini-3.8-flash`), JSON response via `responseMimeType: application/json`. If provider is none or the key is missing, skip with one log line and zero network calls.
- Circuit breaker: after the first failed call in a run for ANY reason (HTTP error, timeout, non-JSON, invalid shape), stop all AI calls for that run.
- Remove GitHub Models code and the `models: read` permission. Update SPEC §6 note, README and tests (mock HTTP, no network).

R10. Deterministic "条件" chips (works with no AI): parse the title/description for common conditions and show them as small chips on cards: `Prime 免运`/`需 Prime` (Prime), `自提 C&C` (C&C, Click & Collect), `满 $N 免运` (e.g. "$59 Spend", "$150 Order"), `会员/定向` (targeted flag, "members"), `即将开始` (upcoming), `需激活` ("Activate"), `返现` (cashback). Keep it conservative; test with the real titles in fixtures. When an AI caveat exists, show it in addition.

Keep: stdlib only, offline tests green, check_layout 8/8 PASS (re-run it), commit with Codex trailer, no push.
