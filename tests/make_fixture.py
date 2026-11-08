"""Generate a SYNTHETIC screenplay ZIP that mimics the audited format of the real pack.

All story content is invented. Used for tests and as the public demo dataset
(the real Kuku pack must never be committed).

Quirks reproduced from the audit: ep 6 uses UPPERCASE scene headers, one block
out of order, a small dialogue overlap, a SOUND FX line that literally says
"cliffhanger", character aliases, CAMERA coverage gaps.

    python tests/make_fixture.py sample_data/synthetic_sample.zip
"""
import io, sys, zipfile, random


def ts(t):
    m = int(t // 60)
    return f"{m:02d}:{t - 60 * m:05.2f}"


LINES = [
    ("CAMERA", None, "Wide shot of the great hall, candles flickering."),
    ("MIRA", "Outraged, Trembling", '"How dare you stand at this altar after what you did?"'),
    ("ACTION", None, "Mira slaps Edric across the face. The guests gasp."),
    ("EDRIC", "Cold", '"You signed the contract yourself, Mira."'),
    ("CAMERA", None, "Close-up on the torn contract in Edric's hand."),
    ("LADY MIRA", "Defiant", '"Then I will burn it, and your name with it!"'),
    ("SOUND FX", None, "A low drone swells."),
    ("THE OLD STEWARD", "Fearful", '"My lady, the duke\'s guards are at the gate."'),
    ("EDRIC", "Smirking", '"Kneel, and I may let your brother live."'),
    ("CAMERA", None, "Slow push-in on Mira's face."),
    ("MIRA", "Screaming", '"Never! Not while I still breathe!"'),
    ("ACTION", None, "Guards drag a chained prisoner into the hall."),
    ("CORIN", "Weak, Desperate", '"Sister... he knows the truth about our father."'),
    ("MIRA", "Shocked", '"What truth? Edric, what did you do to him?"'),
    ("EDRIC", "Menacing", '"Tomorrow at dawn, the whole kingdom will know who you really are."'),
    ("SOUND FX", None, "Thunder cracks. Cut to black."),
]
CALM = [
    ("MIRA", "Relieved", '"Thank you. We are safe now."'),
    ("CORIN", "Warm", '"It\'s over, sister. Rest."'),
    ("CAMERA", None, "Wide shot of the quiet courtyard at sunset."),
]


def episode(num, rng, upper=False, quirks=False):
    lines = [
        f"EPISODE NUMBER: {num}",
        f"EPISODE LOGLINE: Mira confronts Edric at the altar of Ashvale (synthetic ep {num}).",
        "CONTINUITY NOTES: Synthetic test data. Mira wears the silver veil.",
        "",
        "--- SCRIPT START ---",
        "",
    ]
    t = 0.0
    seq = (CALM if num % 3 == 0 else []) + LINES[: rng.randint(10, len(LINES))] + LINES[1: rng.randint(8, len(LINES))]
    if num % 2 == 0:
        seq = seq + CALM[:2]
    # build blocks with times
    blocks = []
    for lab, emo, text in seq:
        dur = round(rng.uniform(2.0, 5.0), 2)
        gap = 0.15 if (lab == "CAMERA" and rng.random() < 0.3) else 0.0
        blocks.append([lab, emo, text, round(t + gap, 2), round(t + gap + dur, 2)])
        t = round(t + gap + dur, 2)
    total = t
    mid = round(blocks[len(blocks) // 2][3], 2)
    scenes = [(1, 0.0, mid), (2, mid, total)]
    if quirks:
        # small dialogue overlap (0.3 s) on block 3
        blocks[3][3] = round(blocks[3][3] - 0.3, 2)
        blocks.append(["SOUND FX", None, "Ominous sting - a classic cliffhanger beat.", round(total - 2.0, 2), total])
    for sn, ss, se in scenes:
        lines += [
            ("SCENE" if upper else "SCENE") + f" {sn:02d}",
            ("SCENE HEADING: INT. GREAT HALL - NIGHT" if upper else "Scene heading: INT. GREAT HALL - NIGHT"),
            ("SCENE START: " if upper else "Scene start: ") + ts(ss),
            ("SCENE END: " if upper else "Scene end: ") + ts(se),
            ("ACTIONS AND DIALOGUE:" if upper else "Actions and dialogue:"),
            "",
        ]
        sb = [b for b in blocks if ss - 0.31 <= b[3] < se]
        if quirks and sn == 1 and len(sb) > 4:
            sb[2], sb[3] = sb[3], sb[2]  # out-of-order block in file
        for lab, emo, text, s, e in sb:
            label = lab if emo is None else f"{lab} ({emo})"
            lines += [f"**{label}:**", f"Start: ({ts(s)}) | End: ({ts(e)})", text, ""]
    lines.append("--- SCRIPT END ---")
    return "\n".join(lines) + "\n"


def build(path, n=8, seed=7):
    rng = random.Random(seed)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i in range(1, n + 1):
            z.writestr(f"synthetic_pack/episode-{i:03d}-Episode {1000 + i}.txt",
                       episode(i, rng, upper=(i == 6), quirks=(i == 2)))
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "sample_data/synthetic_sample.zip"))
