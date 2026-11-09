"""JSON + CSV export."""
from __future__ import annotations

import csv
import io
import json
import os

from .models import Promo
from .validate import passes

CSV_FIELDS = ["rank", "id", "kind", "episode", "segments", "duration", "total", "hook", "cliffhanger",
              "standalone", "density", "spoiler_risk", "heur_hook", "heur_cliffhanger", "heur_standalone", "validator_pass",
              "flags", "post_first", "hook_text", "cliffhanger_text", "why", "status"]
REVIEW_FIELDS = ["timestamp", "promo_id", "episode", "segments", "decision", "reason", "note"]


def promo_row(p: Promo) -> dict:
    return {
        "rank": p.rank, "id": p.id, "kind": p.kind, "episode": p.ep,
        "segments": "; ".join(s.label() for s in p.segments), "duration": p.duration, "total": p.total,
        "hook": p.scores["hook"], "cliffhanger": p.scores["cliffhanger"], "standalone": p.scores["standalone"],
        "density": p.scores["density"], "spoiler_risk": p.scores.get("spoiler_risk", 0.0), "heur_hook": p.heuristic.get("hook"),
        "heur_cliffhanger": p.heuristic.get("cliffhanger"), "heur_standalone": p.heuristic.get("standalone"),
        "validator_pass": passes(p.flags), "flags": "; ".join(p.flags), "post_first": p.post_first,
        "hook_text": p.hook_text, "cliffhanger_text": p.cliffhanger_text, "why": p.why, "status": p.status,
    }


def to_csv(promos: list[Promo]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    w.writeheader()
    for p in promos:
        w.writerow(promo_row(p))
    return buf.getvalue()


def to_json(promos: list[Promo], cold: list[Promo], meta: dict) -> str:
    return json.dumps({"meta": meta, "promos": [p.to_dict() for p in promos],
                       "cold_open_promos": [p.to_dict() for p in cold]}, indent=2, ensure_ascii=False)


def review_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=REVIEW_FIELDS)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in REVIEW_FIELDS})
    return buf.getvalue()


def write_all(out_dir: str, promos, cold, meta) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    files = {
        "promos.json": to_json(promos, cold, meta),
        "promos.csv": to_csv(promos),
        "cold_open_promos.csv": to_csv(cold),
        "run_meta.json": json.dumps(meta, indent=2, ensure_ascii=False, default=str),
    }
    paths = []
    for n, txt in files.items():
        p = os.path.join(out_dir, n)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(txt)
        paths.append(p)
    return paths
