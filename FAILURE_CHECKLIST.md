# Failure checklist (verifier reads this; humans too)

Run before 12:00, before 2:00, and at 3:45 freeze. Each line: PASS / FAIL + the actual output.

## Must never fail on stage
- [ ] /feed kid and teen return in < 300 ms with the LLM key removed from .env
- [ ] The 3 demo videos' /lens responses each have >= 2 tactics and a reality_check
- [ ] Every evidence string is a literal substring of the video text (case-insensitive)
- [ ] No hidden_ad on a video whose description has a disclosure word
- [ ] Persona switch changes the feed visibly (kid: no lens cards; teen: lens cards + blocked_count)
- [ ] Frontend works on mock JSON with the API down

## Should pass, cut if not by the cut line
- [ ] Modulate transcript on 3 demo videos (cut 1:30)
- [ ] k-ID SDK age signal reaching /feed (cut 2:00 → persona dropdown)
- [ ] Adversarial loop: 3 rounds logged in data/loop_log.json (cut 3:00 → slide)
- [ ] eval.py accuracy >= 70% in every cell (if not, show the real number anyway; never edit gold.json)

## Deploy
- [ ] Render URL responds to /feed kid and teen (wake it 10 min before judging)
- [ ] Cole's frontend points at the Render URL; ngrok fallback tested once

## Environment
- [ ] Phone hotspot tested, laptop on charger, Claude Code logged in and under usage limit
- [ ] Backup screenshots of all screens in deck/
- [ ] Submission form fields drafted in SUBMISSION.txt by 3:00
