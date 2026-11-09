"""Editor pack: turn ranked promos into things a video editor can use directly.

Writes (for the top N promos, single + cold-open):
  clip_sheet.csv     one row per segment: promo, episode file, in/out (seconds + timecode), caption, notes
  briefs.md          one short brief per promo: timings, why, script excerpt with HOOK / CLIFF markers
  promos.edl         CMX3600 EDL (import into Premiere / Resolve / FCP via EDL import)
  cut_promos.sh/.bat ffmpeg commands that cut each promo from the episode videos (frame-accurate re-encode)

Assumption: each episode's video sits in VIDEO_DIR with the same name as its script file and VIDEO_EXT
(e.g. "episode-003-Episode 123.txt" -> "videos/episode-003-Episode 123.mp4"). Both are parameters.
"""
from __future__ import annotations

import csv
import io
import os
import zipfile

from .models import Promo
from .parser import Episode, fmt

HOOK_S, CLIFF_S = 3.0, 5.0


def timecode(t: float, fps: int) -> str:
    f = int(round(t * fps))
    h, f = divmod(f, 3600 * fps)
    m, f = divmod(f, 60 * fps)
    s, f = divmod(f, fps)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def video_name(ep: Episode, ext: str) -> str:
    return os.path.splitext(os.path.basename(ep.file))[0] + ext


def _short(t: str, n=70) -> str:
    t = (t or "").strip().strip('"“”')
    return t if len(t) <= n else t[: n - 1] + "…"


def clip_sheet(promos: list[Promo], eps: dict[int, Episode], fps: int, ext: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["promo_id", "rank", "kind", "segment", "episode", "video_file", "in_s", "out_s", "in_tc", "out_tc",
                "segment_s", "promo_total_s", "caption_suggestion", "ends_on", "spoiler_risk", "validator_flags",
                "editor_notes"])
    for p in promos:
        for i, s in enumerate(p.segments, 1):
            ep = eps[s.ep]
            notes = []
            if p.kind == "cold_open":
                notes.append("cold open: segment 1 is the teaser, hard cut to segment 2")
            if s.end >= ep.duration - 0.5:
                notes.append("ends at episode end: keep the original sting")
            notes.append("hold 0.5 s of black/end card after the last frame")
            w.writerow([p.id, p.rank or "", p.kind, i, s.ep, video_name(ep, ext), f"{s.start:.2f}", f"{s.end:.2f}",
                        timecode(s.start, fps), timecode(s.end, fps), f"{s.end - s.start:.2f}", f"{p.duration:.2f}",
                        _short(p.hook_text), _short(p.cliffhanger_text), p.scores.get("spoiler_risk", 0.0),
                        "; ".join(p.flags), "; ".join(notes)])
    return buf.getvalue()


def brief(p: Promo, eps: dict[int, Episode]) -> str:
    segs = " + ".join(f"ep {s.ep} {fmt(s.start)}–{fmt(s.end)}" for s in p.segments)
    out = [f"## {p.id}{f'  (#{p.rank})' if p.rank else ''}: {segs} · {p.duration:.1f} s · score {p.total:.2f}",
           "", f"**Caption idea:** {_short(p.hook_text, 90)}", f"**Ends on:** {_short(p.cliffhanger_text, 90)}",
           f"**Why:** {p.why}", ""]
    if p.flags:
        out.append(f"**Flags:** {', '.join(p.flags)}")
        out.append("")
    hook_end = p.segments[0].start + HOOK_S
    cliff_start = p.segments[-1].end - CLIFF_S
    out.append("```")
    for si, s in enumerate(p.segments):
        ep = eps[s.ep]
        if len(p.segments) > 1:
            out.append(f"--- segment {si + 1} (ep {s.ep}) ---")
        for b in ep.blocks:
            if b.kind == "CAMERA" or b.start < s.start - 0.01 or b.end > s.end + 0.01:
                continue
            mark = ""
            if si == 0 and b.start < hook_end:
                mark = "HOOK "
            if si == len(p.segments) - 1 and b.end > cliff_start:
                mark += "CLIFF"
            who = b.label if b.kind == "DIALOGUE" else b.kind
            out.append(f"{mark:<10} {fmt(b.start)}  {who}: {_short(b.text, 110)}")
    out += ["```", ""]
    return "\n".join(out)


