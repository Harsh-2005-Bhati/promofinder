"""Combine heuristic (+ optional LLM) scores, NMS dedupe, per-episode top-K, global ranking with diversity."""
from __future__ import annotations

from . import features
from .candidates import generate, segment_from_indices
from .models import Promo, Segment
from .parser import Episode, fmt
from .validate import validate, HARD_CHECKS

WEIGHTS = {"hook": 0.35, "cliffhanger": 0.35, "standalone": 0.20, "density": 0.10}
SPOILER_PENALTY = 0.25  # total -= 0.25 * spoiler_risk
TOP_PER_EP = 5
NMS_OVERLAP = 0.5
TOP_N_DIVERSE = 20
MAX_PER_EP_TOP = 2


def total(scores: dict) -> float:
    return round(sum(WEIGHTS[k] * scores[k] for k in WEIGHTS) - SPOILER_PENALTY * scores.get("spoiler_risk", 0.0), 4)


def why_text(feat: dict) -> str:
    r = feat["reasons"]
    parts = []
    if r["hook"]:
        parts.append("Hook: " + "; ".join(r["hook"]))
    if r["cliffhanger"]:
        parts.append("Cliffhanger: " + "; ".join(r["cliffhanger"]))
    sw = [x for x in r["standalone"] if x != "base 0.6"]
    if sw:
        parts.append("Context: " + "; ".join(sw))
    if feat.get("spoiler_risk", 0) > 0:
        parts.append(f"Spoiler risk {feat['spoiler_risk']:.2f}: " + "; ".join(r.get("spoiler", [])))
    return " | ".join(parts) or "No strong signals."


def _q(t: str, n: int = 9) -> str:
    w = (t or "").strip().strip('"“”').split()
    return " ".join(w[:n]) + ("…" if len(w) > n else "")


def one_line(feat: dict, hook_text: str, cliff_text: str) -> str:
    """One plain-English line: what stops the scroll, what leaves it open, does it stand alone."""
    r = feat["reasons"]
    emo = next((x.split(": ", 1)[1] for x in r["hook"] if x.startswith("intense emotion: ")), None)
    shock = next((x.split(": ", 1)[1].split(",")[0].strip() for x in r["hook"] if x.startswith("shock words: ")), None)
    if emo:
        opener = f"Opens on {'an' if emo[0] in 'aeiou' else 'a'} {emo} line"
    elif shock:
        opener = f"Opens on a '{shock}' moment"
    elif any("CAMERA-only" in x for x in r["hook"]):
        opener = "Slow visual opening"
    else:
        opener = "Opens on a charged line"
    opener += f' ("{_q(hook_text)}")'
    c = " ".join(r["cliffhanger"])
    if "question" in c:
        ender = "cuts on an unanswered question"
    elif "threat" in c:
        ender = "cuts on a threat"
    elif "reveal" in c:
        ender = "cuts on a reveal"
    elif "tense action" in c:
        ender = "cuts mid-action"
    elif "calm" in c or "resolution" in c or "tender" in c:
        ender = "ends on a calm beat (weak cliffhanger)"
    else:
        ender = "ends without a clear cliffhanger"
    if "episode end" in c:
        ender += ", the episode's own ending"
    ender += f' ("{_q(cliff_text)}")'
    ctx = "stands alone" if feat["standalone"] >= 0.8 else "needs a little context" if feat["standalone"] >= 0.6 \
        else "needs prior context"
    risk = "; spoiler risk" if feat.get("spoiler_risk", 0) >= 0.4 else ""
    return f"{opener}, {ender}; {ctx}{risk}."


def overlap_frac(a: Segment, b: Segment) -> float:
    if a.ep != b.ep:
        return 0.0
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    return inter / max(min(a.end - a.start, b.end - b.start), 1e-6)


def nms(promos: list[Promo], k: int = TOP_PER_EP, thr: float = NMS_OVERLAP) -> list[Promo]:
    keep: list[Promo] = []
    for p in sorted(promos, key=lambda p: -p.total):
        if all(overlap_frac(p.segments[0], q.segments[0]) <= thr for q in keep):
            keep.append(p)
        if len(keep) >= k:
            break
    return keep


