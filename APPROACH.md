# PromoFinder: approach note

## The problem, as I understood it
A microdrama series has 50+ episodes. Every promo slot (Reels, Shorts, in-app trailers, paid ads) needs a
20–60 s clip that **stops the scroll in 3 seconds and ends on a question the viewer must answer by watching**.
Today someone has to watch or read the series to find those moments, then hand timings to an editor. That's
slow, it doesn't scale across series and languages, and the picks depend on who's doing it.

Who the output is for:
- the **promo / growth person** who decides what to post (needs a ranked shortlist with reasons), and
- the **video editor** who cuts it (needs exact in/out points, not prose).

## What I built
A pipeline + Streamlit app that reads the screenplay ZIP and returns ranked clips, each with timings, the hook
line, the ending line and the reason it was picked. A reviewer can approve or reject each clip with a reason,
and the app exports an **editor pack** (clip sheet with timecodes, one-page briefs, an EDL for
Premiere/Resolve, and ffmpeg cut scripts).

## Key decisions and tradeoffs
1. **Code owns every timestamp; the LLM never writes one.** Timestamps are the one thing that must be exactly
   right, and they're already in the script. The LLM (optional) can only re-score candidates and point at
   block numbers; code converts those to times and re-runs every check. A hallucinated line or an invalid
   range gets flagged or discarded, never shipped.
2. **Rules first, LLM second.** Rules are free, instant (≈18 s for 50 episodes), deterministic and
   explainable ("ends on a question; threat: *never*"). I wanted to see how far they go before paying for an
   LLM call per episode, and to have a baseline the LLM must beat.
3. **Validate everything, fix nothing silently.** Every promo is checked (length, bounds, no cut mid-line, a
   line in the first 3 s, quoted text actually inside the clip). Failures are flagged, not patched, so a
   reviewer can trust what passes.
4. **Measure with a human-in-the-loop review, not vibes.** Approve/reject with a reason tag in the app → a
   label file → `evaluate.py`. Matching is strict (both cut points within 1.5 s), because a different ending is
   a different promo.
5. **Don't send confidential scripts to a free model.** Free-tier Gemini inputs may be used to improve
   Google's products. I ran the LLM judge only on synthetic data; the real comparison needs a no-training key.
6. **Spoilers are a business problem, not just a quality score.** Promos recruit new viewers who start at
   episode 1. A late reveal ("You're the Duke?") is the most dramatic line in the series *and* the worst
   promo, so spoiler risk is weighted by how late the episode is.

## How I iterated
- **v1** (blueprint rules) → reviewed the top 20 → **11/20 approved**. The 9 rejects fell into four patterns:
  spoilers (2), fake cliffhangers that end on a calm or tender beat with a music swell (3), openers that only
  make sense mid-conversation (3), and a clip starting just after the slap that motivates it (1).
- **v2**: one rule per pattern, plus a word-boundary bug fix ("fire" was matching "firewood"). All 9 rejects
  left the top 20; the 12 new entrants were reviewed blind → **16/20 approved**. Validator pass stayed 100 %,
  and all 4 key logline moments are still covered.
- **LLM judge on synthetic data (Gemini 3.8 Flash):** it worked end to end, was much stricter than the
  rules on hooks and context, and the validator caught 3 promos where Gemini proposed a better range but
  quoted lines from the old one. That was a prompt ambiguity, now fixed. This is why code checks every LLM
  output instead of trusting it.
- I **froze the rules** there. The 4 remaining failures ("Burn it." with no context, a loud lament read as
  tension, exposition with a spoiler the word list misses) are about meaning. More rules would just fit my
  own labels; this is where an LLM judge earns its cost.

## What I'd do next (first 2–4 weeks with the team)
1. **Sit with the promo team for a week.** Questions I'd ask: Which platforms and lengths? Do they cut from
   scripts or from video? Who approves? What made last month's best promo work? Which metric matters:
   3-second hold, completion, installs? The weights should follow their answers, not my guesses.
2. **Pilot on one live series:** the tool proposes 10, an editor cuts the approved ones, we A/B them against
   hand-picked promos on hold rate and CTR. Every approve/reject feeds `eval/labels.csv`.
3. **LLM judge with a no-training key**, compared against rules on the same labels. Keep it only where it
   beats rules by enough to pay for itself (well under ₹1 per episode on a Flash-class model).
4. **Beyond scripts:** many series won't have timed scripts. Speech-to-text + shot detection can produce the
   same block format from video, and the rest of the pipeline stays unchanged.
5. **Reuse across teams:** the same "find the 30 s that hooks" engine works for audio stories (Kuku FM) and
   for trailer selection in new markets; only the source format changes.

## Honest limits
- Two review rounds of 20; the reviewer also designed the rules. A blind review by the promo team is the real
  test.
- The rules are tuned on one series (period romance). Another genre will need its own word lists and a fresh
  round of labels.
- Script timings are assumed to match the final video; the editor pack inherits any drift.
