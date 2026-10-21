from pipeline.build_pool import video_text
from pipeline.judge import (DEMO_RULES, LABELS, TRUSTED_CHANNELS, concern_of, judge, keep_tactic, kid_verdict, quote_ok,
                            parse_rules, teen_verdict)


def video(title="", description="", captions="", channel="Some Channel", age_limit=0):
    return {"title": title, "description": description, "captions": captions, "channel": channel, "age_limit": age_limit}


def tactic(label, evidence, reason="why"):
    return {"label": label, "evidence": evidence, "reason": reason}


# --- quote check -------------------------------------------------------------

def test_evidence_with_different_whitespace_is_still_found():
    v = video(title="Giveaway Ends Tonight at Midnight")
    assert keep_tactic(tactic("fake_urgency", "Giveaway  Ends\nTonight"), v) is True


def test_evidence_missing_from_text_is_dropped_whatever_the_label():
    v = video(title="A calm video", description="nothing here")
    assert keep_tactic(tactic("fake_urgency", "last chance"), v) is False


def test_unknown_label_is_dropped():
    v = video(title="spam spam")
    assert keep_tactic(tactic("spam", "spam"), v) is False


# --- label rules -------------------------------------------------------------

def test_hidden_ad_dropped_when_description_discloses():
    v = video(description="use code SAVE10 for 10% off. I earn a commission.")
    assert keep_tactic(tactic("hidden_ad", "use code SAVE10"), v) is False


def test_hidden_ad_kept_when_only_captions_mention_ad():
    v = video(description="use code SAVE10 for 10% off", captions="this is not an ad I promise")
    assert keep_tactic(tactic("hidden_ad", "use code SAVE10"), v) is True


def test_hidden_ad_needs_a_monetized_link_or_code():
    v = video(description="I love this tea, check their website")
    assert keep_tactic(tactic("hidden_ad", "check their website"), v) is False


def test_body_image_pressure_needs_number_span_or_before_after():
    assert keep_tactic(tactic("body_image_pressure", "20 pounds in 2 weeks"), video(title="lost 20 pounds in 2 weeks")) is True
    assert keep_tactic(tactic("body_image_pressure", "before and after"), video(title="my before and after")) is True
    assert keep_tactic(tactic("body_image_pressure", "feel confident"), video(title="feel confident")) is False


def test_engagement_bait_and_social_proof_patterns():
    assert keep_tactic(tactic("engagement_bait", "Subscribe or ELSE"), video(title="Subscribe or ELSE!")) is True
    assert keep_tactic(tactic("fake_social_proof", "Everyone Is OBSESSED"), video(title="Gadgets Everyone Is OBSESSED With")) is True
    assert keep_tactic(tactic("fake_social_proof", "so good"), video(title="so good")) is False


def test_misleading_thumbnail_needs_title_claim_and_caption_contradiction():
    v = video(title="I quit YouTube forever", captions="just kidding I am not quitting")
    assert keep_tactic(tactic("misleading_thumbnail", "I quit YouTube forever", "I am not quitting"), v) is True
    assert keep_tactic(tactic("misleading_thumbnail", "I quit YouTube forever", "something else"), v) is False


# --- teen verdict ------------------------------------------------------------

def test_teen_flag_on_weight_number_plus_span_in_title():
    assert teen_verdict(video(title="LOSE 10 POUNDS IN 3 DAYS"), [], {}) == "flag"


def test_teen_flag_on_hidden_ad_with_weight_loss_title():
    v = video(title="APPLE CIDER VINEGAR FOR WEIGHT LOSS", description="my plans: https://bit.ly/x")
    assert teen_verdict(v, [tactic("hidden_ad", "bit.ly")], {}) == "flag"


def test_teen_flag_not_block_on_concern_words_or_verified_llm_category():
    assert teen_verdict(video(title="Best Vape Tricks"), [], {}) == "flag"
    assert teen_verdict(video(title="calm"), [], {"concern_category": "manosphere", "concern_evidence": "calm"}) == "flag"
    assert teen_verdict(video(title="calm"), [], {"concern_category": "manosphere", "concern_evidence": "not in text"}) == "show"


def test_teen_block_only_for_youtube_age_limit():
    assert teen_verdict(video(title="calm", age_limit=18), [], {}) == "block"


def test_teen_show_by_default():
    assert teen_verdict(video(title="How to fold paper"), [], {"concern_category": "none"}) == "show"


def test_concern_of_returns_category_evidence_reason_or_none():
    v = video(title="HOOD FIGHTS 2024 & STREET FIGHTS")
    lens = {"concern_category": "violence_glorification", "concern_evidence": "STREET FIGHTS", "concern_reason": "Real people get hurt."}
    assert concern_of(v, lens) == {"category": "violence_glorification", "evidence": "STREET FIGHTS", "reason": "Real people get hurt."}
    # LLM silent but a concern word is in the title: still a concern, evidence is the matched word
    assert concern_of(v, {})["category"] == "violence_glorification"
    assert concern_of(v, {})["evidence"] in ("hood fights", "street fights")  # leftmost match wins
    assert concern_of(video(title="How to fold paper"), {}) is None


# --- parent rules + kid verdict ----------------------------------------------

def test_parse_rules_demo_sentence():
    assert parse_rules(DEMO_RULES) == (["science", "lego", "animals"], ["unboxing", "challenges", "buy now"])


