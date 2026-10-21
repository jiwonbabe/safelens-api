Check the demo path end to end against the running API on http://localhost:8000.

1. Call GET /feed?age_band=kid&child_id=mia and GET /feed?age_band=teen&child_id=mia. Print the first 3 titles of each with their verdict and blocked_count.
2. Call GET /video/{id}/lens for the three demo videos (ids are listed in CLAUDE.md under "Demo picks" if present, else use the first teen item). Print labels, evidence, and reality_check for each.
3. Call POST /parent/rules with the demo rules text from CLAUDE.md. Print how many "show" and "approve" items came back and the note on the first "approve".
4. Time each call. Flag anything over 300 ms.
5. End with "DEMO OK" or a list of what is empty, missing, or slow. Do not change any code.
