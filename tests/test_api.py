from fastapi.testclient import TestClient

from api.main import app, DEMO_PICKS

client = TestClient(app)
FEED_KEYS = ["video_id", "title", "channel", "thumbnail", "views", "verdict", "lens_available"]
RULES = "Science experiments, LEGO builds, animal documentaries. No unboxing, no challenges, nothing with buy now."


def test_kid_feed_returns_only_show_items_with_contract_fields():
    d = client.get("/feed?age_band=kid&child_id=mia").json()
    assert d["age_band"] == "kid" and len(d["items"]) >= 5
    assert all(list(i) == FEED_KEYS for i in d["items"])
    assert all(i["verdict"] == "show" and i["lens_available"] is False for i in d["items"])
    assert d["blocked_count"] == 56 - len(d["items"])


def test_teen_feed_is_the_whole_pool_demo_picks_first():
    d = client.get("/feed?age_band=teen&child_id=mia").json()
    assert len(d["items"]) == 56 and d["blocked_count"] == 0
    assert {i["verdict"] for i in d["items"]} == {"show", "flag"}
    assert all(i["lens_available"] is True and list(i) == FEED_KEYS for i in d["items"])
    assert [i["video_id"] for i in d["items"][:3]] == DEMO_PICKS


def test_feed_rejects_bad_or_missing_age_band():
    assert client.get("/feed?age_band=adult").status_code == 400
    assert client.get("/feed").status_code == 400
    assert client.get("/feed?age_band=adult").json() == {"error": "age_band must be kid or teen"}


def test_lens_has_contract_shape_and_verbatim_evidence():
    d = client.get("/video/_OxuxhHF1WI/lens").json()
    assert list(d) == ["video_id", "verdict", "tactics", "quiz_options", "reality_check", "concern", "signals"]
    assert d["verdict"] == "show" and d["concern"] is None
    assert "fake_urgency" in [t["label"] for t in d["tactics"]]
    assert all(list(t) == ["label", "evidence", "reason"] for t in d["tactics"])
    assert len(d["quiz_options"]) == 4 and d["reality_check"]
    assert list(d["signals"]) == ["age_limit", "upload_days_ago", "voice_emotion"]


def test_lens_of_flagged_video_carries_a_concern():
    d = client.get("/video/9ivV1sbd9cs/lens").json()
    assert d["verdict"] == "flag"
    assert list(d["concern"]) == ["category", "evidence", "reason"] and d["concern"]["category"] == "violence_glorification"


def test_lens_unknown_video_is_404():
    r = client.get("/video/nope/lens")
    assert r.status_code == 404 and r.json() == {"error": "unknown video_id"}


def test_parent_rules_returns_chips_and_sorted_queue_with_notes():
    d = client.post("/parent/rules", json={"child_id": "mia", "rules_text": RULES}).json()
    assert d["child_id"] == "mia"
    assert d["allow"] == ["science", "lego", "animals"] and d["deny"] == ["unboxing", "challenges", "buy now"]
    q = d["queue"]
    assert len(q) == 56 and all(list(i) == ["video_id", "title", "channel", "thumbnail", "topics", "match", "verdict", "note"] for i in q)
    assert [i["match"] for i in q] == sorted((i["match"] for i in q), reverse=True)
    assert all(i["note"] is None for i in q if i["verdict"] == "show")
    assert all(i["note"] for i in q if i["verdict"] != "show")
    assert any(i["verdict"] == "approve" for i in q)


def test_parent_rules_change_the_kid_feed_for_that_child():
    before = client.get("/feed?age_band=kid&child_id=zed").json()["items"]
    client.post("/parent/rules", json={"child_id": "zed", "rules_text": "LEGO builds only."})
    after = client.get("/feed?age_band=kid&child_id=zed").json()["items"]
    assert len(after) < len(before) and all(i["channel"] == "LEGO" for i in after)
    assert len(client.get("/feed?age_band=kid&child_id=mia").json()["items"]) == len(before)  # other child untouched
