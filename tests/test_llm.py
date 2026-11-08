"""LLM layer tests with fake providers (no network)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from promofinder.llm import LLMProvider, extract_json  # noqa: E402
from promofinder.pipeline import run  # noqa: E402
from promofinder.validate import passes  # noqa: E402
from tests.make_fixture import build  # noqa: E402
import re  # noqa: E402


class Fake(LLMProvider):
    name, model = "fake", "fake-1"

    def __init__(self, mode):
        self.mode, self.calls = mode, 0

    def judge(self, prompt, schema):
        self.calls += 1
        if self.mode == "badjson":
            raise ValueError("not json")
        cands = re.findall(r"- (E\d+-P\d+): blocks \[(\d+)\]\.\.\[(\d+)\]", prompt)
        out = []
        for cid, a, b in cands:
            j = {"candidate_id": cid, "hook_score": 5, "cliffhanger_score": 4, "standalone_score": 3,
                 "hook_text": "", "cliffhanger_text": "", "why": "fake", "adjust": None}
            if self.mode == "hallucinate":
                j["hook_text"] = "The spaceship lands on Mars tonight"
            if self.mode == "bad_adjust":
                j["adjust"] = {"first_idx": 0, "last_idx": 9999}
            if self.mode == "short_adjust":
                j["adjust"] = {"first_idx": int(a), "last_idx": int(a)}  # one block -> <20 s -> discarded
            out.append(j)
        return {"judgments": out}


def _zip(tmp_path):
    return build(str(tmp_path / "s.zip"))


def test_llm_scores_replace_heuristic(tmp_path):
    res = run(_zip(tmp_path), provider=Fake("ok"))
    p = res.promos[0]
    assert p.scores["hook"] == 1.0 and p.scores["cliffhanger"] == 0.75 and p.llm["why"] == "fake"
    assert "hook" in p.heuristic and all(passes(x.flags) for x in res.promos)


def test_hallucinated_text_is_flagged(tmp_path):
    res = run(_zip(tmp_path), provider=Fake("hallucinate"))
    assert all("hook_text_not_in_window" in p.flags for p in res.promos)


def test_invalid_adjust_discarded(tmp_path):
    for mode in ("bad_adjust", "short_adjust"):
        res = run(_zip(tmp_path), provider=Fake(mode))
        assert all("llm_adjust_discarded" in p.flags for p in res.promos)
        assert all(20 <= p.duration <= 60 for p in res.promos)


def test_bad_json_retry_then_fallback(tmp_path):
    f = Fake("badjson")
    res = run(_zip(tmp_path), provider=f)
    assert f.calls == 2 * len(res.episodes)  # one retry per episode
    assert all("llm_fallback" in p.flags for p in res.promos)


def test_cache(tmp_path):
    f = Fake("ok")
    run(_zip(tmp_path), provider=f, cache_dir=str(tmp_path / "cache"))
    n = f.calls
    res = run(_zip(tmp_path), provider=f, cache_dir=str(tmp_path / "cache"))
    assert f.calls == n and res.meta["llm"]["cached"] == len(res.episodes)


def test_extract_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": 2} hope that helps') == {"a": 2}
