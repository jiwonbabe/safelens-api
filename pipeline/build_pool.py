"""data/raw/*.info.json + *.en.vtt -> data/videos.json"""
import glob
import json
import os
import re

RAW = "data/raw"
AUDIO = "data/audio"
OUT = "data/videos.json"
KEYS = ["id", "url", "title", "channel", "channel_follower_count", "description", "thumbnail",
        "upload_date", "view_count", "age_limit", "captions", "audio_file"]


def clean_vtt(text):
    """Drop VTT header, timestamps, tags, blanks, and repeated lines. Join with spaces."""
    lines = []
    for line in text.splitlines():
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        if lines and lines[-1] == line:
            continue
        lines.append(line)
    return " ".join(lines)


def collapse(text):
    return re.sub(r"\s+", " ", text).strip()


def video_text(video):
    """Lowercased title + description + captions, whitespace collapsed. The judge searches this."""
    return collapse(f"{video.get('title') or ''}\n{video.get('description') or ''}\n{video.get('captions') or ''}").lower()


def load_videos(path=OUT):
    return json.load(open(path, encoding="utf-8"))


def read_video(info_path):
    d = json.load(open(info_path, encoding="utf-8"))
    vid = d["id"]
    vtt_path = f"{RAW}/{vid}.en.vtt"
    audio_path = f"{AUDIO}/{vid}.mp3"
    return {
        "id": vid,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "title": d.get("title") or "",
        "channel": d.get("channel") or d.get("uploader") or "",
        "channel_follower_count": d.get("channel_follower_count") or 0,
        "description": d.get("description") or "",
        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        "upload_date": d.get("upload_date") or "",
        "view_count": d.get("view_count") or 0,
        "age_limit": d.get("age_limit") or 0,
        "captions": clean_vtt(open(vtt_path, encoding="utf-8", errors="ignore").read()) if os.path.exists(vtt_path) else "",
        "audio_file": audio_path if os.path.exists(audio_path) else None,
    }


def main():
    videos = [read_video(p) for p in sorted(glob.glob(f"{RAW}/*.info.json"))]
    json.dump(videos, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"loaded {len(videos)} videos, {sum(1 for v in videos if v['captions'])} with captions")


def self_check():
    assert clean_vtt("WEBVTT\n\n00:00.000 --> 00:01.000\n<c>hi</c> there\nhi there\n\nnext") == "hi there next"
    assert "elephant toothpaste" in video_text({"title": "The Great Elephant Toothpaste", "description": "", "captions": ""})
    print("build_pool self-check ok")


if __name__ == "__main__":
    self_check()
    main()
