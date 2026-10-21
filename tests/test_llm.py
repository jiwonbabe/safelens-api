import os

import pytest

from pipeline.llm import ask, fill, load_prompt, parse_json, MAX_FIELD_CHARS


def test_fill_replaces_keys_and_leaves_literal_json_braces():
    out = fill('Return {"ok": true}. Title: {title} Channel: {channel}', {"title": "A", "channel": "B"})
    assert out == 'Return {"ok": true}. Title: A Channel: B'


def test_fill_caps_long_values():
    out = fill("{captions}", {"captions": "x" * (MAX_FIELD_CHARS + 500)})
    assert len(out) == MAX_FIELD_CHARS


def test_parse_json_strips_code_fences():
    assert parse_json('```json\n{"ok": true}\n```') == {"ok": True}
    assert parse_json('{"ok": true}') == {"ok": True}


def test_parse_json_raises_on_prose():
    with pytest.raises(ValueError):
        parse_json("Sure! Here is the JSON you asked for.")


def test_load_prompt_reads_the_txt_file():
    assert "{rules_text}" in load_prompt("topics")
    assert "{captions}" in load_prompt("lens")


@pytest.mark.skipif(not os.path.exists(".env"), reason="needs .env with an LLM key")
def test_ask_live_returns_parsed_dict():
    out = ask('Reply with exactly this JSON and nothing else: {"ok": true, "echo": "{title}"}', {"title": "x"})
    assert out["ok"] is True
    assert out["echo"] == "x"
