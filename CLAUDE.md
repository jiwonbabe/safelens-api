# SafeLens

One video pool, three feeds by age. A kid (8) gets a feed their parent picked. A teen (15) gets the same pool plus a "lens" that shows how each video tries to hook them, so they learn to spot it instead of having it blocked. Built in one day at the k-ID Build for Everyone hackathon (Oct 21, 2026).

Judges score five things: adapts by age, real use of k-ID and partner tools, it works live, people would use it, ambition. Every decision below serves those five.

## Non-negotiable principles

1. **The LLM proposes, code decides.** The model returns label candidates with a verbatim quote as evidence. `judge.py` keeps a label only if the quote is literally present in the video's title, description, or captions, and only if it passes that label's rule. Nothing a teen sees is written by the model alone.
2. **Fixed label set.** Exactly six labels. Never add, rename, or merge one during the build.
3. **Precompute everything.** The API serves cached results. No live LLM call on the demo path.
4. **Lanes do not cross.** Frontend lives in a separate repo (`safelens-web`, Cole). This repo is API, pipeline, prompts, data, tests only. If the frontend needs a change in the response shape, update the contract here and tell Cole; never patch around it.
5. **No code before 10:20 AM Oct 21.** This file, prompts as text, data, and tests/gold.json are allowed before that. Source files are not.

## Lanes

| Lane | Owner | Files | Never touches |
| --- | --- | --- | --- |
| A. Pipeline + API | Jiwon | this repo (`safelens-api`): `api/`, `pipeline/`, `prompts/`, `cache/`, `data/` | the frontend repo |
| B. Screens + pitch | Cole | separate repo `safelens-web` plus the deck | this repo; response shapes |
| C. Verification | gold set + eval | `tests/gold.json`, `eval.py` | frozen after 10:30 AM; never edited to make a score look better |

The contract between A and B is the JSON in "API contract" below, also shipped to Cole as `API_SPEC.md` + `mock/*.json`. The frontend builds against those mock files and swaps to the real API with one URL change. Never create a `frontend/` folder in this repo.

## Labels (fixed)

| Label | Meaning | Rule in judge.py, applied after the quote check |
| --- | --- | --- |
| fake_urgency | false time pressure | quote matches a pattern like "N hours left", "last chance", "ends tonight", "only today" |
| hidden_ad | creator earns from your purchase and does not say so | a monetized link or code is present (discount code, amzn.to, bit.ly, "link in bio", t.me) AND no disclosure word anywhere ("ad", "sponsored", "paid partnership", "affiliate", "commission", "I earn"). If a disclosure word exists, the label is dropped. |
| body_image_pressure | makes your body a problem to fix fast | a number + a time span about weight, skin, or muscle ("10 lb in 5 days", "glass skin in 7 days", before/after) |
| engagement_bait | asks for likes, comments, or shares with pressure | "like in 3 seconds", "comment or", "share this or", "subscribe or" |
| misleading_thumbnail | title or thumbnail claims what the content does not deliver | needs two quotes: the claim in the title and a contradicting line in the captions; LLM-proposed only |
| fake_social_proof | invented popularity | "millions use", "everyone is", "best selling", "100% results", numbers with no source |

Emotional pressure from Modulate (voice emotion) is NOT a label. It is a helper signal judge.py may use to confirm fake_urgency or body_image_pressure.

## Verdicts by age band

Teen (15):
- `show`: no labels, or labels the Lens can explain (any of the six)
- `flag`: shown in full with the Lens plus a "flagged to parent" mark. Two reasons: strong body_image_pressure (number + span) or a health product with no disclosure; or a concern category with nothing to learn from the hooks alone: gambling-like (loot boxes, skin betting), violence glorification (fight compilations), substance glorification (vaping, drinking, SARMs), weapons with buy links, private-contact recruiting (t.me, "DM me"), manosphere clips, reckless driving. A flagged video is never hidden from the teen: the Lens explains what is wrong with it and what to keep in mind while watching (`concern` in the lens response). Decided 10:55 Oct 21: blocking a teen only pushes them to another app; explaining keeps them here.
- `block`: only YouTube `age_limit >= 18` (YouTube itself refuses to play these without sign-in). Nothing in the current pool.

