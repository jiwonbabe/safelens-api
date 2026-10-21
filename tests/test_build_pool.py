import json
import os

from pipeline.build_pool import clean_vtt, video_text, KEYS, OUT


def test_clean_vtt_strips_header_timestamps_tags_and_repeats():
    raw = "WEBVTT\nKind: captions\n\n00:00.000 --> 00:01.000\n<c>hi</c> there\nhi there\n\nnext"
    assert clean_vtt(raw) == "hi there next"


def test_video_text_is_lowercase_and_whitespace_collapsed():
    video = {"title": "The Great  Elephant\nToothpaste", "description": "Line one\n\nline two", "captions": ""}
    assert video_text(video) == "the great elephant toothpaste line one line two"


def test_videos_json_has_every_video_with_the_contract_keys():
    assert os.path.exists(OUT), "run python pipeline/build_pool.py first"
    videos = json.load(open(OUT))
    assert len(videos) == 56
    assert all(sorted(v) == sorted(KEYS) for v in videos)
    assert sum(1 for v in videos if v["captions"]) == 53
