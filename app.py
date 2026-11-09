"""PromoFinder AI — Streamlit UI.  streamlit run app.py"""
import datetime as dt
import html
import json
import os

import pandas as pd
import streamlit as st

from promofinder.export import to_csv, to_json, review_csv, promo_row
from promofinder.parser import fmt
from promofinder.pipeline import run
from promofinder.validate import passes, ALL_CHECKS

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULTS = [("Local pack (data/input.zip)", os.path.join(HERE, "data", "input.zip")),
            ("Synthetic sample (public demo)", os.path.join(HERE, "sample_data", "synthetic_sample.zip"))]
REASONS = ["weak hook", "weak cliffhanger", "missing context", "spoiler", "timestamp issue", "other"]
PROVIDERS = ["none", "gemini", "groq", "anthropic", "openai"]

st.set_page_config(page_title="PromoFinder AI", page_icon="🎬", layout="wide")
ss = st.session_state
ss.setdefault("decisions", {})
ss.setdefault("review_log", [])


def secret(name):
    try:
        return st.secrets.get(name)
    except Exception:
        return None


# ---------------- sidebar ----------------
with st.sidebar:
    st.title("🎬 PromoFinder AI")
    up = st.file_uploader("Screenplay ZIP, or episode .txt files", type=["zip", "txt"], accept_multiple_files=True)
    avail = [(l, p) for l, p in DEFAULTS if os.path.exists(p)]
    src_label = None
    if not up and avail:
        src_label = st.radio("…or use bundled", [l for l, _ in avail], index=0)
    provider_name = st.selectbox("LLM judge", PROVIDERS, index=0,
                                 help="'none' = rule-based only. LLMs only re-score/adjust by block index.")
    key = ""
    if provider_name == "gemini":
        st.caption("⚠️ Gemini *free tier* inputs may be used by Google to improve its products. Don't send "
                   "confidential scripts on a free key; use the synthetic sample or a paid key.")
    if provider_name != "none":
        key = st.text_input(f"{provider_name} API key (session only)", type="password",
                            help="Leave blank to use env var / st.secrets")
    go = st.button("Run", type="primary", width="stretch")


def get_source():
    if up:
        if len(up) == 1 and up[0].name.lower().endswith(".zip"):
            return up[0].getvalue(), up[0].name
        txts = [(f.name, f.getvalue()) for f in up if f.name.lower().endswith(".txt")]
        if txts:
            return txts, f"{len(txts)} uploaded .txt file(s)"
        return up[0].getvalue(), up[0].name
    for l, p in avail:
        if l == src_label:
            with open(p, "rb") as f:
                return f.read(), os.path.basename(p)
    return None, None


@st.cache_data(show_spinner=False)
def run_rules(data):
    return run(data)


def do_run():
    data, name = get_source()
    if data is None:
        st.warning("Upload a ZIP first.")
        return
    if isinstance(data, list):
        data = sorted(data)
    try:
        if provider_name == "none":
            res = run_rules(data)
        else:
            from promofinder.llm import get_provider
            env_key = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
                       "openai": "OPENAI_API_KEY"}[provider_name]
            prov = get_provider(provider_name, api_key=key or secret(env_key) or None)
            bar = st.progress(0.0, "Judging episodes…")
            res = run(data, provider=prov, cache_dir=os.path.join(HERE, "outputs", "cache"),
                      progress=lambda i, n, ep: bar.progress((i + 1) / n, f"Episode {ep.num} ({i+1}/{n})"))
            bar.empty()
    except Exception as ex:
        st.error(f"Run failed: {type(ex).__name__}: {ex}")
        return
    ss.result, ss.source_name = res, name


if go or ("result" not in ss and get_source()[0] is not None):
    with st.spinner("Parsing and scoring…"):
        do_run()

if "result" not in ss:
    st.info("Upload a screenplay ZIP in the sidebar and press **Run**.")
    st.stop()

res = ss.result
if not res.promos:
    st.error("No promos could be generated from this input.")
    for w in res.warnings:
        st.warning(w)
    for e in res.episodes:
        for w in e.warnings:
            st.text(f"ep {e.num}: {w}")
    st.stop()
epmap = {e.num: e for e in res.episodes}
allp = res.promos + res.cold_opens
for p in allp:  # apply reviewer decisions
    p.status = ss.decisions.get(p.id, {}).get("decision", "pending")

m = res.meta
c = st.columns(6)
c[0].metric("Episodes", m["episodes_parsed"])
c[1].metric("Runtime", f"{m['total_runtime_s']/60:.0f} min")
c[2].metric("Candidates", m["candidates_generated"])
c[3].metric("Promos kept", m["promos_kept"])
c[4].metric("Validator pass", f"{m['validator_pass_rate']:.0%}")
c[5].metric("Provider", m["provider"])
st.caption(f"Source: {ss.source_name} · run {m['timestamp']}")


