"""Score a ranking against human review labels.

    python evaluate.py outputs/promos.csv [--labels eval/labels.csv] [--top 20] [--compare other/promos.csv]

A promo matches a label when it is the same episode and both cut points are within 1.5 s.
Reports approved / rejected / unlabelled in the top N. Unlabelled promos must be reviewed before a
precision number is claimed (no guessing).
"""
import argparse
import csv


def ts(x):
    m, s = x.split(":")
    return int(m) * 60 + float(s)


def load_promos(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        segs = []
        for part in r["segments"].split(";"):
            ep, rng = part.strip().split(":", 1)
            a, b = rng.split("-")
            segs.append((int(ep), ts(a), ts(b)))
        out.append(dict(r, _segs=segs))
    return out


def iou(a, b):
    if a[0] != b[0]:
        return 0.0
    inter = max(0.0, min(a[2], b[2]) - max(a[1], b[1]))
    union = max(a[2], b[2]) - min(a[1], b[1])
    return inter / union if union > 0 else 0.0


def load_labels(path):
    return [dict(r, _seg=(int(r["episode"]), float(r["start"]), float(r["end"])))
            for r in csv.DictReader(open(path, encoding="utf-8"))]


def match(promo, labels, tol=1.5):
    """Strict: same episode and both cut points within 1.5 s. A clip with a different ending is a different promo
    (the ending decides the cliffhanger), so it must be reviewed again rather than inherit a label."""
    a = promo["_segs"][-1]
    for l in labels:
        b = l["_seg"]
        if a[0] == b[0] and abs(a[1] - b[1]) <= tol and abs(a[2] - b[2]) <= tol:
            return l
    return None


def report(path, labels, top):
    P = load_promos(path)[:top]
    rows, c = [], {"approved": 0, "rejected": 0, "unlabelled": 0}
    for p in P:
        l = match(p, labels)
        d = l["decision"] if l else "unlabelled"
        c[d] += 1
        rows.append((p["rank"], p["id"], p["segments"], d, (l or {}).get("reason", "")))
    return P, rows, c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("promos")
    ap.add_argument("--labels", default="eval/labels.csv")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--compare", default=None, help="another promos.csv to compute overlap@N against")
    ap.add_argument("--recall", action="store_true", help="also report recall@1/3/5 on eval/key_moments.csv")
    a = ap.parse_args()
    labels = load_labels(a.labels)
    P, rows, c = report(a.promos, labels, a.top)
    for r in rows:
        print(f"{r[0]:>3} {r[1]:<9} {r[2]:<28} {r[3]:<10} {r[4]}")
    lab = c["approved"] + c["rejected"]
    print(f"\ntop {a.top}: approved {c['approved']}, rejected {c['rejected']}, unlabelled {c['unlabelled']}"
          + (f"  -> precision on labelled {c['approved']}/{lab} = {c['approved']/lab:.0%}" if lab else ""))
    if c["unlabelled"]:
        print("review the unlabelled promos and add them to the labels file before quoting precision")
    if a.compare:
        Q = load_promos(a.compare)[:a.top]
        hit = sum(1 for p in P if any(iou(p["_segs"][-1], q["_segs"][-1]) >= 0.5 for q in Q))
        print(f"overlap@{a.top} with {a.compare}: {hit}/{a.top}")
    if a.recall:
        for k in (1, 3, 5):
            rows = recall_at_k(a.promos, k=k)
            print(f"recall@{k} (key moment covered by one of the episode's top {k}): "
                  f"{sum(1 for r in rows if r[2])}/{len(rows)}")
        for ep, moment, pid, rank in recall_at_k(a.promos, k=3):
            print(f"  ep {ep:<3} {'HIT ' + pid + ' (#' + rank + ')' if pid else 'MISS':<18} {moment[:70]}")



def recall_at_k(promos_csv, moments_csv="eval/key_moments.csv", k=3, min_cover=0.5):
    """Share of key moments where one of the episode's top-k promos covers >= min_cover of the moment."""
    P = load_promos(promos_csv)
    rows = []
    for m in csv.DictReader(open(moments_csv, encoding="utf-8")):
        ep, a, b = int(m["episode"]), float(m["start"]), float(m["end"])
        top = [p for p in P if p["_segs"][-1][0] == ep][:k]  # ranked order = per-episode order
        hit = None
        for p in top:
            for (e, s, t) in p["_segs"]:
                if e == ep and (min(b, t) - max(a, s)) >= min_cover * (b - a):
                    hit = p
        rows.append((ep, m["moment"], hit["id"] if hit else "", hit["rank"] if hit else ""))
    return rows


if __name__ == "__main__":
    main()
