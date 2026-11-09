"""Turn reviewer decisions into concrete tuning advice (human-in-the-loop).

    python feedback.py data/input.zip [--labels eval/labels.csv] [--out eval/feedback_report.md]

For every labelled clip it recomputes the current rule scores, then reports
  1. rejection reasons and their share,
  2. per score component: mean on approved vs rejected clips (does the score already separate them?),
  3. for each rejection reason, whether the matching component now ranks those clips below the approved ones,
  4. a suggestion: the reason with the largest share whose component does NOT yet separate well.
"""
import argparse
import csv
from collections import Counter
from statistics import mean

from promofinder.candidates import make_segment
from promofinder.features import compute
from promofinder.parser import parse_any

REASON_TO_SCORE = {"weak hook": "hook", "weak cliffhanger": "cliffhanger", "missing context": "standalone",
                   "spoiler": "spoiler_risk"}
HIGHER_IS_BETTER = {"hook": True, "cliffhanger": True, "standalone": True, "spoiler_risk": False}
FIX_HINT = {"hook": "improve the hook rules (e.g. penalise openers that are quiet or need context); raising the "
                    "hook weight would not help while the score can't tell good hooks from bad",
            "cliffhanger": "improve the ending rules; raising the cliffhanger weight would not help yet",
            "standalone": "improve the context rules; raising the standalone weight would not help yet",
            "spoiler_risk": "extend the reveal word list / series-arc detection"}


def build(src, labels_path):
    eps, _ = parse_any(src)
    E = {e.num: e for e in eps}
    n = max(E)
    rows = []
    for l in csv.DictReader(open(labels_path, encoding="utf-8")):
        ep = E.get(int(l["episode"]))
        if not ep:
            continue
        seg = make_segment(ep, float(l["start"]), float(l["end"]))
        f = compute(ep, seg, n)
        rows.append(dict(l, **{k: f[k] for k in REASON_TO_SCORE.values()}))
    return rows


def report(rows) -> str:
    app = [r for r in rows if r["decision"] == "approved"]
    rej = [r for r in rows if r["decision"] == "rejected"]
    out = [f"# Reviewer feedback report", "", f"{len(rows)} labelled clips: {len(app)} approved, {len(rej)} rejected.", ""]
    reasons = Counter(r["reason"] for r in rej)
    out += ["## Why clips were rejected", "", "| reason | count | share |", "|---|---|---|"]
    out += [f"| {k} | {v} | {v / len(rej):.0%} |" for k, v in reasons.most_common()]
    out += ["", "## Do the current scores separate approved from rejected?", "",
            "| score | mean (approved) | mean (rejected for this reason) | separates? |", "|---|---|---|---|"]
    verdict = {}
    for reason, key in REASON_TO_SCORE.items():
        rr = [r[key] for r in rej if r["reason"] == reason]
        if not rr:
            continue
        a, b = mean(r[key] for r in app), mean(rr)
        good = (a - b) if HIGHER_IS_BETTER[key] else (b - a)
        verdict[reason] = good
        out.append(f"| {key} | {a:.2f} | {b:.2f} ({reason}) | {'yes' if good > 0.1 else 'weakly' if good > 0 else 'NO'} "
                   f"(gap {good:+.2f}) |")
    weakest = sorted(reasons, key=lambda k: (verdict.get(k, 1) > 0.1, -reasons[k]))
    top = weakest[0] if weakest else None
    out += ["", "## Suggestion", ""]
    if top and verdict.get(top, 1) <= 0.1:
        key = REASON_TO_SCORE[top]
        out.append(f"**{reasons[top] / len(rej):.0%} of rejections are '{top}', and the `{key}` score barely separates "
                   f"them from approved clips (gap {verdict[top]:+.2f}).** Next step: {FIX_HINT[key]}, then "
                   f"re-review the new top 20 before trusting the change.")
    else:
        out.append("Every rejection reason is already separated by its score (gap > 0.10). Remaining rejects are "
                   "judgement calls about meaning: route them to the LLM judge rather than adding more rules.")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--labels", default="eval/labels.csv")
    ap.add_argument("--out", default="eval/feedback_report.md")
    a = ap.parse_args()
    txt = report(build(a.src, a.labels))
    open(a.out, "w", encoding="utf-8").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
