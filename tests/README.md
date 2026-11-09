# Tests (27, no network needed)

Run with `python -m pytest -q`.

| File | What it checks |
|---|---|
| `test_parser.py` | Reading scripts, including uppercase headers and broken files. |
| `test_pipeline.py` | Clips never cut mid-dialogue; the validator catches bad promos; ranking and the per-episode limit. |
| `test_features.py` | The rules added after review: spoilers, calm endings, mid-conversation openers, a slap just before the cut. |
| `test_llm.py` | The AI judge with fake models: hallucinated text is flagged, invalid ranges are discarded, bad JSON → retry → fallback, cache, model swap, custom API URL. |
| `test_editor.py` | The editor pack: timecodes, EDL, cut scripts. |
| `test_robustness.py` | 10 kinds of messy input (uppercase, missing headers, renamed characters, `HH:MM:SS`, truncated, garbage): warnings, never a crash. |
| `make_fixture.py` | Builds the synthetic demo pack used by the tests and the public app. |
