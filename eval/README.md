# Evaluation: how I know the promos are good

| File | What it is |
|---|---|
| `review_v2_top20.csv` | **Start here.** The final top 20 with my decision and reason for each: **16 approved, 4 rejected (80 %)**. |
| `labels.csv` | Every review decision from both rounds (32 clips): episode, start, end, approved/rejected, reason, round. Used by `evaluate.py`. |
| `key_moments.csv` | The key story moment of 15 episodes, picked from the logline **before** looking at the tool's picks. Used to measure recall. |
| `feedback_report.md` | Output of `feedback.py`: which rejection reasons are most common and whether each score already separates good clips from bad ones (the hook score is the weak one). |

Reproduce the numbers (needs the screenplay ZIP locally):
```
python evaluate.py outputs/promos.csv --recall    # precision on the top 20 + recall on the 15 key moments
python feedback.py data/input.zip                 # what reviewers rejected, and what to fix next
```
The first version's review is in `outputs/review_log.csv` (11 / 20 approved).
