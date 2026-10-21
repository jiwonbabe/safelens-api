import subprocess
import sys

from eval import CELLS, classify, score


def row(**over):
    base = {"video_id": "v", "title": "T", "tactics": [], "verdict_teen": "show", "verdict_kid": "show",
            "proposal": {"lens": {"tactics": []}, "topics": {}}}
    base.update(over)
    return base


def tactic(label, evidence="E"):
    return {"label": label, "evidence": evidence, "reason": "r"}


def test_score_teen_rows_need_verdict_and_exact_label_set():
    g = {"video_id": "v", "age_band": "teen", "verdict": "show", "labels": ["fake_urgency"]}
    assert score(g, row(tactics=[tactic("fake_urgency")])) == ("teen show", True)
    assert score(g, row(tactics=[tactic("fake_urgency"), tactic("hidden_ad")])) == ("teen show", False)
    assert score(g, row(verdict_teen="flag", tactics=[tactic("fake_urgency")])) == ("teen show", False)
    g2 = {"video_id": "v", "age_band": "teen", "verdict": "flag", "labels": []}
    assert score(g2, row(verdict_teen="flag", tactics=[tactic("hidden_ad")])) == ("teen flag", True)  # no gold labels: verdict only


def test_score_kid_and_control_rows():
    assert score({"video_id": "v", "age_band": "kid", "verdict": "approve", "labels": []}, row(verdict_kid="approve")) == ("kid approve", True)
    assert score({"video_id": "v", "age_band": "kid", "verdict": "hide", "labels": []}, row(verdict_kid="approve")) == ("kid hide", False)
    assert score({"video_id": "v", "age_band": "both", "verdict": "show", "labels": []}, row()) == ("control", True)
    assert score({"video_id": "v", "age_band": "both", "verdict": "show", "labels": []}, row(tactics=[tactic("hidden_ad")])) == ("control", False)


def test_classify_names_the_cause_of_each_miss():
    g = {"age_band": "teen", "verdict": "show", "labels": ["body_image_pressure", "fake_social_proof"]}
    r = row(tactics=[tactic("hidden_ad", "use code X")], title="use code X 10 pounds in 3 days",
            proposal={"lens": {"tactics": [tactic("hidden_ad", "use code X"), tactic("body_image_pressure", "not in text")]}, "topics": {}})
    out = classify(g, r, "use code x 10 pounds in 3 days")
    assert "body_image_pressure: quote-not-found" in out
    assert "fake_social_proof: LLM-missed-it" in out
    assert "hidden_ad: rule-too-loose" in out
    r2 = row(proposal={"lens": {"tactics": [tactic("body_image_pressure", "10 pounds in 3 days")]}, "topics": {}})
    assert "body_image_pressure: rule-too-strict" in classify({"age_band": "teen", "verdict": "show", "labels": ["body_image_pressure"]}, r2, "10 pounds in 3 days")
    assert "verdict: rule-too-strict" in classify({"age_band": "teen", "verdict": "show", "labels": []}, row(verdict_teen="flag"), "")
    assert "verdict: rule-too-loose" in classify({"age_band": "kid", "verdict": "hide", "labels": []}, row(verdict_kid="approve"), "")


def test_eval_script_runs_and_prints_the_table():
    out = subprocess.run([sys.executable, "eval.py"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert all(c in out.stdout for c in CELLS) and "total" in out.stdout
