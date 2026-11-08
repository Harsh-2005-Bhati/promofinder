# PromoFinder AI

**Live app:** https://promofinder-rb4wbkeye8i8jttfu7ay67.streamlit.app/ (opens on a synthetic demo pack; upload the
screenplay ZIP in the sidebar to run it on the real pack) · **Code:** https://github.com/Harsh-2005-Bhati/promofinder

Reads a microdrama screenplay ZIP and outputs ranked **20–60 s promo clips** (episode, segment start/end,
hook, cliffhanger, why-it-works). Hybrid design: **deterministic code owns every timestamp**; an optional
LLM only re-scores code-generated candidates and may suggest a different *block-index* range, which code
converts to times and re-validates.

## Quick start (Windows, from `E:\promofinder`)

```powershell
cd E:\promofinder\promofinder
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

## Results on the real pack (rule-based, `--llm none`)
All numbers below come from `outputs/run_meta.json`, `outputs/promos.csv` and `outputs/review_log.csv`
(unedited). The run is deterministic: re-running the CLI on the same ZIP reproduces `promos.csv` byte for byte.

| metric | value |
|---|---|
| Episodes parsed | **50 / 50** (0 files failed) |
| Blocks parsed | **3,727** (1,754 CAMERA + 1,487 DIALOGUE + 372 ACTION + 114 SOUND FX, matches the audit) |
| Total runtime | 6,162.6 s (≈103 min) |
| Parse warnings | 15: overlapping dialogue pairs and out-of-order blocks, all known quirks, all handled |
| Candidate windows (20–60 s) | **16,167** |
| Promos kept (NMS + top 5/episode) | **196** (some short episodes have <5 sufficiently distinct windows) |
| Validator pass rate, single-segment | **196 / 196 = 100 %** |
| Validator pass rate, cold-open (2-segment) | **40 / 40 = 100 %** |
| Top-20 diversity | 20 different episodes |
| Pipeline run time | ≈18 s for the full pack (rule-based, no API calls) |

### Precision proxy: top-20 review
The global top 20 were reviewed in the app (Approve / Reject + reason tag; log in `outputs/review_log.csv`).
Decisions were drafted by Claude after reading each clip's full script and checked by me.

**Approved 11 / 20 = 55 %.** Rejections: weak cliffhanger 3, weak hook 2, missing context 2, spoiler 2.

### Recall proxy: key logline moments
For the four episodes the blueprint names, a top-3 promo of that episode overlaps the key moment in all four
cases (4 / 4): altar betrayal ep 1 (E001-P1, #3 overall, contains "I changed my mind."), briars ep 13
(E013-P1, #16), fire ep 18 (E018-P2), duke proclamation ep 42 (E042-P1, #15). The planned 10-episode check
was cut to these 4 for time.

### Failure cases (verbatim, from the reviewed top 20)
1. **Spoilers score highly.** E045-P1 (#4) opens on *"You're the Duke?"*; E042-P1 (#15) ends on the
   proclamation *"This is my son… The rightful Duke of Ashburn!"*. Reveal lines contain the strongest
   shock/reveal words, and the rules have no notion of where an episode sits in the series arc.
2. **Fake cliffhangers.** E025-P1 (#10) ends on *"Alexander turns, falling into step beside Juliana…"*;
   E016-P1 (#14) ends on a tender look plus an SFX line that literally says "cliffhanger hold", even though
   the actual twist (*"Gerald Harrington paid us!"*) is mid-clip. The SFX lexicon rewards "swell" regardless
   of what the scene is doing; E007-P1 (#12) ends on the villains simply leaving.
3. **Mid-conversation openers.** E035-P1 (#2) *"A traitor?"*, E043-P1 (#9) *"We will not."*, E038-P1
   (#18) *"Why?"*. Short replies aren't detected as needing context; the standalone check only catches a
   question just before the window and conjunction/pronoun openers.
4. **Cut just after the inciting beat.** E024-P1 (#20) starts on Juliana's reaction to a strike that happens
   just before the window.
5. **Fixed during review:** E003-P1 originally opened on *"...and it isn't you."*; the leading ellipsis hid
   the "and" opener from the standalone penalty. Stripping leading `.…-—` fixed it; the promo now opens on
   *"You have humiliated this family enough for one day."*

### What I'd do next
- Run the LLM judge (`--llm gemini`) and report overlap@20 against the rule-based top 20. Failure types 1–3
  are judgement calls the rules cannot make, and the prompt already asks the model to avoid spoilers.
- Add a "spoiler" feature (penalise reveal lines in the last ~20 % of the series or matching later loglines).
- Score the cliffhanger on the last *dialogue or action* line, not on SFX labels.

### How to reproduce / extend the evaluation
- Validator pass rate: printed by the CLI and stored in `run_meta.json`.
- Precision proxy: approve/reject the top 20 in the UI → Quality tab → export `review_log.csv`.
- Rules vs LLM: overlap@20 between `outputs/promos.csv` and `outputs/llm_<provider>/promos.csv`.

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
- Development and unit tests use a synthetic pack (`tests/make_fixture.py`) that reproduces the audited
  format and quirks, so the public repo and the deployed app contain no Kuku data. The real pack was run
  locally; only its outputs are committed.
- `EPISODE NUMBER: Episode 1` and `EPISODE NUMBER: 1` are both accepted; if the header is missing the number
  is taken from the file name (`episode-001-…`).
- The hosted app never stores uploads; an uploaded ZIP lives only in that browser session's memory.

## Layout
```
app.py  run_pipeline.py  requirements.txt
promofinder/ parser.py candidates.py features.py scoring.py validate.py llm.py prompts.py export.py pipeline.py models.py
tests/       test_parser.py test_pipeline.py test_llm.py make_fixture.py
sample_data/synthetic_sample.zip     outputs/
```
