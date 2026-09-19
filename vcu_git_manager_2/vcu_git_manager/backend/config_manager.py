"""
Persistent configuration for the VCU Local GitHub Manager.

Everything the Settings screen shows is stored in data/config.json.
That file is read on startup and rewritten whenever the user saves
Settings, so the app always reopens exactly where it was left.
"""

import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

DEFAULT_CONFIG = {
    "local_project_path": "",      # e.g. D:\\Projects\\Zitto_MB_V1
    "project_name": "",            # e.g. Zitto_MB_V1
    "github_owner": "",            # e.g. velmuruganv098
    "github_repo": "",             # e.g. Zitto_MB_V1
    "github_token": "",           # Personal Access Token (stored locally only)
    "branch": "main",
    "github_path": "/",
    "previous_revision": "V1",
    "new_revision": "V2",
    "revision_notes": "",
    "revision_notes_folder": "Revision_Notes",
    "backup_folder": ".backups",
    "diff_note_prefix": "DIFFERENCE",
    "text_file_extensions": [
        ".c", ".h", ".cpp", ".hpp", ".cc", ".py", ".md", ".txt", ".json",
        ".yaml", ".yml", ".ini", ".cfg", ".xml", ".html", ".css", ".js",
        ".ld", ".mk", "Makefile", ".s", ".asm", ".gitignore", ".csv"
    ],
    "exclude_dirs": [".git", ".backups", "__pycache__", ".vscode", "Revision_Notes"],
}

_lock = threading.Lock()


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "revisions"), exist_ok=True)


def load_config():
    """Return the saved config, merged over defaults so new fields
    added in later versions of the app always have a value."""
    ensure_data_dir()
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(new_values: dict):
    """Merge new_values into the existing config and persist it."""
    with _lock:
        cfg = load_config()
        cfg.update(new_values)
        ensure_data_dir()
        tmp_path = CONFIG_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp_path, CONFIG_PATH)
        return cfg
