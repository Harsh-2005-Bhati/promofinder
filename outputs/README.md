# Raw outputs (unedited)

Everything here was produced by running the tool. Nothing was edited by hand.

## Real pack: Kuku's 50 episodes (final version, v2)
| File | What it is |
|---|---|
| `promos.csv` | **Start here.** All 201 promos, ranked best first: episode, start/end time, hook line, cliffhanger line, one-line *why*, scores, check result. Opens in Excel. |
| `promos.json` | The same promos with every detail (all rule reasons, segment times in seconds). |
| `cold_open_promos.csv` | 41 two-part promos: a ≤6 s teaser line + a main clip from the same episode. |
| `run_meta.json` | Run summary: 50 episodes, 3,727 script lines, 16,167 candidate clips, 201 kept, **100 % passed every check**, all warnings. |
| `review_log.csv` | My approve/reject clicks on the **first version (v1)** top 20 in the app: 11 approved, 9 rejected. (E044-P1 was clicked twice.) |

How to read the `segments` column: `1:00:46.80-01:10.60` = episode 1, from 00:46.80 to 01:10.60.

## Other runs
| Folder | What it is |
|---|---|
| `synthetic_sample/` | A full run on the invented demo pack (safe to publish), including the **editor pack**: clip sheet with timecodes, one-page briefs, an EDL for Premiere/Resolve and ffmpeg cut scripts. The editor pack for the real pack is not published because the briefs quote long script passages. |
| `llm_gemini_synthetic/` | The optional AI judge (Gemini 3.8 Flash) run on the demo pack. Kuku's scripts were never sent to a free-tier AI. |

No screenplay files are stored anywhere in this repository.
