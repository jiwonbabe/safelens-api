# Lane A 빌드 (파이프라인 + judge + API) 실행 계획 (한국어판)

> 원문: `2026-10-21-lane-a-build.md`. 실행 에이전트는 영어판을 기준으로 삼고, 이 문서는 사람이 읽기 위한 번역본이다. 두 문서가 다르면 영어판이 우선한다.

**목표:** `data/raw/*`에서 출발해 "LLM이 제안하고 코드가 결정하는" 파이프라인으로 `cache/lens.sqlite`를 만들고, 계약에 적힌 세 엔드포인트를 그 캐시만으로 서빙한다.

**구조:** `build_pool.py`가 yt-dlp 원본을 `data/videos.json`으로 바꾼다. `run_lens.py`가 영상마다 Inworld를 두 번 호출하고(`topics.txt`, `lens.txt`) 두 제안을 `judge.py`에 넘긴다. judge는 인용이 원문에 있는 라벨만 남기고 판정을 내려 SQLite에 영상당 JSON 한 행을 쓴다. `api/main.py`는 SQLite만 읽고 LLM을 절대 부르지 않는다. `judge.kid_verdict`는 순수 함수라 `/parent/rules`가 새 부모 규칙으로 캐시된 풀을 LLM 없이 다시 채점할 수 있다.

**기술:** Python 3.12, FastAPI + uvicorn, sqlite3(표준 라이브러리), Inworld를 가리키는 `openai` 클라이언트, `python-dotenv`. `tests/` 폴더 없음(FIRST_PROMPT). 모듈마다 `__main__` 자체 점검을 둔다.

**스펙:** `CLAUDE.md`(원칙, 라벨, 판정, API 계약), `FIRST_PROMPT.txt`(파일 목록과 순서). 프롬프트: `prompts/topics.txt`, `prompts/lens.txt`.

> **10:55 변경 (지원):** 틴은 절대 차단하지 않는다. `teen_verdict`는 `show`/`flag`만 반환(`block`은 `age_limit >= 18`일 때만). 옛 차단 카테고리는 `flag`가 되고 `judge.concern_of`가 만든 `concern` 객체 `{category, evidence, reason}`이 캐시 행에 저장되며(`block_category` 대체) `/video/{id}/lens`가 `concern`으로 돌려준다(일반 show는 null). `/feed?age_band=teen`은 풀 전체를 반환하고 `blocked_count`는 18+만 센다. `lens.txt` 필드는 `concern_category`, `concern_evidence`, `concern_reason`으로 이름이 바뀌었다. gold: 틴 `block` 12행이 `flag`로 바뀌었고 eval의 teen block 셀은 비게 된다.

## 전역 제약

- LLM은 제안만, 코드가 결정. evidence가 `title + description + captions`의 대소문자 무시 부분 문자열이 아니면 라벨을 버린다.
- 라벨은 정확히 여섯 개: `fake_urgency, hidden_ad, body_image_pressure, engagement_bait, misleading_thumbnail, fake_social_proof`.
- 전부 미리 계산. `api/` 안에서 LLM 호출 금지.
- 응답 형태는 CLAUDE.md 계약 그대로. 필드 추가·삭제·이름 변경 금지.
- 평범한 클래스와 함수만. dataclass, namedtuple, Enum, Protocol 금지. 쉬운 영어 이름.
- 프롬프트는 `prompts/*.txt`에만. 치환은 키별 replace(템플릿 안에 JSON 리터럴 `{}`가 있어 `str.format`은 터진다).
- `frontend/`, `tests/` 만들지 않음. `tests/gold.json` 수정 금지.
- SQLite 테이블 하나: `lens_cache(video_id TEXT PRIMARY KEY, json TEXT)`.
- `.env` 키: `LLM_PROVIDER, INWORLD_API_KEY, INWORLD_MODEL, OPENAI_API_KEY, MODULATE_API_KEY`. 동작 확인된 모델: `openai/gpt-4o-mini`.
- 데모 영상(오늘 갱신): `_OxuxhHF1WI`(fake_urgency), `YjIA7HJXFg0`(hidden_ad + body), `jZumiXIiCWE`(hidden_ad, HgjRJAh9kME 대체).

