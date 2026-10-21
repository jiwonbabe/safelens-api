"""For every video: ask topics.txt and lens.txt, judge, write one row to cache/lens.sqlite."""
import argparse
import collections
import datetime
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # so `python pipeline/run_lens.py` works

from pipeline.build_pool import load_videos
from pipeline.cache import all_rows, get, open_db, put
from pipeline.judge import DEMO_RULES, DISCLOSURE, LABELS, MONETIZED, head_of, judge
from pipeline.llm import ask, load_prompt

VOICE_PATH = "data/voice.json"  # written by pipeline/voice.py: {video_id: excited|pressured|calm}

ROW_KEYS = ["video_id", "title", "channel", "thumbnail", "views", "upload_date", "age_limit", "topics", "match",
            "commercial_hook", "kid_risk", "tactics", "verdict_teen", "verdict_kid", "concern", "reality_check",
            "quiz_options", "signals", "llm_error", "proposal"]

# Used only when the LLM gave no reason for a label it proposed and the judge kept.
LABEL_FALLBACK = {
    "fake_urgency": "A deadline that is not real, so you click before you think.",
    "hidden_ad": "The creator earns when you buy through this, and the video never says so.",
    "body_image_pressure": "A number and a deadline that turn your body into a problem to fix fast.",
    "engagement_bait": "Asks for likes, comments, or subscribes with pressure, so the video spreads.",
    "misleading_thumbnail": "The title promises something the video does not deliver.",
    "fake_social_proof": "Popularity with no source, so you trust it because 'everyone' does.",
}


# Used only when the judge found a concern by keyword and the LLM wrote no concern_reason.
CONCERN_FALLBACK = {
    "gambling_like": "Opening cases or betting skins is gambling with real money, and the video is paid to make it look like a game. Notice how losses are cut out.",
    "violence_glorification": "Real people get hurt in these clips, and the channel earns from every view. Notice how the edit skips what happens after someone falls.",
    "substance_glorification": "Vaping, drinking, or drugs are shown as fun with the harm left out. Notice who is selling the product behind the clip.",
    "weapons_with_links": "This is a weapon shown as a toy, with a link to buy one. Notice that the video never shows what it does to a person.",
    "private_contact_recruiting": "A link that moves you to Telegram or DMs takes you where nobody can see what happens next. Notice what they ask for once you are there.",
    "manosphere": "This clip sells one man's rules about how people should treat each other, cut for outrage. Notice what it wants you to feel about the other side.",
    "reckless_driving": "Street takeovers and stunts are filmed to look free, with the crashes and arrests left out. Notice who is holding the camera.",
    "adult": "This video is made for adults. Notice that the age gate is there because the content is not built for you.",
    "body_image_pressure": "A number and a deadline turn your body into a problem to fix fast. Notice that the video never shows what happens after the deadline.",
    "undisclosed_health_product": "A health product is being sold here and the video never says it earns from your purchase. Notice who profits if you buy.",
    "fake_urgency": "The deadline is the hook and the voice is pushing it. Notice whether anything actually changes when the clock runs out.",
}


def days_ago(upload_date):
    if not upload_date or len(upload_date) != 8:
        return None
    then = datetime.date(int(upload_date[:4]), int(upload_date[4:6]), int(upload_date[6:]))
    return (datetime.date.today() - then).days


def load_voice():
    return json.load(open(VOICE_PATH)) if os.path.exists(VOICE_PATH) else {}


def facts(video, voice=None):
    head = head_of(video)
    return {
        "voice_emotion": voice or "unknown",
        "upload_days_ago": days_ago(video.get("upload_date")),
        "has_money_link": "yes" if re.search(MONETIZED, head) else "no",
        "has_disclosure": "yes" if re.search(DISCLOSURE, head) else "no",
    }


def quiz_options(video_id, labels):
    options = list(dict.fromkeys(labels))[:4]
    rng = random.Random(video_id)
    options += rng.sample([l for l in LABELS if l not in options], 4 - len(options))
    rng.shuffle(options)
    return options


def build_row(video, proposal, error, voice=None):
    verdict = judge(video, proposal, voice)
    for t in verdict["tactics"]:
        t["reason"] = t["reason"] or LABEL_FALLBACK[t["label"]]
    if verdict["concern"] and not verdict["concern"]["reason"]:
        verdict["concern"]["reason"] = CONCERN_FALLBACK.get(verdict["concern"]["category"], "")
    lens = proposal.get("lens") or {}
    return {
        "video_id": video["id"], "title": video["title"], "channel": video["channel"], "thumbnail": video["thumbnail"],
        "views": video.get("view_count") or 0, "upload_date": video.get("upload_date") or "",
        "age_limit": video.get("age_limit") or 0,
        "topics": verdict["topics"], "match": verdict["match"], "commercial_hook": verdict["commercial_hook"],
        "kid_risk": verdict["kid_risk"], "tactics": verdict["tactics"],
        "verdict_teen": verdict["verdict_teen"], "verdict_kid": verdict["verdict_kid"], "concern": verdict["concern"],
        "reality_check": lens.get("reality_check") or "",
        "quiz_options": quiz_options(video["id"], [t["label"] for t in verdict["tactics"]]),
        "signals": {"age_limit": video.get("age_limit") or 0, "upload_days_ago": days_ago(video.get("upload_date")), "voice_emotion": voice},
        "llm_error": error,
        "proposal": proposal,  # raw LLM output, so eval can tell "LLM missed it" from "judge dropped it"
    }


def run_one(video):
    voice = VOICE.get(video["id"])
    proposal, errors = {"lens": {}, "topics": {}}, []
    fields = {**video, **facts(video, voice), "rules_text": DEMO_RULES}
    for name in ("topics", "lens"):
        try:
            proposal[name] = ask(load_prompt(name), fields)
        except Exception as e:  # no retries: record and judge on rules alone
            errors.append(f"{name}: {type(e).__name__}: {e}"[:300])
    return build_row(video, proposal, "; ".join(errors) or None, voice)


def rejudge(video, cached):
    """Re-run the judge on the stored LLM proposal. No LLM call: rule changes are free to apply."""
    return build_row(video, cached.get("proposal") or {"lens": {}, "topics": {}}, cached.get("llm_error"), VOICE.get(video["id"]))


def needs_run(cached, force):
    return force or cached is None or cached.get("llm_error") is not None


VOICE = {}


def main():
    VOICE.update(load_voice())
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated video ids")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rejudge", action="store_true", help="re-run judge on cached proposals, no LLM")
    args = parser.parse_args()
    db = open_db()
    videos = load_videos()
    if args.only:
        wanted = set(args.only.split(","))
        videos = [v for v in videos if v["id"] in wanted]
    if args.rejudge:
        todo, rows = [], [rejudge(v, get(db, v["id"])) for v in videos if get(db, v["id"])]
    else:
        todo = [v for v in videos if needs_run(get(db, v["id"]), args.force)]
        print(f"{len(todo)} to run, {len(videos) - len(todo)} cached")
    with ThreadPoolExecutor(max_workers=6) as pool:
        for row in (rows if args.rejudge else pool.map(run_one, todo)):
            put(db, row["video_id"], row)
            labels = [t["label"] for t in row["tactics"]]
            err = f" (error: {row['llm_error'][:60]})" if row["llm_error"] else ""
            print(f"{row['video_id']} {row['verdict_teen']:5} {row['verdict_kid']:7} {labels}{err}")
    counts = collections.Counter((r["verdict_teen"], r["verdict_kid"]) for r in all_rows(db))
    print("cache:", len(all_rows(db)), "rows;", dict(counts))


if __name__ == "__main__":
    main()
