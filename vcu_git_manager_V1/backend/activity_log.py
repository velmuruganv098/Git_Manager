"""
Persistent operation history, stored as a JSON array in
data/activity_log.json. This is the UI replacement for scrolling back
through CMD history.
"""

import json
import os
import threading
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "data", "activity_log.json")

_lock = threading.Lock()


def _load():
    if not os.path.exists(LOG_PATH):
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def append_activity(record: dict):
    with _lock:
        records = _load()
        record = dict(record)
        record.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
        records.insert(0, record)  # newest first
        records = records[:500]    # keep the log from growing without bound
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        tmp = LOG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        os.replace(tmp, LOG_PATH)


def list_activity(limit=100):
    return _load()[:limit]