def row(**over):
    base = {"title": "Elephant Toothpaste", "channel": "SciShow Kids", "topics": ["science"], "match": 95,
            "tactics": [], "verdict_teen": "show", "kid_risk": "none", "commercial_hook": None}
    base.update(over)
    return base


ALLOW, DENY = ["science", "lego", "animals"], ["unboxing", "challenges", "buy now"]


def test_kid_show_for_trusted_channel_without_hook():
    assert kid_verdict(row(), ALLOW, DENY) == "show"


def test_kid_approve_for_untrusted_channel_or_hook():
    assert kid_verdict(row(channel="Matt Creationz"), ALLOW, DENY) == "approve"
    assert kid_verdict(row(channel="Matt Creationz", commercial_hook="Tinker Crate by KiwiCo"), ALLOW, DENY) == "approve"


def test_kid_hide_only_for_safety_risk_or_teen_flag():
    assert kid_verdict(row(kid_risk="jumpscare"), ALLOW, DENY) == "hide"
    assert kid_verdict(row(verdict_teen="block"), ALLOW, DENY) == "hide"
    assert kid_verdict(row(verdict_teen="flag"), ALLOW, DENY) == "hide"


def test_kid_approve_for_deny_rule_or_topic_mismatch_so_the_parent_decides():
    assert kid_verdict(row(title="Giant Unboxing!"), ALLOW, DENY) == "approve"  # deny word, parent decides
    assert kid_verdict(row(topics=["toys"]), ALLOW, DENY) == "approve"  # no allowed topic, parent decides


# --- judge end to end --------------------------------------------------------

def test_judge_keeps_verified_tactics_and_sets_both_verdicts():
    v = video(title="Last Chance to Win This Tesla - Ends Tonight", description="GET IN NOW: https://x.com", channel="Auto Auction")
    proposal = {
        "lens": {"tactics": [tactic("fake_urgency", "Ends Tonight"), tactic("fake_urgency", "two hours left")],
                 "concern_category": "none", "concern_evidence": None, "reality_check": "Nobody gives away a car."},
        "topics": {"topics": ["cars"], "match": 10, "deny_hit": None,
                   "commercial_hook": {"present": True, "evidence": "GET IN NOW"},
                   "kid_risk": {"category": "none", "evidence": None}},
    }
    out = judge(v, proposal)
    assert [t["evidence"] for t in out["tactics"]] == ["Ends Tonight"]
    assert out["verdict_teen"] == "show"
    assert out["verdict_kid"] == "approve"  # no allowed topic: the parent decides
    assert out["commercial_hook"] == "GET IN NOW"
    assert out["concern"] is None
    assert out["topics"] == ["cars"] and out["match"] == 10


def test_judge_survives_empty_proposals():
    out = judge(video(title="Best Vape Tricks"), {"lens": {}, "topics": {}})
    assert out["tactics"] == [] and out["verdict_teen"] == "flag" and out["verdict_kid"] == "hide"
    assert out["concern"]["category"] == "substance_glorification"
    assert out["kid_risk"] == "none" and out["topics"] == [] and out["match"] == 0


def test_label_set_is_exactly_six():
    assert LABELS == ["fake_urgency", "hidden_ad", "body_image_pressure", "engagement_bait", "misleading_thumbnail", "fake_social_proof"]
    assert "SciShow Kids" in TRUSTED_CHANNELS


# --- 11:30 fixes after the first full run -----------------------------------

def test_trusted_channel_with_product_hook_but_no_tactics_is_show():
    assert kid_verdict(row(channel="LEGO", topics=["lego"], commercial_hook="LEGO Ideas Medieval Blacksmith 21325"), ALLOW, DENY) == "show"


def test_hidden_ad_quote_itself_must_show_the_link_or_code():
    v = video(description="Watch the full report. Subscribe: https://bit.ly/cbc  kits range from twenty-five dollars")
    assert keep_tactic(tactic("hidden_ad", "kits range from twenty-five dollars"), v) is False


def test_hidden_ad_ignores_subscribe_links():
    v = video(description="SUBSCRIBE TO Annoying Orange! ▸ http://bit.ly/AOSub")
    assert keep_tactic(tactic("hidden_ad", "SUBSCRIBE TO Annoying Orange! ▸ http://bit.ly/AOSub"), v) is False
    v = video(description='Be sure to use the code "thebrilliantbeauty" to get 12% off your order!')
    assert keep_tactic(tactic("hidden_ad", 'use the code "thebrilliantbeauty" to get 12% off'), v) is True


def test_quote_check_ignores_surrounding_quotation_marks():
    v = video(title="Pregnancy Battle: Spiderman Gives Shots")
    assert quote_ok('"Pregnancy Battle: Spiderman Gives Shots"', video_text(v)) is True
    assert quote_ok("“Spiderman Gives Shots”", video_text(v)) is True


def test_judge_drops_null_or_none_strings_the_llm_puts_in_topics():
    out = judge(video(title="x"), {"lens": {}, "topics": {"topics": ["null", "None", "", "science"], "match": 50}})
    assert out["topics"] == ["science"]


def test_body_pattern_accepts_hyphenated_spans():
    assert keep_tactic(tactic("body_image_pressure", "14-Day Detox Results"), video(title="My 14-Day Detox Results")) is True
