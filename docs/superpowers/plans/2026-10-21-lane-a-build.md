# Lane A Build (pipeline + judge + API) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the builder is the `builder` agent and the reviewer is the `verifier` agent (`.claude/agents/`).

**Goal:** From `data/raw/*` produce `cache/lens.sqlite` through an LLM-proposes / code-decides pipeline, and serve the three contract endpoints from that cache only.

**Architecture:** `build_pool.py` turns raw yt-dlp output into `data/videos.json`. `run_lens.py` asks Inworld twice per video (`topics.txt`, `lens.txt`), hands both proposals to `judge.py`, which keeps only quote-verified labels and decides verdicts, and writes one JSON row per video into SQLite. `api/main.py` reads SQLite and never calls an LLM. `judge.kid_verdict` is a pure function so `/parent/rules` can re-score the cached pool against new parent rules without an LLM call.

**Tech Stack:** Python 3.12, FastAPI + uvicorn, sqlite3 (stdlib), `openai` client pointed at Inworld, `python-dotenv`. No tests/ directory (FIRST_PROMPT); each module carries a `__main__` self-check.

**Spec:** `CLAUDE.md` (principles, labels, verdicts, API contract) and `FIRST_PROMPT.txt` (file list and order). Prompts: `prompts/topics.txt`, `prompts/lens.txt`.

> **Change 10:55 Oct 21 (Jiwon):** teens are never blocked. `teen_verdict` returns `show`/`flag` only (`block` solely for `age_limit >= 18`). Former block categories become `flag` with a `concern` object `{category, evidence, reason}` from `judge.concern_of`, stored in the cache row (replaces `block_category`) and returned by `/video/{id}/lens` as `concern` (null for plain show). `/feed?age_band=teen` returns the whole pool; `blocked_count` counts 18+ only. `lens.txt` fields renamed to `concern_category`, `concern_evidence`, `concern_reason`. Gold: 12 teen `block` rows became `flag`; eval's teen-block cell is empty.

## Global Constraints

- The LLM proposes, code decides. A label whose evidence is not a case-insensitive substring of `title + description + captions` is dropped.
- Exactly six labels: `fake_urgency, hidden_ad, body_image_pressure, engagement_bait, misleading_thumbnail, fake_social_proof`.
- Precompute everything. No LLM call inside `api/`.
- Response shapes are the contract in CLAUDE.md verbatim. No extra, missing, or renamed fields.
- Plain classes and functions. No dataclass, namedtuple, Enum, Protocol. Easy English names.
- Prompts stay in `prompts/*.txt`; placeholders filled by per-key replace (the templates contain literal `{}` JSON, so `str.format` would crash).
- Never create `frontend/` or `tests/`. Never edit `tests/gold.json`.
- SQLite: one table `lens_cache(video_id TEXT PRIMARY KEY, json TEXT)`.
- `.env` keys: `LLM_PROVIDER, INWORLD_API_KEY, INWORLD_MODEL, OPENAI_API_KEY, MODULATE_API_KEY`. Working model: `openai/gpt-4o-mini`.
- Demo picks (updated today): `_OxuxhHF1WI` (fake_urgency), `YjIA7HJXFg0` (hidden_ad + body), `jZumiXIiCWE` (hidden_ad, replaces HgjRJAh9kME).

## Review Focus

1. Evidence with different whitespace/line breaks than the source (captions are joined with spaces, descriptions have newlines): the quote check must collapse whitespace on both sides, or real labels get dropped. Pinned in Task 3 `judge` self-check.
2. A disclosure word inside captions only (someone says "an ad" in speech): disclosure is checked on title + description only, as the verifier does. Pinned in Task 3.
3. LLM returns fenced ```json or trailing prose: `llm.ask` must strip fences before `json.loads` and raise on anything else. Pinned in Task 2.
4. A video with an LLM failure must still get a row (verdict from rules only, empty tactics) so `/feed` never has holes. Pinned in Task 4.
5. `age_band` missing or not in {kid, teen} returns 400, never a kid feed. Pinned in Task 5.

Open decision for Jiwon (does not block Tasks 1-2): `tm9Xfv6wpN4` (apple cider vinegar, "WEIGHT LOSS" in title, sells weight-loss plans, no disclosure) is `show` in gold but the flag rule below will mark it `flag`. CLAUDE.md defines flag as "a health product with no disclosure", so the rule is right and gold is arguably wrong. Decide before the 10:30 freeze; otherwise accept one known miss.

Missing file: `eval.py` does not exist, and FIRST_PROMPT forbids the builder from touching it. Task 6 writes it only after Jiwon says so.

---

### Task 1: `pipeline/build_pool.py`

**Files:**
- Create: `pipeline/__init__.py` (empty), `pipeline/build_pool.py`
- Output: `data/videos.json`

**Interfaces:**
- Produces: `data/videos.json` = list of dicts with keys exactly `id, url, title, channel, channel_follower_count, description, thumbnail, upload_date, view_count, age_limit, captions, audio_file`. `captions` is `""` when no `.en.vtt`. `audio_file` is `data/audio/<id>.mp3` if it exists else `null`. `thumbnail` = `https://i.ytimg.com/vi/<id>/hqdefault.jpg`.
- Produces: `load_videos() -> list[dict]` (reads `data/videos.json`) and `video_text(video) -> str` (lowercased `title + "\n" + description + "\n" + captions` with whitespace collapsed to single spaces). Both are imported by later tasks.
- Produces: `clean_vtt(text: str) -> str`: drops `WEBVTT`/`Kind:`/`Language:` header lines, timestamp lines (`-->`), `<...>` tags, blank lines, and any line equal to the previous kept line; joins with single spaces.