## 리뷰 초점

1. 원문과 공백·줄바꿈이 다른 evidence(자막은 공백으로 합쳐지고 설명란엔 줄바꿈이 있다): 인용 검사는 양쪽 공백을 정규화해야 한다. 안 그러면 진짜 라벨이 떨어진다. Task 3 자체 점검에 고정.
2. 자막에만 등장하는 밝힘 단어(말로 "an ad"라고 한 경우): 밝힘 검사는 verifier와 같이 제목 + 설명란에서만. Task 3에 고정.
3. LLM이 ```json 펜스나 뒤에 잡담을 붙여 줄 때: `llm.ask`는 펜스를 벗긴 뒤 `json.loads`하고, 그 외엔 예외. Task 2에 고정.
4. LLM 호출이 실패한 영상도 행은 있어야 한다(규칙만으로 판정, tactics 빈 배열). `/feed`에 구멍이 생기면 안 된다. Task 4에 고정.
5. `age_band`가 없거나 {kid, teen} 밖이면 400. 키즈 피드를 돌려주면 안 된다. Task 5에 고정.

지원 님이 정할 것(Task 1~2는 막지 않음): `tm9Xfv6wpN4`(사과식초, 제목에 "WEIGHT LOSS", 체중감량 플랜 판매, 밝힘 없음)는 gold에서 `show`인데 아래 flag 규칙은 `flag`로 판정한다. CLAUDE.md는 flag를 "밝힘 없는 건강 제품"으로 정의하므로 규칙이 맞고 gold가 틀렸다고 볼 수 있다. 10:30 동결 전에 결정. 아니면 미스 1건을 감수한다.

빠진 파일: `eval.py`가 없다. FIRST_PROMPT는 builder가 건드리지 말라고 했으므로 Task 6은 지원 님이 허락한 뒤에만 쓴다.

---

### Task 1: `pipeline/build_pool.py`

**파일:**
- 생성: `pipeline/__init__.py`(빈 파일), `pipeline/build_pool.py`
- 출력: `data/videos.json`

**인터페이스:**
- 생산: `data/videos.json` = 키가 정확히 `id, url, title, channel, channel_follower_count, description, thumbnail, upload_date, view_count, age_limit, captions, audio_file`인 dict의 리스트. `.en.vtt`가 없으면 `captions`는 `""`. `audio_file`은 `data/audio/<id>.mp3`가 있으면 그 경로, 없으면 `null`. `thumbnail` = `https://i.ytimg.com/vi/<id>/hqdefault.jpg`.
- 생산: `load_videos() -> list[dict]`(`data/videos.json` 읽기), `video_text(video) -> str`(`title + "\n" + description + "\n" + captions`를 소문자화하고 공백을 하나로 접은 문자열). 뒤 태스크들이 import한다.
- 생산: `clean_vtt(text: str) -> str`: `WEBVTT`/`Kind:`/`Language:` 헤더, 타임스탬프 줄(`-->`), `<...>` 태그, 빈 줄, 직전에 남긴 줄과 같은 줄을 버리고 공백 하나로 잇는다.

- [ ] **1단계: `clean_vtt`, `video_text`, `load_videos`, `main()` 작성.** `main()`은 `data/raw/*.info.json`을 글롭해 dict를 만들고 `data/videos.json`(indent 1, ensure_ascii False)을 쓰고 `loaded N videos, M with captions`를 출력.
- [ ] **2단계: `main()` 앞에 `__main__` 자체 점검 추가**: `assert clean_vtt("WEBVTT\n\n00:00.000 --> 00:01.000\n<c>hi</c> there\nhi there\n\nnext") == "hi there next"`, `assert "elephant toothpaste" in video_text({"title":"The Great Elephant Toothpaste","description":"","captions":""})`.
- [ ] **3단계: 실행** `python pipeline/build_pool.py` → 기대: `loaded 56 videos, 45 with captions`, `data/videos.json` 생성.
- [ ] **4단계: 형태 확인**: `python -c "import json;v=json.load(open('data/videos.json'));print(sorted(v[0]))"`가 위 12개 키를 출력.
- [ ] **5단계: 커밋** `git add pipeline data/videos.json && git commit -m "pipeline: build_pool from raw yt-dlp output"`

