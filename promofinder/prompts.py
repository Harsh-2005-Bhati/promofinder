"""Judge prompt + JSON schema. The LLM sees block indices and may only answer with indices — never times."""
from __future__ import annotations

from .models import Promo
from .parser import Episode, fmt

SCHEMA = {
    "type": "object",
    "properties": {
        "judgments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "hook_score": {"type": "integer", "minimum": 1, "maximum": 5},
                    "cliffhanger_score": {"type": "integer", "minimum": 1, "maximum": 5},
                    "standalone_score": {"type": "integer", "minimum": 1, "maximum": 5},
                    "hook_text": {"type": "string"},
                    "cliffhanger_text": {"type": "string"},
                    "why": {"type": "string"},
                    "adjust": {"type": ["object", "null"],
                               "properties": {"first_idx": {"type": "integer"}, "last_idx": {"type": "integer"}}},
                },
                "required": ["candidate_id", "hook_score", "cliffhanger_score", "standalone_score",
                             "hook_text", "cliffhanger_text", "why"],
            },
        }
    },
    "required": ["judgments"],
}

SYSTEM = ("You are a senior promo editor for vertical microdramas. You judge candidate promo clips cut from one "
          "episode script. Promos run 20-60 seconds on social feeds: the first 3 seconds must stop the scroll "
          "(hook) and the last ~5 seconds must leave the viewer desperate to know what happens (cliffhanger). "
          "A promo must make sense to a stranger who has not seen the show (standalone). Avoid spoiling the "
          "episode's final resolution. Respond with JSON only.")


def block_line(b) -> str:
    who = b.label if b.kind == "DIALOGUE" else b.kind
    return f"[{b.idx}] {fmt(b.start)}-{fmt(b.end)} {who}: {b.text}"


def build_prompt(ep: Episode, cands: list[Promo]) -> str:
    lines = [SYSTEM, "", f"EPISODE {ep.num}", f"LOGLINE: {ep.logline}", "", "SCRIPT BLOCKS (index, time, label, text):"]
    lines += [block_line(b) for b in ep.blocks]
    lines += ["", "CANDIDATES (block index ranges, inclusive):"]
    for p in cands:
        s = p.segments[0]
        lines.append(f"- {p.id}: blocks [{s.first_idx}]..[{s.last_idx}] ({s.duration:.1f}s)")
    lines += [
        "",
        "For EVERY candidate return an object with:",
        "  candidate_id, hook_score 1-5, cliffhanger_score 1-5, standalone_score 1-5,",
        "  hook_text: the exact script text of the hook line (copy verbatim from a block inside the candidate),",
        "  cliffhanger_text: the exact script text of the final line (verbatim, inside the candidate),",
        "  why: one or two sentences on why it works or fails,",
        "  adjust: null, or {first_idx, last_idx} block indices if a slightly different range is clearly better.",
        "RULES: never output timestamps; only block indices. Adjusted range must stay 20-60 s long.",
        "If you return an adjust range, ALL scores, hook_text and cliffhanger_text must describe that FINAL range",
        "(hook_text = a line from its first blocks, cliffhanger_text = its last line), not the original candidate.",
        'Output exactly: {"judgments": [ ... ]}',
    ]
    return "\n".join(lines)
