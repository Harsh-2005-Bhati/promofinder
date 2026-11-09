"""Deterministic checks for every promo. Failing promos are flagged, never silently fixed."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .candidates import blocks_in, spanning_dialogue, MIN_DUR, MAX_DUR, EPS
from .models import Promo
from .parser import Episode

HARD_CHECKS = [
    "seg_start_ge_end", "seg_out_of_bounds", "duration_out_of_range", "segments_overlap",
    "segments_out_of_order", "cut_inside_dialogue", "no_hook_block_first_3s", "unknown_episode",
]
SOFT_CHECKS = ["hook_text_not_in_window", "cliffhanger_text_not_in_window"]
FUZZY_MIN = 0.8


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", re.sub(r"\s+", " ", (t or "").lower())).strip()


def fuzzy_in(needle: str, texts: list[str]) -> float:
    """Best similarity of needle against any block text, or any same-length token window of it."""
    n = _norm(needle)
    if not n:
        return 0.0
    best = 0.0
    nt = n.split()
    for t in texts:
        h = _norm(t)
        if not h:
            continue
        if n in h:
            return 1.0
        best = max(best, SequenceMatcher(None, n, h).ratio())
        ht = h.split()
        k = len(nt)
        if len(ht) > k:
            for i in range(0, len(ht) - k + 1):
                best = max(best, SequenceMatcher(None, n, " ".join(ht[i:i + k])).ratio())
    return best


def validate(promo: Promo, eps: dict[int, Episode]) -> list[str]:
    flags: list[str] = []
    segs = promo.segments
    for seg in segs:
        ep = eps.get(seg.ep)
        if ep is None:
            flags.append("unknown_episode")
            continue
        if seg.start >= seg.end:
            flags.append("seg_start_ge_end")
        if seg.start < -EPS or seg.end > ep.duration + EPS:
            flags.append("seg_out_of_bounds")
        for t in (seg.start, seg.end):
            if spanning_dialogue(ep, t):
                flags.append("cut_inside_dialogue")
    total = sum(s.end - s.start for s in segs)
    if not (MIN_DUR - EPS <= total <= MAX_DUR + EPS):
        flags.append("duration_out_of_range")
    for a, b in zip(segs, segs[1:]):
        if (b.ep, b.start) < (a.ep, a.start):
            flags.append("segments_out_of_order")
        if a.ep == b.ep and b.start < a.end - EPS and a.start < b.end - EPS:
            flags.append("segments_overlap")
    # hook: a DIALOGUE/ACTION block must start within the first 3 s of the promo
    first = segs[0]
    ep = eps.get(first.ep)
    if ep is not None:
        lim = first.start + 3.0
        if not any(b.is_line and first.start - EPS <= b.start < lim for b in ep.blocks):
            flags.append("no_hook_block_first_3s")
    # hallucination check: texts must appear in the promo window(s)
    texts = []
    for seg in segs:
        ep = eps.get(seg.ep)
        if ep:
            texts += [b.text for b in blocks_in(ep, seg.start, seg.end)]
    if promo.hook_text and fuzzy_in(promo.hook_text, texts) < FUZZY_MIN:
        flags.append("hook_text_not_in_window")
    if promo.cliffhanger_text and fuzzy_in(promo.cliffhanger_text, texts) < FUZZY_MIN:
        flags.append("cliffhanger_text_not_in_window")
    return sorted(set(flags))


ALL_CHECKS = HARD_CHECKS + SOFT_CHECKS


def passes(flags: list[str]) -> bool:
    """True if no validator check failed (informational llm_* flags don't count)."""
    return not any(f in ALL_CHECKS for f in flags)
