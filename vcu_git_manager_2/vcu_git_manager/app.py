"""
VCU Local GitHub Manager
========================
A local HTTP server + browser UI that replaces the CMD-based Git/GitHub
workflow described in the project requirement:

    LOCAL <-> COMPARE <-> DIFFERENCE NOTE <-> CONFIRM <-> GITHUB

Run it with:

    python app.py

then open http://127.0.0.1:5757 in your browser. All settings are saved
to data/config.json and reloaded automatically the next time you start
the app.
"""

import os
import re
import shutil
import tempfile
import traceback
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from backend import activity_log, backup_manager, config_manager, diff_note
from backend import compare_engine, git_manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=None)

# In-memory cache of the last scan, keyed by direction, so "confirm" can
# reuse exactly what the user previewed without re-scanning.
_LAST_SCAN = {"upload": None, "pull": None}


# --------------------------------------------------------------------------
# Static UI
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def error_response(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def require_project(cfg):
    path = cfg.get("local_project_path", "").strip()
    if not path:
        raise ValueError("Set a Local Project Path in Settings first.")
    if not os.path.isdir(path):
        raise ValueError(f"Local Project Path does not exist:\n{path}")
    return path


def parse_github_owner_repo(owner_raw, repo_raw):
    """Accepts either a clean 'owner' + 'repo', or a full GitHub URL /
    'owner/repo' shorthand pasted into either field, and returns a clean
    (owner, repo) pair either way."""
    owner_raw = (owner_raw or "").strip()
    repo_raw = (repo_raw or "").strip()

    candidate = repo_raw if "github.com" in repo_raw else (owner_raw if "github.com" in owner_raw else "")
    if candidate:
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", candidate)
        if m:
            return m.group(1), m.group(2)

    if "/" in repo_raw and not owner_raw:
        parts = [p for p in repo_raw.strip("/").split("/") if p]
        if len(parts) >= 2:
            return parts[-2], parts[-1]

    return owner_raw, repo_raw


def require_github(cfg):
    owner, repo = parse_github_owner_repo(cfg.get("github_owner", ""), cfg.get("github_repo", ""))
    if not owner or not repo:
        raise ValueError("Set the GitHub owner and repository name in Settings first.")
    return owner, repo


def revision_already_used(path, cfg, new_rev):
    """Returns the existing difference-note filename if `new_rev` has
    already been used as a 'TO' revision for this project, else None."""
    notes_dir = os.path.join(path, cfg.get("revision_notes_folder", "Revision_Notes"))
    if not os.path.isdir(notes_dir):
        return None
    suffix = f"_TO_{new_rev}.txt".lower()
    for fname in os.listdir(notes_dir):
        if fname.lower().endswith(suffix):
            return fname
    return None


def project_meta(cfg):
    name = cfg.get("project_name", "").strip()
    if not name:
        name = os.path.basename(cfg.get("local_project_path", "").rstrip("/\\")) or "project"
    return name


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({"ok": True, "config": config_manager.load_config()})


@app.route("/api/config", methods=["POST"])
def post_config():
    data = request.get_json(force=True, silent=True) or {}
    cfg = config_manager.save_config(data)
    return jsonify({"ok": True, "config": cfg})


@app.route("/api/environment", methods=["GET"])
def environment():
    return jsonify({
        "ok": True,
        "git_available": git_manager.is_git_available(),
    })


# --------------------------------------------------------------------------
# Project status
# --------------------------------------------------------------------------

@app.route("/api/status", methods=["GET"])
def status():
    cfg = config_manager.load_config()
    try:
        path = require_project(cfg)
    except ValueError as e:
        return jsonify({"ok": True, "repo_ready": False, "message": str(e)})

    is_repo = git_manager.is_repo(path)
    info = {
        "ok": True,
        "repo_ready": is_repo,
        "local_project_path": path,
    }
    if is_repo:
        info["current_branch"] = git_manager.current_branch(path)
        info["current_commit"] = git_manager.current_commit(path)
        info["uncommitted_changes"] = git_manager.status_porcelain(path)
        info["branches"] = git_manager.list_branches(path)
        info["remote_url"] = git_manager._scrub_token(git_manager.get_remote_url(path))
    return jsonify(info)


@app.route("/api/init_or_clone", methods=["POST"])
def init_or_clone():
    """Prepare the local project folder: clone it from GitHub if it does
    not exist yet locally, or `git init` + attach the remote if it exists
    but isn't a repo yet."""
    cfg = config_manager.load_config()
    try:
        owner, repo = require_github(cfg)
        path = cfg.get("local_project_path", "").strip()
        if not path:
            raise ValueError("Set a Local Project Path in Settings first.")
        token = cfg.get("github_token") or None
        url = git_manager.build_https_url(owner, repo, token)

        if not os.path.exists(path) or not os.listdir(path):
            git_manager.clone_repo(url, path)
            action = "cloned"
        elif not git_manager.is_repo(path):
            git_manager.init_repo(path)
            git_manager.set_remote_url(path, git_manager.build_https_url(owner, repo, None))
            action = "initialized (existing folder linked to remote)"
        else:
            action = "already a git repository"

        activity_log.append_activity({
            "operation": "INIT/CLONE", "result": "SUCCESS",
            "details": action, "local": path,
            "github": f"{owner}/{repo}",
        })
        return jsonify({"ok": True, "action": action})
    except (ValueError, git_manager.GitError) as e:
        activity_log.append_activity({"operation": "INIT/CLONE", "result": "FAILED", "details": str(e)})
        return error_response(str(e))


@app.route("/api/fetch", methods=["POST"])
def fetch():
    cfg = config_manager.load_config()
    try:
        path = require_project(cfg)
        owner, repo = require_github(cfg)
        git_manager.fetch(path, token=cfg.get("github_token") or None, owner=owner, repo=repo)
        return jsonify({"ok": True, "branches": git_manager.list_branches(path)})
    except (ValueError, git_manager.GitError) as e:
        return error_response(str(e))


# --------------------------------------------------------------------------
# UPLOAD workflow:  LOCAL -> GITHUB
# --------------------------------------------------------------------------

@app.route("/api/upload/scan", methods=["POST"])
def upload_scan():
    """SCAN -> COMPARE -> FILE-BY-FILE -> LINE-BY-LINE -> GENERATE DIFFERENCE NOTE"""
    cfg = config_manager.load_config()
    old_archive = None
    try:
        path = require_project(cfg)
        owner, repo = require_github(cfg)
        branch = cfg.get("branch", "main").strip() or "main"
        token = cfg.get("github_token") or None

        if not git_manager.is_repo(path):
            raise ValueError("This folder is not a git repository yet. Use "
                              "'Prepare repository' on the Status tab first.")

        new_rev = cfg.get("new_revision", "").strip()
        if not new_rev:
            raise ValueError("Enter a New revision label before scanning.")
        clash = revision_already_used(path, cfg, new_rev)
        if clash:
            raise ValueError(
                f"Revision label '{new_rev}' is already used ({clash} already exists "
                f"in {cfg.get('revision_notes_folder', 'Revision_Notes')}/). "
                f"Choose a different New revision label."
            )
        # Previous revision is optional - blank just means "first upload /
        # no prior labeled revision", not an error.
        from_rev = cfg.get("previous_revision", "").strip() or "INITIAL"

        # "Previous" state = current HEAD of the branch we're about to push to.
        # Fetch first so we know about the real remote tip if it moved.
        try:
            git_manager.fetch(path, token=token, owner=owner, repo=repo)
        except git_manager.GitError:
            pass  # offline / first push - fall back to local HEAD only

        base_ref = None
        if git_manager.ref_exists(path, f"origin/{branch}"):
            base_ref = f"origin/{branch}"
        elif git_manager.ref_exists(path, "HEAD"):
            base_ref = "HEAD"

        if base_ref:
            old_archive = git_manager.archive_ref_to_dir(path, base_ref)
        else:
            # No commits anywhere yet - genuinely the first upload. Compare
            # against an empty directory so every local file shows as ADDED.
            old_archive = tempfile.mkdtemp(prefix="vcu_empty_")
            base_ref = "(no previous commits - first upload)"

        comparison = compare_engine.compare_dirs(
            old_archive, path, exclude_dirs=cfg.get("exclude_dirs")
        )

        meta = {
            "project_name": project_meta(cfg),
            "from_rev": from_rev,
            "to_rev": new_rev,
            "branch": branch,
            "direction": "LOCAL -> GITHUB",
            "user_notes": cfg.get("revision_notes", ""),
            "source_label": path,
            "dest_label": f"{owner}/{repo} ({branch})",
        }
        note_text = diff_note.build_diff_note(comparison, meta)
        filename = f"{cfg.get('diff_note_prefix', 'DIFFERENCE')}_{meta['from_rev']}_TO_{meta['to_rev']}.txt"

        _LAST_SCAN["upload"] = {
            "comparison": comparison, "meta": meta, "filename": filename,
            "note_text": note_text, "base_ref": base_ref, "branch": branch,
        }

        return jsonify({
            "ok": True,
            "summary": comparison["summary"],
            "files": comparison["files"],
            "note_filename": filename,
            "note_text": note_text,
            "from_rev": meta["from_rev"], "to_rev": meta["to_rev"],
            "branch": branch,
        })
    except (ValueError, git_manager.GitError) as e:
        return error_response(str(e))
    finally:
        if old_archive:
            git_manager.cleanup_dir(old_archive)


@app.route("/api/upload/confirm", methods=["POST"])
def upload_confirm():
    """USER CONFIRMATION -> COMMIT -> PUSH -> VERIFY -> ACTIVITY LOG"""
    cfg = config_manager.load_config()
    scan = _LAST_SCAN.get("upload")
    if not scan:
        return error_response("Run a scan before confirming the upload.")

    try:
        path = require_project(cfg)
        owner, repo = require_github(cfg)
        token = cfg.get("github_token") or None
        branch = scan["branch"]

        notes_dir = os.path.join(path, cfg.get("revision_notes_folder", "Revision_Notes"))
        os.makedirs(notes_dir, exist_ok=True)
        note_path = os.path.join(notes_dir, scan["filename"])
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(scan["note_text"])

        git_manager.create_branch_if_missing(path, branch)
        git_manager.add_all(path)

        commit_message = (
            f"Revision {scan['meta']['from_rev']} -> {scan['meta']['to_rev']}: "
            f"{cfg.get('revision_notes', '').strip() or 'project update'}"
        )
        committed = git_manager.commit(path, commit_message)
        git_manager.push(path, branch, token=token, owner=owner, repo=repo)

        # Verify: local HEAD should now equal the remote branch tip.
        git_manager.fetch(path, token=token, owner=owner, repo=repo)
        local_sha = git_manager.current_commit(path)
        remote_sha = git_manager.current_commit(path, f"origin/{branch}")
        verified = bool(local_sha and remote_sha and local_sha == remote_sha)

        record = {
            "operation": "LOCAL -> GITHUB (UPLOAD)",
            "result": "SUCCESS" if verified else "PUSHED (verification inconclusive)",
            "branch": branch,
            "revision": f"{scan['meta']['from_rev']} -> {scan['meta']['to_rev']}",
            "files_changed": scan["comparison"]["summary"]["modified"]
                              + scan["comparison"]["summary"]["added"]
                              + scan["comparison"]["summary"]["deleted"],
            "notes": cfg.get("revision_notes", ""),
            "difference_note": scan["filename"],
            "committed": committed,
            "local": path,
            "github": f"{owner}/{repo}",
        }
        activity_log.append_activity(record)

        # roll revision labels forward for next time (still editable by user)
        config_manager.save_config({
            "previous_revision": scan["meta"]["to_rev"],
            "new_revision": _next_revision_label(scan["meta"]["to_rev"]),
        })

        _LAST_SCAN["upload"] = None
        return jsonify({"ok": True, "verified": verified, "record": record})
    except (ValueError, git_manager.GitError) as e:
        activity_log.append_activity({
            "operation": "LOCAL -> GITHUB (UPLOAD)", "result": "FAILED", "details": str(e),
        })
        return error_response(str(e))


def _next_revision_label(label):
    m = re.match(r"^([A-Za-z]*)(\d+)$", label.strip())
    if m:
        prefix, num = m.groups()
        return f"{prefix}{int(num) + 1}"
    return label + "+1"


# --------------------------------------------------------------------------
# PULL workflow:  GITHUB -> LOCAL
# --------------------------------------------------------------------------

@app.route("/api/pull/scan", methods=["POST"])
def pull_scan():
    """FETCH -> SCAN -> COMPARE -> FILE-BY-FILE -> LINE-BY-LINE -> DIFFERENCE NOTE"""
    cfg = config_manager.load_config()
    remote_archive = None
    try:
        path = require_project(cfg)
        owner, repo = require_github(cfg)
        branch = cfg.get("branch", "main").strip() or "main"
        token = cfg.get("github_token") or None

        if not git_manager.is_repo(path):
            raise ValueError("This folder is not a git repository yet. Use "
                              "'Prepare repository' on the Status tab first.")

        new_rev = cfg.get("new_revision", "").strip()
        if not new_rev:
            raise ValueError("Enter a New revision label before scanning.")
        clash = revision_already_used(path, cfg, new_rev)
        if clash:
            raise ValueError(
                f"Revision label '{new_rev}' is already used ({clash} already exists "
                f"in {cfg.get('revision_notes_folder', 'Revision_Notes')}/). "
                f"Choose a different New revision label."
            )
        from_rev = cfg.get("previous_revision", "").strip() or "INITIAL"

        git_manager.fetch(path, token=token, owner=owner, repo=repo)
        remote_ref = f"origin/{branch}"
        if not git_manager.ref_exists(path, remote_ref):
            raise ValueError(f"Branch '{branch}' was not found on the remote after fetch.")

        remote_archive = git_manager.archive_ref_to_dir(path, remote_ref)
        comparison = compare_engine.compare_dirs(
            path, remote_archive, exclude_dirs=cfg.get("exclude_dirs")
        )

        meta = {
            "project_name": project_meta(cfg),
            "from_rev": from_rev,
            "to_rev": new_rev,
            "branch": branch,
            "direction": "GITHUB -> LOCAL",
            "user_notes": cfg.get("revision_notes", ""),
            "source_label": f"{owner}/{repo} ({branch})",
            "dest_label": path,
        }
        note_text = diff_note.build_diff_note(comparison, meta)
        filename = f"{cfg.get('diff_note_prefix', 'DIFFERENCE')}_{meta['from_rev']}_TO_{meta['to_rev']}.txt"

        _LAST_SCAN["pull"] = {
            "comparison": comparison, "meta": meta, "filename": filename,
            "note_text": note_text, "branch": branch,
        }

        return jsonify({
            "ok": True,
            "summary": comparison["summary"],
            "files": comparison["files"],
            "note_filename": filename,
            "note_text": note_text,
            "from_rev": meta["from_rev"], "to_rev": meta["to_rev"],
            "branch": branch,
        })
    except (ValueError, git_manager.GitError) as e:
        return error_response(str(e))
    finally:
        if remote_archive:
            git_manager.cleanup_dir(remote_archive)


@app.route("/api/pull/confirm", methods=["POST"])
def pull_confirm():
    """BACKUP LOCAL -> REPLACE -> VERIFY -> ACTIVITY LOG"""
    cfg = config_manager.load_config()
    scan = _LAST_SCAN.get("pull")
    if not scan:
        return error_response("Run a scan before confirming the pull.")

    try:
        path = require_project(cfg)
        owner, repo = require_github(cfg)
        token = cfg.get("github_token") or None
        branch = scan["branch"]

        backup_folder_name = cfg.get("backup_folder", ".backups")
        notes_folder_name = cfg.get("revision_notes_folder", "Revision_Notes")

        backup_path = backup_manager.backup_project(
            path, backup_folder_name, scan["meta"]["from_rev"]
        )

        # Replace local content with the remote branch. `protect_dirs` keeps
        # `git clean -fd` from deleting the backup we just made (it's
        # untracked, so without this it would be wiped immediately).
        git_manager.pull_reset_hard(
            path, branch, token=token, owner=owner, repo=repo,
            protect_dirs=[backup_folder_name + "/"],
        )

        # Write the difference note AFTER the replace, so the reset/clean
        # step can't remove it either.
        notes_dir = os.path.join(path, notes_folder_name)
        os.makedirs(notes_dir, exist_ok=True)
        note_path = os.path.join(notes_dir, scan["filename"])
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(scan["note_text"])

        remote_sha = git_manager.current_commit(path, f"origin/{branch}")
        local_sha = git_manager.current_commit(path)
        verified = bool(local_sha and remote_sha and local_sha == remote_sha)

        record = {
            "operation": "GITHUB -> LOCAL (PULL / REPLACE)",
            "result": "SUCCESS" if verified else "REPLACED (verification inconclusive)",
            "branch": branch,
            "revision": f"{scan['meta']['from_rev']} -> {scan['meta']['to_rev']}",
            "files_changed": scan["comparison"]["summary"]["modified"]
                              + scan["comparison"]["summary"]["added"]
                              + scan["comparison"]["summary"]["deleted"],
            "backup_path": backup_path,
            "difference_note": scan["filename"],
            "local": path,
            "github": f"{owner}/{repo}",
        }
        activity_log.append_activity(record)

        config_manager.save_config({
            "previous_revision": scan["meta"]["to_rev"],
            "new_revision": _next_revision_label(scan["meta"]["to_rev"]),
        })

        _LAST_SCAN["pull"] = None
        return jsonify({"ok": True, "verified": verified, "record": record})
    except (ValueError, git_manager.GitError) as e:
        activity_log.append_activity({
            "operation": "GITHUB -> LOCAL (PULL / REPLACE)", "result": "FAILED", "details": str(e),
        })
        return error_response(str(e))


# --------------------------------------------------------------------------
# Activity history
# --------------------------------------------------------------------------

@app.route("/api/activity", methods=["GET"])
def activity():
    return jsonify({"ok": True, "records": activity_log.list_activity()})


@app.errorhandler(Exception)
def handle_unexpected(e):
    if isinstance(e, HTTPException):
        # Let normal HTTP errors (404s, etc.) pass through as-is instead of
        # being reported as a 500 "unexpected error".
        return e
    traceback.print_exc()
    return jsonify({"ok": False, "error": f"Unexpected error: {e}"}), 500


if __name__ == "__main__":
    config_manager.ensure_data_dir()
    print("=" * 60)
    print(" VCU Local GitHub Manager")
    print(" Open this in your browser: http://127.0.0.1:5757")
    print(" Press CTRL+C here to stop the server.")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5757, debug=False)
