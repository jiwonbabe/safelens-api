"""The LLM proposes, this file decides. A label stays only if its quote is in the video text and it passes the label's rule."""
import re

from pipeline.build_pool import collapse, video_text
from pipeline.rules import parse_rules, topic_hits  # noqa: F401  re-exported for judge users

LABELS = ["fake_urgency", "hidden_ad", "body_image_pressure", "engagement_bait", "misleading_thumbnail", "fake_social_proof"]
TRUSTED_CHANNELS = ["SciShow Kids", "Nat Geo Kids", "LEGO"]
DEMO_RULES = "Science experiments, LEGO builds, animal documentaries. No unboxing, no challenges, nothing with buy now."

DISCLOSURE = r"\b(ad|ads|sponsored|paid partnership|affiliate|commission|i earn)\b"
MONETIZED = r"amzn\.to|bit\.ly|link in bio|t\.me|discount code|promo code|use (the )?code|code:? ?[\"'“”‘’]?[a-z0-9]{3,}|\d+% off|saves? (you )?\d+%"
URGENCY = r"\d+ ?(hours?|minutes?|days?) left|last chance|ends tonight|only today|ends at midnight|hurry"
BODY = r"\d+[ -]?(lb|lbs|pounds|kg|days?|weeks?|months?)\b|before (and|&) after|glass skin"
BAIT = r"like in \d|comment or|share this or|subscribe or|or else"
PROOF = r"millions use|everyone is|everyone's|best selling|100%|#1|\bno\.? ?1\b|\d"
CONCERN_WORDS = {
    "private_contact_recruiting": r"t\.me|dm me|discord\.gg|join my discord|sugar daddy|sugar baby|onlyfans",
    "gambling_like": r"gambling|case opening|loot box",
    "substance_glorification": r"vape|sarms|getting drunk",
    "violence_glorification": r"street fights?|hood fights?|fight compilation",
    "manosphere": r"andrew tate|red pill|redpill|alpha male|high value man",
    "reckless_driving": r"street takeover|sideshow",
    "weapons_with_links": r"switchblade|karambit",
    "cosmetic_procedure": r"lip filler|fillers?\b|botox|nose job|rhinoplasty|eyelid surgery|liposuction|\blipo\b|buccal fat|jaw (shaving|surgery)|skin whitening|skin lightening|glutathione",
    "dangerous_challenge": r"blackout challenge|benadryl challenge|dry scoop|chroming|one chip challenge|skull ?breaker|milk crate challenge",
    "money_scheme": r"cash app flip|flip \$?\d+ to|join my team|make money from your phone|passive income secret|guaranteed profit",
}
EDUCATIONAL = (r"\b(reacts?( to)?|the truth about|exposed|explained|explains|debunk(ed|ing)?|warning|news|lawsuit|parents sue"
               r"|doctor|surgeon|dentist|dermatologist|nutritionist|fact[ -]?check)\b")
FLAG_TITLE = r"\d+ ?(lb|lbs|pounds|kg)\b.{0,20}\b\d+ ?(day|days|week|weeks)\b"
HEALTH_TITLE = r"weight loss|fat loss|fat burn"


QUOTE_MARKS = "\"'“”‘’«»「」"


def quote_ok(evidence, text):
    """Case-insensitive substring, whitespace collapsed, surrounding quotation marks ignored."""
    quote = collapse(str(evidence or "")).strip(QUOTE_MARKS).lower()
    return bool(quote) and quote in text


def head_of(video):
    return collapse(f"{video.get('title') or ''} {video.get('description') or ''}").lower()


def keep_tactic(tactic, video):
    label, evidence = tactic.get("label"), tactic.get("evidence")
    text = video_text(video)
    if label not in LABELS or not quote_ok(evidence, text):
        return False
    quote = collapse(str(evidence)).strip(QUOTE_MARKS).lower()
    head = head_of(video)
    if label == "fake_urgency":
        return bool(re.search(URGENCY, quote))
    if label == "hidden_ad":  # the quote itself must show the money link or code; subscribe links are not money
        return bool(re.search(MONETIZED, quote)) and "subscribe" not in quote and not re.search(DISCLOSURE, head)
    if label == "body_image_pressure":
        return bool(re.search(BODY, quote))
    if label == "engagement_bait":
        return bool(re.search(BAIT, quote))
    if label == "misleading_thumbnail":
        title = collapse(video.get("title") or "").lower()
        captions = collapse(video.get("captions") or "").lower()
        return quote in title and quote_ok(tactic.get("reason"), captions)
    if label == "fake_social_proof":
        return bool(re.search(PROOF, quote))
    return False