Kid (8):
- `show`: matches parent rules AND channel on the trusted list AND no labels
- `approve`: matches parent rules but has a commercial hook (unboxing, product name without disclosure, clickbait title) or an untrusted channel; hidden from the kid, sent to the parent queue as "needs your call"
- `hide`: does not match parent rules, or any teen `flag`/`block` category, or horror, jump scares, scary stories, Elsagate-style costumed-character content, pranks that make a child cry, strong language

Block/hide decisions come from `judge.py` rules over text signals plus the LLM's category proposal. Frame analysis is out of scope; say so if asked.

## API contract

Base URL during the day: `http://localhost:8000`. CORS open.

### POST /parent/rules
Request:
```json
{ "child_id": "mia", "rules_text": "Science experiments, LEGO builds, animal documentaries. No unboxing, no challenges, nothing with buy now." }
```
Response:
```json
{
  "child_id": "mia",
  "allow": ["science", "lego", "animals"],
  "deny": ["unboxing", "challenges", "buy now"],
  "queue": [
    { "video_id": "wfnsRi8Jgdw", "title": "The Great Elephant Toothpaste Experiment!", "channel": "SciShow Kids", "thumbnail": "https://i.ytimg.com/vi/wfnsRi8Jgdw/hqdefault.jpg", "topics": ["science"], "match": 96, "verdict": "show", "note": null },
    { "video_id": "_p-10Dnytgw", "title": "School/Science Project - Water Wheel || Tinker Crate by KiwiCo", "channel": "Matt Creationz", "thumbnail": "https://i.ytimg.com/vi/_p-10Dnytgw/hqdefault.jpg", "topics": ["science"], "match": 88, "verdict": "approve", "note": "Names a product (KiwiCo) with no disclosure" }
  ]
}
```

### GET /feed?age_band=kid|teen&child_id=mia
Response:
```json
{
  "age_band": "teen",
  "items": [
    { "video_id": "_OxuxhHF1WI", "title": "Last Chance to Win This $30,000 Tesla Model X - Giveaway Ends Tonight at Midnight", "channel": "Auto Auction Rebuilds", "thumbnail": "https://i.ytimg.com/vi/_OxuxhHF1WI/hqdefault.jpg", "views": 1200000, "verdict": "show", "lens_available": true },
    { "video_id": "3kdnLb-fdrY", "title": "How I lost 20 pounds in 2 weeks on a low budget", "channel": "Nkemamaka Ike", "thumbnail": "https://i.ytimg.com/vi/3kdnLb-fdrY/hqdefault.jpg", "views": 54000, "verdict": "flag", "lens_available": true }
  ],
  "blocked_count": 0
}
```
For `age_band=kid` only `verdict: "show"` items are returned. For `age_band=teen` every `show` and `flag` item is returned (the whole pool unless `age_limit >= 18`). `blocked_count` is for the parent dashboard.

### GET /video/{video_id}/lens
Response:
```json
{
  "video_id": "_OxuxhHF1WI",
  "verdict": "show",
  "tactics": [
    { "label": "fake_urgency", "evidence": "Giveaway Ends Tonight at Midnight", "reason": "\"Ends tonight\" has been on this video for 3 weeks. It is there so you do not stop to think." },
    { "label": "fake_social_proof", "evidence": "$30,000 Tesla", "reason": "A big prize makes the offer feel real. The video never shows a winner." }
  ],
  "quiz_options": ["fake_urgency", "hidden_ad", "body_image_pressure", "fake_social_proof"],
  "reality_check": "Nobody gives away a $30,000 car for a click. The link collects your email and phone so they can sell to you later.",
  "concern": null,
  "signals": { "age_limit": 0, "upload_days_ago": 21, "voice_emotion": "excited" }
}
```
`concern` is `null` for a plain `show`. For a `flag` with a concern category it is `{ "category": "violence_glorification", "evidence": "HOOD FIGHTS 2024 & STREET FIGHTS", "reason": "Real people get hurt in these clips. The channel earns from every view, so it needs you to feel the fight is entertainment." }`. The frontend shows it above the tactics as "What is wrong with this video".

