"""Free-text parent rules -> (allow, deny). The LLM proposes tags, code keeps vocabulary words, parse_rules is the no-LLM fallback."""
import re
from concurrent.futures import ThreadPoolExecutor

TOPIC_SYNONYMS = {
    "science": ["science", "experiments", "experiment", "stem", "chemistry", "physics", "과학", "실험"],
    "space": ["space", "planets", "astronomy", "rockets", "우주"],
    "lego": ["lego", "legos", "bricks", "레고"],
    "animals": ["animals", "animal", "nature", "wildlife", "documentaries", "zoo", "동물", "자연"],
    "toys": ["toys", "toy", "장난감"],
    "gaming": ["gaming", "games", "game", "minecraft", "roblox", "게임"],
    "crafts": ["crafts", "craft", "diy", "만들기", "공예"],
    "music": ["music", "songs", "음악"],
    "sports": ["sports", "soccer", "football", "스포츠", "운동"],
    "cooking": ["cooking", "baking", "recipes", "요리"],
    "cars": ["cars", "vehicles", "trucks", "자동차"],
    "cartoons": ["cartoons", "animation", "만화"],
    "education": ["education", "educational", "learning", "교육"],
    "unboxing": ["unboxing", "unbox", "haul", "언박싱"],
    "challenges": ["challenges", "challenge", "챌린지"],
    "pranks": ["pranks", "prank", "몰카", "장난"],
    "horror": ["horror", "scary", "creepy", "jumpscare", "jump scares", "jump scare", "공포", "무서운"],
    "violence": ["violence", "fights", "fighting", "폭력", "싸움"],
    "weapons": ["weapons", "guns", "knives", "무기"],
    "shopping": ["shopping", "쇼핑"],
}
ALLOW_WORDS = list(TOPIC_SYNONYMS)[:13]
DENY_WORDS = list(TOPIC_SYNONYMS)[13:]

NEGATION = r"\b(no|not|never|nothing( with)?|don'?t( want)?|do not( want)?|avoid|without|ban|block|skip)\b|금지|안 ?돼|싫어|빼고|제외|말고"
FILLER = r"\b(please|absolutely|and|also|videos?|stuff|content|things?)\b"

POOL = ThreadPoolExecutor(max_workers=2)
RULES_TIMEOUT = 5


def position(text, word):
    """First index in text of any synonym of word (or the phrase itself); -1 when none is there."""
    found = [p for p in (text.find(s) for s in TOPIC_SYNONYMS.get(word, [word])) if p >= 0]
    return min(found) if found else -1


def synonym_in(synonym, text):
    if synonym.isascii():  # English: whole words/phrases. Korean: substring, particles attach (레고는)
        return bool(re.search(r"\b" + re.escape(synonym) + r"\b", text))
    return synonym in text


def topic_hits(text, words=None):
    """Canonical words with a synonym in text, ordered by first appearance, deduped. No fuzzy matching."""
    # ponytail: typos are the LLM path's job; difflib.get_close_matches(cutoff=0.8) here if the fallback must fix them
    text = text.lower()
    hits = [w for w in (words or TOPIC_SYNONYMS) if any(synonym_in(s, text) for s in TOPIC_SYNONYMS[w])]
    return sorted(hits, key=lambda w: position(text, w))


def dedupe(items):
    return list(dict.fromkeys(items))


def parse_rules(rules_text):
    """Pure, no LLM. The fallback and the default rules."""
    # ponytail: a deny clause keeps every topic hit, so "no toy unboxing" also denies toys; the LLM path is finer
    text = rules_text.lower()
    text = re.sub(r" except | but (not|no) ", ". no ", text).replace(" but ", ". ")
    allow, deny = [], []
    for clause in re.split(r"[.,;!?\n]", text):
        clause = clause.strip()
        if not clause:
            continue
        if re.search(NEGATION, clause):
            hits = topic_hits(clause)
            phrase = " ".join(re.sub(FILLER, " ", re.sub(NEGATION, " ", clause)).split())
            deny += hits or ([phrase] if 1 <= len(phrase.split()) <= 3 else [])
        else:
            allow += topic_hits(clause, ALLOW_WORDS)
    return dedupe(allow) or list(ALLOW_WORDS), dedupe(deny)


def ask_rules(rules_text):
    from pipeline.llm import ask, load_prompt  # inside so a missing key is a KeyError at call time, caught by the caller
    return ask(load_prompt("rules"), {"rules_text": rules_text})


def parse_rules_llm(rules_text):
    """LLM proposes, code keeps vocabulary words and short deny phrases. Anything odd -> parse_rules."""
    # ponytail: a timed-out call keeps running in the pool thread until the 20 s client timeout; nobody waits for it
    try:
        out = POOL.submit(ask_rules, rules_text).result(timeout=RULES_TIMEOUT)
        if not isinstance(out.get("allow"), list) or not isinstance(out.get("deny"), list):
            raise ValueError("allow/deny must be lists")
        allow = [w for item in out["allow"] for w in topic_hits(str(item), ALLOW_WORDS)]
        deny = []
        for item in out["deny"]:
            phrase = " ".join(str(item).lower().split())
            deny += topic_hits(phrase) or ([phrase] if 1 <= len(phrase.split()) <= 3 and len(phrase) <= 25 else [])
    except Exception:
        return parse_rules(rules_text)
    if not allow and not deny:
        return parse_rules(rules_text)
    text = rules_text.lower()
    allow = sorted(dedupe(allow), key=lambda w: position(text, w))
    deny = sorted(dedupe(deny), key=lambda w: position(text, w))
    return allow or list(ALLOW_WORDS), deny
