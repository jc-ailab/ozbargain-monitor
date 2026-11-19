"""Conservative RSS-only condition hints; no inference from price alone."""
import re

MONEY = r'(\d+(?:,\d{3})*(?:\.\d{1,2})?)'


def condition_chips(title, description='', flags=()):
    chips = []
    # Match within each field, never join unrelated title/description fragments.
    texts = (title, description)
    def has(pattern):
        return any(re.search(pattern, text, re.I) for text in texts)

    if has(r'\$0(?:\.00)?\s*(?:with\s+)?prime\b|\bfree\s+(?:delivery|shipping)\s+(?:with|for)\s+prime\b|\bprime\s+free\s+(?:delivery|shipping)\b'):
        chips.append('Prime 免运')
    elif has(r'\b(?:with|requires?|for)\s+(?:amazon\s+)?prime\b|\bprime\s+(?:only|members?)\b|[\[(]\s*(?:amazon\s+)?prime\s*[\])]'):
        chips.append('需 Prime')
    if has(r'\bc\s*&\s*c\b|\bclick\s*(?:&|and)\s*collect\b'):
        chips.append('自提 C&C')

    for text in texts:
        # OzBargain delivery shorthand: ($0 Prime/$59 Spend),
        # ($0 C&C/$130 Order), ($0 with $150 Order).
        if re.search(r'\b(?:delivery|shipping|postage)\b', text, re.I):
            for group in re.findall(r'\(([^()]*)\)', text):
                if re.search(r'\$0(?:\.00)?(?![\d.])\s*(?:(?:with\s+)?prime\b|c\s*&\s*c\b|(?:with\s+)?\$\d)', group, re.I):
                    for amount in re.findall(r'\$' + MONEY + r'\s*(?:metro\s+)?(?:spend|order)\b', group, re.I):
                        chips.append(f'满 ${amount} 免运')
        # Explicit prose, e.g. free shipping on orders over $59.
        for amount in re.findall(r'\bfree\s+(?:delivery|shipping|postage)\s+(?:on\s+)?(?:orders?\s+)?(?:over|above|from|of\s+at\s+least)\s+\$' + MONEY, text, re.I):
            chips.append(f'满 ${amount} 免运')
    if 'targeted' in flags or has(r'\b(?:members|targeted)\b'):
        chips.append('会员/定向')
    if 'upcoming' in flags or has(r'\bupcoming\b'):
        chips.append('即将开始')
    if has(r'\bactivate\b|\bactivation\s+required\b'):
        chips.append('需激活')
    if has(r'\bcashback\b'):
        chips.append('返现')
    return list(dict.fromkeys(chips))
