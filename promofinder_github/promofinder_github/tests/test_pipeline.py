import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from promofinder.candidates import generate, spanning_dialogue  # noqa: E402
from promofinder.models import Promo, Segment  # noqa: E402
from promofinder.parser import parse_zip  # noqa: E402
from promofinder.pipeline import run  # noqa: E402
from promofinder.validate import validate, passes  # noqa: E402
from tests.make_fixture import build  # noqa: E402


def _eps(tmp_path):
    eps, _ = parse_zip(build(str(tmp_path / "s.zip")))
    return eps


def test_candidates_never_cut_dialogue(tmp_path):
    for ep in _eps(tmp_path):
        for s in generate(ep):
            assert 20 <= s.end - s.start <= 60
            assert not spanning_dialogue(ep, s.start) and not spanning_dialogue(ep, s.end)
            assert 0 <= s.start < s.end <= ep.duration + 1e-6


def _promo(seg, hook="", cliff=""):
    return Promo(id="t", segments=[seg], duration=seg.duration, hook_text=hook, cliffhanger_text=cliff,
                 why="", scores={}, total=0)


def test_validator_flags_bad_promos(tmp_path):
    ep = _eps(tmp_path)[0]
    m = {ep.num: ep}
    d = [b for b in ep.blocks if b.kind == "DIALOGUE" and b.end - b.start > 1][2]
    mid = (d.start + d.end) / 2
    flags = validate(_promo(Segment(ep.num, mid, mid + 25, 0, 0)), m)
    assert "cut_inside_dialogue" in flags
    assert "duration_out_of_range" in validate(_promo(Segment(ep.num, d.start, d.start + 5, 0, 0)), m)
    assert "seg_out_of_bounds" in validate(_promo(Segment(ep.num, 0, ep.duration + 30, 0, 0)), m)
    good = Segment(ep.num, d.start, d.start + 30, 0, 0)
    assert "hook_text_not_in_window" in validate(_promo(good, hook="The dragon ate my homework yesterday"), m)
    assert "hook_text_not_in_window" not in validate(_promo(good, hook=d.text), m)


def test_full_run_and_diversity(tmp_path):
    res = run(build(str(tmp_path / "s.zip"), n=50, seed=3))  # rule needs >=10 episodes
    assert res.promos and all(passes(p.flags) for p in res.promos)
    top = res.promos[:20]
    for e in {p.ep for p in top}:
        assert sum(p.ep == e for p in top) <= 2
    assert [p.rank for p in res.promos] == list(range(1, len(res.promos) + 1))
    for p in res.cold_opens:
        assert len(p.segments) == 2 and p.segments[0].end <= p.segments[1].start
