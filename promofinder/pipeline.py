"""End-to-end orchestration shared by the CLI and the Streamlit app."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from . import features
from .candidates import END_PAD, snap_end, make_segment, spanning_dialogue
from .models import Promo
from .parser import Episode, parse_zip
from .scoring import episode_candidates, rank, total, why_text, WEIGHTS, apply_llm
from .validate import validate, passes

COLD_HOOK_MAX = 6.0


@dataclass
class RunResult:
    episodes: list[Episode]
    promos: list[Promo]
    cold_opens: list[Promo]
    warnings: list[str]
    meta: dict = field(default_factory=dict)


def cold_opens(ep: Episode, top: list[Promo]) -> list[Promo]:
    """Stretch: hook segment (≤6 s, highest-hook line earlier in the episode) + main segment ending on the
    best cliffhanger. Same episode, segments in time order, non-overlapping, total 20–60 s."""
    if not top:
        return []
    main = max(top, key=lambda p: p.scores["cliffhanger"])
    mseg = main.segments[0]
    best = None
    for b in ep.blocks:
        if not b.is_line or b.end > mseg.start - 0.01:
            continue
        e = snap_end(ep, min(b.end + END_PAD, mseg.start, ep.duration), b.end)
        if e - b.start > COLD_HOOK_MAX or spanning_dialogue(ep, b.start):
            continue
        seg = make_segment(ep, b.start, e)
        if seg is None:
            continue
        h, _, ht = features.hook(ep, seg, [x for x in ep.blocks if x.start >= seg.start - 0.01 and x.end <= seg.end + 0.01])
        if best is None or h > best[0]:
            best = (h, seg, ht)
    if not best:
        return []
    h, hseg, ht = best
    dur = hseg.duration + mseg.duration
    if not (20 <= dur <= 60):
        # trim nothing silently; just don't propose an out-of-range combo
        return []
    sc = dict(main.scores, hook=round(max(h, main.scores["hook"]), 3))
    p = Promo(id=f"E{ep.num:03d}-C1", segments=[hseg, mseg], duration=round(dur, 2), hook_text=ht,
              cliffhanger_text=main.cliffhanger_text,
              why=f"Cold open: strongest early hook line + {main.id}'s cliffhanger ending. " + main.why,
              scores=sc, total=total(sc), kind="cold_open", heuristic=dict(main.heuristic, hook=round(h, 3)))
    return [p]


def run(zip_src, provider=None, progress=None, cache_dir=None) -> RunResult:
    eps, gw = parse_zip(zip_src)
    epmap = {e.num: e for e in eps}
    allp, colds, n_cand = [], [], 0
    llm_stats = {"calls": 0, "cached": 0, "fallbacks": 0, "adjust_discarded": 0, "adjusted": 0}
    for i, ep in enumerate(eps):
        if progress:
            progress(i, len(eps), ep)
        try:
            top, n = episode_candidates(ep)
        except Exception as ex:  # one bad episode never kills the run
            gw.append(f"ep {ep.num}: candidate generation failed ({ex})")
            continue
        n_cand += n
        if provider is not None and provider.name != "none" and top:
            from .llm import judge_episode
            js, status = judge_episode(provider, ep, top, cache_dir=cache_dir)
            llm_stats["calls" if status == "ok" else ("cached" if status == "cached" else "fallbacks")] += 1
            if js is None:
                for p in top:
                    p.flags.append("llm_fallback")
            else:
                for p in top:
                    if p.id in js:
                        apply_llm(ep, p, js[p.id])
                    else:
                        p.flags.append("llm_missing_judgement")
        for p in top:
            llm_stats["adjust_discarded"] += "llm_adjust_discarded" in p.flags
            llm_stats["adjusted"] += "llm_adjusted" in p.flags
        allp += top
        colds += cold_opens(ep, top)
    for p in allp + colds:
        p.flags = sorted(set(p.flags + validate(p, epmap)))
    ranked = rank(allp)
    colds.sort(key=lambda p: -p.total)
    meta = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "provider": getattr(provider, "name", "none") if provider else "none",
        "model": getattr(provider, "model", None) if provider else None,
        "weights": WEIGHTS,
        "episodes_parsed": len(eps),
        "blocks": sum(len(e.blocks) for e in eps),
        "total_runtime_s": round(sum(e.duration for e in eps), 2),
        "candidates_generated": n_cand,
        "promos_kept": len(ranked),
        "cold_open_promos": len(colds),
        "validator_pass": sum(passes(p.flags) for p in ranked),
        "validator_pass_rate": round(sum(passes(p.flags) for p in ranked) / max(len(ranked), 1), 4),
        "cold_open_pass_rate": round(sum(passes(p.flags) for p in colds) / max(len(colds), 1), 4),
        "global_warnings": gw,
        "episode_warnings": {e.num: e.warnings for e in eps if e.warnings},
        "llm": llm_stats if provider is not None and provider.name != "none" else None,
    }
    return RunResult(eps, ranked, colds, gw, meta)
