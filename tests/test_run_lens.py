import pipeline.run_lens as rl
from pipeline.judge import LABELS


def video(**over):
    base = {"id": "vid1", "title": "Last Chance to Win - Ends Tonight", "channel": "Auto", "description": "use code SAVE10",
            "captions": "", "upload_date": "20260615", "view_count": 11191, "age_limit": 0, "thumbnail": "t.jpg"}
    base.update(over)
    return base


def test_facts_from_code_checked_signals():
    f = rl.facts(video())
    assert f["upload_days_ago"] > 100
    assert f["has_money_link"] == "yes" and f["has_disclosure"] == "no"
    assert rl.facts(video(description="affiliate links below", upload_date=""))["has_disclosure"] == "yes"
    assert rl.facts(video(upload_date=""))["upload_days_ago"] is None


def test_build_row_has_contract_keys_and_four_quiz_options():
    lens = {"tactics": [{"label": "fake_urgency", "evidence": "Ends Tonight", "reason": ""}],
            "concern_category": "none", "reality_check": "A fact."}
    topics = {"topics": ["cars"], "match": 10, "commercial_hook": {"present": False}, "kid_risk": {"category": "none"}}
    row = rl.build_row(video(), {"lens": lens, "topics": topics}, None)
    assert sorted(row) == sorted(rl.ROW_KEYS)
    assert row["verdict_teen"] == "show" and row["verdict_kid"] == "hide"
    assert len(row["quiz_options"]) == 4 and "fake_urgency" in row["quiz_options"]
    assert set(row["quiz_options"]) <= set(LABELS)
    assert row["tactics"][0]["reason"] == rl.LABEL_FALLBACK["fake_urgency"]  # empty LLM reason is filled
    assert row["signals"] == {"age_limit": 0, "upload_days_ago": rl.facts(video())["upload_days_ago"], "voice_emotion": None}
    assert row["llm_error"] is None and row["reality_check"] == "A fact."
    assert row["proposal"] == {"lens": lens, "topics": topics}  # raw LLM output kept for eval


def test_build_row_is_deterministic_per_video():
    row1 = rl.build_row(video(), {"lens": {}, "topics": {}}, None)
    row2 = rl.build_row(video(), {"lens": {}, "topics": {}}, None)
    assert row1["quiz_options"] == row2["quiz_options"]


def test_run_one_records_llm_error_but_still_judges(monkeypatch):
    def boom(prompt_text, fields):
        raise RuntimeError("timeout")
    monkeypatch.setattr(rl, "ask", boom)
    row = rl.run_one(video(title="Best Vape Tricks"))
    assert "timeout" in row["llm_error"]
    assert row["verdict_teen"] == "flag" and row["concern"]["category"] == "substance_glorification"
    assert row["tactics"] == [] and row["reality_check"] == ""


def test_needs_run_skips_only_clean_cached_rows():
    assert rl.needs_run(None, force=False) is True
    assert rl.needs_run({"llm_error": None}, force=False) is False
    assert rl.needs_run({"llm_error": "timeout"}, force=False) is True
    assert rl.needs_run({"llm_error": None}, force=True) is True


def test_rejudge_rebuilds_a_row_from_its_stored_proposal_without_llm(monkeypatch):
    def boom(prompt_text, fields):
        raise AssertionError("ask must not be called on rejudge")
    monkeypatch.setattr(rl, "ask", boom)
    old = rl.build_row(video(), {"lens": {"tactics": [{"label": "fake_urgency", "evidence": "Ends Tonight", "reason": "r"}]}, "topics": {}}, None)
    new = rl.rejudge(video(), old)
    assert [t["label"] for t in new["tactics"]] == ["fake_urgency"] and new["proposal"] == old["proposal"]
