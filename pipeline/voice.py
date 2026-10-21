"""Modulate voice emotion -> cache signals.voice_emotion. Helper signal only; never adds a label."""
import json
import os
import subprocess
import sys

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.build_pool import load_videos  # noqa: E402
from pipeline.cache import all_rows, get, open_db, put  # noqa: E402

load_dotenv()
EMOTION_URL = "https://platform.modulate.ai/api/velma-2-emotion-batch"
VOICE_PATH = "data/voice.json"  # read by run_lens so the judge and the lens prompt see the voice
EXCITED, PRESSURED = ("Happy", "Surprised"), ("Afraid", "Angry")


def map_emotion(label):
    """Modulate label -> excited | pressured | calm (CLAUDE.md). None stays None."""
    if label is None:
        return None
    if label in EXCITED:
        return "excited"
    if label in PRESSURED:
        return "pressured"
    return "calm"


def clip(audio_path, seconds=30):
    """First N seconds as a new mp3 next to the source. Modulate wants 5-30 s."""
    out = audio_path.replace(".mp3", f"_{seconds}s.mp3")
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", audio_path, "-t", str(seconds), "-c", "copy", out], check=True)
    return out


def emotion_of(audio_path):
    """One Modulate call on a 30 s clip. Returns the raw label, e.g. "Happy". Raises on failure."""
    with open(clip(audio_path), "rb") as f:
        r = requests.post(EMOTION_URL, headers={"X-API-Key": os.environ["MODULATE_API_KEY"]}, files={"upload_file": f}, timeout=120)
    r.raise_for_status()
    return r.json().get("emotion")


def update_cache(db, videos):
    """For every video with audio: call Modulate, write signals.voice_emotion. Failure leaves null. Returns {id: emotion}."""
    done = {}
    for v in videos:
        if not v.get("audio_file"):
            continue
        row = get(db, v["id"])
        if row is None:
            continue
        try:
            done[v["id"]] = map_emotion(emotion_of(v["audio_file"]))
        except Exception as e:  # ponytail: no retries; the cut line for Modulate is 1:30 PM
            print(f"{v['id']} modulate failed: {e}")
            done[v["id"]] = None
        row["signals"]["voice_emotion"] = done[v["id"]]
        put(db, v["id"], row)
    saved = json.load(open(VOICE_PATH)) if os.path.exists(VOICE_PATH) else {}
    saved.update({k: v for k, v in done.items() if v})
    json.dump(saved, open(VOICE_PATH, "w"), indent=1)
    return done


if __name__ == "__main__":
    db = open_db()
    result = update_cache(db, load_videos())
    for vid, emo in result.items():
        print(vid, emo)
    print("voice_emotion set on", sum(1 for r in all_rows(db) if r["signals"].get("voice_emotion")), "rows")
