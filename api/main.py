"""Three endpoints, served from cache/lens.sqlite. The only LLM call is POST /parent/rules, 5 s timeout with a rule-based fallback."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pipeline.age import resolve_age
from pipeline.cache import all_rows, get, open_db
from pipeline.judge import DEMO_RULES, TRUSTED_CHANNELS, kid_verdict, parse_rules, topic_hits
from pipeline.rules import parse_rules_llm

app = FastAPI(title="SafeLens API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DEMO_PICKS = ["_OxuxhHF1WI", "YjIA7HJXFg0", "jZumiXIiCWE"]
RULES = {"mia": parse_rules(DEMO_RULES)}  # ponytail: in-memory rules, lost on restart; demo re-posts them.


def rows():
    return all_rows(open_db())


def rules_for(child_id):
    return RULES.get(child_id) or RULES["mia"]


def video_url(video_id):
    return "https://www.youtube.com/watch?v=" + video_id


def feed_item(row, verdict, lens_available):
    return {"video_id": row["video_id"], "url": video_url(row["video_id"]), "title": row["title"], "channel": row["channel"], "thumbnail": row["thumbnail"],
            "views": row["views"], "verdict": verdict, "lens_available": lens_available}


def kid_note(row, verdict, deny):
    if verdict == "show":
        return None
    if verdict == "hide":
        if row["kid_risk"] != "none":
            return row["kid_risk"]
        return f"teen {row['verdict_teen']}"
    if row["commercial_hook"]:
        return f"Names a product with no disclosure: \"{row['commercial_hook']}\""
    title = row["title"].lower()
    found = set(topic_hits(title + " " + " ".join(row["topics"])))
    hit = [d for d in deny if d in found or d in title]
    if hit:
        return f"deny rule: {hit[0]}"
    if row["tactics"]:
        return f"Has a lens tactic: {row['tactics'][0]['label']}"
    if row["channel"] not in TRUSTED_CHANNELS:
        return "Untrusted channel"
    return "no allowed topic"


@app.exception_handler(Exception)
def on_error(request: Request, e: Exception):
    return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/")
def root():
    return {"ok": True, "service": "safelens-api", "videos": len(rows())}


@app.get("/feed")
def feed(age_band: str = "", child_id: str = "mia", dob: str = "", jurisdiction: str = "US-CA"):
    if dob:
        try:
            age_band, source = resolve_age(dob, jurisdiction)
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "dob must be YYYY-MM-DD"})
    elif age_band in ("kid", "teen"):
        source = "client"
    else:
        return JSONResponse(status_code=400, content={"error": "age_band must be kid or teen"})
    if age_band == "adult":
        return {"age_band": "adult", "age_source": source, "items": [], "blocked_count": 0}
    data = rows()
    if age_band == "kid":
        allow, deny = rules_for(child_id)
        shown = sorted([r for r in data if kid_verdict(r, allow, deny) == "show"], key=lambda r: -r["match"])
        items = [feed_item(r, "show", False) for r in shown]
        return {"age_band": "kid", "age_source": source, "items": items, "blocked_count": len(data) - len(items)}
    teen = [r for r in data if r["verdict_teen"] in ("show", "flag")]
    teen.sort(key=lambda r: (DEMO_PICKS.index(r["video_id"]) if r["video_id"] in DEMO_PICKS else 99, -r["views"]))
    return {"age_band": "teen", "age_source": source, "items": [feed_item(r, r["verdict_teen"], True) for r in teen],
            "blocked_count": len(data) - len(teen)}


@app.get("/video/{video_id}/lens")
def lens(video_id: str):
    row = get(open_db(), video_id)
    if row is None:
        return JSONResponse(status_code=404, content={"error": "unknown video_id"})
    return {"video_id": row["video_id"], "url": video_url(row["video_id"]), "verdict": row["verdict_teen"], "tactics": row["tactics"],
            "quiz_options": row["quiz_options"], "reality_check": row["reality_check"], "concern": row["concern"],
            "signals": row["signals"]}


@app.post("/parent/rules")
def parent_rules(body: dict):
    child_id = body.get("child_id") or "mia"
    allow, deny = parse_rules_llm(body.get("rules_text") or "")
    RULES[child_id] = (allow, deny)
    queue = []
    for r in rows():
        verdict = kid_verdict(r, allow, deny)
        queue.append({"video_id": r["video_id"], "url": video_url(r["video_id"]), "title": r["title"], "channel": r["channel"], "thumbnail": r["thumbnail"],
                      "topics": r["topics"], "match": r["match"], "verdict": verdict, "note": kid_note(r, verdict, deny)})
    queue.sort(key=lambda q: -q["match"])
    return {"child_id": child_id, "allow": allow, "deny": deny, "queue": queue}
