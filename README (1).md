# PromoFinder AI

**Live app:** https://promofinder-rb4wbkeye8i8jttfu7ay67.streamlit.app/ (opens on a synthetic demo pack; upload the
screenplay ZIP in the sidebar to run it on the real pack) · **Code:** https://github.com/Harsh-2005-Bhati/promofinder ·
**Approach note (read this first):** [APPROACH.md](APPROACH.md)

Reads a microdrama screenplay ZIP and returns ranked **20–60 s promo clips** (episode, start/end, hook,
cliffhanger, why-it-works), plus an **editor pack** a video editor can use directly (clip sheet, briefs, EDL,
ffmpeg cut scripts). Deterministic code owns every timestamp; an optional LLM only re-scores code-generated
candidates and may suggest a different *block-index* range, which code converts to times and re-validates.

## Results at a glance (real pack: 50 episodes, 103 min)

| | v1 rules | **v2 rules** |
|---|---|---|
| Top-20 approved by review | 11 / 20 (55 %) | **16 / 20 (80 %)** |
| Validator pass rate (all kept promos) | 196 / 196 | **201 / 201 (100 %)** |
| Cold-open (2-segment) promos passing | 40 / 40 | **41 / 41 (100 %)** |
| Key logline moments covered by a top-3 promo of that episode | 4 / 4 | **4 / 4** |
| Run time, full pack | ≈18 s | ≈18 s, no API calls |
| LLM judge (synthetic pack only) | – | 6/8 episodes judged, 13/14 adjustments accepted, 3 caption mismatches caught by the validator |

