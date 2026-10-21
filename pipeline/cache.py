"""One table: lens_cache(video_id TEXT PRIMARY KEY, json TEXT). The API reads only this."""
import json
import os
import sqlite3

PATH = "cache/lens.sqlite"


def open_db(path=PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS lens_cache (video_id TEXT PRIMARY KEY, json TEXT)")
    db.commit()
    return db


def put(db, video_id, row):
    db.execute("INSERT OR REPLACE INTO lens_cache (video_id, json) VALUES (?, ?)", (video_id, json.dumps(row, ensure_ascii=False)))
    db.commit()


def get(db, video_id):
    found = db.execute("SELECT json FROM lens_cache WHERE video_id = ?", (video_id,)).fetchone()
    return json.loads(found[0]) if found else None


def all_rows(db):
    return [json.loads(j) for (j,) in db.execute("SELECT json FROM lens_cache")]
