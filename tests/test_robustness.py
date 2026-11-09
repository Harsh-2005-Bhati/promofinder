"""A new or messy show must produce warnings, never a crash (the interview may run it on unseen input)."""
import io
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from promofinder.parser import parse_any  # noqa: E402
from promofinder.pipeline import run  # noqa: E402
from promofinder.validate import passes  # noqa: E402
from tests.make_fixture import build  # noqa: E402

MUTATIONS = {
    "upper": lambda t: t.upper(),
    "crlf_tabs": lambda t: t.replace("\n", "\r\n").replace(": ", ":\t"),
    "no_headers": lambda t: "\n".join(l for l in t.splitlines()
                                      if not l.upper().startswith(("EPISODE", "CONTINUITY", "---"))),
    "renamed": lambda t: t.replace("MIRA", "ELENA").replace("EDRIC", "VIKTOR"),
    "no_parens": lambda t: re.sub(r"Start: \((\S+)\) \| End: \((\S+)\)", r"Start: \1 | End: \2", t),
    "drop_ts": lambda t: "\n".join(l for i, l in enumerate(t.splitlines()) if not (l.startswith("Start:") and i % 5 == 0)),
    "truncated": lambda t: t[: len(t) // 2],
    "hours_ts": lambda t: re.sub(r"\((\d\d):(\d\d\.\d\d)\)", r"(00:\1:\2)", t),
    "curly_bom": lambda t: "﻿" + t.replace("'", "’"),
}


def _messy_zip(tmp_path):
    src = zipfile.ZipFile(build(str(tmp_path / "s.zip")))
    names = sorted(n for n in src.namelist() if n.endswith(".txt"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for (kind, f), n in zip(MUTATIONS.items(), names * 2):
            z.writestr(f"show/sub dir/{kind}-{os.path.basename(n)}", f(src.read(n).decode()).encode())
        z.writestr("show/garbage.txt", "not a screenplay\n" * 20)
        z.writestr("show/empty.txt", "")
        z.writestr("show/notes.md", "ignored")
        z.writestr("__MACOSX/._x.txt", b"\x00")
    return buf.getvalue()


def test_messy_show_warns_not_crashes(tmp_path):
    res = run(_messy_zip(tmp_path))
    assert len(res.episodes) >= 8  # every mutated script is usable
    assert any("garbage.txt" in w and "skipped" in w for w in res.warnings)
    assert res.promos and all(passes(p.flags) for p in res.promos)
    ups = [e for e in res.episodes if "upper-" in e.file][0]
    assert ups.blocks and ups.scenes
    hours = [e for e in res.episodes if "hours_ts-" in e.file][0]
    assert len(hours.blocks) > 10 and hours.duration > 30


def test_bad_inputs(tmp_path):
    assert parse_any(b"not a zip")[1] == ["not a valid ZIP file"]
    eps, gw = parse_any(_zip_of({"a.md": "x"}))
    assert not eps and gw
    p = tmp_path / "ep.txt"
    src = zipfile.ZipFile(build(str(tmp_path / "s.zip")))
    p.write_bytes(src.read(sorted(n for n in src.namelist() if n.endswith(".txt"))[0]))
    eps, _ = parse_any(str(p))  # single episode file
    assert len(eps) == 1 and eps[0].blocks
    eps, _ = parse_any(str(tmp_path))  # folder
    assert len(eps) == 1


def _zip_of(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, t in files.items():
            z.writestr(n, t)
    return buf.getvalue()
