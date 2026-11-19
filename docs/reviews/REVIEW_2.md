# Review 2 (Claude Opus 5.5, 2026-11-20)

Verdict: APPROVE WITH ONE REQUIRED FIX. 29/29 tests pass on my machine. Second live run: 50 items, free = 4 (all correct), tiers 3/6/11. Real-width phone render (375px iframe) has no overflow and the Top 3 scores are visible.

## Required

R7. **`scripts/check_layout.py` does not test phone widths.** Headless Chrome on macOS clamps the window to a minimum width of 500px: a page that prints `innerWidth` at `--window-size=375,800` reports `W=500`. So every 360/375/390 PASS in Round 2 was really a 500px test. Fix: load the page inside an iframe of the exact width (e.g. a generated wrapper page `<iframe src="index.html?layoutcheck=1" style="width:Wpx;height:2400px;border:0">` served from the same origin, window 500 or 1300 wide) and read overflow from the iframe document; also assert the iframe's `innerWidth == W`, so this can't silently pass again. Keep screenshots. Run it and report the real results; fix any overflow it finds.

## Notes
- The free false positive I saw on "Muscle Nation" came from state written by the Round 1 code; `free_deal()` returns False on that title now. No change needed.
