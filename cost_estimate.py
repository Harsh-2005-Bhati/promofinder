"""Cost / scale estimate for the LLM judge step (rules-only is free).

    python cost_estimate.py data/input.zip [--shows-per-week 10] [--out-tokens 4000]

Input tokens are measured from the real prompts (characters / 4, the usual English approximation).
Output tokens per call are an assumption (JSON for 5 candidates is ~600 tokens; thinking models add
reasoning tokens that are billed as output), so the table shows a low and a high case.
Prices: Gemini 3.8 Flash paid tier, Google pricing page (Nov 2026): $0.75 in / $3.75 out per 1M tokens
until 31 Dec 2026, $1.50 / $7.50 from 1 Jan 2027; Batch API is 50 % cheaper. INR at ~95 per USD.
"""
import argparse

from promofinder.parser import parse_any
from promofinder.prompts import build_prompt
from promofinder.scoring import episode_candidates

PRICE_IN, PRICE_OUT = 1.50, 7.50  # $/1M tokens, 2027 list price (the higher one)
USD_INR = 95.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--shows-per-week", type=int, default=10)
    a = ap.parse_args()
    eps, _ = parse_any(a.src)
    n = max(e.num for e in eps)
    in_tok = [len(build_prompt(e, episode_candidates(e, n)[0])) / 4 for e in eps]
    per_ep_in = sum(in_tok) / len(in_tok)
    print(f"episodes {len(eps)}, measured input tokens/episode: mean {per_ep_in:,.0f}, max {max(in_tok):,.0f}")
    print(f"{'output tokens/call':>20} {'₹/episode':>10} {'₹/show':>8} {'₹/week std':>11} {'₹/week batch':>13}")
    for out in (1000, 4000):
        usd = per_ep_in * PRICE_IN / 1e6 + out * PRICE_OUT / 1e6
        ep_inr = usd * USD_INR
        show = ep_inr * len(eps)
        week = show * a.shows_per_week
        print(f"{out:>20,} {ep_inr:>10.2f} {show:>8.0f} {week:>11,.0f} {week / 2:>13,.0f}")


if __name__ == "__main__":
    main()
