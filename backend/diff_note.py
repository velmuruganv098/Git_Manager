"""
Builds the plain-text DIFFERENCE_<FROM>_TO_<TO>.txt document described in
the requirement: a permanent, human-readable revision record that travels
with the code, separate from - but alongside - the automatically detected
diff.
"""

from datetime import datetime

LINE = "=" * 60
THIN = "-" * 60


def _fmt_size(n):
    return "N/A" if n is None else f"{n:,} bytes"


def _fmt_lines(n):
    return "N/A" if n is None else f"{n:,}"


def build_diff_note(comparison, meta):
    """
    comparison: dict returned by compare_engine.compare_dirs
    meta: {
        project_name, from_rev, to_rev, branch, direction,
        user_notes, source_label, dest_label
    }
    """
    s = comparison["summary"]
    files = comparison["files"]
    out = []

    out.append(LINE)
    out.append("PROJECT REVISION DIFFERENCE")
    out.append(LINE)
    out.append("")
    out.append(f"PROJECT:\n{meta.get('project_name', '')}")
    out.append("")
    out.append(f"FROM:\n{meta.get('from_rev', '')}")
    out.append("")
    out.append(f"TO:\n{meta.get('to_rev', '')}")
    out.append("")
    out.append(f"DATE:\n{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
    out.append("")
    out.append(f"BRANCH:\n{meta.get('branch', '')}")
    out.append("")
    out.append(f"DIRECTION:\n{meta.get('direction', '')}")
    out.append("")
    out.append(f"SOURCE:\n{meta.get('source_label', '')}")
    out.append("")
    out.append(f"DESTINATION:\n{meta.get('dest_label', '')}")

    if meta.get("user_notes"):
        out.append("")
        out.append(LINE)
        out.append("REVISION NOTES (author-entered - what was intended/done)")
        out.append(LINE)
        out.append(meta["user_notes"].strip())

    out.append("")
    out.append(LINE)
    out.append("SUMMARY (automatically detected - what actually changed)")
    out.append(LINE)
    out.append("")
    out.append(f"Files Checked     : {s['files_checked']}")
    out.append(f"Unchanged         : {s['unchanged']}")
    out.append(f"Modified          : {s['modified']}")
    out.append(f"Added             : {s['added']}")
    out.append(f"Deleted           : {s['deleted']}")
    out.append("")
    out.append(f"Lines Added       : {s['lines_added']}")
    out.append(f"Lines Deleted     : {s['lines_deleted']}")
    out.append("")
    out.append(LINE)
    out.append("FILE DIFFERENCES")
    out.append(LINE)

    changed = [f for f in files if f["status"] != "UNCHANGED"]
    unchanged = [f for f in files if f["status"] == "UNCHANGED"]

    idx = 0
    for f in changed:
        idx += 1
        out.append("")
        out.append(f"[{idx}] {f['path']}")
        out.append(THIN)
        out.append("")
        out.append(f"STATUS:\n{f['status']}")
        out.append("")

        if f["binary"]:
            out.append("TYPE:\nBINARY DIFFERENCE (size/hash compared, not line content)")
            out.append("")

        out.append(f"OLD SIZE:\n{_fmt_size(f['old_size'])}")
        out.append("")
        out.append(f"NEW SIZE:\n{_fmt_size(f['new_size'])}")
        out.append("")
        if not f["binary"]:
            out.append(f"OLD LINES:\n{_fmt_lines(f['old_lines'])}")
            out.append("")
            out.append(f"NEW LINES:\n{_fmt_lines(f['new_lines'])}")
            out.append("")
        out.append(f"OLD SHA-256:\n{f['old_sha256'] or 'FILE DOES NOT EXIST'}")
        out.append("")
        out.append(f"NEW SHA-256:\n{f['new_sha256'] or 'FILE DOES NOT EXIST'}")

        if f["line_blocks"]:
            out.append("")
            out.append(THIN)
            out.append("LINE DIFFERENCE")
            out.append(THIN)
            for b in f["line_blocks"]:
                out.append("")
                if b["type"] == "TRUNCATED":
                    out.append("... (further differences in this file omitted for length) ...")
                    continue
                out.append(f"STATUS: {b['type']}")
                if b["old_lines"]:
                    out.append(f"OLD (from line {b['old_start']}):")
                    for l in b["old_lines"][:20]:
                        out.append(f"  {l}")
                if b["new_lines"]:
                    out.append(f"NEW (from line {b['new_start']}):")
                    for l in b["new_lines"][:20]:
                        out.append(f"  {l}")
        out.append("")
        out.append(LINE)

    if unchanged:
        out.append("")
        out.append("UNCHANGED FILES (verified, content identical)")
        out.append(THIN)
        for f in unchanged:
            out.append(f"{f['path']}  -  SIZE: SAME  -  SHA256: SAME")
        out.append("")
        out.append(LINE)

    return "\n".join(out) + "\n"
