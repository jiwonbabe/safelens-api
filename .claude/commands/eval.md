Run `python eval.py` against tests/gold.json and report.

Steps:
1. Run it. If it fails to run, paste the error and stop. Do not edit eval.py or tests/gold.json.
2. Print a table: cell (teen show / teen flag / teen block / kid show / kid approve / kid hide / control) × gold count × correct × accuracy.
3. For every miss, print: video_id, title, gold verdict + labels, predicted verdict + labels, and the evidence quotes the judge kept.
4. Classify each miss as one of: quote-not-found (judge dropped a correct LLM label), rule-too-strict, rule-too-loose, LLM-missed-it.
5. Suggest at most 2 rule changes in judge.py, each as a one-line diff. Do not apply them.