- [ ] **Step 1: Write `clean_vtt`, `video_text`, `load_videos`, and `main()`** in `pipeline/build_pool.py`. `main()` globs `data/raw/*.info.json`, builds each dict, writes `data/videos.json` (indent 1, ensure_ascii False), prints `loaded N videos, M with captions`.

- [ ] **Step 2: Add a `__main__` self-check before `main()` runs**: `assert clean_vtt("WEBVTT\n\n00:00.000 --> 00:01.000\n<c>hi</c> there\nhi there\n\nnext") == "hi there next"` and `assert "elephant toothpaste" in video_text({"title":"The Great Elephant Toothpaste","description":"","captions":""})`.

- [ ] **Step 3: Run** `python pipeline/build_pool.py`
Expected: `loaded 56 videos, 45 with captions` and `data/videos.json` exists.

- [ ] **Step 4: Verify shape**: `python -c "import json;v=json.load(open('data/videos.json'));print(sorted(v[0]))"` prints the 12 keys above.

- [ ] **Step 5: Commit** `git add pipeline data/videos.json && git commit -m "pipeline: build_pool from raw yt-dlp output"`

---

### Task 2: `pipeline/llm.py`

**Files:**
- Create: `pipeline/llm.py`

**Interfaces:**
- Produces: `ask(prompt_text: str, fields: dict) -> dict`. Fills every `{key}` in `prompt_text` by `replace("{"+key+"}", str(value))` for each key in `fields`. Calls the provider named by `LLM_PROVIDER` (`inworld` default, `openai` backup) with `timeout=20`, `max_retries=0`, `temperature=0`. Strips a leading ```json / ``` fence and trailing ``` if present, then `json.loads`. Raises on HTTP error, timeout, or invalid JSON (no catching inside).
- Produces: `load_prompt(name: str) -> str` reads `prompts/<name>.txt`.
- Consumes: `.env` via `dotenv.load_dotenv()`.

Client construction (from CLAUDE.md): `OpenAI(base_url="https://api.inworld.ai/v1", api_key="unused", default_headers={"Authorization": f"Basic {key}"}, timeout=20, max_retries=0)`; for `openai` provider, `OpenAI(api_key=OPENAI_API_KEY, timeout=20, max_retries=0)` with model `gpt-4o-mini`.

- [ ] **Step 1: Write `load_prompt`, `ask`, and a `__main__` self-check** that asserts fence stripping on the literal string ```` ```json\n{"ok": true}\n``` ```` through the same parse helper, then calls `ask('Return ONLY {"ok": true}. Ignore: {title}', {"title": "x"})` and prints the dict.

- [ ] **Step 2: Run** `python pipeline/llm.py`
Expected: `{'ok': True}` printed, no traceback.

- [ ] **Step 3: Confirm captions cap**: `ask` truncates any field value longer than 12000 characters (the 46-minute Amazon video has ~6k words); add `# ponytail: hard cap, chunking if a label hides past 12k chars`.

- [ ] **Step 4: Commit** `git add pipeline/llm.py && git commit -m "pipeline: llm.ask for inworld/openai"`

---

### Task 3: `pipeline/judge.py`

**Files:**
- Create: `pipeline/judge.py`

