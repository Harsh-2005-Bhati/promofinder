# PromoFinder AI

Reads a microdrama screenplay ZIP and outputs ranked **20–60 s promo clips** (episode, segment start/end,
hook, cliffhanger, why-it-works). Hybrid design: **deterministic code owns every timestamp**; an optional
LLM only re-scores code-generated candidates and may suggest a different *block-index* range, which code
converts to times and re-validates.

## Quick start (Windows, from `E:\promofinder`)

```powershell
cd E:\promofinder
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                         # 15 tests, no network needed

# put the screenplay pack at data\input.zip (data/ is git-ignored, never commit it)
python run_pipeline.py data\input.zip --out outputs\        # rule-based, prints the summary
streamlit run app.py                                         # UI at http://localhost:8501
```

macOS/Linux: same commands with `source .venv/bin/activate` and `/` paths.

### Optional LLM judge
```powershell
set GEMINI_API_KEY=...        # or GROQ_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY
python run_pipeline.py data\input.zip --llm gemini           # -> outputs\llm_gemini\
```
Model overrides: `GEMINI_MODEL`, `GROQ_MODEL`, `ANTHROPIC_MODEL`, `OPENAI_MODEL` env vars or `--model`.
Defaults: `gemini-2.5-flash`, `llama-3.3-70b-versatile`, `claude-haiku-5-5`, `gpt-4o-mini`.
Responses are cached in `outputs/cache/{provider}_{ep}.json` keyed by prompt hash (re-runs are free).

## Outputs
| file | content |
|---|---|
| `promos.json` | run meta + every kept promo (segments with seconds and `MM:SS.ss`, rule scores, LLM scores, flags) + cold-open promos |
| `promos.csv` | one row per promo; `segments` as `ep:MM:SS.ss-MM:SS.ss; …` |
| `cold_open_promos.csv` | multi-segment promos (stretch goal) |
| `run_meta.json` | provider, model, timestamp, counts, validator pass rate, all parse warnings |
| `review_log.csv` | downloaded from the UI's Export tab: approve/reject decisions with reason tags |

`outputs/synthetic_sample/` holds a run on the **synthetic** demo pack only (invented story, safe to publish).
Raw outputs for the real pack are produced by the command above and are not edited by hand.

## Pipeline
1. **Parse** (`parser.py`): regex, case-insensitive headers (ep 6 is UPPERCASE), `MM:SS.ss` → seconds,
   blocks sorted by start, speaker/emotion split, character alias normalisation. Every anomaly becomes a
   warning; one bad file never stops the run.
2. **Candidates** (`candidates.py`): starts = each DIALOGUE/ACTION start; ends = each DIALOGUE/ACTION/SFX end
   + 0.3 s pad (capped at episode end); keep 20–60 s. If a dialogue line spans a cut, the start moves to the
   line start; the end pad shrinks back to the line edge (or extends past an overlapping line).
3. **Features** (`features.py`, no API): hook (first 3 s), cliffhanger (last 5 s), standalone, density, each
   0–1 with weights documented inline and human-readable reasons kept per promo.
4. **Prune** (`scoring.py`): per episode NMS (drop windows overlapping >50 % of the shorter one with a better
   one), top 5.
5. **LLM judge** (optional, `llm.py` + `prompts.py`): one call per episode with numbered blocks + the 5
   candidates; JSON with 1–5 scores, verbatim hook/cliffhanger text, `adjust:{first_idx,last_idx}|null`.
   Validated with pydantic; bad JSON → 1 retry → heuristic fallback (`llm_fallback` flag).
6. **Score**: `total = 0.35 hook + 0.35 cliffhanger + 0.20 standalone + 0.10 density`; LLM scores
   (mapped 1–5 → 0–1) replace rule scores when present; both are kept.
7. **Rank**: global sort; top 20 has ≤2 promos per episode; top 10 marked `post_first`.
8. **Cold opens** (stretch): strongest early hook line (≤6 s) + the episode's best-cliffhanger window,
   same episode, in order, non-overlapping, 20–60 s total.
