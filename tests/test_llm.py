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


def test_gemini_model_fallback_and_backoff(monkeypatch):
    from promofinder import llm

    def fake_req(url, headers, body=None, timeout=120):
        if url.endswith("/models?pageSize=200"):
            return {"models": [{"name": f"models/{n}", "supportedGenerationMethods": ["generateContent"]}
                               for n in ("gemini-2.5-flash", "gemini-3.6-flash", "gemini-3.6-flash-lite",
                                         "gemini-3.8-flash-preview")]}
        if "gemini-old" in url:
            raise llm.HTTPStatusError(404, b"gone")
        return {"candidates": [{"content": {"parts": [{"text": '{"judgments": []}'}]}}]}

    monkeypatch.setattr(llm, "_request", fake_req)
    g = llm.GeminiProvider("k", "gemini-old")
    assert g.judge("p", {}) == {"judgments": []} and g.model == "gemini-3.6-flash"

    n = {"c": 0}

    def flaky(url, headers, body=None, timeout=120):
        n["c"] += 1
        if n["c"] < 3:
            raise llm.HTTPStatusError(429, b"rate")
        return {"ok": 1}

    monkeypatch.setattr(llm, "_request", flaky)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    assert llm._post("u", {}, {}) == {"ok": 1} and n["c"] == 3


def test_adjusted_range_texts_must_come_from_final_range(tmp_path):
    """Regression for the Gemini run: texts quoted from the ORIGINAL clip after an adjust are flagged."""
    from promofinder.parser import parse_zip

    eps, _ = parse_zip(_zip(tmp_path))
    E = {e.num: e for e in eps}

    class Adj(LLMProvider):
        name, model = "adj", "adj-1"

        def __init__(self, stale):
            self.stale = stale

        def judge(self, prompt, schema):
            out = []
            for cid, a, b in re.findall(r"- (E\d+-P\d+): blocks \[(\d+)\]\.\.\[(\d+)\]", prompt):
                ep = E[int(cid[1:4])]
                a, b = int(a), int(b)
                na = a + 1 if a + 1 <= b else a  # shift start by one block
                final = [x for x in ep.blocks[na:b + 1] if x.is_line]
                orig = [x for x in ep.blocks[a:b + 1] if x.is_line]
                src = orig if self.stale else final
                out.append({"candidate_id": cid, "hook_score": 4, "cliffhanger_score": 4, "standalone_score": 4,
                            "hook_text": src[0].text, "cliffhanger_text": src[-1].text, "why": "x",
                            "adjust": {"first_idx": na, "last_idx": b}})
            return {"judgments": out}

    good = run(_zip(tmp_path), provider=Adj(stale=False))
    adjusted = [p for p in good.promos if "llm_adjusted" in p.flags]
    assert adjusted and not any("hook_text_not_in_window" in p.flags for p in adjusted)
    assert "If you return an adjust range" in __import__("promofinder.prompts", fromlist=["x"]).build_prompt(
        eps[0], good.promos[:1])
