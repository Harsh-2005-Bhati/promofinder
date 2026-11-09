"""Rule-based hook / cliffhanger / standalone / density features (0-1 each). No API calls.

Weights are documented inline; every score keeps a list of human-readable reasons.
"""
from __future__ import annotations

import re

from .candidates import EPS
from .models import Segment
from .parser import Episode, Block

HOOK_WIN = 3.0
CLIFF_WIN = 5.0

SHOCK = ["slap", "strike", "struck", "blood", "fire", "burn", "poison", "arrest", "kneel", "chain", "execution",
         "execute", "witch", "duke", "married", "marry", "betray", "betrayal", "betrayed", "how dare", "kill", "dead", "die", "murder",
         "knife", "sword", "scream", "gasp", "divorce", "pregnant", "traitor", "liar", "slave", "prison", "guards"]
THREAT = ["or else", "unless", "i will", "i'll", "you will", "you'll", "tomorrow", "before dawn", "at dawn",
          "never", "pay for", "regret", "last chance", "if you", "kneel", "mark my words", "you will see"]
REVEAL = ["truth", "secret", "who you really", "who are you", "it was you", "alive", "pregnant", "heir",
          "real father", "real mother", "is my", "is your", "the duke", "identity", "lied", "you knew"]
RESOLUTION = ["thank you", "safe now", "it's over", "it is over", "all is well", "rest now", "goodnight",
              "good night", "happily", "we did it", "forgive you"]
SFX_SWELL = ["swell", "sting", "boom", "thunder", "crash", "drone", "heartbeat", "gasp", "black", "fade",
             "cliffhanger", "silence", "scream", "shatter", "slam"]
INTENSE_EMO = ["outraged", "screaming", "furious", "shocked", "terrified", "desperate", "enraged", "sobbing",
               "horrified", "menacing", "trembling", "hysterical", "defiant", "panicked", "fearful", "livid",
               "cold", "seething", "venomous", "triumphant", "smirking"]
CONFLICT = SHOCK + ["hate", "how could", "enough", "get out", "you dare", "lies", "never", "liar", "shame"]
TENDER_EMO = ["tender", "soft", "gentle", "warm", "loving", "relieved", "reassuring", "sincere", "calm", "amused",
              "resigned", "reverent", "humble", "softly", "intimate", "reflective", "heartfelt", "devoted", "vowing",
              "wondering", "impressed", "proud", "content", "peaceful", "smiling", "grateful"]
CALM_ACTION = ["walk", "together", "side by side", "gaze", "smile", "embrace", "hug", "kiss", "rests", "nods", "sigh",
               "relax", "peaceful", "sunset", "twilight", "leaves", "departs", "retreat", "settles", "bond", "comfort"]
TENSE_ACTION = ["gasp", "freez", "lunge", "grab", "raise", "blade", "iron", "blood", "collapse", "burst", "slam", "strike",
                "slap", "seize", "drag", "scream", "chain", "flame", "fire", "knife", "sword", "poison", "faint", "stagger",
                "shock", "horror", "trembl", "thrust", "choke", "shatter", "lacerat", "claw"]
INCITING = ["strike", "strikes", "struck", "slap", "slaps", "hits", "stab", "shoves", "punch", "whip", "throws",
            "kicks", "smash", "fires", "shoots"]
REACTION_OPENER = ["gasp", "recoil", "flinch", "reels", "clutch", "absorbs", "doubles over", "stumbles back"]
INTERJECTION_OK = "!"  # short exclamations ("Stop!", "Silence!") are self-contained hooks
# identity/status reveals that spoil the series arc when shown from late episodes
SERIES_REVEAL = ["the duke", "you're the duke", "rightful", "true identity", "who you really are", "who i really am",
                 "my son", "is alive", "you're alive", "you are alive", "the heir", "proclaim", "real name", "not dead",
                 "all this time", "duchess of"]
WEAK_OPENERS = ("and ", "but ", "so ", "yes", "no,", "no.", "no!", "no ", "because ", "then ", "well,", "well ", "okay", "ok ")
PRONOUN_OPENERS = ("he ", "she ", "they ", "it ", "that ", "this ", "him ", "her ", "them ", "those ", "these ")


SUFFIX = r"(?:s|es|ed|d|ing|ly|al)?\b"


def _has(text: str, words, stem: bool = False) -> list[str]:
    """Whole-word match allowing simple inflections ("slap" ~ "slaps", "slapped" is listed separately if needed).
    stem=True matches word prefixes (for stem lists like "trembl", "freez")."""
    t = (text or "").lower().replace("’", "'")
    tail = "" if stem else SUFFIX
    return [w for w in words if re.search(r"\b" + re.escape(w) + tail, t)]