9. **Validate** (`validate.py`, every promo): start<end; within episode; total 20–60 s; segments in order
   and non-overlapping; no cut inside a dialogue line; a DIALOGUE/ACTION block starts in the first 3 s;
   hook/cliffhanger text fuzzy-matches (≥0.8) text inside the window (catches LLM hallucination).
   Failing promos are **kept and flagged, never fixed**.

## Streamlit UI
Sidebar: ZIP upload (or bundled `data/input.zip` if present locally, else the synthetic sample), provider
(default `none`), session-only API key, Run. Tabs: **Ranked promos** (filterable table, top-10 "post first",
expander per promo with script excerpt — first 3 s in yellow, last 5 s in red, context in grey — scores
rules-vs-final, flags, Approve/Reject with reason tag + note), **Cold opens**, **Episodes** (parse stats +
warnings), **Quality** (validator pass rates, approve rate, top-20 precision proxy, flag + rejection-reason
histograms), **Export** (JSON/CSV/review log). Decisions live in `st.session_state` (no database).

## Deploy to Streamlit Community Cloud
1. Create a **public GitHub repo** and push this folder (`data/` and `*.zip` are git-ignored except the
   synthetic sample — double-check with `git status` that no screenplay file is staged):
   ```
   git remote add origin https://github.com/<you>/promofinder.git
   git push -u origin master
   ```
2. On https://share.streamlit.io → **Create app** → pick the repo/branch, main file `app.py`, Python 3.11+.
3. (Optional) *Advanced settings → Secrets*: `GEMINI_API_KEY = "..."`. Without it the app runs rule-only.
4. Reviewers upload the ZIP in the sidebar; the public app ships only with the synthetic sample.

## Evaluation (fill from real runs only)
- Validator pass rate: printed by the CLI / `run_meta.json` (target 100 % on hard checks).
- Recall proxy: for 10 episodes pick the key logline moment by hand (e.g. altar betrayal ep 1, briars ep 13,
  fire ep 18, duke reveal ep 42) and check whether a top-3 promo of that episode overlaps it.
- Precision proxy: approve/reject the global top 20 in the UI → approve rate in the Quality tab; export
  `review_log.csv` for the reason tags.
- Rules vs LLM: overlap@20 between `outputs/promos.csv` and `outputs/llm_<provider>/promos.csv` (compare
  `segments` of the top 20).
- Copy failure cases verbatim from the flagged rows / rejected reviews.

## Assumptions
- Candidate start points are DIALOGUE/ACTION block starts only (never CAMERA/SFX), so a line or action is
  always on screen within the first second of a single-segment promo.
- "Overlapping >50 %" in NMS = intersection / duration of the shorter window.
- "No cut inside a dialogue line" uses a 0.01 s tolerance; cuts may fall inside CAMERA/ACTION/SFX blocks.
- Rare labels (VFX, TRANSITION, TEXT, SUPER, INSERT) are treated as non-speech CAMERA-like blocks; MUSIC as SFX;
  any other label is dialogue (`NAME (Emotion, …) (O.S.)`).
- Blocks with no timestamp line or with end<start are skipped with a warning (not guessed).
- Character aliases listed in the blueprint are normalised for the "≥2 named characters" standalone bonus;
  the estate-name spelling variants do not affect scoring, so they are left as written.
- The diversity rule (≤2 per episode in top 20) needs ≥10 episodes to be fully satisfiable; with fewer, the
  remaining top-20 slots are filled by score.
- Cold-open hook segments come from earlier in the same episode (blueprint: "segments in order"); no
  cross-episode combos yet.
- LLM scores 1–5 map linearly to 0–1; density always comes from rules. LLM `adjust` ranges that fail any hard
  check are discarded (`llm_adjust_discarded`) and the original window is kept.
- LLM providers are called over plain HTTPS (urllib) so no vendor SDK is needed; default model names may
  need updating via env vars.
- Development and tests used a synthetic pack (`tests/make_fixture.py`) that reproduces the audited
  format and quirks; the real pack was not available in the build environment.

## Layout
```
app.py  run_pipeline.py  requirements.txt
promofinder/ parser.py candidates.py features.py scoring.py validate.py llm.py prompts.py export.py pipeline.py models.py
tests/       test_parser.py test_pipeline.py test_llm.py make_fixture.py
sample_data/synthetic_sample.zip     outputs/
```
