# SafeLens API spec (frontend contract)

For Cole. Your repo is `safelens-web`; mine is `safelens-api`. Build every screen against the JSON files in `mock/` (attached) this morning. They are the exact shapes the real API returns. When the API is up (target: early afternoon), change the base URL and nothing else.

Base URL: `https://safelens-api.onrender.com` (Jiwon will confirm the exact URL once deployed, early afternoon). Keep it in one config variable. CORS is open. Until then, use the mock files.

## Three screens, three calls

| Screen | Call | Mock file |
| --- | --- | --- |
| Parent setup | `POST /parent/rules` | `mock/parent_rules.json` |
| Kid feed | `GET /feed?age_band=kid&child_id=mia` | `mock/feed_kid.json` |
| Teen feed | `GET /feed?age_band=teen&child_id=mia` then `GET /video/{video_id}/lens` per card | `mock/feed_teen.json`, `mock/lens_*.json` |

## 1. POST /parent/rules

Request body:
```json
{ "child_id": "mia", "rules_text": "Science experiments, LEGO builds, animal documentaries. No unboxing, no challenges, nothing with buy now." }
```

Response: `allow` and `deny` are the parsed rules (show them as chips). `queue` is every video the AI considered, with a `verdict`:
- `show` → goes into the kid feed as-is
- `approve` → show in the parent's list with the orange "needs your call" badge and the `note`; parent can remove or keep
- `hide` → do not show in the queue at all (or show a count: "N hidden")

`match` is 0–100. Sort the queue by match, descending.

## 2. GET /feed?age_band=kid|teen&child_id=mia

- `age_band` comes from k-ID: age < 13 → `kid`, 13–17 → `teen`. Until k-ID is wired, a dropdown with the three k-ID test personas sets it.
- `kid` returns only `verdict: "show"` items. No lens, no search, no autoplay, no comments.
- `teen` returns `show` and `flag` items. `flag` items get a small "flagged to parent" mark on the card. Every teen item has `lens_available: true`.
- `blocked_count` is for a one-line footer ("12 videos were kept out of this feed") and for the parent dashboard.

## 3. GET /video/{video_id}/lens  (teen only)

This drives the quiz:
1. Show the card with `quiz_options` as 4 chips. The teen picks any number.
2. On "Check my answer", reveal `tactics` (each: `label`, `evidence`, `reason`) and the `reality_check` box.
3. Score in the frontend:
   - correct = chosen ∩ {t.label for t in tactics}
   - false alarms = chosen − {t.label for t in tactics}
   - text: "You caught {correct} of {len(tactics)}" plus " (1 false alarm)" when false alarms > 0
4. `evidence` is a verbatim quote from the video's title, description, or captions. Show it in quotes. Never paraphrase it.

Label display names:

| label | show as |
| --- | --- |
| fake_urgency | Fake urgency |
| hidden_ad | Hidden ad |
| body_image_pressure | Body-image pressure |
| engagement_bait | Engagement bait |
| misleading_thumbnail | Misleading thumbnail |
| fake_social_proof | Fake social proof |

`signals` is optional context (age_limit, upload_days_ago, voice_emotion). Safe to ignore in the UI.

## Errors

- Missing or invalid `age_band` → 400
- Unknown `video_id` → 404
- Anything else → 500 with `{ "error": "..." }`. Show a quiet toast and keep the mock data on screen.

## What the demo must show (2 minutes)

1. Parent setup: type rules → queue appears → remove one "needs your call" → Publish
2. Switch persona to kid → kid feed
3. Switch persona to teen → same pool, teen feed → open the Tesla giveaway card → pick chips → Check my answer → reveal + reality check → "You caught 2 of 3"
4. One line of numbers from Jiwon's eval at the end

Mockup screens are the reference for look and flow; improve the design freely, keep the flow.