def mid_conversation(ep: Episode, seg: Segment, wb: list[Block]) -> bool:
    """Clip opens on a short reply (<=4 words, not a shouted exclamation) right after someone else spoke."""
    dl = [b for b in wb if b.kind == "DIALOGUE"]
    if not dl or dl[0].start > seg.start + 1.0:
        return False
    ft = _clean(dl[0].text)
    words = re.findall(r"[A-Za-z']+", ft)
    recent = [b for b in ep.blocks if b.kind == "DIALOGUE" and seg.start - 6.0 <= b.end <= seg.start + EPS]
    return len(words) <= 4 and not ft.rstrip().endswith(INTERJECTION_OK) and bool(recent)


def _clean(text: str) -> str:
    return text.strip().strip('"“”').lstrip('.…-— ').strip()


def window_blocks(ep: Episode, seg: Segment) -> list[Block]:
    return [b for b in ep.blocks if b.start >= seg.start - EPS and b.end <= seg.end + EPS]


def hook(ep: Episode, seg: Segment, wb: list[Block]):
    lim = seg.start + HOOK_WIN
    first = [b for b in wb if b.start < lim]
    lines = [b for b in first if b.is_line]
    score, why = 0.0, []
    if any(b.start <= seg.start + 1.0 for b in lines):
        score += 0.35; why.append("line within 1 s")  # weight 0.35
    text = " ".join(b.text for b in first)
    if "!" in text or "?" in text:
        score += 0.2; why.append("exclamation/question in first 3 s")  # 0.20
    shock = _has(text, SHOCK)
    if shock:
        score += min(0.3, 0.2 + 0.05 * len(shock)); why.append("shock words: " + ", ".join(shock[:3]))  # ≤0.30
    emo = [e for b in lines for e in _has(b.emotion or "", INTENSE_EMO)]
    if emo:
        score += 0.15; why.append("intense emotion: " + emo[0])  # 0.15
    if not any(b.kind in ("DIALOGUE", "ACTION", "SFX") for b in first):
        score -= 0.4; why.append("first 3 s CAMERA-only")  # penalty 0.40
    if mid_conversation(ep, seg, wb):
        score -= 0.3; why.append("needs prior context: opens on a short reply")  # penalty 0.30
    hook_block = lines[0] if lines else (wb[0] if wb else None)
    return max(0.0, min(1.0, score)), why, (hook_block.text if hook_block else "")


def cliffhanger(ep: Episode, seg: Segment, wb: list[Block]):
    """Judged on the last DIALOGUE/ACTION line. SFX/music can only reinforce real tension, never create it."""
    tail = [b for b in wb if b.end > seg.end - CLIFF_WIN]
    lines = [b for b in wb if b.is_line]
    last = lines[-1] if lines else None
    score, why = 0.0, []
    if last:
        lt = last.text
        if last.kind == "DIALOGUE":
            if "?" in lt:
                score += 0.3; why.append("ends on a question")  # 0.30
            th, rv = _has(lt, THREAT), _has(lt, REVEAL)
            if th:
                score += 0.25; why.append("threat/ultimatum: " + th[0])  # 0.25
            if rv:
                score += 0.25; why.append("reveal: " + rv[0])  # 0.25
            if "!" in lt:
                score += 0.1; why.append("ends on exclamation")  # 0.10
            emo = last.emotion or ""
            if _has(emo, INTENSE_EMO):
                score += 0.15; why.append("intense delivery: " + _has(emo, INTENSE_EMO)[0])  # 0.15
            if _has(emo, TENDER_EMO) and not _has(emo, INTENSE_EMO):
                score -= 0.25; why.append("tender/calm delivery: " + _has(emo, TENDER_EMO)[0])  # penalty
        else:  # ACTION
            te, ca = _has(lt, TENSE_ACTION, stem=True), _has(lt, CALM_ACTION, stem=True)
            if te and len(te) >= len(ca):
                score += 0.3; why.append("ends on tense action: " + te[0])
            elif ca:
                score -= 0.35; why.append("ends on calm/resolving action: " + ca[0])
        if last.end < seg.end - CLIFF_WIN:
            score -= 0.2; why.append("last line >5 s before cut")  # penalty
        res = _has(lt, RESOLUTION)
        if res:
            score -= 0.4; why.append("resolution words: " + res[0])  # penalty 0.40
    line_tension = score
    sfx = [w for b in tail if b.kind in ("SFX", "CAMERA") for w in _has(b.text, SFX_SWELL)]
    if sfx:
        if line_tension >= 0.25:
            score += 0.15; why.append("SFX/visual swell reinforces: " + sfx[0])  # 0.15
        else:
            why.append("SFX swell ignored (scene not tense)")
    if seg.end >= ep.duration - 0.5 and line_tension >= 0.25:
        score += 0.2; why.append("ends at episode end on a tense line")  # 0.20
    return max(0.0, min(1.0, score)), why, (last.text if last else "")