**Interfaces:**
- Consumes: `video_text(video)` from Task 1.
- Produces: `judge(video, proposal) -> {"tactics": [...], "verdict_teen": str, "verdict_kid": str, "concern": dict | None, "kid_risk": str, "commercial_hook": str | None, "topics": list, "match": int}` where `proposal = {"lens": <lens.txt JSON or {}>, "topics": <topics.txt JSON or {}>}`. Each kept tactic is `{"label", "evidence", "reason"}` exactly as proposed.
- Produces: `kid_verdict(row, allow: list, deny: list) -> str` (pure; also used by the API). `row` is the cached row from Task 4 (needs `title, channel, topics, match, tactics, verdict_teen, kid_risk, commercial_hook`).
- Produces: `parse_rules(rules_text: str) -> (allow: list, deny: list)` (pure, no LLM). Sentences are split on `.`; phrases on `,`; a phrase starting with `no ` / `nothing with ` goes to `deny` with that prefix removed; otherwise it goes to `allow` as the first word of the phrase that is in `TOPIC_WORDS = ["science","lego","animals","animal","toys","gaming","games","horror","pranks","crafts","music","sports","cooking","unboxing","challenges"]` (map `animal`→`animals`, `games`→`gaming`), else the whole lowercased phrase. Demo text must yield `allow=["science","lego","animals"]`, `deny=["unboxing","challenges","buy now"]`.
- Produces: `TRUSTED_CHANNELS = ["SciShow Kids", "Nat Geo Kids", "LEGO"]`, `LABELS` (the six), `DISCLOSURE = r"\b(ad|ads|sponsored|paid partnership|affiliate|commission|i earn)\b"`.

Rules (`text` = `video_text(video)`; `head` = lowercased title + description, whitespace collapsed; `title` = lowercased title):

| label | kept when |
| --- | --- |
| any | `collapse(evidence).lower() in text`, else dropped |
| fake_urgency | evidence matches `\d+ ?(hours?|minutes?|days?) left|last chance|ends tonight|only today|ends at midnight|hurry` |
| hidden_ad | `head` matches `amzn\.to|bit\.ly|link in bio|t\.me|discount code|promo code|use (the )?code|code [a-z0-9]{3,}|\d+% off` AND `head` has no `DISCLOSURE` match |
| body_image_pressure | evidence matches `\d+ ?(lb|lbs|pounds|kg|days?|weeks?|months?)` or `before (and|&) after` or `glass skin` |
| engagement_bait | evidence matches `like in \d|comment or|share this or|subscribe or|or else` |
| misleading_thumbnail | `collapse(evidence).lower() in title` AND `collapse(reason).lower() in captions` |
| fake_social_proof | evidence matches `millions use|everyone is|everyone's|best selling|100%|#1|no\.? ?1` or contains a digit |

Concern (`concern_of(video, lens) -> dict | None`; `lens` proposal fields `concern_category`, `concern_evidence`, `concern_reason`):
- `{category, evidence, reason}` when `concern_category != "none"` and `concern_evidence` passes the quote check; else when `head` matches one of `CONCERN_WORDS` (`private_contact_recruiting: t\.me|dm me`, `gambling_like: gambling|case opening|loot box`, `substance_glorification: vape|sarms|getting drunk`, `violence_glorification: street fights?|hood fights?|fight compilation`, `manosphere: andrew tate`, `reckless_driving: street takeover|sideshow`, `weapons_with_links: switchblade|karambit`), with the matched word as evidence; else `None`. `reason` is the LLM's `concern_reason` or `""`.

Verdict teen (`age_limit` from video). A teen is never walled off; a concern becomes an explanation:
- `block` only if `age_limit >= 18` (YouTube refuses to play it anyway). None in the pool.
- else `flag` if `concern_of(...)` is not None, or `title` matches `\d+ ?(lb|lbs|pounds|kg)\b.{0,20}\b\d+ ?(day|days|week|weeks)\b`, or (`hidden_ad` kept AND `title` matches `weight loss|fat loss|fat burn`).
- else `show`.

Verdict kid via `kid_verdict(row, allow, deny)`:
- `hide` if `row["verdict_teen"] in ("flag","block")`, or `row["kid_risk"] != "none"`, or any deny word appears in `title` or in `row["topics"]`, or no topic in `allow` overlaps `row["topics"]`.
- else `approve` if `row["commercial_hook"]` is non-null (hook evidence passed the quote check), or `row["tactics"]` non-empty, or `row["channel"] not in TRUSTED_CHANNELS`.
- else `show`.