---

### Task 2: `pipeline/llm.py`

**파일:** 생성 `pipeline/llm.py`

**인터페이스:**
- 생산: `ask(prompt_text: str, fields: dict) -> dict`. `fields`의 키마다 `prompt_text`의 `{key}`를 `replace("{"+key+"}", str(value))`로 채운다. `LLM_PROVIDER`(기본 `inworld`, 백업 `openai`)가 가리키는 공급자를 `timeout=20`, `max_retries=0`, `temperature=0`으로 호출. 앞의 ```json / ``` 펜스와 뒤의 ```를 벗긴 뒤 `json.loads`. HTTP 오류, 타임아웃, JSON 파싱 실패는 그대로 예외(내부에서 잡지 않음).
- 생산: `load_prompt(name: str) -> str`는 `prompts/<name>.txt`를 읽는다.
- 소비: `dotenv.load_dotenv()`로 `.env`.

클라이언트 생성(CLAUDE.md): `OpenAI(base_url="https://api.inworld.ai/v1", api_key="unused", default_headers={"Authorization": f"Basic {key}"}, timeout=20, max_retries=0)`. `openai` 공급자는 `OpenAI(api_key=OPENAI_API_KEY, timeout=20, max_retries=0)`에 모델 `gpt-4o-mini`.

- [ ] **1단계: `load_prompt`, `ask`, `__main__` 자체 점검 작성.** 리터럴 ```` ```json\n{"ok": true}\n``` ````을 같은 파싱 헬퍼에 넣어 펜스 제거를 assert하고, `ask('Return ONLY {"ok": true}. Ignore: {title}', {"title": "x"})`를 호출해 dict를 출력.
- [ ] **2단계: 실행** `python pipeline/llm.py` → 기대: `{'ok': True}`, 트레이스백 없음.
- [ ] **3단계: 자막 상한 확인**: `ask`는 12000자를 넘는 필드 값을 자른다(46분짜리 Amazon 영상이 약 6천 단어). `# ponytail: hard cap, chunking if a label hides past 12k chars` 주석.
- [ ] **4단계: 커밋** `git add pipeline/llm.py && git commit -m "pipeline: llm.ask for inworld/openai"`

---

### Task 3: `pipeline/judge.py`

**파일:** 생성 `pipeline/judge.py`

**인터페이스:**
- 소비: Task 1의 `video_text(video)`.
- 생산: `judge(video, proposal) -> {"tactics": [...], "verdict_teen": str, "verdict_kid": str, "concern": dict | None, "kid_risk": str, "commercial_hook": str | None, "topics": list, "match": int}`. `proposal = {"lens": <lens.txt JSON 또는 {}>, "topics": <topics.txt JSON 또는 {}>}`. 남긴 tactic은 제안 그대로 `{"label", "evidence", "reason"}`.
- 생산: `kid_verdict(row, allow: list, deny: list) -> str`(순수 함수, API도 사용). `row`는 Task 4의 캐시 행(`title, channel, topics, match, tactics, verdict_teen, kid_risk, commercial_hook` 필요).
- 생산: `parse_rules(rules_text: str) -> (allow, deny)`(순수, LLM 없음). 문장은 `.`로, 구는 `,`로 나눈다. `no ` / `nothing with `로 시작하는 구는 접두어를 떼고 `deny`로. 나머지는 `TOPIC_WORDS = ["science","lego","animals","animal","toys","gaming","games","horror","pranks","crafts","music","sports","cooking","unboxing","challenges"]`에 있는 첫 단어를 `allow`로(`animal`→`animals`, `games`→`gaming`), 없으면 구 전체를 소문자로. 데모 문장은 `allow=["science","lego","animals"]`, `deny=["unboxing","challenges","buy now"]`가 나와야 한다.
- 생산: `TRUSTED_CHANNELS = ["SciShow Kids", "Nat Geo Kids", "LEGO"]`, `LABELS`(여섯 개), `DISCLOSURE = r"\b(ad|ads|sponsored|paid partnership|affiliate|commission|i earn)\b"`.

