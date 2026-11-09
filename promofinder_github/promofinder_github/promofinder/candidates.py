"""Deterministic candidate windows snapped to block boundaries. All times come from parsed blocks."""
from __future__ import annotations

from .models import Segment
from .parser import Episode

MIN_DUR, MAX_DUR = 20.0, 60.0
END_PAD = 0.3
EPS = 0.01


def spanning_dialogue(ep: Episode, t: float):
    """Dialogue blocks that strictly contain time t (a cut at t would split the line)."""
    return [b for b in ep.blocks if b.kind == "DIALOGUE" and b.start + EPS < t < b.end - EPS]


def snap_start(ep: Episode, s: float) -> float:
    for _ in range(10):
        sp = spanning_dialogue(ep, s)
        if not sp:
            return s
        s = min(b.start for b in sp)
    return s


def snap_end(ep: Episode, e: float, anchor_end: float) -> float:
    """Pad may land inside the next line: first shrink the pad back toward the anchor; if a line still
    spans (an overlapping line), extend to its end."""
    for _ in range(10):
        sp = spanning_dialogue(ep, e)
        if not sp:
            return e
        earliest = min(b.start for b in sp)
        if earliest >= anchor_end - EPS:
            e = max(anchor_end, earliest)
        else:
            e = max(b.end for b in sp)
    return e


def blocks_in(ep: Episode, s: float, e: float):
    """Blocks that overlap [s, e]."""
    return [b for b in ep.blocks if b.end > s + EPS and b.start < e - EPS]


def make_segment(ep: Episode, s: float, e: float) -> Segment | None:
    inside = blocks_in(ep, s, e)
    if not inside:
        return None
    return Segment(ep=ep.num, start=round(s, 2), end=round(e, 2),
                   first_idx=min(b.idx for b in inside), last_idx=max(b.idx for b in inside))


def segment_from_indices(ep: Episode, first_idx: int, last_idx: int) -> Segment | None:
    """Used for LLM adjustments: indices -> times (start of first block, end of last block + pad, snapped)."""
    if not (0 <= first_idx <= last_idx < len(ep.blocks)):
        return None
    s = snap_start(ep, ep.blocks[first_idx].start)
    anchor = max(b.end for b in ep.blocks[first_idx:last_idx + 1])
    e = snap_end(ep, min(anchor + END_PAD, ep.duration), anchor)
    return make_segment(ep, s, e)


def generate(ep: Episode, min_dur=MIN_DUR, max_dur=MAX_DUR) -> list[Segment]:
    starts = sorted({b.start for b in ep.blocks if b.kind in ("DIALOGUE", "ACTION")})
    ends = sorted({(b.end, min(b.end + END_PAD, ep.duration)) for b in ep.blocks
                   if b.kind in ("DIALOGUE", "ACTION", "SFX")})
    out, seen = [], set()
    for s0 in starts:
        s = snap_start(ep, s0)
        for anchor, e0 in ends:
            if e0 - s < min_dur - 1 or e0 - s > max_dur + 1:
                continue
            e = snap_end(ep, e0, anchor)
            d = e - s
            if not (min_dur <= d <= max_dur):
                continue
            key = (round(s, 2), round(e, 2))
            if key in seen:
                continue
            seen.add(key)
            seg = make_segment(ep, s, e)
            if seg:
                out.append(seg)
    return out
