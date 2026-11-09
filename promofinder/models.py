from __future__ import annotations

from dataclasses import dataclass, field, asdict

from .parser import fmt


@dataclass
class Segment:
    ep: int
    start: float
    end: float
    first_idx: int
    last_idx: int

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 2)

    def label(self) -> str:
        return f"{self.ep}:{fmt(self.start)}-{fmt(self.end)}"


@dataclass
class Promo:
    id: str
    segments: list[Segment]
    duration: float
    hook_text: str
    cliffhanger_text: str
    why: str
    scores: dict
    total: float
    flags: list[str] = field(default_factory=list)
    status: str = "pending"  # pending|approved|rejected
    kind: str = "single"  # single|cold_open
    heuristic: dict = field(default_factory=dict)  # heuristic sub-scores (always kept)
    llm: dict | None = None  # LLM judgement (if any)
    rank: int | None = None
    post_first: bool = False
    why_detail: str = ""  # full rule reasons; `why` is the one-line summary the brief asks for

    @property
    def ep(self) -> int:
        return self.segments[0].ep

    def to_dict(self) -> dict:
        d = asdict(self)
        d["segments"] = [dict(asdict(s), start_ts=fmt(s.start), end_ts=fmt(s.end), duration=s.duration)
                         for s in self.segments]
        return d