규칙(`text` = `video_text(video)`; `head` = 소문자 제목 + 설명란, 공백 정규화; `title` = 소문자 제목):

| 라벨 | 남기는 조건 |
| --- | --- |
| 공통 | `collapse(evidence).lower() in text`, 아니면 버림 |
| fake_urgency | evidence가 `\d+ ?(hours?|minutes?|days?) left|last chance|ends tonight|only today|ends at midnight|hurry`에 매칭 |
| hidden_ad | `head`가 `amzn\.to|bit\.ly|link in bio|t\.me|discount code|promo code|use (the )?code|code [a-z0-9]{3,}|\d+% off`에 매칭 AND `head`에 `DISCLOSURE` 매칭 없음 |
| body_image_pressure | evidence가 `\d+ ?(lb|lbs|pounds|kg|days?|weeks?|months?)` 또는 `before (and|&) after` 또는 `glass skin`에 매칭 |
| engagement_bait | evidence가 `like in \d|comment or|share this or|subscribe or|or else`에 매칭 |
| misleading_thumbnail | `collapse(evidence).lower() in title` AND `collapse(reason).lower() in captions` |
| fake_social_proof | evidence가 `millions use|everyone is|everyone's|best selling|100%|#1|no\.? ?1`에 매칭하거나 숫자를 포함 |

우려(concern) (`concern_of(video, lens) -> dict | None`; `lens` 제안의 `concern_category`, `concern_evidence`, `concern_reason`):
- `concern_category != "none"`이고 `concern_evidence`가 인용 검사를 통과하면 `{category, evidence, reason}`. 아니면 `head`가 `CONCERN_WORDS` 중 하나에 매칭될 때(`private_contact_recruiting: t\.me|dm me`, `gambling_like: gambling|case opening|loot box`, `substance_glorification: vape|sarms|getting drunk`, `violence_glorification: street fights?|hood fights?|fight compilation`, `manosphere: andrew tate`, `reckless_driving: street takeover|sideshow`, `weapons_with_links: switchblade|karambit`) 매칭된 단어를 evidence로. 둘 다 아니면 `None`. `reason`은 LLM의 `concern_reason` 또는 `""`.

틴 판정(`age_limit`은 영상에서). 틴에게 벽은 없다. 우려는 설명이 된다:
- `block`: `age_limit >= 18`일 때만(YouTube가 어차피 재생을 막음). 현재 풀에는 없음.
- 아니면 `flag`: `concern_of(...)`가 None이 아니거나, `title`이 `\d+ ?(lb|lbs|pounds|kg)\b.{0,20}\b\d+ ?(day|days|week|weeks)\b`에 매칭하거나, (`hidden_ad`가 남았고 `title`이 `weight loss|fat loss|fat burn`에 매칭).
- 아니면 `show`.

키즈 판정 `kid_verdict(row, allow, deny)`:
- `hide`: `row["verdict_teen"] in ("flag","block")`, 또는 `row["kid_risk"] != "none"`, 또는 deny 단어가 `title`이나 `row["topics"]`에 등장, 또는 `allow`와 `row["topics"]`의 교집합이 없음.
- 아니면 `approve`: `row["commercial_hook"]`이 non-null(훅 evidence가 인용 검사 통과), 또는 `row["tactics"]`가 비어 있지 않음, 또는 `row["channel"] not in TRUSTED_CHANNELS`.
- 아니면 `show`.

`judge()`는 `kid_risk` = topics 제안의 `kid_risk.category`(evidence가 인용 검사 통과 시) 아니면 `"none"`, `commercial_hook` = `present`이고 인용 통과 시 훅 evidence 문자열 아니면 `None`, `verdict_kid = kid_verdict(row, *parse_rules(DEMO_RULES))`로 계산한다. `DEMO_RULES`는 CLAUDE.md 데모 문장.

