import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from promofinder import editor  # noqa: E402
from promofinder.pipeline import run  # noqa: E402
from tests.make_fixture import build  # noqa: E402


def test_timecode():
    assert editor.timecode(23.8, 30) == "00:00:23:24"
    assert editor.timecode(3600, 25) == "01:00:00:00"


def test_pack(tmp_path):
    res = run(build(str(tmp_path / "s.zip")))
    files = editor.build(res.promos, res.cold_opens, res.episodes, top=5)
    assert set(files) >= {"clip_sheet.csv", "briefs.md", "promos.edl", "cut_promos.sh", "cut_promos.bat"}
    rows = files["clip_sheet.csv"].strip().splitlines()
    assert len(rows) - 1 == sum(len(p.segments) for p in res.promos[:5] + res.cold_opens[:1])
    assert files["promos.edl"].startswith("TITLE:") and "FROM CLIP NAME" in files["promos.edl"]
    assert files["cut_promos.sh"].count("ffmpeg -y") == 5 + min(1, len(res.cold_opens))
    assert editor.as_zip(files)[:2] == b"PK"
