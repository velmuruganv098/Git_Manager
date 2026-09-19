"""
File-by-file, line-by-line comparison between two directory trees.

Used for BOTH directions of the workflow:
  UPLOAD (local -> GitHub): old_dir = archived HEAD/branch, new_dir = local working copy
  PULL   (GitHub -> local): old_dir = local working copy, new_dir = archived remote branch

The result is a single structured dict that both the diff-note generator
and the UI JSON responses are built from, so the note and the on-screen
preview always agree.
"""

import difflib
import hashlib
import os


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_binary(path):
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        if b"\x00" in chunk:
            return True
        chunk.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True
    except OSError:
        return True


def _read_lines(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def _walk(root, exclude_dirs):
    files = {}
    if not root or not os.path.isdir(root):
        return files
    exclude = set(exclude_dirs or [])
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude]
        for fname in filenames:
            abspath = os.path.join(dirpath, fname)
            relpath = os.path.relpath(abspath, root).replace(os.sep, "/")
            files[relpath] = abspath
    return files


def _line_diff_blocks(old_lines, new_lines, context_limit=40):
    """Turn a SequenceMatcher opcode list into compact MODIFIED/ADDED/DELETED
    blocks, each carrying the 1-based starting line number on each side."""
    blocks = []
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        block = {
            "type": {"replace": "MODIFIED", "delete": "DELETED", "insert": "ADDED"}[tag],
            "old_start": i1 + 1,
            "old_lines": old_lines[i1:i2],
            "new_start": j1 + 1,
            "new_lines": new_lines[j1:j2],
        }
        blocks.append(block)
        if len(blocks) >= context_limit:
            blocks.append({"type": "TRUNCATED", "old_start": 0, "old_lines": [],
                            "new_start": 0, "new_lines": []})
            break
    return blocks


def compare_dirs(old_dir, new_dir, exclude_dirs=None, max_line_diff_size=2_000_000):
    old_files = _walk(old_dir, exclude_dirs)
    new_files = _walk(new_dir, exclude_dirs)

    all_paths = sorted(set(old_files) | set(new_files))
    entries = []
    summary = {
        "files_checked": len(all_paths),
        "unchanged": 0, "modified": 0, "added": 0, "deleted": 0,
        "lines_added": 0, "lines_deleted": 0,
    }

    for rel in all_paths:
        old_path = old_files.get(rel)
        new_path = new_files.get(rel)

        if old_path and not new_path:
            status = "DELETED"
        elif new_path and not old_path:
            status = "ADDED"
        else:
            old_hash = _sha256(old_path)
            new_hash = _sha256(new_path)
            status = "UNCHANGED" if old_hash == new_hash else "MODIFIED"

        entry = {
            "path": rel,
            "status": status,
            "binary": False,
            "old_size": os.path.getsize(old_path) if old_path else None,
            "new_size": os.path.getsize(new_path) if new_path else None,
            "old_sha256": None,
            "new_sha256": None,
            "old_lines": None,
            "new_lines": None,
            "line_blocks": [],
        }

        if old_path:
            entry["old_sha256"] = _sha256(old_path)
        if new_path:
            entry["new_sha256"] = _sha256(new_path)

        is_bin = _is_binary(old_path or new_path)
        entry["binary"] = is_bin

        if status == "UNCHANGED":
            summary["unchanged"] += 1
        elif status == "ADDED":
            summary["added"] += 1
            if not is_bin:
                try:
                    entry["new_lines"] = len(_read_lines(new_path))
                    if os.path.getsize(new_path) <= max_line_diff_size:
                        summary["lines_added"] += entry["new_lines"]
                except OSError:
                    pass
        elif status == "DELETED":
            summary["deleted"] += 1
            if not is_bin:
                try:
                    entry["old_lines"] = len(_read_lines(old_path))
                    if os.path.getsize(old_path) <= max_line_diff_size:
                        summary["lines_deleted"] += entry["old_lines"]
                except OSError:
                    pass
        elif status == "MODIFIED":
            summary["modified"] += 1
            if not is_bin:
                try:
                    old_lines = _read_lines(old_path)
                    new_lines = _read_lines(new_path)
                    entry["old_lines"] = len(old_lines)
                    entry["new_lines"] = len(new_lines)
                    if max(os.path.getsize(old_path), os.path.getsize(new_path)) <= max_line_diff_size:
                        blocks = _line_diff_blocks(old_lines, new_lines)
                        entry["line_blocks"] = blocks
                        for b in blocks:
                            summary["lines_added"] += len(b.get("new_lines", []))
                            summary["lines_deleted"] += len(b.get("old_lines", []))
                except OSError:
                    pass

        entries.append(entry)

    return {"summary": summary, "files": entries}
