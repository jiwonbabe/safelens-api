"""Adversarial loop: a red-team LLM writes baits, the detector (lens prompt + judge) tries to catch them.
Misses feed the next round so the baits get harder. Writes data/loop_log.json. Changes nothing else."""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.judge import LABELS, judge  # noqa: E402
from pipeline.llm import ask, load_prompt  # noqa: E402
from pipeline.run_lens import facts  # noqa: E402

LOG = "data/loop_log.json"


def bait_to_video(bait, round_no, i):
    return {"id": f"bait-r{round_no}-{i}", "title": bait.get("title") or "", "description": bait.get("description") or "",
            "captions": bait.get("captions") or "", "channel": "red team", "age_limit": 0, "view_count": 0,
            "upload_date": datetime.date.today().strftime("%Y%m%d"), "thumbnail": ""}


def score(bait, kept):
    intended = [l for l in bait.get("intended_labels") or [] if l in LABELS]
    return {"caught": [l for l in intended if l in kept], "missed": [l for l in intended if l not in kept],
            "extra": [l for l in kept if l not in intended]}


def format_missed(missed_baits):
    if not missed_baits:
        return ""
    lines = ["Last round the detector MISSED these. Write new baits in the same spirit, harder:"]
    lines += [f'- "{b["title"]}" (missed: {", ".join(b["missed"])})' for b in missed_baits]
    return "\n".join(lines)


def detect(video):
    """Same path as the real pipeline: lens prompt -> judge. Returns kept labels."""
    proposal = ask(load_prompt("lens"), {**video, **facts(video)})
    return [t["label"] for t in judge(video, {"lens": proposal, "topics": {}})["tactics"]]


def run_round(round_no, missed_baits):
    baits = ask(load_prompt("bait_writer"), {"missed_examples": format_missed(missed_baits)}).get("baits") or []
    entry = {"round": round_no, "baits": [], "intended_total": 0, "caught_total": 0}
    for i, bait in enumerate(baits):
        video = bait_to_video(bait, round_no, i)
        try:
            kept, error = detect(video), None
        except Exception as e:  # no retries; a failed detect counts as a miss
            kept, error = [], f"{type(e).__name__}: {e}"[:200]
        s = score(bait, kept)
        entry["baits"].append({"title": video["title"], "description": video["description"], "captions": video["captions"], "intended": [l for l in bait.get("intended_labels") or [] if l in LABELS],
                               "kept": kept, "caught": s["caught"], "missed": s["missed"], "extra": s["extra"], "error": error})
        entry["intended_total"] += len(s["caught"]) + len(s["missed"])
        entry["caught_total"] += len(s["caught"])
    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    log, missed = [], []
    for r in range(1, args.rounds + 1):
        entry = run_round(r, missed)
        log.append(entry)
        missed = [b for b in entry["baits"] if b["missed"]]
        rate = entry["caught_total"] / entry["intended_total"] if entry["intended_total"] else 0
        print(f"round {r}: {len(entry['baits'])} baits, caught {entry['caught_total']}/{entry['intended_total']} = {rate:.0%}, missed baits {len(missed)}")
        for b in entry["baits"]:
            flag = "MISS" if b["missed"] else "ok  "
            print(f"  {flag} {b['title'][:60]!r} intended={b['intended']} kept={b['kept']}{' error=' + b['error'] if b['error'] else ''}")
    json.dump(log, open(LOG, "w"), indent=1, ensure_ascii=False)
    print(f"wrote {LOG}")


if __name__ == "__main__":
    main()
