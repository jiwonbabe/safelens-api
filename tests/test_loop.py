import json

import pipeline.loop as loop


BAIT = {"title": "They are GIVING AWAY 50 PS5s tonight", "description": "grab yours before midnight: https://bit.ly/x",
        "captions": "only 2 hours left guys", "intended_labels": ["fake_urgency", "hidden_ad"]}


def test_bait_to_video_has_the_pool_shape():
    v = loop.bait_to_video(BAIT, 2, 3)
    assert v["id"] == "bait-r2-3" and v["title"] == BAIT["title"] and v["captions"] == BAIT["captions"]
    assert v["channel"] == "red team" and v["age_limit"] == 0 and v["view_count"] == 0 and len(v["upload_date"]) == 8


def test_score_splits_caught_and_missed():
    assert loop.score(BAIT, ["fake_urgency", "fake_social_proof"]) == {"caught": ["fake_urgency"], "missed": ["hidden_ad"], "extra": ["fake_social_proof"]}


def test_format_missed_feeds_the_next_round():
    text = loop.format_missed([{"title": "T1", "missed": ["hidden_ad"]}, {"title": "T2", "missed": ["engagement_bait"]}])
    assert "T1" in text and "hidden_ad" in text and "T2" in text
    assert loop.format_missed([]) == ""


def test_run_round_uses_the_judge_and_logs_every_bait(monkeypatch):
    def fake_ask(prompt_text, fields):
        if "baits" in prompt_text:
            return {"baits": [BAIT, {**BAIT, "title": "calm video", "description": "", "captions": "", "intended_labels": ["engagement_bait"]}]}
        return {"tactics": [{"label": "fake_urgency", "evidence": "only 2 hours left", "reason": "r"}], "concern_category": "none"}
    monkeypatch.setattr(loop, "ask", fake_ask)
    entry = loop.run_round(1, [])
    assert entry["round"] == 1 and len(entry["baits"]) == 2
    first = entry["baits"][0]
    assert first["intended"] == ["fake_urgency", "hidden_ad"] and first["kept"] == ["fake_urgency"] and first["missed"] == ["hidden_ad"]
    assert first["description"] == BAIT["description"] and first["captions"] == BAIT["captions"]  # text is logged so misses can be read
    assert entry["intended_total"] == 3 and entry["caught_total"] == 1
    assert entry["baits"][1]["kept"] == []  # quote "only 2 hours left" is not in the calm video, judge drops it


def test_run_round_survives_a_failed_detect(monkeypatch):
    calls = {"n": 0}
    def fake_ask(prompt_text, fields):
        if "baits" in prompt_text:
            return {"baits": [BAIT]}
        raise RuntimeError("timeout")
    monkeypatch.setattr(loop, "ask", fake_ask)
    entry = loop.run_round(1, [])
    assert entry["baits"][0]["kept"] == [] and "timeout" in entry["baits"][0]["error"]
