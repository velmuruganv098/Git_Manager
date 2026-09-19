"""
Thin wrapper around the git command line tool.

Every function shells out to the real `git` binary that must already be
installed on the PC this app runs on. Nothing here talks to GitHub's API
directly - it uses git's own HTTPS remote support, optionally with a
Personal Access Token embedded in the remote URL for the duration of a
single push/pull/fetch so the token is never permanently written into
.git/config.
"""

import os
import re
import shutil
import subprocess
import tarfile
import tempfile


class GitError(Exception):
    pass


def _run(args, cwd=None, check=True, timeout=120):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise GitError(
            "git was not found on this computer. Install Git for Windows "
            "and make sure 'git' is on your PATH, then restart this app."
        )
    except subprocess.TimeoutExpired:
        raise GitError(f"git {' '.join(args)} timed out.")

    if check and result.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed:\n{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def is_git_available():
    try:
        _run(["--version"], check=True)
        return True
    except GitError:
        return False


def is_repo(path):
    return os.path.isdir(os.path.join(path, ".git"))


def init_repo(path):
    os.makedirs(path, exist_ok=True)
    _run(["init"], cwd=path)


def clone_repo(remote_url, dest_path):
    parent = os.path.dirname(os.path.abspath(dest_path))
    os.makedirs(parent, exist_ok=True)
    _run(["clone", remote_url, dest_path])


def get_remote_url(path, remote="origin"):
    result = _run(["remote", "get-url", remote], cwd=path, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def set_remote_url(path, url, remote="origin"):
    existing = get_remote_url(path, remote)
    if existing is None:
        _run(["remote", "add", remote, url], cwd=path)
    else:
        _run(["remote", "set-url", remote, url], cwd=path)


def build_https_url(owner, repo, token=None):
    if token:
        return f"https://{token}@github.com/{owner}/{repo}.git"
    return f"https://github.com/{owner}/{repo}.git"


def _scrub_token(url):
    """Strip an embedded token out of a URL for safe display/logging."""
    return re.sub(r"https://[^@/]+@", "https://", url or "")


def current_branch(path):
    result = _run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path, check=False)
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return None if branch == "HEAD" else branch


def current_commit(path, ref="HEAD"):
    result = _run(["rev-parse", ref], cwd=path, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def status_porcelain(path):
    result = _run(["status", "--porcelain"], cwd=path)
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    return lines


def list_branches(path):
    local = _run(["branch", "--format=%(refname:short)"], cwd=path, check=False)
    remote = _run(["branch", "-r", "--format=%(refname:short)"], cwd=path, check=False)
    local_branches = [b for b in local.stdout.splitlines() if b.strip()]
    remote_branches = [b for b in remote.stdout.splitlines() if b.strip() and "->" not in b]
    return {"local": local_branches, "remote": remote_branches}


def fetch(path, remote="origin", token=None, owner=None, repo=None):
    _with_temporary_token(path, remote, token, owner, repo, lambda: _run(["fetch", remote], cwd=path))


def checkout(path, branch):
    _run(["checkout", branch], cwd=path)


def create_branch_if_missing(path, branch):
    branches = list_branches(path)
    if branch not in branches["local"]:
        # try to base it on a matching remote branch, else current HEAD
        remote_match = f"origin/{branch}"
        if remote_match in branches["remote"]:
            _run(["checkout", "-b", branch, remote_match], cwd=path)
        else:
            _run(["checkout", "-b", branch], cwd=path)
    else:
        checkout(path, branch)


def add_all(path):
    _run(["add", "-A"], cwd=path)


def commit(path, message):
    result = _run(["commit", "-m", message], cwd=path, check=False)
    if result.returncode != 0:
        combined = (result.stdout + result.stderr).lower()
        if "nothing to commit" in combined:
            return False  # not an error - just nothing changed
        raise GitError(f"git commit failed:\n{result.stderr.strip() or result.stdout.strip()}")
    return True


def push(path, branch, remote="origin", token=None, owner=None, repo=None):
    def do_push():
        result = _run(["push", "-u", remote, branch], cwd=path, check=False)
        if result.returncode != 0:
            raise GitError(f"git push failed:\n{_scrub_token(result.stderr.strip() or result.stdout.strip())}")
    _with_temporary_token(path, remote, token, owner, repo, do_push)


def pull_reset_hard(path, branch, remote="origin", token=None, owner=None, repo=None,
                     protect_dirs=None):
    """Reset the local branch to exactly match the remote branch.

    `protect_dirs` (e.g. the backup folder) are excluded from `git clean`
    so a backup taken just before this call - or anything else untracked
    that the app itself owns - is never deleted by the replace step."""
    def do_pull():
        _run(["fetch", remote], cwd=path)
        create_branch_if_missing(path, branch)
        _run(["reset", "--hard", f"{remote}/{branch}"], cwd=path)
        clean_args = ["clean", "-fd"]
        for d in (protect_dirs or []):
            clean_args += ["-e", d]
        _run(clean_args, cwd=path)
    _with_temporary_token(path, remote, token, owner, repo, do_pull)


def _with_temporary_token(path, remote, token, owner, repo, action):
    """Temporarily swap the remote URL to one carrying the token (if given),
    run `action`, then always restore the original remote URL."""
    if not token or not owner or not repo:
        return action()

    original = get_remote_url(path, remote)
    tokened = build_https_url(owner, repo, token)
    try:
        set_remote_url(path, tokened, remote)
        return action()
    finally:
        if original:
            set_remote_url(path, original, remote)
        else:
            set_remote_url(path, build_https_url(owner, repo, None), remote)


def archive_ref_to_dir(path, ref, remote="origin"):
    """Export the full tree of `ref` (e.g. 'main', 'origin/main', a commit
    sha) into a fresh temp directory and return that directory's path.
    Uses `git archive` + Python's tarfile module so no external tar/zip
    utility is required on the host machine."""
    tmp_dir = tempfile.mkdtemp(prefix="vcu_archive_")
    tar_path = os.path.join(tempfile.gettempdir(), next(tempfile._get_candidate_names()) + ".tar")
    try:
        result = subprocess.run(
            ["git", "archive", "--format=tar", ref],
            cwd=path,
            stdout=open(tar_path, "wb"),
            stderr=subprocess.PIPE,
            timeout=120,
        )
        if result.returncode != 0:
            raise GitError(
                f"git archive {ref} failed:\n{result.stderr.decode(errors='ignore').strip()}"
            )
        with tarfile.open(tar_path) as tar:
            tar.extractall(tmp_dir)
    finally:
        if os.path.exists(tar_path):
            os.remove(tar_path)
    return tmp_dir


def cleanup_dir(path):
    shutil.rmtree(path, ignore_errors=True)


def ref_exists(path, ref):
    result = _run(["rev-parse", "--verify", "--quiet", ref], cwd=path, check=False)
    return result.returncode == 0
