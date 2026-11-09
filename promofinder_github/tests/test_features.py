"""Unit tests for the rule features added after the top-20 review (no real data needed)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from promofinder import features as F  # noqa: E402
from promofinder.models import Segment  # noqa: E402
from promofinder.parser import Block, Episode  # noqa: E402


def B(i, kind, start, end, text, speaker=None, emotion=None):
    return Block(ep=1, idx=i, kind=kind, speaker=speaker, emotion=emotion, start=start, end=end, text=text,
                 scene=1, label=speaker or kind, character=speaker)


def ep_of(blocks, num=1, dur=None):
    return Episode(num=num, file="x", logline="", continuity="", duration=dur or blocks[-1].end, blocks=blocks)


def test_word_boundaries():
    assert F._has("He carries firewood", F.SHOCK) == []
    assert F._has("She slaps him", F.SHOCK) == ["slap"]
    assert F._has("He is trembling", ["trembl"], stem=True) == ["trembl"]


def test_mid_conversation_opener():
    bl = [B(0, "DIALOGUE", 0, 2, '"Who betrayed us?"', "A"), B(1, "DIALOGUE", 2.5, 3.5, '"A traitor?"', "B"),
          B(2, "DIALOGUE", 4, 30, '"Yes, and he is here."', "A")]
    ep = ep_of(bl)
    seg = Segment(1, 2.5, 30, 1, 2)
    assert F.mid_conversation(ep, seg, F.window_blocks(ep, seg))
    bl[1].text = '"Stop!"'  # shouted exclamation is a self-contained hook
    assert not F.mid_conversation(ep, seg, F.window_blocks(ep, seg))


def test_calm_ending_is_not_a_cliffhanger():
    tense = [B(0, "DIALOGUE", 0, 20, '"Who sent you?"', "A", "Roaring")]
    calm = [B(0, "DIALOGUE", 0, 18, '"Who sent you?"', "A", "Roaring"),
            B(1, "ACTION", 18, 20, "They walk together into the sunset.")]
    swell = B(2, "SFX", 19, 20, "Cello swell into a cliffhanger hold.")
    for bl, lo, hi in ((tense, 0.25, 1.0), (calm + [swell], 0.0, 0.1)):
        ep = ep_of(bl, dur=40)
        seg = Segment(1, 0, 20, 0, len(bl) - 1)
        c, why, _ = F.cliffhanger(ep, seg, F.window_blocks(ep, seg))
        assert lo <= c <= hi, (c, why)


def test_spoiler_scales_with_series_position():
    bl = [B(0, "DIALOGUE", 0, 25, '"You are the rightful Duke!"', "A")]
    seg = Segment(1, 0, 25, 0, 0)
    early, _ = F.spoiler(ep_of(bl, num=3), seg, bl, 50)
    late, why = F.spoiler(ep_of(bl, num=48), seg, bl, 50)
    assert early == 0 and late > 0.4 and any("rightful" in w for w in why)


def test_inciting_beat_just_before_cut():
    bl = [B(0, "ACTION", 8, 9.5, "She strikes him with the crop."),
          B(1, "ACTION", 10, 11, "He gasps, clutching his face."),
          B(2, "DIALOGUE", 11, 35, '"You will regret this."', "A")]
    ep = ep_of(bl)
    seg = Segment(1, 10, 35, 1, 2)
    s, why = F.standalone(ep, seg, F.window_blocks(ep, seg))
    assert any("inciting beat" in w for w in why)
