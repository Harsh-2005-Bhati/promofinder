# The code, file by file

The pipeline runs top to bottom: **parse → cut candidates → score → (optional AI judge) → validate → rank → export**.

| File | What it does |
|---|---|
| `parser.py` | Reads the screenplay ZIP / folder / .txt files into episodes and timed lines. Handles messy input (uppercase, missing headers, `HH:MM:SS` times) with warnings, never crashes. |
| `candidates.py` | Cuts every possible 20–60 s clip, only at line boundaries (never mid-dialogue). |
| `features.py` | The rules: hook (first 3 s), cliffhanger (last line), standalone, density, spoiler risk. Each score keeps its reasons. |
| `scoring.py` | Combines the scores, removes near-duplicate clips, keeps the top 5 per episode, ranks globally (max 2 per episode in the top 20), writes the one-line *why*. |
| `llm.py` | The optional AI judge: Gemini, Anthropic, OpenAI, Groq or any OpenAI-compatible URL. Cache, retry, fallback to rules. |
| `prompts.py` | The prompt the AI judge sees. The AI may only return line numbers, never timestamps. |
| `validate.py` | Checks every promo: length, bounds, no cut mid-line, a line in the first 3 s, quoted text really inside the clip. |
| `pipeline.py` | Runs all the steps in order; also builds the two-part cold-open promos. |
| `editor.py` | The editor pack: clip sheet, briefs, EDL and ffmpeg cut scripts. |
| `export.py` | Writes `promos.csv`, `promos.json`, `run_meta.json`. |
| `models.py` | Data classes for a segment and a promo. |