def make_promo(ep: Episode, seg: Segment, pid: str, n_eps: int | None = None) -> Promo:
    f = features.compute(ep, seg, n_eps)
    sc = {k: f[k] for k in WEIGHTS}
    sc["spoiler_risk"] = f["spoiler_risk"]
    return Promo(id=pid, segments=[seg], duration=seg.duration, hook_text=f["hook_text"],
                 cliffhanger_text=f["cliffhanger_text"], why=one_line(f, f["hook_text"], f["cliffhanger_text"]),
                 why_detail=why_text(f), scores=dict(sc), total=total(sc),
                 heuristic=dict(sc, n_eps=n_eps, reasons=f["reasons"]))


def episode_candidates(ep: Episode, n_eps: int | None = None) -> tuple[list[Promo], int]:
    segs = generate(ep)
    promos = [make_promo(ep, s, f"E{ep.num:03d}-c{i}", n_eps) for i, s in enumerate(segs)]
    top = nms(promos)
    for r, p in enumerate(top, 1):
        p.id = f"E{ep.num:03d}-P{r}"
    return top, len(segs)


def apply_llm(ep: Episode, promo: Promo, j: dict) -> None:
    """Merge a validated LLM judgement. LLM gives only block indices; code converts to times."""
    promo.llm = dict(j)
    adj = j.get("adjust")
    if adj:
        seg = segment_from_indices(ep, int(adj["first_idx"]), int(adj["last_idx"]))
        old = promo.segments
        if seg is not None:
            promo.segments = [seg]
            hard = [f for f in validate(promo, {ep.num: ep}) if f in HARD_CHECKS]
            if hard:
                promo.segments = old
                promo.flags.append("llm_adjust_discarded")
            else:
                promo.duration = seg.duration
                promo.flags.append("llm_adjusted")
                f = features.compute(ep, seg, promo.heuristic.get("n_eps"))
                promo.heuristic = dict({k: f[k] for k in WEIGHTS}, spoiler_risk=f["spoiler_risk"],
                                       n_eps=promo.heuristic.get("n_eps"), reasons=f["reasons"])
        else:
            promo.flags.append("llm_adjust_discarded")
    to01 = lambda v: round((max(1, min(5, int(v))) - 1) / 4, 3)  # noqa: E731
    sc = {"hook": to01(j["hook_score"]), "cliffhanger": to01(j["cliffhanger_score"]),
          "standalone": to01(j["standalone_score"]), "density": promo.heuristic["density"],
          "spoiler_risk": promo.heuristic.get("spoiler_risk", 0.0)}
    promo.scores = sc
    promo.total = total(sc)
    if j.get("hook_text"):
        promo.hook_text = j["hook_text"]
    if j.get("cliffhanger_text"):
        promo.cliffhanger_text = j["cliffhanger_text"]
    if j.get("why"):
        promo.why = j["why"]


def rank(promos: list[Promo]) -> list[Promo]:
    """Sort by total; top-20 contains at most 2 promos per episode; rest follow by score."""
    ordered = sorted(promos, key=lambda p: (-p.total, p.ep, p.segments[0].start))
    top, rest, per = [], [], {}
    for p in ordered:
        if len(top) < TOP_N_DIVERSE and per.get(p.ep, 0) < MAX_PER_EP_TOP:
            top.append(p)
            per[p.ep] = per.get(p.ep, 0) + 1
        else:
            rest.append(p)
    out = top + rest
    for i, p in enumerate(out, 1):
        p.rank = i
        p.post_first = i <= 10
    return out


def post_first_reason(p: Promo) -> str:
    s = p.segments[0]
    return (f"#{p.rank} ep {p.ep} {fmt(s.start)}-{fmt(s.end)} ({p.duration:.1f}s) total {p.total:.2f} "
            f"[hook {p.scores['hook']:.2f}, cliff {p.scores['cliffhanger']:.2f}]")