def concern_of(video, lens):
    """{category, evidence, reason} when the LLM's category has a verified quote or a concern word is in title+description, else None."""
    text, head = video_text(video), head_of(video)
    category = lens.get("concern_category") or "none"
    if category != "none" and quote_ok(lens.get("concern_evidence"), text):
        return {"category": category, "evidence": lens["concern_evidence"], "reason": lens.get("concern_reason") or ""}
    title = collapse(video.get("title") or "").lower()
    if re.search(EDUCATIONAL, title):  # a reaction, debunk, news, or clinician TITLE is not a promo; only an LLM-verified quote can flag it
        return None
    for category, pattern in CONCERN_WORDS.items():
        hit = re.search(pattern, head)
        if hit:
            return {"category": category, "evidence": hit.group(0), "reason": lens.get("concern_reason") or ""}
    return None


VOICE_CONFIRMS = ("fake_urgency", "body_image_pressure")  # Modulate may confirm these two, never add a label


def teen_verdict(video, tactics, lens, voice=None):
    """show or flag. Nothing is hidden from a teen except YouTube 18+; a flag carries an explanation instead of a wall.
    voice: Modulate emotion (excited | pressured | calm | None). A pressured voice confirms urgency/body pressure into a flag."""
    title = collapse(video.get("title") or "").lower()
    if (video.get("age_limit") or 0) >= 18:
        return "block"
    labels = [t["label"] for t in tactics]
    has_hidden_ad = "hidden_ad" in labels
    voice_confirmed = voice == "pressured" and any(l in VOICE_CONFIRMS for l in labels)
    if concern_of(video, lens) or re.search(FLAG_TITLE, title) or (has_hidden_ad and re.search(HEALTH_TITLE, title)) or voice_confirmed:
        return "flag"
    return "show"


def flag_concern(video, tactics):
    """A flag that has no category concern still gets one, mirrored from the tactic that caused the flag, so the
    frontend can rely on: verdict flag => concern present."""
    title = collapse(video.get("title") or "").lower()
    for t in tactics:
        if t["label"] == "body_image_pressure":
            return {"category": "body_image_pressure", "evidence": t["evidence"], "reason": t["reason"] or ""}
    for t in tactics:
        if t["label"] == "hidden_ad" and re.search(HEALTH_TITLE, title):
            return {"category": "undisclosed_health_product", "evidence": t["evidence"], "reason": t["reason"] or ""}
    hit = re.search(FLAG_TITLE, title)
    if hit:
        return {"category": "body_image_pressure", "evidence": hit.group(0), "reason": ""}
    for t in tactics:  # voice-confirmed urgency
        if t["label"] in VOICE_CONFIRMS:
            return {"category": t["label"], "evidence": t["evidence"], "reason": t["reason"] or ""}
    return None


def kid_verdict(row, allow, deny):
    """Pure. hide = safety only; approve = anything the parent should decide; show = trusted, on-topic, clean.
    Used at precompute time with DEMO_RULES and by the API with the parent's own rules."""
    title = (row.get("title") or "").lower()
    topics = [t.lower() for t in row.get("topics") or []]
    if row.get("verdict_teen") in ("flag", "block") or (row.get("kid_risk") or "none") != "none":
        return "hide"
    found = set(topic_hits(title + " " + " ".join(topics)))
    if any(d in found or d in title for d in deny):
        return "approve"
    if not set(allow) & found:
        return "approve"
    if row.get("tactics") or row.get("channel") not in TRUSTED_CHANNELS:  # a trusted channel's own product is not a hook
        return "approve"
    return "show"


def judge(video, proposal, voice=None):
    lens = proposal.get("lens") or {}
    topics = proposal.get("topics") or {}
    text = video_text(video)
    tactics = [{"label": t.get("label"), "evidence": t.get("evidence"), "reason": t.get("reason") or ""}
               for t in lens.get("tactics") or [] if isinstance(t, dict) and keep_tactic(t, video)]
    risk = topics.get("kid_risk") or {}
    kid_risk = risk.get("category") or "none"
    if kid_risk != "none" and not quote_ok(risk.get("evidence"), text):
        kid_risk = "none"
    hook = topics.get("commercial_hook") or {}
    commercial_hook = hook.get("evidence") if hook.get("present") and quote_ok(hook.get("evidence"), text) else None
    row = {
        "title": video.get("title"), "channel": video.get("channel"),
        "topics": [t for t in topics.get("topics") or [] if str(t).strip().lower() not in ("", "null", "none")],
        "match": int(topics.get("match") or 0),
        "tactics": tactics, "verdict_teen": teen_verdict(video, tactics, lens, voice),
        "kid_risk": kid_risk, "commercial_hook": commercial_hook,
        "concern": concern_of(video, lens),
    }
    if row["verdict_teen"] == "flag" and row["concern"] is None:
        row["concern"] = flag_concern(video, tactics)
    row["verdict_kid"] = kid_verdict(row, *parse_rules(DEMO_RULES))
    return {k: row[k] for k in ["tactics", "verdict_teen", "verdict_kid", "concern", "kid_risk", "commercial_hook", "topics", "match"]}
