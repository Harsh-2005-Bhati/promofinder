"""CLI: python run_pipeline.py input.zip --out outputs/ [--llm none|gemini|groq|anthropic|openai]"""
import argparse
import os
import sys
import time

from promofinder.export import write_all
from promofinder.parser import fmt
from promofinder.pipeline import run
from promofinder.validate import passes


def main(argv=None):
    ap = argparse.ArgumentParser(description="PromoFinder AI: rank 20-60 s promo clips from a screenplay ZIP")
    ap.add_argument("zip", help="screenplay ZIP, a folder of .txt files, or a single episode .txt")
    ap.add_argument("--out", default=None, help="output dir (default outputs/ or outputs/llm_<provider>/)")
    ap.add_argument("--llm", default="none", choices=["none", "gemini", "groq", "anthropic", "openai", "custom"])
    ap.add_argument("--model", default=None, help="override provider model name")
    ap.add_argument("--base-url", default=None, help="OpenAI-compatible endpoint for --llm custom/openai")
    ap.add_argument("--editor-top", type=int, default=20, help="promos in the editor pack (0 = skip)")
    ap.add_argument("--fps", type=int, default=30, help="frame rate for EDL/clip-sheet timecodes")
    ap.add_argument("--video-dir", default="videos", help="folder with episode videos (for cut scripts)")
    ap.add_argument("--video-ext", default=".mp4")
    a = ap.parse_args(argv)
    out = a.out or ("outputs" if a.llm == "none" else os.path.join("outputs", f"llm_{a.llm}"))

    provider = None
    if a.llm != "none":
        from promofinder.llm import get_provider
        try:
            provider = get_provider(a.llm, model=a.model, base_url=a.base_url)
        except ValueError as ex:
            sys.exit(f"error: {ex}")
    t0 = time.time()
    res = run(a.zip, provider=provider, cache_dir=os.path.join("outputs", "cache"),
              progress=lambda i, n, ep: print(f"\r[{i+1}/{n}] ep {ep.num}", end="", file=sys.stderr))
    print(file=sys.stderr)
    res.meta["elapsed_s"] = round(time.time() - t0, 1)
    paths = write_all(out, res.promos, res.cold_opens, res.meta)
    if a.editor_top:
        from promofinder import editor
        files = editor.build(res.promos, res.cold_opens, res.episodes, top=a.editor_top, fps=a.fps,
                             video_dir=a.video_dir, ext=a.video_ext)
        paths += editor.write(os.path.join(out, "editor_pack"), files)

    m = res.meta
    nwarn = sum(len(e.warnings) for e in res.episodes) + len(res.warnings)
    print(f"\n== PromoFinder summary ({m['provider']}) ==")
    print(f"episodes parsed      : {m['episodes_parsed']}  (blocks {m['blocks']}, runtime {m['total_runtime_s']} s)")
    print(f"parse warnings       : {nwarn}")
    for w in res.warnings:
        print("  [global]", w)
    for e in res.episodes:
        for w in e.warnings:
            print(f"  [ep {e.num}] {w}")
    print(f"candidates generated : {m['candidates_generated']}  -> kept {m['promos_kept']} after NMS/top-5")
    print(f"validator pass rate  : {m['validator_pass']}/{m['promos_kept']} = {m['validator_pass_rate']:.1%}")
    print(f"cold-open promos     : {m['cold_open_promos']} (pass rate {m['cold_open_pass_rate']:.1%})")
    if m.get("llm"):
        print(f"llm                  : {m['llm']}")
    print("\nTop 10 (post first):")
    for p in res.promos[:10]:
        segs = "; ".join(f"ep{s.ep} {fmt(s.start)}-{fmt(s.end)}" for s in p.segments)
        ok = "PASS" if passes(p.flags) else "FLAG " + ",".join(p.flags)
        print(f"{p.rank:>2}. {p.id:<10} {segs} ({p.duration:.1f}s) total={p.total:.3f} {ok}")
        print(f"     hook: {p.hook_text[:90]}")
        print(f"     end : {p.cliffhanger_text[:90]}")
    print("\nwrote:", ", ".join(paths))


if __name__ == "__main__":
    main()
