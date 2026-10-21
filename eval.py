"""Accuracy of cache/lens.sqlite against tests/gold.json. Never edits either. Exit code 0 always."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline.build_pool import collapse, load_videos, video_text  # noqa: E402
from pipeline.cache import all_rows, open_db  # noqa: E402
from pipeline.judge import QUOTE_MARKS  # noqa: E402

CELLS = ["teen show", "teen flag", "teen block", "kid show", "kid approve", "kid hide", "control"]
STRICTNESS = {"show": 0, "approve": 1, "flag": 1, "hide": 2, "block": 2}


def kept_labels(row):
    return [t["label"] for t in row["tactics"]]


def score(gold, row):
    """-> (cell, correct). Teen: verdict and, when gold names labels, the exact label set. Kid: verdict. Control: show with no labels."""
    if gold["age_band"] == "teen":
        ok = row["verdict_teen"] == gold["verdict"] and (not gold["labels"] or set(gold["labels"]) == set(kept_labels(row)))
        return f"teen {gold['verdict']}", ok
    if gold["age_band"] == "kid":
        return f"kid {gold['verdict']}", row["verdict_kid"] == gold["verdict"]
    return "control", row["verdict_teen"] == "show" and not row["tactics"]


def classify(gold, row, text):
    """One cause per wrong label or verdict: quote-not-found, rule-too-strict, rule-too-loose, LLM-missed-it."""
    kept = kept_labels(row)
    proposed = {t.get("label"): t.get("evidence") for t in (row["proposal"].get("lens") or {}).get("tactics") or [] if isinstance(t, dict)}
    causes = []
    for label in gold["labels"]:
        if label in kept:
            continue
        if label not in proposed:
            causes.append(f"{label}: LLM-missed-it")
        elif collapse(str(proposed[label] or "")).strip(QUOTE_MARKS).lower() in text:
            causes.append(f"{label}: rule-too-strict")
        else:
            causes.append(f"{label}: quote-not-found")
    for label in kept:
        if gold["labels"] and label not in gold["labels"]:
            causes.append(f"{label}: rule-too-loose")
        if gold["age_band"] == "both":
            causes.append(f"{label}: rule-too-loose")
    pred = row["verdict_teen"] if gold["age_band"] != "kid" else row["verdict_kid"]
    if pred != gold["verdict"]:
        causes.append("verdict: rule-too-strict" if STRICTNESS[pred] > STRICTNESS[gold["verdict"]] else "verdict: rule-too-loose")
    return causes


def main():
    gold = json.load(open("tests/gold.json"))
    rows = {r["video_id"]: r for r in all_rows(open_db())}
    videos = {v["id"]: v for v in load_videos()}
    cells = {c: [0, 0] for c in CELLS}
    misses = []
    for g in gold:
        row = rows.get(g["video_id"])
        if row is None:
            misses.append((g["video_id"], "(not in cache)", g, None, ["missing"]))
            cells.setdefault(f"{g['age_band']} {g['verdict']}" if g["age_band"] != "both" else "control", [0, 0])[0] += 1
            continue
        cell, ok = score(g, row)
        cells[cell][0] += 1
        cells[cell][1] += ok
        if not ok:
            misses.append((g["video_id"], row["title"][:50], g, row, classify(g, row, video_text(videos[g["video_id"]]))))
    print(f"{'cell':13} gold correct accuracy")
    for cell in CELLS:
        n, k = cells[cell]
        print(f"{cell:13} {n:4} {k:7} {('%3d%%' % (100 * k / n)) if n else '  --'}")
    total_n = sum(n for n, _ in cells.values())
    total_k = sum(k for _, k in cells.values())
    print(f"total {total_k}/{total_n} = {100 * total_k / total_n:.0f}%")
    print(f"\nmisses ({len(misses)}):")
    for vid, title, g, row, causes in misses:
        pred = f"{row['verdict_teen']}/{row['verdict_kid']} {kept_labels(row)}" if row else "-"
        evidence = [t["evidence"][:40] for t in row["tactics"]] if row else []
        print(f"  {vid} {title}\n     gold {g['verdict']} {g['labels']} | pred {pred} | evidence {evidence}\n     cause: {'; '.join(causes)}")


if __name__ == "__main__":
    main()
