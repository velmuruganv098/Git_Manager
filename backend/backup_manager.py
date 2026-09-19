"""
Creates a timestamped copy of the local project's working tree before any
destructive PULL/replace operation, so the previous version is always
recoverable.
"""

import os
import re
import shutil
from datetime import datetime


def _safe_label(label):
    """A revision label may legally contain '/' (it can double as a git
    branch name elsewhere in this app), but used raw in a folder name a
    slash would be read as a path separator. Swap anything filesystem-
    unsafe for '-' here only - this never touches the real branch name."""
    return re.sub(r'[\\/:*?"<>|]', "-", str(label).strip()) or "unnamed"


def backup_project(project_path, backup_root_name, label):
    """Copies the working tree (excluding .git and the backups folder
    itself) into <project_path>/<backup_root_name>/<timestamp>_<label>/."""
    backup_root = os.path.join(project_path, backup_root_name)
    os.makedirs(backup_root, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest = os.path.join(backup_root, f"{stamp}_{_safe_label(label)}")

    def ignore(dirpath, names):
        rel = os.path.relpath(dirpath, project_path)
        ignored = {".git", backup_root_name}
        if rel == ".":
            return [n for n in names if n in ignored]
        return []

    shutil.copytree(project_path, dest, ignore=ignore)
    return dest