- [ ] **1단계: `judge.py` 작성**: 상수, `quote_ok(evidence, text)`, `head_of(video)`, `keep_tactic(tactic, video)`, `concern_of(video, lens)`, `teen_verdict(video, tactics, lens)`, `kid_verdict`, `parse_rules`, `judge`. (`collapse`는 `build_pool`에서 import.)
- [ ] **2단계: `__main__` 자체 점검 추가**(가짜 영상은 `title/description/captions/channel/age_limit`를 가진 dict):
  - 제목 `"Giveaway Ends Tonight at Midnight"`에 대해 evidence `"Giveaway  Ends\nTonight"`가 `fake_urgency`로 남는다(공백 정규화).
  - 설명란 `"use code SAVE10 … commission"`의 `hidden_ad`는 버려지고, 설명란 `"use code SAVE10"` + 자막 `"this is not an ad"`는 남는다(자막은 밝힘으로 안 침).
  - 원문에 없는 evidence는 라벨과 무관하게 버려진다.
  - 라벨 `"spam"`은 버려진다.
  - 제목 `"LOSE 10 POUNDS IN 3 DAYS"` → `verdict_teen == "flag"`, 제목 `"Best Vape Tricks"` → `"flag"`이고 `concern.category == "substance_glorification"`, LLM 카테고리에 검증 안 된 인용 + 키워드 없음 → `"show"`, `age_limit 18` → `"block"`.
  - `parse_rules(DEMO_RULES) == (["science","lego","animals"], ["unboxing","challenges","buy now"])`.
  - 훅 없는 SciShow Kids 과학 행의 `kid_verdict` → `"show"`, 같은 행에 채널 `"Matt Creationz"` → `"approve"`, topics `["horror"]` → `"hide"`.
- [ ] **3단계: 실행** `python pipeline/judge.py` → 기대: `judge self-check ok`.
- [ ] **4단계: 커밋** `git add pipeline/judge.py && git commit -m "pipeline: judge rules over LLM proposals"`

---

### Task 4: `pipeline/run_lens.py` → `cache/lens.sqlite`

**파일:** 생성 `pipeline/run_lens.py`, `pipeline/cache.py`. 출력 `cache/lens.sqlite`.

**인터페이스:**
- 소비: `load_videos`, `video_text`(Task 1); `ask`, `load_prompt`(Task 2); `judge`, `LABELS`(Task 3).
- 생산(`pipeline/cache.py`): `open_db(path="cache/lens.sqlite")`(테이블 없으면 생성), `put(db, video_id, row)`, `get(db, video_id) -> dict | None`, `all_rows(db) -> list[dict]`.
- 생산: 영상당 캐시 행 한 개. 키: `video_id, title, channel, thumbnail, views, upload_date, age_limit, topics, match, commercial_hook, kid_risk, tactics, verdict_teen, verdict_kid, concern, reality_check, quiz_options, signals, llm_error`. `signals = {"age_limit", "upload_days_ago"(upload_date와 오늘 차이), "voice_emotion": null}`. `quiz_options` = 남긴 라벨 + `LABELS`에서 뽑은 오답으로 4개, `random.Random(video_id)`로 섞음. `reality_check` = lens 제안 문자열, LLM 실패 시 `""`. `llm_error` = 오류 문자열 또는 `null`.
- CLI: `python pipeline/run_lens.py [--only id1,id2] [--force]`. 이미 캐시된 영상은 `--force` 없으면 건너뜀. `concurrent.futures.ThreadPoolExecutor(max_workers=6)`. 영상마다 topics 호출(`rules_text = DEMO_RULES`), lens 호출(`upload_date`, `view_count`에 더해 프롬프트가 기대하는 사실 3개: `upload_days_ago`(정수), `has_money_link`(`judge.MONETIZED`를 `head_of(video)`에 적용한 "yes"/"no"), `has_disclosure`(`judge.DISCLOSURE`로 "yes"/"no")). LLM이 `reason`을 안 주면 코드에 적힌 라벨별 고정 문장 `LABEL_FALLBACK`으로 채운다. 각 호출 실패 시 그 제안은 `{}`, `llm_error` 기록. 영상당 한 줄 `id verdict_teen verdict_kid [labels] (error?)`, 마지막에 판정별 집계.

