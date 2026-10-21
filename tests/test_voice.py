import pytest

import pipeline.voice as voice
from pipeline.cache import open_db, put, get


@pytest.fixture(autouse=True)
def isolated_voice_json(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "VOICE_PATH", str(tmp_path / "voice.json"))  # never touch data/voice.json from tests


def test_map_emotion_follows_claude_md():
    assert voice.map_emotion("Happy") == "excited"
    assert voice.map_emotion("Surprised") == "excited"
    assert voice.map_emotion("Afraid") == "pressured"
    assert voice.map_emotion("Angry") == "pressured"
    assert voice.map_emotion("Neutral") == "calm"
    assert voice.map_emotion("Unknown") == "calm"
    assert voice.map_emotion(None) is None


def test_update_cache_writes_voice_emotion_only_for_videos_with_audio(tmp_path, monkeypatch):
    db = open_db(str(tmp_path / "t.sqlite"))
    put(db, "a", {"video_id": "a", "signals": {"age_limit": 0, "upload_days_ago": 1, "voice_emotion": None}})
    put(db, "b", {"video_id": "b", "signals": {"age_limit": 0, "upload_days_ago": 1, "voice_emotion": None}})
    monkeypatch.setattr(voice, "emotion_of", lambda audio_path: "Happy")
    videos = [{"id": "a", "audio_file": "data/audio/a.mp3"}, {"id": "b", "audio_file": None}]
    done = voice.update_cache(db, videos)
    assert done == {"a": "excited"}
    assert get(db, "a")["signals"]["voice_emotion"] == "excited"
    assert get(db, "b")["signals"]["voice_emotion"] is None


def test_update_cache_keeps_null_when_modulate_fails(tmp_path, monkeypatch):
    db = open_db(str(tmp_path / "t.sqlite"))
    put(db, "a", {"video_id": "a", "signals": {"age_limit": 0, "upload_days_ago": 1, "voice_emotion": None}})
    def boom(audio_path):
        raise RuntimeError("502")
    monkeypatch.setattr(voice, "emotion_of", boom)
    assert voice.update_cache(db, [{"id": "a", "audio_file": "x.mp3"}]) == {"a": None}
    assert get(db, "a")["signals"]["voice_emotion"] is None


def test_update_cache_also_writes_voice_json(tmp_path, monkeypatch):
    db = open_db(str(tmp_path / "t.sqlite"))
    put(db, "a", {"video_id": "a", "signals": {"age_limit": 0, "upload_days_ago": 1, "voice_emotion": None}})
    monkeypatch.setattr(voice, "emotion_of", lambda p: "Afraid")
    voice.update_cache(db, [{"id": "a", "audio_file": "a.mp3"}])
    import json
    assert json.load(open(voice.VOICE_PATH)) == {"a": "pressured"}