Details, method and failure cases are in [Evaluation](#evaluation).

## Quick start (Windows)

```powershell
cd E:\promofinder\promofinder
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                         # 24 tests, no network needed

# put the screenplay pack at data\input.zip (data/ is git-ignored, never commit it)
python run_pipeline.py data\input.zip --out outputs\        # rule-based; prints the summary
python evaluate.py outputs\promos.csv                        # top-20 vs review labels in eval\labels.csv
streamlit run app.py                                         # UI at http://localhost:8501
```
macOS/Linux: `source .venv/bin/activate` and `/` paths.

CLI options: `--llm none|gemini|groq|anthropic|openai`, `--model`, `--editor-top 20` (0 = no editor pack),
`--fps 30`, `--video-dir videos`, `--video-ext .mp4`.

## Outputs

| file | content |
|---|---|
| `promos.json` | run meta + every kept promo (segments in seconds and `MM:SS.ss`, rule scores, LLM scores, spoiler risk, flags, reasons) + cold-open promos |
| `promos.csv` | one row per promo; `segments` as `ep:MM:SS.ss-MM:SS.ss; …` |
| `cold_open_promos.csv` | two-segment promos (teaser line + main clip) |
| `run_meta.json` | provider, model, timestamp, counts, validator pass rate, all parse warnings |
| `editor_pack/` | clip sheet, briefs, EDL, cut scripts (see below) |
| `review_log.csv` | exported from the app: approve/reject decisions with reason tags |

Committed: `outputs/` holds the unedited rule-based run on the real pack (without its editor pack, because the
briefs quote long script passages); `outputs/synthetic_sample/` holds a full run, editor pack included, on the
invented demo pack.

### Editor pack (for the promo / video team)
- `clip_sheet.csv`: one row per segment: episode video file, in/out in seconds **and timecode**, caption
  idea (the hook line), ending line, spoiler risk, flags, editor notes.
- `briefs.md`: one short brief per promo: timings, why it works, and the script excerpt with **HOOK**
  (first 3 s) and **CLIFF** (last 5 s) lines marked.
- `promos.edl`: CMX3600 EDL, importable into Premiere Pro / DaVinci Resolve as a rough-cut timeline.
- `cut_promos.sh` / `cut_promos.bat`: ffmpeg commands that cut every promo (cold opens are concatenated)
  from the episode videos, frame-accurate re-encode. Assumes each video has the script file's name.
  Verified on generated test videos: all 25 output files match the planned durations within 0.15 s.

## How it works
1. **Parse** (`parser.py`): regex, case-insensitive (ep 6 headers are UPPERCASE), `MM:SS.ss` → seconds, blocks
   sorted by start, speaker / emotion split, character alias normalisation. Anomalies become warnings; one bad
   file never stops the run.
2. **Candidates** (`candidates.py`): starts = DIALOGUE/ACTION starts; ends = DIALOGUE/ACTION/SFX ends + 0.3 s
   pad; keep 20–60 s; cuts are moved off any dialogue line they would split.
3. **Features** (`features.py`, no API, each 0–1 with reasons kept):
   - **hook** (first 3 s): line within 1 s, `!`/`?`, shock words, intense delivery; penalties for CAMERA-only
     openings and for openers that need prior context.
   - **cliffhanger** (last 5 s): judged on the last *dialogue or action line*: question, threat, reveal,
     intense delivery, tense action; penalties for calm or tender endings and resolution words. Music and
     SFX swells can only reinforce a tense line, never create one.
   - **standalone**: conjunction/pronoun openers, short replies mid-conversation, a slap or strike that
     happens just before the cut, two or more characters in conflict, starts at a scene start.
   - **spoiler risk**: identity or status reveals ("rightful Duke", "my son", "you're alive"), weighted by how
     late the episode sits in the series. Promos recruit new viewers who start at episode 1.
   - **density**: lines per second, share of intense emotion tags.
4. **Prune** (`scoring.py`): per-episode NMS (>50 % overlap of the shorter window), top 5.
5. **Score**: `0.35 hook + 0.35 cliffhanger + 0.20 standalone + 0.10 density − 0.25 spoiler_risk`.
6. **Rank**: global; the top 20 holds ≤2 promos per episode; the top 10 are marked "post first".
7. **Cold opens**: strongest early hook line (≤6 s) + the episode's best-cliffhanger clip, in order, 20–60 s.
8. **Validate** (`validate.py`, every promo): start<end, inside episode, 20–60 s total, segments ordered and
   non-overlapping, no cut inside a dialogue line, a line starts in the first 3 s, hook/cliffhanger text
   fuzzy-matches text inside the clip (catches LLM hallucination). Failing promos are kept and flagged.
9. **Optional LLM judge** (`llm.py`, `prompts.py`): one call per episode; the model sees numbered blocks and
   may only answer with block indices and 1–5 scores. pydantic validation, one retry, then rule fallback;
   cached by prompt hash; backoff on 429/5xx; Gemini auto-switches to an available model if the configured
   one is retired.

## Evaluation

**Labels.** `eval/review_v2_top20.csv` lists the current top 20 with their decisions; `eval/labels.csv` holds every review decision (episode, start, end, approved/rejected, reason,
round). A promo matches a label only if it is the same episode and **both cut points are within 1.5 s**, because
a clip with a different ending is a different promo. `evaluate.py` refuses to quote precision while any top-20
promo is unlabelled.

**Round 1 (v1 rules).** Reviewed the global top 20 in the app: 11 approved, 9 rejected (weak cliffhanger 3,
weak hook 2, missing context 2, spoiler 2). Decisions were drafted by Claude after reading each clip's full
script and checked by me.

**Fixes (v2).** Each rejection pattern became a rule (see *How it works*): spoiler risk, last-line cliffhanger
with tender/calm penalties, mid-conversation opener, inciting beat just before the cut. A word-boundary bug
("fire" matching "firewood") was found and fixed along the way.

**Round 2 (v2 rules).** The 8 round-1 approvals with unchanged cut points stayed in the top 20; all 9
rejections left it. The 12 promos new to the top 20 were reviewed blind with the same criteria: 8 approved,
4 rejected. **Top-20: 16/20 = 80 %.** The rules were then frozen; tuning further against the same labels
would only fit my own judgement.

**Caveats.** n = 20 per round. The reviewer also designed the rules, so round 2 is a held-out check of *new
clips*, not of an independent reviewer. The next step is a blind review by someone from the promo team.

**Recall proxy.** For the four episodes the blueprint names, a top-3 promo of that episode covers the key
moment in all four cases: altar betrayal ep 1 (E001-P1, #1), briars ep 13 (E013-P1, #15), fire ep 18
(E018-P1, #7), duke proclamation ep 42 (E042-P3). The ep 42 clip carries spoiler risk 0.59, so it is
deliberately ranked low globally (#148): it stays findable for an in-series recap, but isn't pushed as an
acquisition promo.

**Remaining failures (v2 top 20, verbatim).**
1. E029-P1 (#11) opens on *"You still call this a legacy?"*: the object needs context, but the line is 6
   words, so the short-reply rule doesn't fire.
2. E029-P2 (#13) ends on Juliana's lament in the cell (*"I saved her! I healed her!"*): loud and emotional,
   but not a question or threat. Rules read shouting as tension.
3. E032-P2 (#18) opens on *"Burn it."*: what "it" is only becomes clear from the previous scene.
4. E043-P1 (#20) is the title-fraud exposition in ep 43: its reveal words ("declared dead", "title") aren't
   in the identity-reveal list.

All four are judgement calls about meaning, not surface signals. That's the case for the LLM judge.

**LLM judge.** Unit-tested with fake providers (scores replace rule scores, hallucinated text is flagged,
invalid index ranges are discarded, bad JSON → retry → fallback, cache hits, model fallback, backoff), then
run with **Gemini 3.8 Flash on the synthetic pack only**. Google's pricing page says free-tier Gemini inputs
may be used to improve its products, and the screenplays are Kuku's confidential material.

Synthetic run (`outputs/llm_gemini_synthetic/`, unedited):
- 6 / 8 episodes judged; 2 hit the 120 s read timeout and **fell back to rule scores** as designed.
  Timeout is now 300 s with retries; the full run took 18.6 min (thinking model, free-tier pacing).
- 14 boundary adjustments proposed: **13 accepted, 1 discarded** by the hard checks.
- **The validator flagged 3 / 29 promos** (`hook_text_not_in_window`). Root cause: in each case Gemini
  rejected the original clip, proposed a better range, but quoted lines from the *original* range. The prompt
  never said which range the scores and quotes describe. Fixed by requiring them to describe the final range
  (regression test added). Without the validator these promos would have shipped with captions that aren't
  in the clip.
- Gemini is much stricter than the rules: on the 21 judged promos it scored **hook −0.31** and
  **standalone −0.37** lower on average (cliffhanger ≈ equal), and its lowest verdicts named calm endings
  ("Ending on a peaceful resolution deflates all accumulated tension…") and slow openings. Those are the
  same failure types found by hand in round 1.
- Synthetic episodes are near-duplicates, so this run tests the plumbing, not ranking quality.

With a no-training key (Gemini paid tier, Anthropic or OpenAI API) the real-pack comparison is two
commands: `python run_pipeline.py data\input.zip --llm gemini` then
`python evaluate.py outputs\llm_gemini\promos.csv --compare outputs\promos.csv`.

## Deploy (Streamlit Community Cloud)
1. Push this folder to a **public** GitHub repo (check that `data/` and `.venv/` are not included).
2. share.streamlit.io → **Create app** → repo, branch `main`, file `app.py` → Deploy.
3. Optional: *Settings → Secrets* `GEMINI_API_KEY = "..."`. Without it the app runs rules-only.
The hosted app ships only the synthetic sample. Uploaded ZIPs live in that browser session's memory only.

## Assumptions
- Candidate starts are DIALOGUE/ACTION block starts only, so something happens on screen within 1 s.
- "Overlapping >50 %" in NMS = intersection / duration of the shorter window.
- "No cut inside a dialogue line" uses a 0.01 s tolerance; cuts may fall inside CAMERA/ACTION/SFX blocks.
- Rare labels (VFX, TRANSITION, TEXT, SUPER, INSERT) count as CAMERA-like; MUSIC as SFX; anything else is
  dialogue (`NAME (Emotion, …) (O.S.)`). Blocks with no timestamp or end<start are skipped with a warning.
- `EPISODE NUMBER: Episode 1` and `EPISODE NUMBER: 1` both parse; otherwise the number comes from the file name.
- Spoiler risk only applies to the last 40 % of the series and uses a generic identity-reveal word list; the
  series' own late-arc vocabulary isn't learned.
- The diversity rule (≤2 per episode in the top 20) needs ≥10 episodes to be fully satisfiable.
- Cold-open hook segments come from earlier in the same episode; no cross-episode combinations.
- LLM scores 1–5 map linearly to 0–1; density and spoiler risk always come from rules.
- Editor pack: episode videos share the script file's name; timecodes default to 30 fps (`--fps`).
- Development and unit tests use a synthetic pack (`tests/make_fixture.py`) that reproduces the audited
  format and quirks; the real pack was run locally and only its outputs are committed.

## Layout
```
app.py  run_pipeline.py  evaluate.py  requirements.txt  APPROACH.md
promofinder/  parser.py candidates.py features.py scoring.py validate.py pipeline.py
              editor.py export.py llm.py prompts.py models.py
eval/labels.csv            review decisions, rounds 1-2
tests/                     24 tests + synthetic pack generator
sample_data/synthetic_sample.zip
outputs/                   real-pack run (rules) + synthetic_sample/ full run
```