- [ ] **1단계: `pipeline/cache.py` 작성**(sqlite3, `INSERT OR REPLACE`).
- [ ] **2단계: `pipeline/run_lens.py` 작성**: `build_row(video) -> dict`, `main()`.
- [ ] **3단계: 데모 3개 스모크**: `python pipeline/run_lens.py --only _OxuxhHF1WI,YjIA7HJXFg0,jZumiXIiCWE` → 기대: 세 줄. Tesla에 `fake_urgency`, Teatox에 `hidden_ad`, Flat Tummy에 `hidden_ad`. `llm_error` 없음.
- [ ] **4단계: 전체 실행**: `python pipeline/run_lens.py` → 기대: 56줄과 집계. `llm_error`는 소수. `--force` 없이 한 번 더 돌려 실패분을 채운다(`llm_error` 있는 행은 캐시 안 된 것으로 취급).
- [ ] **5단계: 무결성 체크**(리뷰 초점 4, verifier의 judge 무결성 항목): 모든 행을 읽어 assert. 모든 tactic 라벨이 `LABELS` 안, 모든 evidence(정규화·소문자)가 해당 영상 `video_text`에 포함, 제목+설명란에 `DISCLOSURE`가 매칭되는 행에 `hidden_ad` 없음, 모든 행에 `quiz_options` 4개, 행 수 56. `cache ok` 출력.
- [ ] **6단계: 커밋** `git add pipeline/cache.py pipeline/run_lens.py cache/lens.sqlite && git commit -m "pipeline: run_lens builds the cache"`

---

### Task 5: `api/main.py`

**파일:** 생성 `api/__init__.py`(빈 파일), `api/main.py`

**인터페이스:**
- 소비: `open_db, all_rows, get`(Task 4); `kid_verdict, parse_rules, DEMO_RULES`(Task 3).
- 생산: CLAUDE.md "API contract"의 세 엔드포인트 그대로. 모듈 전역 `RULES = {"mia": parse_rules(DEMO_RULES)}`, `POST /parent/rules`가 `RULES[child_id]`를 교체. `# ponytail: in-memory rules, lost on restart; demo re-posts them.`
- `GET /feed`: `age_band`가 `{"kid","teen"}` 밖이면 400 `{"error": "age_band must be kid or teen"}`. `child_id` 기본 `"mia"`, 모르는 child는 데모 규칙. kid: `kid_verdict(row, allow, deny) == "show"`인 행, `lens_available: false`, `blocked_count` = 보여주지 않은 행 수. teen: `verdict_teen in ("show","flag")`(풀 전체), `lens_available: true`, `blocked_count` = `block` 행 수(18+만, 보통 0). 아이템 키는 정확히 `video_id, title, channel, thumbnail, views, verdict, lens_available`. teen은 데모 3개(`_OxuxhHF1WI, YjIA7HJXFg0, jZumiXIiCWE`) 먼저, 그다음 views 내림차순. kid는 `match` 내림차순.
- `GET /video/{video_id}/lens`: 모르는 id → 404 `{"error": "unknown video_id"}`. `video_id, verdict(verdict_teen), tactics, quiz_options, reality_check, concern, signals` 순서로 반환. `concern`은 캐시된 객체 또는 `null`.
- `POST /parent/rules`: 본문 `{child_id, rules_text}`. `child_id, allow, deny, queue` 반환. queue는 모든 행을 `{video_id, title, channel, thumbnail, topics, match, verdict, note}`로, `verdict = kid_verdict(...)`, `match` 내림차순. `note`: show는 `null`; approve는 훅이 있으면 `"Names a product with no disclosure: \"<commercial_hook>\""`, 아니면 `"Untrusted channel"`, 아니면 `"Has a lens tactic: <label>"`; hide는 `kid_risk` 또는 `"teen <verdict_teen>"` 또는 `"deny rule: <word>"` 또는 `"no allowed topic"`.
- CORS: `allow_origins=["*"]`, 모든 메서드·헤더. 처리 안 된 예외는 예외 핸들러로 500 `{"error": str(e)}`.