`judge()` computes `kid_risk` = topics proposal `kid_risk.category` if its evidence passes the quote check else `"none"`, `commercial_hook` = the hook evidence string if `present` and quote passes else `None`, and sets `verdict_kid = kid_verdict(row, *parse_rules(DEMO_RULES))` with `DEMO_RULES` = the CLAUDE.md demo sentence.

- [ ] **Step 1: Write `judge.py`** with the constants, `quote_ok(evidence, text)`, `head_of(video)`, `keep_tactic(tactic, video)`, `concern_of(video, lens)`, `teen_verdict(video, tactics, lens)`, `kid_verdict`, `parse_rules`, `judge`. (`collapse` is imported from `build_pool`.)

- [ ] **Step 2: Add `__main__` self-check** with these asserts (fake videos are dicts with `title/description/captions/channel/age_limit`):
  - evidence `"Giveaway  Ends\nTonight"` against title `"Giveaway Ends Tonight at Midnight"` is kept as `fake_urgency` (whitespace collapse).
  - `hidden_ad` with description `"use code SAVE10 … commission"` is dropped; with description `"use code SAVE10"` and captions `"this is not an ad"` is kept (captions do not count as disclosure).
  - evidence not in text is dropped whatever the label.
  - label `"spam"` is dropped.
  - title `"LOSE 10 POUNDS IN 3 DAYS"` → `verdict_teen == "flag"`; title `"Best Vape Tricks"` → `"flag"` with `concern.category == "substance_glorification"`; LLM `concern_category` with an unverified quote and no concern word → `"show"`; `age_limit 18` → `"block"`.
  - `parse_rules(DEMO_RULES) == (["science","lego","animals"], ["unboxing","challenges","buy now"])`.
  - `kid_verdict` on SciShow Kids science row with no hook → `"show"`; same row with channel `"Matt Creationz"` → `"approve"`; topics `["horror"]` → `"hide"`.

- [ ] **Step 3: Run** `python pipeline/judge.py`
Expected: `judge self-check ok`.

- [ ] **Step 4: Commit** `git add pipeline/judge.py && git commit -m "pipeline: judge rules over LLM proposals"`

---

### Task 4: `pipeline/run_lens.py` → `cache/lens.sqlite`

**Files:**
- Create: `pipeline/run_lens.py`, `pipeline/cache.py`
- Output: `cache/lens.sqlite`

**Interfaces:**
- Consumes: `load_videos`, `video_text` (Task 1); `ask`, `load_prompt` (Task 2); `judge`, `LABELS` (Task 3).
- Produces (`pipeline/cache.py`): `open_db(path="cache/lens.sqlite")` creating the table if missing; `put(db, video_id, row: dict)`; `get(db, video_id) -> dict | None`; `all_rows(db) -> list[dict]`.
- Produces: one cached row per video with keys `video_id, title, channel, thumbnail, views, upload_date, age_limit, topics, match, commercial_hook, kid_risk, tactics, verdict_teen, verdict_kid, concern, reality_check, quiz_options, signals, llm_error`. `signals = {"age_limit", "upload_days_ago" (from upload_date vs today), "voice_emotion": null}`. `quiz_options` = kept labels plus distractors from `LABELS` up to 4, order shuffled with `random.Random(video_id)`. `reality_check` = lens proposal's string or `""` on LLM failure. `llm_error` = error text or `null`.
- CLI: `python pipeline/run_lens.py [--only id1,id2] [--force]`. Skips videos already cached unless `--force`. Runs videos through `concurrent.futures.ThreadPoolExecutor(max_workers=6)`. Per video: topics call with `rules_text = DEMO_RULES`, lens call with `upload_date`, `view_count`, plus three facts the prompt now expects: `upload_days_ago` (int), `has_money_link` ("yes"/"no" from `judge.MONETIZED` over `head_of(video)`), `has_disclosure` ("yes"/"no" from `judge.DISCLOSURE`); when the LLM gives no `reason`, fill it from `LABEL_FALLBACK` (one fixed sentence per label, written in code); each call wrapped so a failure yields `{}` for that proposal and sets `llm_error`. Prints one line per video: `id verdict_teen verdict_kid [labels] (error?)` and a final count by verdict.

- [ ] **Step 1: Write `pipeline/cache.py`** with the four functions above (sqlite3, `INSERT OR REPLACE`).

- [ ] **Step 2: Write `pipeline/run_lens.py`** with `build_row(video) -> dict` and `main()`.

- [ ] **Step 3: Smoke run on the three demo picks**: `python pipeline/run_lens.py --only _OxuxhHF1WI,YjIA7HJXFg0,jZumiXIiCWE`
Expected: three lines; Tesla has `fake_urgency`, Teatox has `hidden_ad`, Flat Tummy has `hidden_ad`; no `llm_error`.

