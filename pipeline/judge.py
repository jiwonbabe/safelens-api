"""The LLM proposes, this file decides. A label stays only if its quote is in the video text and it passes the label's rule."""
import re

from pipeline.build_pool import collapse, video_text

LABELS = ["fake_urgency", "hidden_ad", "body_image_pressure", "engagement_bait", "misleading_thumbnail", "fake_social_proof"]
TRUSTED_CHANNELS = ["SciShow Kids", "Nat Geo Kids", "LEGO"]
DEMO_RULES = "Science experiments, LEGO builds, animal documentaries. No unboxing, no challenges, nothing with buy now."
TOPIC_WORDS = ["science", "lego", "animals", "animal", "toys", "gaming", "games", "horror", "pranks",
               "crafts", "music", "sports", "cooking", "unboxing", "challenges"]
TOPIC_ALIAS = {"animal": "animals", "games": "gaming"}

DISCLOSURE = r"\b(ad|ads|sponsored|paid partnership|affiliate|commission|i earn)\b"
MONETIZED = r"amzn\.to|bit\.ly|link in bio|t\.me|discount code|promo code|use (the )?code|code [a-z0-9]{3,}|\d+% off"
URGENCY = r"\d+ ?(hours?|minutes?|days?) left|last chance|ends tonight|only today|ends at midnight|hurry"
BODY = r"\d+ ?(lb|lbs|pounds|kg|days?|weeks?|months?)\b|before (and|&) after|glass skin"
BAIT = r"like in \d|comment or|share this or|subscribe or|or else"
PROOF = r"millions use|everyone is|everyone's|best selling|100%|#1|\bno\.? ?1\b|\d"
BLOCK_WORDS = (r"t\.me|dm me|gambling|case opening|loot box|vape|sarms|getting drunk|street fights?|hood fights?"
               r"|fight compilation|andrew tate|street takeover|sideshow|switchblade|karambit")
FLAG_TITLE = r"\d+ ?(lb|lbs|pounds|kg)\b.{0,20}\b\d+ ?(day|days|week|weeks)\b"
HEALTH_TITLE = r"weight loss|fat loss|fat burn"


def quote_ok(evidence, text):
    return bool(evidence) and collapse(str(evidence)).lower() in text


def head_of(video):
    return collapse(f"{video.get('title') or ''} {video.get('description') or ''}").lower()


def keep_tactic(tactic, video):
    label, evidence = tactic.get("label"), tactic.get("evidence")
    text = video_text(video)
    if label not in LABELS or not quote_ok(evidence, text):
        return False
    quote = collapse(str(evidence)).lower()
    head = head_of(video)
    if label == "fake_urgency":
        return bool(re.search(URGENCY, quote))
    if label == "hidden_ad":
        return bool(re.search(MONETIZED, head)) and not re.search(DISCLOSURE, head)
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


def teen_verdict(video, tactics, lens):
    text, head = video_text(video), head_of(video)
    title = collapse(video.get("title") or "").lower()
    category = lens.get("block_category") or "none"
    if (video.get("age_limit") or 0) >= 18 or re.search(BLOCK_WORDS, head):
        return "block"
    if category != "none" and quote_ok(lens.get("block_evidence"), text):
        return "block"
    has_hidden_ad = any(t["label"] == "hidden_ad" for t in tactics)
    if re.search(FLAG_TITLE, title) or (has_hidden_ad and re.search(HEALTH_TITLE, title)):
        return "flag"
    return "show"


def kid_verdict(row, allow, deny):
    """Pure. Used at precompute time with DEMO_RULES and by the API with the parent's own rules."""
    title = (row.get("title") or "").lower()
    topics = [t.lower() for t in row.get("topics") or []]
    if row.get("verdict_teen") in ("flag", "block") or (row.get("kid_risk") or "none") != "none":
        return "hide"
    if any(word in title or word in topics for word in deny):
        return "hide"
    if not set(allow) & set(topics):
        return "hide"
    if row.get("commercial_hook") or row.get("tactics") or row.get("channel") not in TRUSTED_CHANNELS:
        return "approve"
    return "show"


def parse_rules(rules_text):
    """Plain-words parent rules -> (allow, deny). No LLM."""
    allow, deny = [], []
    for sentence in rules_text.split("."):
        for phrase in sentence.split(","):
            phrase = collapse(phrase).lower()
            if not phrase:
                continue
            if phrase.startswith("no "):
                deny.append(phrase[3:])
            elif phrase.startswith("nothing with "):
                deny.append(phrase[13:])
            else:
                words = [w for w in phrase.split() if w in TOPIC_WORDS]
                allow.append(TOPIC_ALIAS.get(words[0], words[0]) if words else phrase)
    return allow, deny


def judge(video, proposal):
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
        "topics": topics.get("topics") or [], "match": int(topics.get("match") or 0),
        "tactics": tactics, "verdict_teen": teen_verdict(video, tactics, lens),
        "kid_risk": kid_risk, "commercial_hook": commercial_hook,
        "block_category": lens.get("block_category") or "none",
    }
    row["verdict_kid"] = kid_verdict(row, *parse_rules(DEMO_RULES))
    return {k: row[k] for k in ["tactics", "verdict_teen", "verdict_kid", "block_category", "kid_risk", "commercial_hook", "topics", "match"]}
