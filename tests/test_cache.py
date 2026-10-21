from pipeline.cache import all_rows, get, open_db, put


def test_put_get_all_rows_roundtrip(tmp_path):
    db = open_db(str(tmp_path / "t.sqlite"))
    assert get(db, "a") is None
    put(db, "a", {"video_id": "a", "n": 1})
    put(db, "a", {"video_id": "a", "n": 2})  # replace, not duplicate
    put(db, "b", {"video_id": "b", "n": 3})
    assert get(db, "a") == {"video_id": "a", "n": 2}
    assert sorted(r["video_id"] for r in all_rows(db)) == ["a", "b"]