def edl(promos: list[Promo], eps: dict[int, Episode], fps: int, ext: str) -> str:
    lines = ["TITLE: PromoFinder promos", "FCM: NON-DROP FRAME", ""]
    rec = 3600.0  # record timeline starts at 01:00:00:00
    n = 0
    for p in promos:
        for s in p.segments:
            n += 1
            dur = s.end - s.start
            reel = f"EP{s.ep:03d}"[:8]
            lines.append(f"{n:03d}  {reel:<8} AA/V  C        {timecode(s.start, fps)} {timecode(s.end, fps)} "
                         f"{timecode(rec, fps)} {timecode(rec + dur, fps)}")
            lines.append(f"* FROM CLIP NAME: {video_name(eps[s.ep], ext)}")
            lines.append(f"* COMMENT: {p.id} {_short(p.hook_text, 50)}")
            lines.append("")
            rec += dur
        rec += 2.0  # 2 s gap between promos on the record timeline
    return "\n".join(lines)


def _ff(path):
    return path.replace("\\", "/")


def cut_scripts(promos: list[Promo], eps: dict[int, Episode], video_dir: str, ext: str) -> tuple[str, str]:
    enc = "-c:v libx264 -preset veryfast -crf 20 -c:a aac -b:a 160k -movflags +faststart"
    sh = ["#!/usr/bin/env bash", "# Cut each promo from the episode videos. Usage: bash cut_promos.sh [VIDEO_DIR]",
          f'VIDEO_DIR="${{1:-{video_dir}}}"', "mkdir -p promos", ""]
    bat = ["@echo off", "REM Cut each promo from the episode videos. Usage: cut_promos.bat [VIDEO_DIR]",
           f'set "VIDEO_DIR={video_dir}"', 'if not "%~1"=="" set "VIDEO_DIR=%~1"', "if not exist promos mkdir promos", ""]
    for p in promos:
        out = f"promos/{p.id}.mp4"
        if len(p.segments) == 1:
            s = p.segments[0]
            v = video_name(eps[s.ep], ext)
            sh.append(f'ffmpeg -y -ss {s.start:.2f} -i "$VIDEO_DIR/{v}" -t {s.end - s.start:.2f} {enc} "{out}"')
            bat.append(f'ffmpeg -y -ss {s.start:.2f} -i "%VIDEO_DIR%\\{v}" -t {s.end - s.start:.2f} {enc} "{out}"')
        else:
            ins_sh, ins_bat, cat = [], [], ""
            for i, s in enumerate(p.segments):
                v = video_name(eps[s.ep], ext)
                ins_sh.append(f'-ss {s.start:.2f} -t {s.end - s.start:.2f} -i "$VIDEO_DIR/{v}"')
                ins_bat.append(f'-ss {s.start:.2f} -t {s.end - s.start:.2f} -i "%VIDEO_DIR%\\{v}"')
                cat += f"[{i}:v][{i}:a]"
            fc = f'-filter_complex "{cat}concat=n={len(p.segments)}:v=1:a=1[v][a]" -map "[v]" -map "[a]"'
            sh.append(f'ffmpeg -y {" ".join(ins_sh)} {fc} {enc} "{out}"')
            bat.append(f'ffmpeg -y {" ".join(ins_bat)} {fc} {enc} "{out}"')
    return "\n".join(sh) + "\n", "\r\n".join(bat) + "\r\n"


def build(promos: list[Promo], cold: list[Promo], episodes: list[Episode], top: int = 20, fps: int = 30,
          video_dir: str = "videos", ext: str = ".mp4") -> dict[str, str]:
    eps = {e.num: e for e in episodes}
    sel = [p for p in promos[:top]] + [p for p in cold[: max(1, top // 4)]]
    sh, bat = cut_scripts(sel, eps, video_dir, ext)
    head = (f"# Promo briefs: top {min(top, len(promos))} promos + {min(len(cold), max(1, top // 4))} cold opens\n\n"
            "Timings come straight from the script timestamps. HOOK = first 3 s, CLIFF = last 5 s.\n\n")
    return {
        "clip_sheet.csv": clip_sheet(sel, eps, fps, ext),
        "briefs.md": head + "\n".join(brief(p, eps) for p in sel),
        "promos.edl": edl(sel, eps, fps, ext),
        "cut_promos.sh": sh,
        "cut_promos.bat": bat,
        "README.txt": (__doc__ or "").strip() + f"\n\nfps used for timecodes: {fps}\n",
    }


def write(out_dir: str, files: dict[str, str]) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for n, txt in files.items():
        p = os.path.join(out_dir, n)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(txt)
        paths.append(p)
    return paths


def as_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, txt in files.items():
            z.writestr(f"editor_pack/{n}", txt)
    return buf.getvalue()