`quiz_options` always has 4 labels: every correct one plus random distractors from the six. Scoring is done in the frontend: correct = chosen ∩ tactics.labels, false alarms = chosen − tactics.labels.

### Age signal
k-ID gives age and jurisdiction. The frontend passes `age_band` derived from it (`< 13` → kid, `13–17` → teen). If k-ID is not wired, a dropdown with the three k-ID test personas sets it. The API never trusts a raw age from the client.

## Partner APIs (verified from docs, Oct 21)

Inworld (LLM, OpenAI-compatible):
- `POST https://api.inworld.ai/v1/chat/completions`, header `Authorization: Basic $INWORLD_API_KEY` (send the key as-is, do not base64 it again).
- Body follows OpenAI chat completions: `{"model": INWORLD_MODEL, "messages": [...]}`. Text is at `choices[0].message.content`.
- Model ids look like `openai/gpt-5.4`; pick one from inworld.ai/models (Text tab) and set `INWORLD_MODEL` in `.env`.
- With the `openai` package: `OpenAI(base_url="https://api.inworld.ai/v1", api_key="unused", default_headers={"Authorization": f"Basic {key}"})`.
- Backup provider: plain OpenAI with `OPENAI_API_KEY` when `LLM_PROVIDER=openai`.

Modulate (voice):
- Transcription: `POST https://platform.modulate.ai/api/velma-2-stt-batch`, header `X-API-Key: $MODULATE_API_KEY`, multipart field `upload_file`. Response: `text`, `duration_ms`, `utterances[]` (each has `text`, `start_ms`, `speaker`, `language`).
- Emotion: `POST https://platform.modulate.ai/api/velma-2-emotion-batch`, same auth and field. Response: `emotion` (Angry, Disgusted, Afraid, Happy, Neutral, Other, Sad, Surprised, Unknown) plus `time_series`.
- Send a 5 to 30 second clip: cut the first 30 s with `ffmpeg -i in.mp3 -t 30 -c copy out.mp3`. Max 100 MB.
- Map emotion to the lens `signals.voice_emotion`: Surprised or Happy with high energy → "excited", Afraid or Angry → "pressured", else "calm". Judge may use "excited"/"pressured" only to confirm fake_urgency or body_image_pressure, never to add a label.

k-ID:
- Sign-up link and two setup steps are posted the morning of the event in the participant Discord #general and on the event page. Three starter kits and three test personas. On-site support is web and Android. Read the starter kit at 9:30; wire the age signal into `/feed` after 12:00.

## Code style

- Plain Python classes and functions. No dataclass, namedtuple, Enum, or Protocol.
- Easy English names: `video`, `label`, `evidence`, `reason`, `verdict`. Not `tactic_enum`, `evid`.
- Same shape everywhere: a function that takes a `video` dict returns a dict. Helpers for anything used twice.
- FastAPI + SQLite (one table `lens_cache(video_id TEXT PRIMARY KEY, json TEXT)`). No ORM.
- `.env` keys: `LLM_PROVIDER`, `INWORLD_API_KEY`, `INWORLD_MODEL`, `OPENAI_API_KEY`, `MODULATE_API_KEY`.
- Prompts live in `prompts/*.txt`, never inline in Python. They are already written: `topics.txt` (parent rules match + kid risk), `lens.txt` (teen tactics + concern category + reality check), `bait_writer.txt` (adversarial loop). Fill the `{placeholders}` with str.format-style substitution; the LLM must return JSON only.
- Demo picks: `_OxuxhHF1WI` (Tesla giveaway, fake_urgency), `YjIA7HJXFg0` (Skinny Teatox, body_image_pressure), `HgjRJAh9kME` (Flat Tummy Tea, hidden_ad candidate). Verify hidden_ad on the third after reading its description.

