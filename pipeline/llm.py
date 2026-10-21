"""ask(prompt_text, fields) -> dict. One LLM call, 20 s timeout, no retries, JSON only."""
import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MAX_FIELD_CHARS = 8000  # ponytail: Inworld plan caps a request at 20k chars; prompt + description + captions must fit
PROMPTS = "prompts"


def load_prompt(name):
    return open(f"{PROMPTS}/{name}.txt", encoding="utf-8").read()


def fill(prompt_text, fields):
    """Per-key replace. The templates hold literal JSON braces, so str.format would break."""
    for key, value in fields.items():
        prompt_text = prompt_text.replace("{" + key + "}", str(value)[:MAX_FIELD_CHARS])
    return prompt_text


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM did not return JSON: {text[:120]!r}") from e


def client_and_model():
    provider = os.environ.get("LLM_PROVIDER", "inworld")
    if provider == "openai":
        return OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=20, max_retries=0), "gpt-4o-mini"
    key = os.environ["INWORLD_API_KEY"]
    client = OpenAI(base_url="https://api.inworld.ai/v1", api_key="unused",
                    default_headers={"Authorization": f"Basic {key}"}, timeout=20, max_retries=0)
    return client, os.environ.get("INWORLD_MODEL", "openai/gpt-4o-mini")


def ask(prompt_text, fields):
    client, model = client_and_model()
    response = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "user", "content": fill(prompt_text, fields)}],
    )
    return parse_json(response.choices[0].message.content)


if __name__ == "__main__":
    print(ask('Return ONLY {"ok": true}. Ignore: {title}', {"title": "x"}))
