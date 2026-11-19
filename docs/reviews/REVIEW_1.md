# Review 1 (Claude Opus 5.5, 2026-11-20)

Verdict: CHANGES REQUESTED. Tests pass (25/25) and a live run works (48 items, both feeds ok). Desktop UI in dark mode is good. Fix the items below, in order.

## Must fix

R1. **Horizontal overflow on phones (critical).** Headless Chrome at 390px width: the page is wider than the viewport. The Top 3 score block, the right side of titles, the nav tabs, the search sort select and the filter chips are cut off on the right; the "总票数" stat wraps as "162 / 0". Fix the layout so nothing overflows at 360, 375 and 390px (min-width:0 on grid/flex children, wrap long words with overflow-wrap:anywhere, stats grid that fits, score visible in Top 3 and list cards on phone). Use compact numbers in stats when needed (e.g. 1.6k).
   Verification you must run: Chrome is at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`. Add a `scripts/check_layout.py` that serves a fixture build, runs headless Chrome (`--headless=new --window-size=W,2400 --virtual-time-budget=5000 --dump-dom`) for W in 360, 375, 390, 1300, and fails if the page reports overflow. To report it, have app.js set `document.documentElement.dataset.overflow = String(document.documentElement.scrollWidth > window.innerWidth)` after render when the URL has `?layoutcheck=1`. Also save screenshots to /tmp for the record. Run it and include the results in the report. This script is a dev tool, not part of the unittest run (CI has no Chrome).

R2. **Free detection false positives.** Live data: 16 of 48 flagged free, almost all because of "+ Delivery ($0 C&C)" or "$0 Prime". A deal is free only if the deal itself costs nothing: title (after removing parenthesised text and any "+ Delivery/Shipping/Postage ..." tail) contains a standalone "Free" not followed by delivery/shipping/postage/returns, or a price of "$0"/"$0.00" as the main price, or category Freebies. Add tests with these real titles: "Westinghouse 10kg Front Load Washer $645 ($632 via Price-Check Button) + Delivery ($0 C&C)" -> not free; "Muscle Nation Vegan Protein Bar 12-Pack $24 (RRP $54) + Delivery ($0 Prime/$59 Spend) @ Am" -> not free; "[PC, Epic] Free - Bread and Fred @ Epic Games" -> free; "[eBook] Free - Throne Hunters Books 1-5 by Phil Tucker @ Amazon AU & US" -> free; "Free Delivery on All Orders @ X" -> not free.

R3. **Stale items on the page.** State keeps items for 7 days, and every stored item is published. Items that left both feeds have frozen metrics, so over a few days the page fills with hundreds of stale deals and stats inflate. Publish only items whose `last_seen` is within `display_hours` (config, default 36). Keep longer retention in state for history. In the card, if an item is not in the current run's feeds, show "已离开 feed · 数据截至 <time>". Stats count only published items. Test it.

R4. **Tier thresholds too loose.** Live: 14 of 48 are 热门. Change defaults to hot_score 55, hot_votes 80, rising_score 40. Update README score table if it lists them.

## Should fix

R5. In the Top 3 cards on phone, keep the action buttons on one row if they fit, otherwise wrap cleanly; no button may be cut off.
R6. Broken or blank images (e.g. the Coles deal shows an empty white box): show a neutral placeholder with the first letter of the merchant/category when the image fails (`onerror`) or is missing.

## Notes (no change needed)
- Retry counted within the 2-request budget: agreed.
- Workflow guard and orphan state branch logic look right; will be verified on the first real run.
