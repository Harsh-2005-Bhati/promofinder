import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from promofinder.parser import parse_text, parse_label, parse_zip, fmt  # noqa: E402

LOWER = """EPISODE NUMBER: 1
EPISODE LOGLINE: Juliana is betrayed at the altar.
CONTINUITY NOTES: Veil on.

--- SCRIPT START ---

SCENE 01
Scene heading: INT. CHAPEL - DAY
Scene start: 00:00.00
Scene end: 00:10.00
Actions and dialogue:

**CAMERA:**
Start: (00:00.00) | End: (00:04.00)
Wide shot of the chapel.

**LADY JULIANA (Outraged, Trembling) (O.S.):**
Start: (00:05.00) | End: (00:07.50)
"How dare you!"
She is shaking.

**ACTION:**
Start: (00:01.00) | End: (00:03.00)
She slaps him.

**SOUND FX:**
Start: (00:08.00) | End: (00:10.00)
A gasp ripples through the room.

**BROKEN:**
no timestamp here

--- SCRIPT END ---
"""

UPPER = LOWER.replace("Scene heading:", "SCENE HEADING:").replace("Scene start:", "SCENE START:") \
    .replace("Scene end:", "SCENE END:").replace("Actions and dialogue:", "ACTIONS AND DIALOGUE:")


def test_basic_parse():
    ep = parse_text(LOWER, "episode-001-Episode 1.txt")
    assert ep.num == 1
    assert ep.logline.startswith("Juliana")
    assert ep.duration == 10.0
    kinds = [b.kind for b in ep.blocks]
    assert kinds == ["CAMERA", "ACTION", "DIALOGUE", "SFX"]  # sorted by start
    d = ep.blocks[2]
    assert d.speaker == "LADY JULIANA" and d.character == "JULIANA"
    assert d.emotion == "Outraged, Trembling"
    assert d.text == '"How dare you!" She is shaking.'
    assert [b.idx for b in ep.blocks] == [0, 1, 2, 3]
    assert any("out of order" in w for w in ep.warnings)
    assert any("without a 'Start" in w for w in ep.warnings)
    assert ep.scenes[0].start == 0.0 and ep.scenes[0].end == 10.0


def test_uppercase_headers_same_result():
    a, b = parse_text(LOWER, "x"), parse_text(UPPER, "x")
    assert [(x.kind, x.start, x.end, x.text) for x in a.blocks] == [(x.kind, x.start, x.end, x.text) for x in b.blocks]
    assert b.scenes[0].heading == "INT. CHAPEL - DAY"
    assert b.scenes[0].end == 10.0


def test_label_parsing():
    assert parse_label("CAMERA") == ("CAMERA", None, None)
    assert parse_label("SOUND FX") == ("SFX", None, None)
    assert parse_label("GERALD (O.S.)") == ("DIALOGUE", "GERALD", None)


def test_bad_file_never_crashes():
    ep = parse_text("garbage\n**X:**\nStart: (00:05.00) | End: (00:01.00)\nhi\n", "episode-007-x.txt")
    assert ep.num == 7 and ep.blocks == []
    assert any("end<start" in w for w in ep.warnings)


def test_fmt():
    assert fmt(65.5) == "01:05.50"


def test_synthetic_zip(tmp_path):
    from tests.make_fixture import build
    p = build(str(tmp_path / "s.zip"))
    eps, gw = parse_zip(p)
    assert len(eps) == 8 and not gw
    assert all(e.blocks for e in eps)
    ep6 = [e for e in eps if e.num == 6][0]
    assert len(ep6.scenes) == 2 and ep6.scenes[1].end == ep6.duration