## Deploy (Render, free tier)

- `render.yaml` and `requirements.txt` are in the repo. Connect the GitHub repo in the Render dashboard once; every push to main redeploys.
- The API serves only from `cache/lens.sqlite`, so **commit the cache** (it is not in .gitignore). Render needs no LLM key to serve the demo.
- Public URL: `https://safelens-api.onrender.com` (Render assigns the exact name; copy it from the dashboard and send it to Cole).
- Free tier sleeps after 15 min idle and takes ~30 s to wake. Open `/feed?age_band=teen&child_id=mia` in a browser 10 minutes before judging.
- Deploy after step 4 passes `/eval`, not before. Verify with `curl https://<url>/feed?age_band=kid&child_id=mia`.
- If Render is down at demo time: `uvicorn api.main:app --host 0.0.0.0 --port 8000` plus `ngrok http 8000`, send Cole the ngrok URL.

## Commands

```bash
source .venv/bin/activate
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000   # 0.0.0.0 so Cole's laptop can reach it on the hotspot
ngrok http 8000                       # only if the frontend is served over https
python pipeline/build_pool.py        # data/raw -> data/videos.json
python pipeline/run_lens.py          # LLM proposals -> judge -> cache
python eval.py                       # accuracy vs tests/gold.json
python pipeline/loop.py --rounds 3   # adversarial loop (afternoon only)
```

## Failure conditions and fallbacks

| If | Then |
| --- | --- |
| Inworld LLM slow, rate limited, or down | Cache is already built; demo never calls it live. If the cache is not built by 12:00, switch `LLM_PROVIDER` in `.env` to the backup key and run `run_lens.py` on the 10 gold videos only. |
| Modulate transcript or emotion fails | Use YouTube auto-captions; `voice_emotion` becomes `null`. Cut line 1:30 PM. |
| k-ID SDK not integrable by 2:00 PM | Persona dropdown in the frontend. Say on stage where the SDK plugs in. |
| Judge drops every label on a demo video | Check the quote matching first (case, punctuation). Loosen to case-insensitive substring. Never hardcode a label. |
| Frontend not on the real API by 3:00 PM | Frontend keeps its mock JSON (same shapes). The demo still runs. |
| Venue wifi dies or blocks device-to-device traffic | Phone hotspot for both laptops. API on `--host 0.0.0.0`; Cole points at `http://<Jiwon IP>:8000`, or `ngrok http 8000` if the frontend is on https. Demo runs on one laptop regardless. |
| Laptop dies | Backup screenshots of every screen are in `deck/`. |
| Adversarial loop not working by 3:00 PM | Drop it. One slide describing the design. |

Code freeze at 3:45 PM. After that only `deck/` changes. Submit by 4:00 PM.

## Timeline (Oct 21)

| When | Lane A (Jiwon) | Lane B (Cole) |
| --- | --- | --- |
| 9:30–10:20 | Confirm track (Consumer AI). k-ID sign-up link from Discord #general. Read starter kit. | Open mockup in the frontend tool. |
| 10:20–12:00 | Repo, `build_pool.py`, `run_lens.py` via Inworld, `judge.py`, cache. | Parent setup + kid feed on mock JSON. Show Jiwon at 12:00. |
| 12:00–2:00 | k-ID age → `/feed`. Modulate on the 3 demo videos. First real call together. | Teen feed: chips, check, reveal, reality check, score. k-ID personas. |
| 2:00–3:30 | Adversarial loop 3 rounds, `eval.py` number, TTS if time. | Real API URL. Deck + 2-minute script. |
| 3:30–4:30 | Freeze 3:45. Run demo 3 times with 3 personas. | Screenshots into deck. Rehearse. Submit 4:00. |
