Run one round of the adversarial loop and report what the Lens missed.

1. Run `python pipeline/loop.py --rounds 1`. It should: ask the bait-writer prompt for 10 bait titles+descriptions across the six labels, run them through the same run_lens path, and compare detected labels against the labels the bait writer intended.
2. Print a table: bait title / intended labels / detected labels / missed.
3. Print the running score: "Round N: caught X of Y". Append it to data/loop_log.json.
4. For the misses, show the LLM's raw proposal next to the judge's decision so we can see whether the model missed it or the judge dropped it.
5. Propose one prompt wording change to prompts/lens.txt. Do not apply it unless I say so.