def excerpt_html(p, ctx=2.0):
    rows = []
    for si, seg in enumerate(p.segments):
        ep = epmap[seg.ep]
        if len(p.segments) > 1:
            rows.append(f"<tr><td colspan=3 style='background:#eee'><b>Segment {si+1}</b> · ep {seg.ep} "
                        f"{fmt(seg.start)}–{fmt(seg.end)}</td></tr>")
        hook_end = p.segments[0].start + 3.0
        cliff_start = p.segments[-1].end - 5.0
        for b in ep.blocks:
            if b.end < seg.start - ctx or b.start > seg.end + ctx:
                continue
            inside = b.start >= seg.start - 0.01 and b.end <= seg.end + 0.01
            style = "color:#999" if not inside else ""
            tag = ""
            if inside and si == 0 and b.start < hook_end:
                style += ";background:#fff3b0"; tag = "HOOK"
            if inside and si == len(p.segments) - 1 and b.end > cliff_start:
                style += ";background:#ffd6d6"; tag = (tag + " CLIFF").strip()
            who = b.label if b.kind == "DIALOGUE" else b.kind
            rows.append(f"<tr style='{style}'><td style='white-space:nowrap'>[{b.idx}] {fmt(b.start)}–{fmt(b.end)}"
                        f"</td><td><b>{html.escape(who)}</b> <small>{tag}</small></td>"
                        f"<td>{html.escape(b.text)}</td></tr>")
    return ("<div style='max-height:420px;overflow:auto'><table style='font-size:0.85em;width:100%'>"
            + "".join(rows) + "</table></div>"
            "<small>🟨 first 3 s (hook) · 🟥 last 5 s (cliffhanger) · grey = context outside the cut</small>")


def decide(p, decision, reason, note):
    ss.decisions[p.id] = {"decision": decision, "reason": reason if decision == "rejected" else "", "note": note}
    ss.review_log.append({"timestamp": dt.datetime.now().isoformat(timespec="seconds"), "promo_id": p.id,
                          "episode": p.ep, "segments": "; ".join(s.label() for s in p.segments),
                          "decision": decision, "reason": reason if decision == "rejected" else "", "note": note})


def promo_card(p):
    ok = passes(p.flags)
    segs = " + ".join(f"ep{s.ep} {fmt(s.start)}–{fmt(s.end)}" for s in p.segments)
    badge = {"approved": "✅", "rejected": "❌"}.get(p.status, "")
    title = (f"{badge} #{p.rank or '-'} {p.id} · {segs} · {p.duration:.1f}s · score {p.total:.2f}"
             f"{'' if ok else ' · ⚠️ ' + ', '.join(f for f in p.flags if f in ALL_CHECKS)}")
    with st.expander(title):
        a, b = st.columns([3, 2])
        with a:
            st.markdown(f"**Hook:** {html.escape(p.hook_text)}")
            st.markdown(f"**Cliffhanger:** {html.escape(p.cliffhanger_text)}")
            st.markdown(f"**Why it works:** {p.why}")
            st.markdown(excerpt_html(p), unsafe_allow_html=True)
        with b:
            sc = pd.DataFrame({"final": p.scores, "rules": {k: p.heuristic.get(k) for k in p.scores}})
            st.dataframe(sc, width="stretch")
            st.write("Flags:", ", ".join(p.flags) or "none")
            ep = epmap[p.ep]
            st.caption(f"Ep {ep.num} logline: {ep.logline}")
            reason = st.selectbox("Reject reason", REASONS, key=f"r_{p.id}")
            note = st.text_input("Note", key=f"n_{p.id}")
            x, y = st.columns(2)
            if x.button("Approve", key=f"a_{p.id}", width="stretch"):
                decide(p, "approved", reason, note); st.rerun()
            if y.button("Reject", key=f"x_{p.id}", width="stretch"):
                decide(p, "rejected", reason, note); st.rerun()


t1, t2, t3, t4, t5 = st.tabs(["Ranked promos", "Cold opens (multi-segment)", "Episodes", "Quality", "Export"])

with t1:
    f1, f2, f3 = st.columns(3)
    eps_sel = f1.multiselect("Episodes", sorted(epmap))
    only = f2.selectbox("Show", ["all", "validator pass", "flagged", "pending", "approved", "rejected"])
    n = f3.slider("How many", 5, max(5, len(res.promos)), min(20, max(5, len(res.promos))))
    view = [p for p in res.promos if (not eps_sel or p.ep in eps_sel)]
    view = [p for p in view if only == "all" or (only == "validator pass" and passes(p.flags))
            or (only == "flagged" and not passes(p.flags)) or p.status == only]
    df = pd.DataFrame([promo_row(p) for p in view[:n]])
    if not df.empty:
        st.dataframe(df[["rank", "id", "segments", "duration", "total", "hook", "cliffhanger", "standalone",
                         "spoiler_risk", "validator_pass", "status", "hook_text", "cliffhanger_text"]],
                     width="stretch", hide_index=True)
    st.subheader("Top 10 to post first")
    for p in res.promos[:10]:
        st.markdown(f"- **{p.id}** ep {p.ep} {fmt(p.segments[0].start)}–{fmt(p.segments[0].end)} "
                    f"({p.duration:.1f}s, {p.total:.2f}) — {p.why[:160]}")
    st.subheader("Review")
    for p in view[:n]:
        promo_card(p)