- [ ] **Step 4: Full run**: `python pipeline/run_lens.py`
Expected: 56 lines, final counts; `llm_error` on at most a few. Re-run `python pipeline/run_lens.py` once more without `--force` to fill any failures (it skips cached successes; treat rows with `llm_error` as not cached).

- [ ] **Step 5: Integrity check** (Review Focus 4 and verifier's judge-integrity items): `python - <<'EOF'` that loads all rows and asserts: every tactic label in `LABELS`; every evidence collapsed-lowercase is in `video_text` of its video; no `hidden_ad` where `DISCLOSURE` matches the title+description; every row has 4 `quiz_options`; row count == 56. Prints `cache ok`.

- [ ] **Step 6: Commit** `git add pipeline/cache.py pipeline/run_lens.py cache/lens.sqlite && git commit -m "pipeline: run_lens builds the cache"`

---

### Task 5: `api/main.py`

**Files:**
- Create: `api/__init__.py` (empty), `api/main.py`

**Interfaces:**
- Consumes: `open_db, all_rows, get` (Task 4); `kid_verdict, parse_rules, DEMO_RULES` (Task 3); `parse_rules_llm` (Task 7; until Task 7 lands, `parse_rules`).
- Produces the three endpoints exactly as CLAUDE.md "API contract". Module-level `RULES = {"mia": parse_rules(DEMO_RULES)}`; `POST /parent/rules` sets `RULES[child_id] = parse_rules_llm(rules_text)` (Task 7: LLM proposes under a 5 s cap, `parse_rules` is the fallback; the module-level demo rules and `judge()` keep using `parse_rules`). `# ponytail: in-memory rules, lost on restart; demo re-posts them.`
- `GET /feed`: `age_band` not in `{"kid","teen"}` → 400 `{"error": "age_band must be kid or teen"}`. `child_id` defaults `"mia"`; unknown child uses demo rules. Kid: rows where `kid_verdict(row, allow, deny) == "show"`, `lens_available: false`, `blocked_count` = rows not shown. Teen: rows with `verdict_teen in ("show","flag")` (the whole pool), `lens_available: true`, `blocked_count` = rows with `block` (18+ only, normally 0). Item keys exactly `video_id, title, channel, thumbnail, views, verdict, lens_available`. Teen items sorted demo picks first (`_OxuxhHF1WI, YjIA7HJXFg0, jZumiXIiCWE`), then by views desc; kid by `match` desc.
- `GET /video/{video_id}/lens`: unknown id → 404 `{"error": "unknown video_id"}`. Returns `video_id, verdict (verdict_teen), tactics, quiz_options, reality_check, concern, signals` in that order; `concern` is the cached object or `null`.
- `POST /parent/rules`: body `{child_id, rules_text}`; returns `child_id, allow, deny, queue` where queue = every row as `{video_id, title, channel, thumbnail, topics, match, verdict, note}` with `verdict = kid_verdict(...)`, sorted by `match` desc. `note`: `null` for show; for approve `"Names a product with no disclosure: \"<commercial_hook>\""` when hook present, else `"Untrusted channel"`, else `"Has a lens tactic: <label>"`; for hide the `kid_risk` or `"teen <verdict_teen>"` or `"deny rule: <word>"` or `"no allowed topic"`.
- CORS: `allow_origins=["*"]`, all methods and headers. Unhandled exceptions → 500 `{"error": str(e)}` via an exception handler.

- [ ] **Step 1: Write `api/main.py`**: `app`, `rows()` helper (opens the db per request), `feed_item(row, age_band)`, the three routes, the 500 handler.

- [ ] **Step 2: Start** `uvicorn api.main:app --host 0.0.0.0 --port 8000` (background) and run:
```bash
curl -s "localhost:8000/feed?age_band=kid&child_id=mia" | python -m json.tool | head -30
curl -s "localhost:8000/feed?age_band=teen&child_id=mia" | python -c "import sys,json;d=json.load(sys.stdin);print(len(d['items']),d['blocked_count'],[i['verdict'] for i in d['items']])"
curl -s -o /dev/null -w "%{http_code}\n" "localhost:8000/feed?age_band=adult"
curl -s -o /dev/null -w "%{http_code}\n" "localhost:8000/video/nope/lens"
curl -s localhost:8000/video/_OxuxhHF1WI/lens | python -m json.tool
curl -s -X POST localhost:8000/parent/rules -H 'content-type: application/json' -d '{"child_id":"mia","rules_text":"Science experiments, LEGO builds, animal documentaries. No unboxing, no challenges, nothing with buy now."}' | python -c "import sys,json;d=json.load(sys.stdin);print(d['allow'],d['deny']);import collections;print(collections.Counter(q['verdict'] for q in d['queue']));print([q for q in d['queue'] if q['verdict']=='approve'][0])"
```
Expected: kid items all `show` with 7 fields; teen prints `56 0 [...]` (whole pool, mix of show and flag); `400`; `404`; Tesla lens with `fake_urgency` and 4 `quiz_options`; allow/deny equal to the contract example and at least one approve with a note.

- [ ] **Step 3: Timing** `for i in 1 2 3; do curl -s -o /dev/null -w "%{time_total}\n" localhost:8000/video/YjIA7HJXFg0/lens; done` → each under 0.3.

- [ ] **Step 4: Key-removed check** (verifier item): temporarily `mv .env .env.bak`, restart uvicorn, repeat the kid feed curl and the `POST /parent/rules` curl from Step 2, then `mv .env.bak .env`. Expected: same kid feed; the POST still returns `allow=["science","lego","animals"]`, `deny=["unboxing","challenges","buy now"]` within 1 s (fallback path).

- [ ] **Step 5: Commit** `git add api && git commit -m "api: feed, lens, parent rules from cache"`

Stop here. Jiwon runs `/eval` (needs Task 6) and says "deploy".

---

### Task 6 (only after Jiwon says "write eval.py"): `eval.py`

**Files:**
- Create: `eval.py`

**Interfaces:**
- Consumes: `tests/gold.json` rows `{video_id, age_band, verdict, labels}`; cache rows via `all_rows`; `kid_verdict`, `parse_rules`, `DEMO_RULES`.
- Prints per cell (`teen show / teen flag / teen block (empty since 10:55) / kid show / kid approve / kid hide / control`) gold count, correct, accuracy; `both` rows are the `control` cell and count correct when `verdict_teen == "show"` and `verdict_kid != "hide"` and no tactics kept. Teen rows are correct when `verdict_teen` matches and, for `show`/`flag` rows with labels, the kept label set equals the gold label set. Then for every miss prints `video_id, title, gold verdict + labels, predicted verdict + labels, evidence kept`. Exit code 0 always.

- [ ] **Step 1: Write `eval.py`**, run `python eval.py`, paste the table.
- [ ] **Step 2: Commit** `git add eval.py && git commit -m "eval: accuracy vs gold"`

---

### Task 7: free-text parent rules (`pipeline/rules.py`, `prompts/rules.txt`)

A parent types rules as free text ("I'm ok with science and space stuff and lego. Please no toy unboxing videos, nothing scary, and no pranks", "과학 실험, 레고. 언박싱 금지", one-word lists, typos, "except", "don't want"). The LLM proposes tags, code keeps only vocabulary words, a rule-based parser answers when the LLM is slow, down, keyless, or returns garbage. The demo sentence must give the contract lists with the key removed.

**Files:**
- Create: `pipeline/rules.py`, `prompts/rules.txt`, `tests/test_rules.py`
- Modify: `pipeline/judge.py` (move `parse_rules`, `TOPIC_WORDS`, `TOPIC_ALIAS` out; `from pipeline.rules import parse_rules, topic_hits` so `test_judge.py` is unchanged; `kid_verdict` deny/allow lines), `api/main.py` (`POST /parent/rules` only)

**Interfaces:**
- Produces `TOPIC_SYNONYMS`: canonical word -> synonyms, all lowercase. The first 13 keys are `ALLOW_WORDS`, the last 7 `DENY_WORDS`. English synonyms match as whole words/phrases on the lowercased text (`\b`), Korean ones as substrings (particles attach: 레고는).

| canonical | synonyms |
| --- | --- |
| science | science, experiments, experiment, stem, chemistry, physics, 과학, 실험 |
| space | space, planets, astronomy, rockets, 우주 |
| lego | lego, legos, bricks, 레고 |
| animals | animals, animal, nature, wildlife, documentaries, zoo, 동물, 자연 |
| toys | toys, toy, 장난감 |
| gaming | gaming, games, game, minecraft, roblox, 게임 |
| crafts | crafts, craft, diy, 만들기, 공예 |
| music | music, songs, 음악 |
| sports | sports, soccer, football, 스포츠, 운동 |
| cooking | cooking, baking, recipes, 요리 |
| cars | cars, vehicles, trucks, 자동차 |
| cartoons | cartoons, animation, 만화 |
| education | education, educational, learning, 교육 |
| unboxing | unboxing, unbox, haul, 언박싱 |
| challenges | challenges, challenge, 챌린지 |
| pranks | pranks, prank, 몰카, 장난 |
| horror | horror, scary, creepy, jumpscare, jump scares, jump scare, 공포, 무서운 |
| violence | violence, fights, fighting, 폭력, 싸움 |
| weapons | weapons, guns, knives, 무기 |
| shopping | shopping, 쇼핑 |

- `NEGATION = r"\b(no|not|never|nothing( with)?|don'?t( want)?|do not( want)?|avoid|without|ban|block|skip)\b|금지|안 ?돼|싫어|빼고|제외|말고"`. `FILLER = r"\b(please|absolutely|and|also|videos?|stuff|content|things?)\b"`.
- `topic_hits(text, words=None) -> list`: canonical words (default: all keys; pass `ALLOW_WORDS` to restrict) with a synonym in `text.lower()`, ordered by first appearance, deduped. No fuzzy matching. `# ponytail: typos are the LLM path's job; difflib.get_close_matches(cutoff=0.8) here if the fallback must fix them`.
- `parse_rules(rules_text) -> (allow, deny)`: pure, no LLM. Used by `judge()`, `eval.py`, the API default rules, and as the fallback. Steps: lowercase; `re.sub(r" except | but (not|no) ", ". no ", text)`; `" but "` -> `". "`; split on `[.,;!?\n]`; per non-empty clause: if `NEGATION` matches, deny gets `topic_hits(clause)` or, when there is no hit, the clause with `NEGATION` and `FILLER` removed and whitespace collapsed, if it is 1-3 words (`buy now`); else allow gets `topic_hits(clause, ALLOW_WORDS)` (a deny-vocabulary word in an allow clause is ignored). Dedupe keeping order. Empty allow -> `list(ALLOW_WORDS)` (a parent who only lists bans still gets a feed). `# ponytail: a deny clause keeps every topic hit, so "no toy unboxing" also denies toys; the LLM path is finer`.
- `ask_rules(rules_text) -> dict`: `ask(load_prompt("rules"), {"rules_text": rules_text})`, with the `pipeline.llm` import inside the function so a missing key is a caught `KeyError` at call time. Tests monkeypatch this name.
- `parse_rules_llm(rules_text) -> (allow, deny)`: `POOL = ThreadPoolExecutor(max_workers=2)`, `RULES_TIMEOUT = 5`. `out = POOL.submit(ask_rules, rules_text).result(timeout=RULES_TIMEOUT)`. Code decides: `allow` = for each string in `out["allow"]`, `topic_hits(item, ALLOW_WORDS)`; `deny` = for each string in `out["deny"]`, `topic_hits(item)` or, when no hit and the item is 1-3 words and at most 25 chars, the lowercased item. Both lists deduped and sorted by the first position in `rules_text.lower()` of any of the word's synonyms (or the phrase itself), unmatched last, so the LLM and fallback paths agree on chip order. Any exception (timeout, HTTP, `ValueError` from `parse_json`, `KeyError`, non-dict output, non-list fields) or an all-empty result -> `return parse_rules(rules_text)`. Empty allow with non-empty deny -> `ALLOW_WORDS`. `# ponytail: a timed-out call keeps running in the pool thread until the 20 s client timeout; nobody waits for it`.
- `kid_verdict(row, allow, deny)` in `judge.py`, replacing the Task 3 deny/allow lines: `found = set(topic_hits(title + " " + " ".join(topics)))`; `hide` if `any(d in found or d in title for d in deny)`; `hide` if `not set(allow) & found`. So deny `horror` hides topics `["scary"]`, `["jumpscare"]` and a "Creepy Toy Prank" title; allow `science` matches cached topics `["experiments"]`; a free phrase like `buy now` matches the title only. The cache is not rebuilt: `/feed`, `/parent/rules`, and `eval.py` call `kid_verdict` live.
- `prompts/rules.txt` (`{rules_text}` placeholder, filled by `llm.fill`):
```
You turn a parent's free-text rules for an 8-year-old's video feed into topic tags. You only propose. Code decides.
The parent may write in any language, with typos, with allow and deny mixed in one sentence.
Return ONLY this JSON, no prose:
{"allow": ["<topics the parent wants, only from: science, space, lego, animals, toys, gaming, crafts, music, sports, cooking, cars, cartoons, education>"],
 "deny": ["<topics the parent rejects, from the list above or: unboxing, challenges, pranks, horror, violence, weapons, shopping; when none fits, a 1-3 word English phrase for what they reject, e.g. buy now>"]}
Rules:
- Negations (no, not, never, avoid, don't want, except, nothing with, 금지, 안 돼) mean deny. "no toy unboxing" denies unboxing, not toys. "scary" and "jump scares" are horror.
- Topics the parent says are ok, fine, only, loved, or just lists go to allow. Translate other languages to the English tags.
- Never invent a topic the parent did not mention. Empty lists are fine.
Parent rules:
{rules_text}
```

- [ ] **Step 1: Write `tests/test_rules.py` first** (`from pipeline.rules import ...`; `pipeline.judge.DEMO_RULES` for the demo sentence). Fallback cases, exact tuples:
  1. `DEMO_RULES` -> `(["science","lego","animals"], ["unboxing","challenges","buy now"])`
  2. `"I'm ok with science and space stuff and lego. Please no toy unboxing videos, nothing scary, and no pranks"` -> `(["science","space","lego"], ["toys","unboxing","horror","pranks"])`
  3. `"only educational content, animals are fine, absolutely no horror or jump scares"` -> `(["education","animals"], ["horror"])`
  4. `"science"` -> `(["science"], [])`; `"lego, animals, space"` -> `(["lego","animals","space"], [])`
  5. `"과학 실험, 레고. 언박싱 금지"` -> `(["science","lego"], ["unboxing"])`
  6. `"I don't want pranks or challenges. Animals and cooking are great"` -> `(["animals","cooking"], ["pranks","challenges"])`
  7. `"everything except horror"` -> `(list(ALLOW_WORDS), ["horror"])`; `"lego is fine but no unboxing"` -> `(["lego"], ["unboxing"])`
  8. `"avoid violence and weapons; Minecraft and Roblox are ok"` -> `(["gaming"], ["violence","weapons"])`
  9. `""` and `"asdf qwerty"` -> `(list(ALLOW_WORDS), [])`
  `parse_rules_llm` cases (monkeypatch `pipeline.rules.ask_rules`): returns `{"allow":["science","scary","dinosaurs"],"deny":["jump scares","Buy Now","a long sentence that is not a phrase at all"]}` for the demo text -> `(["science"], ["horror","buy now"])`; raises `ValueError` -> equals `parse_rules(text)`; sleeps 1 s with `monkeypatch.setattr(rules, "RULES_TIMEOUT", 0.1)` -> equals `parse_rules(text)` and returns in under 0.5 s; `monkeypatch.delenv("INWORLD_API_KEY", raising=False)` with the real `ask_rules` -> equals `parse_rules(text)`. One live test, `skipif` no `.env` (same guard as `test_llm.py`): `parse_rules_llm(DEMO_RULES)` equals case 1 exactly.
  `kid_verdict` cases (import from `pipeline.judge`, reuse the `row()` helper shape from `test_judge.py`): topics `["science","experiments"]` with allow `["science"]` -> `"show"`; topics `["experiments"]` only -> `"show"`; topics `["scary"]` with deny `["horror"]` -> `"hide"`; title `"Creepy Toy Prank"` topics `["toys"]` allow `["toys"]` deny `["horror"]` -> `"hide"`; title `"Buy now before it ends"` topics `["science"]` deny `["buy now"]` -> `"hide"`.
  Run `pytest tests/test_rules.py` -> ImportError, as expected.

- [ ] **Step 2: Write `pipeline/rules.py` and `prompts/rules.txt`** as specified. `pytest tests/test_rules.py` -> all pass except the `kid_verdict` ones.

- [ ] **Step 3: Move `parse_rules` out of `judge.py`, change `kid_verdict`** as above; delete `TOPIC_WORDS`/`TOPIC_ALIAS`. `pytest tests/` -> everything green, `test_judge.py` untouched.

- [ ] **Step 4: API**: `POST /parent/rules` calls `parse_rules_llm`. Restart uvicorn and run the Step 2 POST curl of Task 5 with `rules_text` = case 2 above; expected `allow` contains `science`, `space`, `lego`, `deny` contains `unboxing`, `horror`, `pranks`, answer within 6 s. Then the Task 5 Step 4 key-removed check including the POST: same lists for the demo sentence, under 1 s.

- [ ] **Step 5: Commit** `git add pipeline/rules.py pipeline/judge.py prompts/rules.txt tests/test_rules.py api/main.py && git commit -m "rules: free-text parent rules, LLM proposes with rule-based fallback"`
