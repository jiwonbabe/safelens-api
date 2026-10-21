import os
import time

import pytest

import pipeline.llm  # noqa: F401  loaded (and .env read) before the missing-key test deletes the key
import pipeline.rules as rules
from pipeline.judge import DEMO_RULES, kid_verdict
from pipeline.rules import ALLOW_WORDS, DENY_WORDS, TOPIC_SYNONYMS, parse_rules, parse_rules_llm, topic_hits

CASE2 = "I'm ok with science and space stuff and lego. Please no toy unboxing videos, nothing scary, and no pranks"


# --- vocabulary --------------------------------------------------------------

def test_vocabulary_split_and_lowercase():
    assert list(TOPIC_SYNONYMS) == ALLOW_WORDS + DENY_WORDS and len(ALLOW_WORDS) == 13 and len(DENY_WORDS) == 7
    assert all(s == s.lower() for v in TOPIC_SYNONYMS.values() for s in v)


def test_topic_hits_whole_words_order_and_dedupe():
    assert topic_hits("Lego bricks and science, lego again") == ["lego", "science"]
    assert topic_hits("gamescience") == []  # whole words only
    assert topic_hits("레고는 좋아요, 공포 금지") == ["lego", "horror"]  # Korean as substring
    assert topic_hits("science and unboxing", ALLOW_WORDS) == ["science"]


# --- parse_rules (fallback) --------------------------------------------------

def test_parse_rules_demo_sentence():
    assert parse_rules(DEMO_RULES) == (["science", "lego", "animals"], ["unboxing", "challenges", "buy now"])


def test_parse_rules_case2():
    assert parse_rules(CASE2) == (["science", "space", "lego"], ["toys", "unboxing", "horror", "pranks"])


def test_parse_rules_only_and_absolutely():
    assert parse_rules("only educational content, animals are fine, absolutely no horror or jump scares") == (["education", "animals"], ["horror"])


def test_parse_rules_one_word_and_lists():
    assert parse_rules("science") == (["science"], [])
    assert parse_rules("lego, animals, space") == (["lego", "animals", "space"], [])


def test_parse_rules_korean():
    assert parse_rules("과학 실험, 레고. 언박싱 금지") == (["science", "lego"], ["unboxing"])


def test_parse_rules_dont_want():
    assert parse_rules("I don't want pranks or challenges. Animals and cooking are great") == (["animals", "cooking"], ["pranks", "challenges"])


def test_parse_rules_except_and_but():
    assert parse_rules("everything except horror") == (list(ALLOW_WORDS), ["horror"])
    assert parse_rules("lego is fine but no unboxing") == (["lego"], ["unboxing"])


def test_parse_rules_avoid_and_game_names():
    assert parse_rules("avoid violence and weapons; Minecraft and Roblox are ok") == (["gaming"], ["violence", "weapons"])


def test_parse_rules_empty_or_garbage_gives_every_allow_word():
    assert parse_rules("") == (list(ALLOW_WORDS), [])
    assert parse_rules("asdf qwerty") == (list(ALLOW_WORDS), [])


# --- parse_rules_llm (code decides) ------------------------------------------

def test_llm_output_is_filtered_to_vocabulary_and_short_phrases(monkeypatch):
    out = {"allow": ["science", "scary", "dinosaurs"], "deny": ["jump scares", "Buy Now", "a long sentence that is not a phrase at all"]}
    monkeypatch.setattr(rules, "ask_rules", lambda text: out)
    assert parse_rules_llm(DEMO_RULES) == (["science"], ["horror", "buy now"])


def test_llm_value_error_falls_back(monkeypatch):
    def boom(text):
        raise ValueError("not json")
    monkeypatch.setattr(rules, "ask_rules", boom)
    assert parse_rules_llm(CASE2) == parse_rules(CASE2)


def test_llm_timeout_falls_back_fast(monkeypatch):
    def slow(text):
        time.sleep(1)
        return {"allow": ["science"], "deny": []}
    monkeypatch.setattr(rules, "ask_rules", slow)
    monkeypatch.setattr(rules, "RULES_TIMEOUT", 0.1)
    start = time.time()
    assert parse_rules_llm(CASE2) == parse_rules(CASE2)
    assert time.time() - start < 0.5


def test_llm_missing_key_falls_back(monkeypatch):
    monkeypatch.delenv("INWORLD_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "inworld")
    assert parse_rules_llm(CASE2) == parse_rules(CASE2)


@pytest.mark.skipif(not os.path.exists(".env"), reason="needs .env with an LLM key")
def test_llm_live_demo_sentence_matches_contract():
    assert parse_rules_llm(DEMO_RULES) == (["science", "lego", "animals"], ["unboxing", "challenges", "buy now"])


# --- kid_verdict through topic_hits ------------------------------------------

def row(**over):
    base = {"title": "Elephant Toothpaste", "channel": "SciShow Kids", "topics": ["science"], "match": 95,
            "tactics": [], "verdict_teen": "show", "kid_risk": "none", "commercial_hook": None}
    base.update(over)
    return base


def test_kid_allow_matches_canonical_and_synonym_topics():
    assert kid_verdict(row(topics=["science", "experiments"]), ["science"], []) == "show"
    assert kid_verdict(row(topics=["experiments"]), ["science"], []) == "show"


def test_kid_deny_matches_synonym_topic_title_and_free_phrase():
    # Task 4 ruling (Jiwon 11:50): a deny hit is "approve" (parent decides), hide is safety only
    assert kid_verdict(row(topics=["scary"]), ["science"], ["horror"]) == "approve"
    assert kid_verdict(row(title="Creepy Toy Prank", topics=["toys"]), ["toys"], ["horror"]) == "approve"
    assert kid_verdict(row(title="Buy now before it ends", topics=["science"]), ["science"], ["buy now"]) == "approve"