with t2:
    st.caption("Hook segment (≤6 s, strongest early line) + main segment ending on the episode's best "
               "cliffhanger. Same episode, in order, total 20–60 s.")
    for p in res.cold_opens:
        promo_card(p)
    if not res.cold_opens:
        st.write("No valid cold-open combinations.")

with t3:
    st.dataframe(pd.DataFrame([{"ep": e.num, "file": e.file, "duration_s": e.duration, "scenes": len(e.scenes),
                                "blocks": len(e.blocks),
                                "dialogue": sum(b.kind == "DIALOGUE" for b in e.blocks),
                                "warnings": len(e.warnings), "logline": e.logline} for e in res.episodes]),
                 width="stretch", hide_index=True)
    for w in res.warnings:
        st.warning(w)
    for e in res.episodes:
        for w in e.warnings:
            st.text(f"ep {e.num}: {w}")

with t4:
    q = st.columns(4)
    q[0].metric("Validator pass (single)", f"{m['validator_pass_rate']:.1%}")
    q[1].metric("Validator pass (cold open)", f"{m['cold_open_pass_rate']:.1%}")
    dec = [d["decision"] for d in ss.decisions.values()]
    q[2].metric("Reviewed", len(dec))
    q[3].metric("Approve rate", f"{dec.count('approved')/len(dec):.0%}" if dec else "–")
    top20 = res.promos[:20]
    rev20 = [p for p in top20 if p.status != "pending"]
    st.write(f"Top-20 precision proxy: {sum(p.status == 'approved' for p in rev20)}/{len(rev20)} reviewed approved")
    fl = pd.Series([f for p in allp for f in p.flags]).value_counts()
    st.write("Flag histogram (all promos)")
    if len(fl):
        st.bar_chart(fl)
    else:
        st.success("No flags raised.")
    rr = pd.Series([d["reason"] for d in ss.decisions.values() if d["decision"] == "rejected"]).value_counts()
    if len(rr):
        st.write("Rejection reasons")
        st.bar_chart(rr)
        top_reason, share = rr.index[0], rr.iloc[0] / rr.sum()
        hint = {"weak hook": "hook rules (first 3 s)", "weak cliffhanger": "ending rules (last 5 s)",
                "missing context": "standalone/context rules", "spoiler": "spoiler word list / penalty",
                "timestamp issue": "candidate cut points", "other": "review notes"}.get(top_reason, "rules")
        st.info(f"**{share:.0%} of your rejections are '{top_reason}'.** That points at the {hint}. "
                "Export review_log.csv; `python feedback.py <zip>` checks whether the matching score already "
                "separates approved from rejected clips before you change any weights.")
    if m.get("llm"):
        st.json(m["llm"])

with t5:
    st.download_button("promos.json", to_json(res.promos, res.cold_opens, m), "promos.json", "application/json")
    st.download_button("promos.csv", to_csv(res.promos), "promos.csv", "text/csv")
    st.download_button("cold_open_promos.csv", to_csv(res.cold_opens), "cold_open_promos.csv", "text/csv")
    st.download_button("run_meta.json", json.dumps(m, indent=2, default=str), "run_meta.json", "application/json")
    st.download_button("review_log.csv", review_csv(ss.review_log), "review_log.csv", "text/csv")
    st.divider()
    st.subheader("Editor pack")
    st.caption("Clip sheet, one-page briefs, EDL (Premiere/Resolve import) and ffmpeg cut scripts for the top promos. "
               "Assumes each episode video has the same name as its script file.")
    e1, e2, e3, e4 = st.columns(4)
    ep_top = e1.number_input("Top N promos", 1, max(1, len(res.promos)), min(20, max(1, len(res.promos))))
    ep_fps = e2.selectbox("Frame rate", [30, 25, 24, 60], index=0)
    ep_dir = e3.text_input("Video folder", "videos")
    ep_ext = e4.selectbox("Video extension", [".mp4", ".mov", ".mkv"], index=0)
    from promofinder import editor
    pack = editor.build(res.promos, res.cold_opens, res.episodes, top=int(ep_top), fps=int(ep_fps),
                        video_dir=ep_dir, ext=ep_ext)
    st.download_button("editor_pack.zip", editor.as_zip(pack), "editor_pack.zip", "application/zip")
    with st.expander("Preview briefs.md"):
        st.markdown(pack["briefs.md"][:20000])
