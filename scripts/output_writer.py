#!/usr/bin/env python3
"""
output_writer.py — Output Writer
Part of the ghost-commit skill.

Writes decision logs, updates CHANGELOG.md, and copies PR descriptions.

Usage:
    python output_writer.py --decision-log content.md --dir .decisions --date 2026-06-07 --hash a3f9c12
    python output_writer.py --changelog "- Fix session bug" --category Fixed --file CHANGELOG.md
    python output_writer.py --init-changelog CHANGELOG.md
"""

import sys
import re
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path


# ── Decision Log Writer ───────────────────────────────────────────────────────

def write_decision_log(
    content: str,
    directory: str,
    date: str,
    short_hash: str,
) -> str:
    """
    Write decision log markdown to .decisions/YYYY-MM-DD-<hash>.md.
    Returns the path written to.
    """
    decisions_dir = Path(directory)
    decisions_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{date}-{short_hash}.md"
    filepath = decisions_dir / filename

    # If file already exists (e.g., re-run), increment suffix
    if filepath.exists():
        i = 1
        while filepath.exists():
            filename = f"{date}-{short_hash}-{i}.md"
            filepath = decisions_dir / filename
            i += 1

    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def update_decision_log_hash(filepath: Path, full_hash: str, short_hash: str):
    """Update the `unknown` placeholder hash in a decision log after commit."""
    if not filepath.exists():
        return
    content = filepath.read_text(encoding="utf-8")
    content = content.replace("`unknown`", f"`{short_hash}`")
    content = content.replace("unknown", full_hash, 1)  # Full hash first occurrence
    filepath.write_text(content, encoding="utf-8")

    # Rename file with real hash
    new_name = filepath.parent / filepath.name.replace("unknown", short_hash)
    if new_name != filepath and not new_name.exists():
        filepath.rename(new_name)


# ── CHANGELOG Writer ──────────────────────────────────────────────────────────

CHANGELOG_HEADER = """\
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

"""

CATEGORY_ORDER = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]


def init_changelog(filepath: str) -> bool:
    """Create a new CHANGELOG.md with the standard header."""
    path = Path(filepath)
    if path.exists():
        return False
    path.write_text(CHANGELOG_HEADER, encoding="utf-8")
    return True


def update_changelog(
    entry: str,
    category: str,
    filepath: str = "CHANGELOG.md",
    section: str = "Unreleased",
) -> bool:
    """
    Insert a new entry under the correct category in [Unreleased].
    Creates the CHANGELOG if it doesn't exist.
    Returns True on success.
    """
    path = Path(filepath)

    if not path.exists():
        # Create with standard header
        path.write_text(CHANGELOG_HEADER, encoding="utf-8")

    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")

    # Find [Unreleased] section
    unreleased_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^##\s+\[Unreleased\]", line, re.I):
            unreleased_idx = i
            break

    if unreleased_idx is None:
        # Add [Unreleased] section at the top (after the header)
        header_end = 0
        for i, line in enumerate(lines):
            if line.startswith("##"):
                header_end = i
                break
        lines.insert(header_end, "\n## [Unreleased]\n")
        unreleased_idx = header_end

    # Find the boundary of [Unreleased] — next ## [version] line
    next_version_idx = len(lines)
    for i in range(unreleased_idx + 1, len(lines)):
        if re.match(r"^##\s+\[", lines[i]) and not re.match(r"^##\s+\[Unreleased\]", lines[i], re.I):
            next_version_idx = i
            break

    # Search for existing category header within [Unreleased]
    cat_idx = None
    for i in range(unreleased_idx + 1, next_version_idx):
        if re.match(rf"^###\s+{category}", lines[i]):
            cat_idx = i
            break

    if cat_idx is not None:
        # Find the last entry in this category
        insert_at = cat_idx + 1
        for i in range(cat_idx + 1, next_version_idx):
            if lines[i].startswith("- ") or lines[i].startswith("* "):
                insert_at = i + 1
            elif lines[i].startswith("###") or re.match(r"^##\s+\[", lines[i]):
                break
        lines.insert(insert_at, entry)
    else:
        # Create new category in the right position per CATEGORY_ORDER
        cat_position = CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else len(CATEGORY_ORDER)

        # Find where to insert this category among existing ones
        insert_after = unreleased_idx + 1
        for existing_cat in CATEGORY_ORDER[:cat_position]:
            for i in range(unreleased_idx + 1, next_version_idx):
                if re.match(rf"^###\s+{existing_cat}", lines[i]):
                    # Skip past this category's entries
                    j = i + 1
                    while j < next_version_idx and not lines[j].startswith("###"):
                        j += 1
                    insert_after = j
                    break

        # Insert category and entry
        new_block = [f"### {category}", entry, ""]
        for item in reversed(new_block):
            lines.insert(insert_after, item)

    path.write_text("\n".join(lines), encoding="utf-8")
    return True


