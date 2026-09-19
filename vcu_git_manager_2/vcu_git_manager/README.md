# VCU Local GitHub Manager

A local HTTP server (Python/Flask backend) with a browser UI that replaces
the CMD-based Git/GitHub workflow for a project like `Zitto_MB_V1`:

```
CMD                          UI
--------------------         --------------------
git status            ->     Status
git fetch              ->     Fetch
git diff               ->     Scan & Compare
git add / commit       ->     Upload -> Confirm
git push               ->     Upload -> Confirm
git pull               ->     Pull -> Confirm
```

Every upload or pull is: **scan the whole project → compare it file-by-file
and line-by-line → generate a permanent difference note → show you exactly
what will change → only then commit/push or backup/replace.**

## Requirements

- Python 3.9+
- [Git](https://git-scm.com/downloads) installed and on your PATH
  (the app shells out to the real `git` binary — it does not reimplement Git)
- A GitHub repository and, if it's private or you want to push, a
  [Personal Access Token](https://github.com/settings/tokens) with `repo` scope

## Running it (Windows)

1. Unzip this folder anywhere, e.g. `D:\Tools\vcu_git_manager`
2. Double-click **run.bat**
   - First run creates a local virtual environment and installs Flask
   - It then starts the server and prints `http://127.0.0.1:5757`
3. Open that address in your browser

## Running it (macOS/Linux)

```bash
./run.sh
```

## First-time setup

1. Open the **Settings** tab
2. Fill in:
   - **Local project path** — e.g. `D:\Projects\Zitto_MB_V1`
   - **Project name** — used in the generated difference note header
   - **GitHub owner / repository / branch** — e.g. `velmuruganv098` / `Zitto_MB_V1` / `main`
   - **Personal Access Token** — only needed for push, or for pulling a
     private repo. Stored locally in `data/config.json` on your own PC and
     never sent anywhere except to GitHub over HTTPS for the duration of a
     fetch/push/pull.
3. Click **Save settings**
4. Go to **Status**. If the local folder isn't a git repository yet, click
   **Prepare repository** — this either clones the GitHub repo into that
   folder (if it's empty) or turns an existing folder into a repo linked to
   your remote.

Everything you type into Settings is written to `data/config.json`
immediately on Save, and is read back automatically the next time you start
`app.py` — closing and reopening the app always restores your last setup.

## Upload — Local → GitHub

1. Open **Upload**
2. Set **Previous revision** / **New revision** labels (e.g. `V1` / `V2`)
   and optional revision notes describing what you changed
3. Click **Scan & compare** — this fetches the remote, archives the current
   branch tip, and compares it file-by-file and line-by-line against your
   local working copy
4. Review the summary and file list; click **View difference note** to read
   the full Notepad-style report before doing anything
5. Click **Confirm upload** — this:
   - writes `Revision_Notes/DIFFERENCE_<from>_TO_<to>.txt` into the project
   - commits everything with a message built from your revision labels and notes
   - pushes to the configured branch
   - fetches again and verifies the local commit matches the remote
   - logs the whole operation to **Activity**

## Pull — GitHub → Local

1. Open **Pull**
2. Set the revision labels
3. Click **Fetch, scan & compare** — fetches the branch and compares your
   local files against exactly what's on GitHub
4. Review the summary, file list and difference note
5. Click **Backup & confirm replace** — this:
   - copies your entire current working tree into
     `<project>/.backups/<timestamp>_<revision>/` first
   - resets the local branch to exactly match the remote (`git fetch` +
     `git reset --hard origin/<branch>` + `git clean -fd`)
   - verifies local and remote commits now match
   - logs the operation to **Activity**

If anything looks wrong afterward, your previous files are sitting untouched
in that `.backups` folder.

## What gets compared, and how

For every file, file-by-file:

- **Added** — exists only on the new side
- **Deleted** — exists only on the old side
- **Modified** — exists on both sides but the SHA-256 hash differs
- **Unchanged** — hashes match (recorded and verified, not dumped in full)

For text files (`.c .h .cpp .py .md .json .yaml .ini .xml .html .css .js`,
etc. — editable in `backend/config_manager.py`), a line-by-line diff is
computed and each changed block is labeled `MODIFIED`, `ADDED`, or `DELETED`
with its starting line number, in the difference note and the on-screen list.

For binary files (`.bin .hex .elf .png .zip`, and anything else that looks
non-text), the app compares existence, size and SHA-256 instead of trying to
diff content, and marks the entry `BINARY DIFFERENCE`.

## Where things live

```
vcu_git_manager/
  app.py                   Flask backend / API
  backend/
    config_manager.py      Settings persistence (data/config.json)
    git_manager.py          Wraps the git CLI (fetch/push/pull/archive)
    compare_engine.py       File-by-file, line-by-line comparison
    diff_note.py             Builds the DIFFERENCE_x_TO_y.txt text
    backup_manager.py        Snapshots the project before a replace
    activity_log.py          data/activity_log.json history
  static/                   Browser UI (HTML/CSS/JS, no build step)
  data/
    config.json             Your saved settings (created on first save)
    activity_log.json       Operation history (created automatically)
```

`data/` is where all persistent state lives — back that folder up if you
want to preserve your settings and history separately from the projects
themselves.

## Notes and limitations

- This tool is built for the solo/linear workflow described in the original
  requirement (scan → compare → confirm → push, or fetch → compare →
  backup → replace). It does not attempt to resolve merge conflicts; a pull
  always replaces local content with the remote branch's content, backing
  up first.
- Very large files (over ~2 MB by default) are still hashed and sized but
  skip the line-by-line pass to keep scans fast; this threshold is
  configurable in `compare_engine.compare_dirs(max_line_diff_size=...)`.
- The Personal Access Token is stored in plain text in `data/config.json`
  on your own machine — keep that folder as private as you would any file
  containing a password.
