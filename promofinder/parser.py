"""ZIP -> Episode/Block dataclasses. Case-insensitive, never crashes on one bad file."""
from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass, field

TS = r"(\d+):(\d+(?:\.\d+)?)"
BLOCK_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*:?\s*$")
SE_RE = re.compile(r"^\s*start:\s*\(?\s*" + TS + r"\s*\)?\s*\|\s*end:\s*\(?\s*" + TS + r"\s*\)?", re.I)
SCENE_RE = re.compile(r"^\s*scene\s+(\d+)\b", re.I)
EP_NUM_RE = re.compile(r"^\s*episode number:\s*(\d+)", re.I)
FILE_NUM_RE = re.compile(r"episode-(\d+)", re.I)

KIND_MAP = {
    "CAMERA": "CAMERA", "ACTION": "ACTION", "SOUND FX": "SFX", "SFX": "SFX", "MUSIC": "SFX",
    # rare visual/editorial labels are treated as non-speech CAMERA-like blocks
    "VFX": "CAMERA", "TRANSITION": "CAMERA", "TEXT": "CAMERA", "SUPER": "CAMERA", "INSERT": "CAMERA",
}
NON_EMOTION = {"O.S.", "V.O.", "O.C.", "CONT'D", "CONT’D"}

# canonical character names (blueprint audit); keys are upper-case speaker names
ALIASES = {
    "LADY JULIANA": "JULIANA",
    "THE FORMER GROOM": "GERALD",
    "LADY IN GOLD GOWN": "CLARISSA",
    "MYSTERIOUS BEARDED MAN": "ALEXANDER",
    "THE BEARDED STRANGER": "ALEXANDER",
    # synthetic fixture
    "LADY MIRA": "MIRA",
}


def to_sec(m: str, s: str) -> float:
    return int(m) * 60 + float(s)


def fmt(t: float) -> str:
    m = int(t // 60)
    return f"{m:02d}:{t - 60 * m:05.2f}"


@dataclass
class Block:
    ep: int
    idx: int
    kind: str  # CAMERA|ACTION|SFX|DIALOGUE
    speaker: str | None
    emotion: str | None
    start: float
    end: float
    text: str
    scene: int
    label: str = ""
    character: str | None = None  # alias-normalised speaker
    line: int = 0  # 1-based line number in source file

    @property
    def is_line(self) -> bool:  # dialogue or action = "content" lines
        return self.kind in ("DIALOGUE", "ACTION")


@dataclass
class Scene:
    num: int
    heading: str = ""
    start: float | None = None
    end: float | None = None


@dataclass
class Episode:
    num: int
    file: str
    logline: str
    continuity: str
    duration: float
    blocks: list[Block]
    warnings: list[str] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)


def parse_label(label: str):
    """'JULIANA (Outraged, Trembling) (O.S.)' -> kind, speaker, emotion."""
    lab = label.strip().rstrip(":").strip()
    up = lab.upper()
    if up in KIND_MAP:
        return KIND_MAP[up], None, None
    speaker = re.split(r"\(", lab, maxsplit=1)[0].strip()
    parens = re.findall(r"\(([^)]*)\)", lab)
    emos = []
    for p in parens:
        for part in p.split(","):
            part = part.strip()
            if part and part.upper() not in NON_EMOTION:
                emos.append(part)
    return "DIALOGUE", speaker or lab, (", ".join(emos) or None)


def canonical(speaker: str | None) -> str | None:
    if not speaker:
        return None
    up = re.sub(r"\s+", " ", speaker.upper()).strip()
    return ALIASES.get(up, up)