- [ ] **1단계: `api/main.py` 작성**: `app`, `rows()` 헬퍼(요청마다 db 열기), `feed_item(row, age_band)`, 라우트 3개, 500 핸들러.
- [ ] **2단계: 기동** `uvicorn api.main:app --host 0.0.0.0 --port 8000`(백그라운드) 후 실행:
```bash
curl -s "localhost:8000/feed?age_band=kid&child_id=mia" | python -m json.tool | head -30
curl -s "localhost:8000/feed?age_band=teen&child_id=mia" | python -c "import sys,json;d=json.load(sys.stdin);print(len(d['items']),d['blocked_count'],[i['verdict'] for i in d['items']])"
curl -s -o /dev/null -w "%{http_code}\n" "localhost:8000/feed?age_band=adult"
curl -s -o /dev/null -w "%{http_code}\n" "localhost:8000/video/nope/lens"
curl -s localhost:8000/video/_OxuxhHF1WI/lens | python -m json.tool
curl -s -X POST localhost:8000/parent/rules -H 'content-type: application/json' -d '{"child_id":"mia","rules_text":"Science experiments, LEGO builds, animal documentaries. No unboxing, no challenges, nothing with buy now."}' | python -c "import sys,json;d=json.load(sys.stdin);print(d['allow'],d['deny']);import collections;print(collections.Counter(q['verdict'] for q in d['queue']));print([q for q in d['queue'] if q['verdict']=='approve'][0])"
```
기대: kid 아이템 전부 `show`에 필드 7개. teen은 `56 0 [...]`(풀 전체, show와 flag 섞임). `400`. `404`. Tesla lens에 `fake_urgency`와 `quiz_options` 4개. allow/deny가 계약 예시와 같고 note 있는 approve 1개 이상.
- [ ] **3단계: 속도** `for i in 1 2 3; do curl -s -o /dev/null -w "%{time_total}\n" localhost:8000/video/YjIA7HJXFg0/lens; done` → 각각 0.3 미만.
- [ ] **4단계: 키 제거 확인**(verifier 항목): `mv .env .env.bak` 후 uvicorn 재기동, kid 피드 curl 반복, `mv .env.bak .env`. 기대: 같은 응답.
- [ ] **5단계: 커밋** `git add api && git commit -m "api: feed, lens, parent rules from cache"`

여기서 멈춘다. 지원 님이 `/eval`(Task 6 필요)을 돌리고 "deploy"라고 말한다.

---

### Task 6 (지원 님이 "eval.py 써"라고 한 뒤에만): `eval.py`

**파일:** 생성 `eval.py`

**인터페이스:**
- 소비: `tests/gold.json` 행 `{video_id, age_band, verdict, labels}`, `all_rows`의 캐시 행, `kid_verdict`, `parse_rules`, `DEMO_RULES`.
- 셀별(`teen show / teen flag / teen block(10:55 이후 비어 있음) / kid show / kid approve / kid hide / control`) gold 수, 정답 수, 정확도 출력. `both` 행은 `control` 셀이며 `verdict_teen == "show"`이고 `verdict_kid != "hide"`이고 남긴 tactic이 없을 때 정답. teen 행은 `verdict_teen`이 맞고, 라벨이 있는 `show`/`flag` 행은 남긴 라벨 집합이 gold 라벨 집합과 같을 때 정답. 그다음 모든 미스에 대해 `video_id, title, gold 판정 + 라벨, 예측 판정 + 라벨, 남긴 evidence` 출력. 종료 코드는 항상 0.

- [ ] **1단계: `eval.py` 작성**, `python eval.py` 실행, 표 붙여넣기.
- [ ] **2단계: 커밋** `git add eval.py && git commit -m "eval: accuracy vs gold"`