def standalone(ep: Episode, seg: Segment, wb: list[Block]):
    score, why = 0.6, ["base 0.6"]
    dl = [b for b in wb if b.kind == "DIALOGUE"]
    if dl:
        first = dl[0]
        ft = _clean(first.text).lower()
        if ft.startswith(WEAK_OPENERS):
            score -= 0.25; why.append("first line opens with conjunction/yes/no")
        if ft.startswith(PRONOUN_OPENERS):
            score -= 0.15; why.append("unresolved pronoun opener")
        prev = [b for b in ep.blocks if b.kind == "DIALOGUE" and b.end <= seg.start + EPS
                and b.end >= seg.start - 1.5]
        if prev and prev[-1].text.rstrip('"” ').endswith("?") and prev[-1].character != first.character:
            score -= 0.2; why.append("first line answers a question outside the window")
        if mid_conversation(ep, seg, wb):
            score -= 0.3; why.append("opens on a short reply mid-conversation")
    before = [b for b in ep.blocks if b.kind in ("ACTION", "SFX") and seg.start - 2.5 <= b.end <= seg.start + EPS]
    inc = [w for b in before for w in _has(b.text, INCITING)]
    if inc:
        score -= 0.3; why.append(f"inciting beat '{inc[0]}' happens just before the cut")
    opener = next((b for b in wb if b.is_line), None)
    if opener is not None and opener.kind == "ACTION" and _has(opener.text, REACTION_OPENER, stem=True) and not inc:
        score -= 0.15; why.append("opens on a reaction whose cause is outside the clip")
    chars = {b.character for b in dl if b.character}
    conflict = any(_has(b.text, CONFLICT) or _has(b.emotion or "", INTENSE_EMO) for b in wb if b.is_line)
    if len(chars) >= 2 and conflict:
        score += 0.3; why.append(f"{len(chars)} characters in conflict")
    if any(abs(sc.start - seg.start) < 0.5 for sc in ep.scenes if sc.start is not None):
        score += 0.1; why.append("starts at scene start")
    return max(0.0, min(1.0, score)), why


def spoiler(ep: Episode, seg: Segment, wb: list[Block], n_eps: int | None):
    """Risk that the clip gives away the series arc: identity/status reveals, weighted by how late the episode is.
    Promos recruit new viewers who start at episode 1, so late-arc reveals cost more than they earn."""
    if not n_eps or n_eps < 3:
        return 0.0, []
    pos = (ep.num - 1) / (n_eps - 1)
    late = max(0.0, (pos - 0.6) / 0.4)
    if late == 0:
        return 0.0, []
    hits = sorted({w for b in wb if b.is_line for w in _has(b.text, SERIES_REVEAL)})
    risk = late * min(1.0, 0.5 * len(hits))
    why = [f"episode {ep.num}/{n_eps} (late in series)"]
    if hits:
        why.append("series reveal: " + ", ".join(hits[:3]))
    risk = max(risk, 0.3 * late)
    return round(min(1.0, risk), 3), why


def density(ep: Episode, seg: Segment, wb: list[Block]):
    dur = max(seg.end - seg.start, 1e-6)
    dl = [b for b in wb if b.kind == "DIALOGUE"]
    rate = len(dl) / dur
    intense = sum(1 for b in dl if _has(b.emotion or "", INTENSE_EMO)) / max(len(dl), 1)
    score = 0.6 * min(1.0, rate / 0.4) + 0.4 * intense
    return min(1.0, score), [f"{len(dl)} lines / {dur:.0f} s", f"{intense:.0%} intense emotion"]


def compute(ep: Episode, seg: Segment, n_eps: int | None = None) -> dict:
    wb = window_blocks(ep, seg)
    h, hw, ht = hook(ep, seg, wb)
    c, cw, ct = cliffhanger(ep, seg, wb)
    s, sw = standalone(ep, seg, wb)
    d, dw = density(ep, seg, wb)
    sp, spw = spoiler(ep, seg, wb, n_eps)
    return {"hook": round(h, 3), "cliffhanger": round(c, 3), "standalone": round(s, 3), "density": round(d, 3),
            "spoiler_risk": sp,
            "hook_text": ht, "cliffhanger_text": ct,
            "reasons": {"hook": hw, "cliffhanger": cw, "standalone": sw, "density": dw, "spoiler": spw}}