def parse_text(text: str, file: str = "?") -> Episode:
    L = text.splitlines()
    warnings: list[str] = []
    name = os.path.basename(file)

    def header(key):
        for l in L:
            if l.strip().lower().startswith(key):
                return l.split(":", 1)[1].strip()
        warnings.append(f"missing header '{key}'")
        return ""

    logline = header("episode logline:")
    continuity = header("continuity notes:")
    num = None
    for l in L:
        m = EP_NUM_RE.match(l)
        if m:
            num = int(m.group(1))
            break
    if num is None:
        m = FILE_NUM_RE.search(name)
        num = int(m.group(1)) if m else 0
        warnings.append(f"EPISODE NUMBER missing; using {num} from filename")
    for k in ("--- script start ---", "--- script end ---"):
        if not any(l.strip().lower().startswith(k) for l in L):
            warnings.append(f"missing marker '{k}'")

    scenes: list[Scene] = []
    raw: list[Block] = []
    cur: Scene | None = None
    i = 0
    while i < len(L):
        l = L[i]
        low = l.strip().lower()
        if SCENE_RE.match(l) and not low.startswith("scene start") and not low.startswith("scene end") \
                and not low.startswith("scene heading"):
            cur = Scene(int(SCENE_RE.match(l).group(1)))
            scenes.append(cur)
        elif low.startswith("scene heading:") and cur:
            cur.heading = l.split(":", 1)[1].strip()
        elif low.startswith("scene start:") or low.startswith("scene end:"):
            m = re.search(TS, l)
            if not m:
                warnings.append(f"L{i+1}: bad scene time '{l.strip()}'")
            elif cur is None:
                warnings.append(f"L{i+1}: scene time before any SCENE line")
            elif low.startswith("scene start:"):
                cur.start = to_sec(*m.groups())
            else:
                cur.end = to_sec(*m.groups())
        elif BLOCK_RE.match(l):
            label = BLOCK_RE.match(l).group(1)
            nx = L[i + 1] if i + 1 < len(L) else ""
            m = SE_RE.match(nx)
            if not m:
                warnings.append(f"L{i+1}: block '{label}' without timestamp; skipped")
                i += 1
                continue
            s, e = to_sec(*m.groups()[:2]), to_sec(*m.groups()[2:])
            j = i + 2
            text_lines = []
            while j < len(L):
                t = L[j]
                tl = t.strip().lower()
                if BLOCK_RE.match(t) or SCENE_RE.match(t) or tl.startswith("--- script end") \
                        or tl.startswith(("scene heading:", "scene start:", "scene end:", "actions and dialogue")):
                    break
                if t.strip():
                    text_lines.append(t.strip())
                j += 1
            if e < s:
                warnings.append(f"L{i+2}: end<start for '{label}' ({fmt(s)}>{fmt(e)}); skipped")
                i = j
                continue
            kind, speaker, emotion = parse_label(label)
            raw.append(Block(ep=num, idx=-1, kind=kind, speaker=speaker, emotion=emotion, start=s, end=e,
                             text=" ".join(text_lines), scene=cur.num if cur else 0, label=label.rstrip(":").strip(),
                             character=canonical(speaker), line=i + 1))
            i = j
            continue
        i += 1

    # sort by start (stable), count out-of-order
    nonmono = sum(1 for a, b in zip(raw, raw[1:]) if b.start < a.start - 0.01)
    if nonmono:
        warnings.append(f"{nonmono} block(s) out of order in file; sorted by start time")
    blocks = sorted(raw, key=lambda b: (b.start, b.end))
    for k, b in enumerate(blocks):
        b.idx = k

    # informative consistency checks (never fatal)
    for a, b in zip(scenes, scenes[1:]):
        if a.end is not None and b.start is not None and abs(b.start - a.end) > 0.05:
            warnings.append(f"scene gap/overlap {a.num}->{b.num}: {fmt(a.end)} vs {fmt(b.start)}")
    dl = [b for b in blocks if b.kind == "DIALOGUE"]
    ov = sum(1 for a, b in zip(dl, dl[1:]) if b.start < a.end - 0.05)
    if ov:
        warnings.append(f"{ov} overlapping dialogue line pair(s)")
    if not blocks:
        warnings.append("no blocks parsed")

    scene_end = max((s.end for s in scenes if s.end is not None), default=0.0)
    block_end = max((b.end for b in blocks), default=0.0)
    if scene_end and block_end and abs(scene_end - block_end) > 0.05:
        warnings.append(f"last block end {fmt(block_end)} != last scene end {fmt(scene_end)}")
    duration = max(scene_end, block_end)
    return Episode(num=num, file=name, logline=logline, continuity=continuity, duration=duration,
                   blocks=blocks, warnings=warnings, scenes=scenes)


def parse_zip(src) -> tuple[list[Episode], list[str]]:
    """src: path, bytes or file-like. Returns (episodes sorted by number, global warnings)."""
    if isinstance(src, (bytes, bytearray)):
        src = io.BytesIO(src)
    gw: list[str] = []
    eps: list[Episode] = []
    with zipfile.ZipFile(src) as z:
        names = sorted(n for n in z.namelist()
                       if n.lower().endswith(".txt") and "__macosx" not in n.lower()
                       and not os.path.basename(n).startswith("."))
        if not names:
            gw.append("ZIP contains no .txt files")
        for n in names:
            try:
                data = z.read(n)
                try:
                    text = data.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text = data.decode("latin-1")
                    gw.append(f"{n}: not UTF-8, decoded as latin-1")
                ep = parse_text(text, n)
                eps.append(ep)
            except Exception as ex:  # never crash on one bad file
                gw.append(f"{n}: failed to parse ({type(ex).__name__}: {ex})")
    seen = {}
    for ep in eps:
        if ep.num in seen:
            gw.append(f"duplicate episode number {ep.num}: {seen[ep.num]} and {ep.file}")
        seen[ep.num] = ep.file
    eps.sort(key=lambda e: e.num)
    return eps, gw
