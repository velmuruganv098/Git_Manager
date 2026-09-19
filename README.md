# Local GitHub Manager

A local HTTP server (Python/Flask backend) with a browser UI that replaces
the CMD-based Git/GitHub workflow:

```
CMD                          UI
--------------------         --------------------
git status            ->     Status
git fetch             ->     Fetch
git diff              ->     Scan & Compare
git branch <name>     ->     Upload -> New revision
git add / commit      ->     Upload -> Confirm
git push              ->     Upload -> Confirm
git pull              ->     Pull -> Confirm
```

Every upload or pull is: **scan the whole project → compare it file-by-file
and line-by-line against an existing branch → generate a permanent
difference note → show you exactly what will change → only then commit/push
or backup/replace.**

## Previous revision / New revision = real branch names

This is the core idea: the "Previous revision" and "New revision" fields
you fill in are the **actual git branch names on GitHub**, not just labels.

- **Upload (Local → GitHub)**
  - *Previous revision* = an existing branch to compare against and branch
    off (e.g. `V0.006`). Leave it blank for a first-ever upload.
  - *New revision* = the branch to create and push your local folder to
    (e.g. `V0.007`). It must not already exist — the app checks this both
    on GitHub and against the notes already written locally, and refuses
    to proceed if that revision name is already used.
- **Pull (GitHub → Local)**
  - *New revision* = the existing branch on GitHub to fetch and replace
    your local folder with (e.g. `V0.006`).
  - *Previous revision* = just a label describing what your local copy
    was before the replace. Optional, used only in the note.

Your local project folder itself is never tied to a specific git branch
while you're editing it by hand — you just edit files normally. When you
click **Confirm upload**, the app points the repository at the new branch
and stages exactly what's on disk **without ever checking out, resetting,
or overwriting a single file** — it uses low-level git plumbing
(`git branch`, `git symbolic-ref`, `git read-tree --reset`) so your edits
are always safe, whether they came from this tool or from you typing
directly in your editor.

## Requirements

- Python 3.9+
- [Git](https://git-scm.com/downloads) installed and on your PATH
  (the app shells out to the real `git` binary — it does not reimplement Git)
- A GitHub repository and, if it's private or you want to push, a
  [Personal Access Token](https://github.com/settings/tokens) with `repo` scope

## Running it (Windows)

1. Unzip this folder anywhere, e.g. `D:\Tools\local_github_manager`
   — **this should be a different location from your actual project
   folder.** Don't unzip it directly into your project.
2. Double-click **run.bat**
   - First run creates a local virtual environment and installs Flask
   - It then starts the server and prints `http://127.0.0.1:5757`
3. Open that address in your browser

## Running it (macOS/Linux)

```bash
./run.sh
```

## Worked example

Using the exact setup you'd have for a project like this:

| Setting | Value |
|---|---|
| Local project path | `C:\Projects\Zitto_MB_V1` |
| Project name | `Zitto_MB_V1` |
| GitHub owner | `velmuruganv098` |
| GitHub repository | `Zitto_MB_V1` |
| Existing branches on GitHub | `master`, `V0.005`, `V0.006`, `dev/can1-can2-v0.005`, `dev/can1-v0.004`, `baseline/v0.003-current`, `fix/can1-architecture`, `fix/can-autobaud-rtt`, `baseline/working-can-autobaud` |

To take your locally-edited `C:\Projects\Zitto_MB_V1` folder and publish it
as the next version on top of `V0.006`:

1. **Settings** → set Local project path, Project name, GitHub owner and
   repository as above → **Save settings**.
2. **Status** → click **Prepare repository** (clones/attaches the repo,
   or corrects the remote URL if a previous attempt saved a bad one).
3. **Upload** →
   - *Previous revision*: `V0.006`
   - *New revision*: `V0.007`
   - *Revision notes*: describe what changed
   - **Scan & compare** → review the file list and the generated
     `DIFFERENCE_V0.006_TO_V0.007.txt`
   - **Confirm upload** → creates branch `V0.007` off `V0.006` on GitHub,
     commits your local files exactly as they are, and pushes it. `master`
     and `V0.006` are left completely untouched.

A full example of the generated note is in
[`example_note/DIFFERENCE_V0.006_TO_V0.007.txt`](example_note/DIFFERENCE_V0.006_TO_V0.007.txt).

To instead **pull** `V0.006` down onto a fresh machine:

1. Same Settings as above.
2. **Pull** → *New revision*: `V0.006` → **Fetch, scan & compare** → review
   → **Backup & confirm replace**. Your current local folder is backed up
   to `.backups/` first, then replaced with exactly what's in `V0.006`.

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
local_github_manager/
  app.py                   Flask backend / API
  backend/
    config_manager.py      Settings persistence (data/config.json)
    git_manager.py          Wraps the git CLI (fetch/push/pull/archive/branch)
    compare_engine.py       File-by-file, line-by-line comparison
    diff_note.py             Builds the DIFFERENCE_x_TO_y.txt text
    backup_manager.py        Snapshots the project before a replace
    activity_log.py          data/activity_log.json history
  static/                   Browser UI (HTML/CSS/JS, no build step)
  example_note/             A worked example difference note
  data/
    config.json             Your saved settings (created on first save)
    activity_log.json       Operation history (created automatically)
```

`data/` is where all persistent state lives. **When you upgrade this app
later, only replace `app.py`, `backend/`, and `static/` — leave your
`data/` folder in place — so your saved settings and activity history
carry over.** If you unzip a fresh copy into a new folder instead, it will
start with empty settings, since `data/config.json` lives inside this
folder.

## Troubleshooting

- **"Set a Local Project Path in Settings first."** — Settings weren't
  saved yet in *this* copy of the app, or you're running a different
  folder than the one you configured. Check Settings and click
  **Save settings** again.
- **"This folder is not a git repository yet."** — go to **Status** and
  click **Prepare repository**.
- **Remote URL looks wrong / has `github.com` appearing twice** — this
  happens if a full URL was pasted into the Repository field in an older
  version. Put just the repo name (e.g. `Zitto_MB_V1`) in Repository and
  just the account name (e.g. `velmuruganv098`) in Owner, then click
  **Prepare repository** again on the Status tab — it will detect and fix
  a mismatched remote URL automatically.
- **"Branch '...' already exists on GitHub."** — you tried to reuse a New
  revision / branch name that's already on GitHub. Pick an unused one
  (e.g. bump `V0.007` → `V0.008`).
- **Local project path** should point at the project itself (e.g.
  `C:\Projects\Zitto_MB_V1`), never at the folder this app is unzipped
  into.

## Notes and limitations

- This tool does not attempt to resolve merge conflicts; a pull always
  replaces local content with the chosen branch's content, backing up
  first. Upload always creates or updates a single named branch rather
  than merging.
- Very large files (over ~2 MB by default) are still hashed and sized but
  skip the line-by-line pass to keep scans fast; this threshold is
  configurable in `compare_engine.compare_dirs(max_line_diff_size=...)`.
- The Personal Access Token is stored in plain text in `data/config.json`
  on your own machine — keep that folder as private as you would any file
  containing a password.