def read_changelog_unreleased(filepath: str = "CHANGELOG.md") -> str:
    """Read the [Unreleased] section content."""
    path = Path(filepath)
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    m = re.search(
        r"##\s+\[Unreleased\](.*?)(?=\n##\s+\[|\Z)",
        content, re.DOTALL | re.IGNORECASE
    )
    return m.group(1).strip() if m else ""


# ── Clipboard Writer ──────────────────────────────────────────────────────────

def copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard. Returns True on success."""
    commands = {
        "darwin": ["pbcopy"],
        "linux":  [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["wl-copy"]],
        "win32":  ["clip"],
    }

    import sys
    platform = sys.platform

    if platform == "darwin":
        try:
            proc = subprocess.Popen(commands["darwin"], stdin=subprocess.PIPE)
            proc.communicate(text.encode("utf-8"))
            return proc.returncode == 0
        except FileNotFoundError:
            return False

    elif platform.startswith("linux"):
        for cmd in commands["linux"]:
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                proc.communicate(text.encode("utf-8"))
                if proc.returncode == 0:
                    return True
            except (FileNotFoundError, OSError):
                continue
        return False

    elif platform == "win32":
        try:
            proc = subprocess.Popen(commands["win32"], stdin=subprocess.PIPE, shell=True)
            proc.communicate(text.encode("utf-8"))
            return proc.returncode == 0
        except Exception:
            return False

    return False


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Write ghost-commit outputs to disk.")

    subparsers = parser.add_subparsers(dest="command")

    # decision-log subcommand
    dl = subparsers.add_parser("decision-log", help="Write a decision log file")
    dl.add_argument("--content", required=True, help="Markdown content or path to .md file")
    dl.add_argument("--dir", default=".decisions", help="Output directory")
    dl.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    dl.add_argument("--hash", required=True, help="Short commit hash")

    # changelog subcommand
    cl = subparsers.add_parser("changelog", help="Update CHANGELOG.md")
    cl.add_argument("--entry", required=True, help="Entry text (e.g. '- Fix session bug')")
    cl.add_argument("--category", required=True, choices=CATEGORY_ORDER)
    cl.add_argument("--file", default="CHANGELOG.md")
    cl.add_argument("--section", default="Unreleased")

    # init-changelog subcommand
    ic = subparsers.add_parser("init-changelog", help="Create new CHANGELOG.md")
    ic.add_argument("--file", default="CHANGELOG.md")

    # clipboard subcommand
    cb = subparsers.add_parser("clipboard", help="Copy text to clipboard")
    cb.add_argument("--text", help="Text to copy")
    cb.add_argument("--file", help="File to copy contents of")

    args = parser.parse_args()

    if args.command == "decision-log":
        content = args.content
        try:
            p = Path(content)
            if p.exists() and p.is_file():
                content = p.read_text(encoding="utf-8")
        except (OSError, ValueError):
            pass  # Content is inline text, not a file path
        path = write_decision_log(content, args.dir, args.date, args.hash)
        print(f"✓ Decision log written: {path}")

    elif args.command == "changelog":
        ok = update_changelog(args.entry, args.category, args.file, args.section)
        if ok:
            print(f"✓ CHANGELOG updated: {args.file}")
        else:
            print(f"✗ Failed to update {args.file}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "init-changelog":
        ok = init_changelog(args.file)
        if ok:
            print(f"✓ Created {args.file}")
        else:
            print(f"⚠ {args.file} already exists")

    elif args.command == "clipboard":
        text = args.text or (Path(args.file).read_text() if args.file else "")
        ok = copy_to_clipboard(text)
        print("✓ Copied to clipboard" if ok else "✗ Clipboard copy failed")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
