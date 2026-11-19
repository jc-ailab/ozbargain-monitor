# PROJECT_CHARTER: ozbargain-monitor

## Why (origin)
On 2026-11-20 Tracy saw two products other people built with the Muse agent app: an OzBargain hot-deal monitor and an Australia Top 100 Super/ETF page. She asked Claude to plan and coordinate a similar product built without Muse, using Codex (and Gemini when useful). She approved: public GitHub repo under `jc-ailab`, build now (before the 11/24 family trip), phases 1–3 first, then the reusable template (step 4) and AI summaries, as one complete product.

## Vision
A small, polished, public product that saves Tracy (and anyone) the time of scanning OzBargain: open the page on a phone, see what is hot or suddenly blowing up, in 10 seconds. Second goal: prove a reusable "source -> snapshot -> score -> page" pattern so new monitors take an hour, not a day.

## Relation to the mainline
Side project. The CBA mainline is not affected (EOI submitted 2026-11-20). Rule: it must not take Tracy's attention during the trip (11/24–12/27). The scheduled refresh stops automatically on 2027-01-01.

## Decision rights
- Claude (architect/reviewer): spec, technical choices, review and acceptance testing, merge.
- Codex (implementer): implementation inside the spec. Never approves its own code.
- Tracy (PO): product direction, anything public beyond this repo, new paid services, new credentials, deleting the repo.
- No secrets in the repo. AI summaries use GitHub Models with the built-in `GITHUB_TOKEN` only.

## Working habits
- Spec in `docs/spec/`, implementation report in `docs/reports/`, review in `docs/reviews/`.
- Honest status words: designed / implemented / verified / operational.
- Tests offline from fixtures; be polite to OzBargain (RSS only, 2 requests per 30 min).

## Candidate next steps (after v1)
1. Watch-keyword alerts (e.g. a GitHub issue or email digest) if Tracy finds herself checking often.
2. A third monitor using the template, chosen by Tracy.
3. Tune score weights after a week of real data.
