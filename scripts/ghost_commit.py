#!/usr/bin/env python3
"""
ghost_commit.py — Main Orchestrator
Part of the ghost-commit skill.

Every commit tells you what changed. ghost-commit tells you why.

Usage:
    python ghost_commit.py --run                     # Full interactive flow
    python ghost_commit.py --hook-mode pre           # Called by pre-commit hook
    python ghost_commit.py --hook-mode post          # Called by post-commit hook
    python ghost_commit.py --print-config            # Show resolved config
    python ghost_commit.py --context                 # Open .ghost-context for editing
    python ghost_commit.py --status                  # Show current git state
"""

import sys
import os
import json
import argparse
import subprocess
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

# ── Locate skill root ────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent
ASSETS_DIR = SKILL_DIR / "assets"

# ── Default config ────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "outputs": {
        "commit_message": True,
        "decision_log": True,
        "changelog": True,
        "pr_description": True,
    },
    "decisions": {
        "directory": ".decisions",
        "gitignore": True,
        "commit_logs": False,
    },
    "changelog": {
        "file": "CHANGELOG.md",
        "auto_update": True,
        "section": "Unreleased",
    },
    "commit": {
        "max_subject_length": 72,
        "enforce_conventional": True,
        "require_scope": False,
    },
    "context": {
        "scratchpad_file": ".ghost-context",
        "clear_after_commit": True,
        "template_reprompt": True,
    },
    "skip": {
        "branches": ["main", "master", "release/*"],
        "commit_patterns": ["^Merge", "^Revert", "^WIP"],
        "file_patterns": ["*.lock", "*.min.js", "dist/*", "*.map"],
    },
}

# ── ANSI ─────────────────────────────────────────────────────────────────────
BOLD    = "\033[1m"
DIM     = "\033[2m"
CYAN    = "\033[36m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
RESET   = "\033[0m"
GHOST   = "👻"

def ansi(text: str, *codes: str) -> str:
    if not sys.stdout.isatty():
        return text
    return "".join(codes) + text + RESET

def header(title: str):
    width = 60
    bar = "─" * width
    print(f"\n{ansi(bar, CYAN)}")
    print(f"{ansi(f'  {GHOST}  ghost-commit — {title}', BOLD + CYAN)}")
    print(f"{ansi(bar, CYAN)}\n")

def section(title: str):
    print(f"\n{ansi('─── ' + title + ' ' + '─' * max(0, 56 - len(title)), DIM)}")

def success(msg: str): print(f"{ansi('✓', GREEN + BOLD)} {msg}")
def warn(msg: str):    print(f"{ansi('⚠', YELLOW + BOLD)} {msg}")
def error(msg: str):   print(f"{ansi('✗', RED + BOLD)} {msg}", file=sys.stderr)
def info(msg: str):    print(f"{ansi('·', DIM)} {msg}")

# ── Git helpers ───────────────────────────────────────────────────────────────

def git(*args: str, check: bool = True) -> str:
    """Run a git command and return stdout."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, check=check
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return ""
    except FileNotFoundError:
        error("git not found — is git installed?")
        sys.exit(1)

def is_git_repo() -> bool:
    return bool(git("rev-parse", "--git-dir", check=False))

def is_merge_commit() -> bool:
    return Path(".git/MERGE_HEAD").exists()

def is_revert_commit() -> bool:
    return Path(".git/REVERT_HEAD").exists()

def get_staged_stat() -> str:
    return git("diff", "--staged", "--stat")

def get_staged_diff() -> str:
    return git("diff", "--staged")

def get_current_branch() -> str:
    return git("branch", "--show-current")

def get_recent_commits(n: int = 5) -> str:
    return git("log", "--oneline", f"-{n}")

def get_short_hash() -> str:
    return git("rev-parse", "--short", "HEAD") or "unknown"

def get_full_hash() -> str:
    return git("rev-parse", "HEAD") or "unknown"

def get_author_name() -> str:
    return git("config", "user.name") or os.environ.get("GIT_AUTHOR_NAME", "Unknown")

def get_author_email() -> str:
    return git("config", "user.email") or os.environ.get("GIT_AUTHOR_EMAIL", "")

def get_staged_files() -> list[str]:
    output = git("diff", "--staged", "--name-only")
    return [f for f in output.split("\n") if f.strip()]

def write_commit_msg(message: str):
    """Write message to COMMIT_EDITMSG so git picks it up."""
    git_dir = git("rev-parse", "--git-dir")
    msg_file = Path(git_dir) / "COMMIT_EDITMSG"
    msg_file.write_text(message, encoding="utf-8")

# ── Config loader ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    config_file = Path(".ghost-commit.yml")
    if config_file.exists():
        try:
            import re
            # Simple YAML-ish parser for our known config shape
            # (stdlib only — no PyYAML dependency)
            content = config_file.read_text()
            # Parse booleans and strings — sufficient for our config schema
            for line in content.split("\n"):
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    key, _, val = line.partition(":")
                    val = val.strip()
                    if val.lower() == "true":   val = True
                    elif val.lower() == "false": val = False
                    # Flat key override only (good enough for most settings)
                    for section_name, section_data in config.items():
                        if isinstance(section_data, dict) and key.strip() in section_data:
                            section_data[key.strip()] = val
        except Exception:
            pass  # Use defaults on any parse error
    return config

# ── Skip detection ────────────────────────────────────────────────────────────

def should_skip(config: dict) -> tuple[bool, str]:
    """Return (should_skip, reason)."""
    import fnmatch

    if is_merge_commit():
        return True, "merge commit detected — ghost-commit skipped"

    if is_revert_commit():
        return True, "revert commit detected — ghost-commit skipped"

    branch = get_current_branch()
    for pattern in config["skip"]["branches"]:
        if fnmatch.fnmatch(branch, pattern):
            return True, f"branch '{branch}' matches skip pattern '{pattern}'"

    staged = get_staged_stat()
    if not staged:
        return True, "nothing staged"

    return False, ""

# ── Branch analysis ───────────────────────────────────────────────────────────

def should_generate_pr(branch: str, config: dict) -> bool:
    """Return True if this branch warrants a PR description."""
    pr_patterns = [
        r"feature/", r"feat/", r"fix/", r"bugfix/", r"hotfix/",
        r"improve/", r"enhancement/", r"task/", r"issue/",
    ]
    import re
    return any(re.match(p, branch) for p in pr_patterns) or "/" in branch

# ── Analysis runner ───────────────────────────────────────────────────────────

def run_analysis() -> dict:
    """Run all analysis scripts and return structured data."""
    from diff_analyzer import analyze_diff
    from context_reader import read_context

    diff = get_staged_diff()
    stat = get_staged_stat()
    files = get_staged_files()
    branch = get_current_branch()
    recent = get_recent_commits()

    # Diff analysis
    analysis = analyze_diff(diff, files)

    # Context reading
    context = read_context()

    return {
        "diff": diff,
        "stat": stat,
        "files": files,
        "branch": branch,
        "recent_commits": recent,
        "author_name": get_author_name(),
        "author_email": get_author_email(),
        "short_hash": get_short_hash(),
        "analysis": analysis,
        "context": context,
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

# ── Output generators ─────────────────────────────────────────────────────────

def generate_commit_message(data: dict, config: dict) -> str:
    """Generate conventional commit message from analysis data."""
    a = data["analysis"]
    ctx = data["context"]

    commit_type  = a.get("type", "chore")
    scope        = a.get("scope")
    breaking     = a.get("breaking_change", False)
    risk         = a.get("risk_level", "Low")

    # Subject line
    type_str = f"{commit_type}!" if breaking else commit_type
    scope_str = f"({scope})" if scope else ""
    
    # Build description
    description = ctx.get("summary") or a.get("description", "update code")
    
    # Enforce max length on subject
    max_len = config["commit"]["max_subject_length"]
    subject = f"{type_str}{scope_str}: {description}"
    if len(subject) > max_len:
        description = description[:max_len - len(f"{type_str}{scope_str}: ") - 3] + "..."
        subject = f"{type_str}{scope_str}: {description}"

    parts = [subject]

    # Body — only if complex change or context provides why
    why = ctx.get("why", "").strip()
    if why and commit_type not in ("style", "test", "chore", "docs"):
        # Wrap at 100 chars
        import textwrap
        wrapped = textwrap.fill(why, width=100)
        parts.append("")
        parts.append(wrapped)

    # Footer
    footers = []
    if breaking:
        breaking_desc = ctx.get("breaking_description", "See migration guide.")
        footers.append(f"BREAKING CHANGE: {breaking_desc}")

    refs = ctx.get("references", "").strip()
    if refs:
        for ref in refs.split(","):
            ref = ref.strip()
            if ref.startswith("#"):
                footers.append(f"Closes {ref}")
            elif ref:
                footers.append(f"Refs {ref}")

    if footers:
        parts.append("")
        parts.extend(footers)

    return "\n".join(parts)


def generate_decision_log(data: dict, config: dict) -> str:
    """Generate decision log markdown."""
    a   = data["analysis"]
    ctx = data["context"]
    
    risk = a.get("risk_level", "Low")
    date = data["date"]
    short_hash = data["short_hash"]
    
    ctx_quality = ctx.get("quality", "LOW")
    
    # Title from context summary or description
    title = ctx.get("summary") or a.get("description", "Code change")

    sections = []
    sections.append(f"# Decision: {title} — {date}\n")

    if risk == "High":
        sections.append("> ⚠️ **HIGH RISK CHANGE** — Review carefully before merging\n")

    # Metadata
    sections.append(f"**Commit:** `{short_hash}`")
    sections.append(f"**Author:** {data['author_name']} <{data['author_email']}>")
    sections.append(f"**Branch:** `{data['branch']}`")
    
    files = data.get("files", [])
    ins = a.get("insertions", 0)
    dels = a.get("deletions", 0)
    sections.append(f"**Files changed:** {len(files)} files, +{ins} −{dels} lines")
    sections.append(f"**Risk level:** {risk}")
    sections.append(f"**Change type:** {a.get('type', 'chore')}")
    sections.append("")
    sections.append("---")
    sections.append("")

    # Context
    sections.append("## Context\n")
    why = ctx.get("why", "").strip()
    if why:
        sections.append(why)
    else:
        sections.append(
            f"*Inferred from diff analysis — no .ghost-context provided.*\n\n"
            f"This change modifies `{'`, `'.join(files[:3])}`. "
            f"Run `python ghost_commit.py --context` before committing to add context."
        )
    sections.append("")

    # Decision
    sections.append("## Decision\n")
    decision = ctx.get("decision", "").strip()
    if not decision:
        # Build from diff analysis
        chg_type = a.get("type", "chore")
        desc = a.get("description", "code updated")
        if chg_type == "feat":
            decision = f"Added {desc}."
        elif chg_type == "fix":
            decision = f"Fixed {desc} by correcting the underlying issue."
        else:
            decision = f"Updated code: {desc}."
    sections.append(decision)
    sections.append("")

    # Alternatives
    sections.append("## Alternatives considered\n")
    alts = ctx.get("tried", "").strip()
    if alts:
        sections.append(alts)
    else:
        sections.append(
            "_Not documented. Use the `# What I tried first` section in `.ghost-context` "
            "to capture this valuable context._"
        )
    sections.append("")

    # Constraints
    sections.append("## Constraints\n")
    constraints = ctx.get("constraints", "").strip()
    sections.append(constraints if constraints else "_Not documented._")
    sections.append("")

    # Security section for high-risk
    if risk == "High":
        sections.append("## Security / Privacy implications\n")
        security = ctx.get("security", "").strip()
        sections.append(security if security else "_Review required — high-risk change detected._")
        sections.append("")

    # Future implications — infer from TODO/FIXME in diff
    sections.append("## Future implications\n")
    todos = _extract_todos(data.get("diff", ""))
    implications = ctx.get("implications", "").strip()
    if implications:
        sections.append(implications)
    if todos:
        sections.append("\nTODOs/FIXMEs in this commit:")
        for todo in todos:
            sections.append(f"- {todo}")
    if not implications and not todos:
        sections.append("_None identified._")
    sections.append("")

    # References
    sections.append("## References\n")
    refs = ctx.get("references", "").strip()
    sections.append(refs if refs else "_None provided._")
    sections.append("")
    sections.append("---")
    sections.append(
        f"_Generated by ghost-commit v1.0.0 | {data['timestamp']}_  \n"
        f"_Context quality: {ctx_quality}_"
    )

    return "\n".join(sections)


def generate_changelog_entry(data: dict) -> tuple[str, str]:
    """Return (category, entry_line)."""
    TYPE_TO_CATEGORY = {
        "feat": "Added",
        "fix": "Fixed",
        "perf": "Changed",
        "refactor": "Changed",
        "docs": "Changed",
        "security": "Security",
        "remove": "Removed",
        "deprecated": "Deprecated",
    }
    a = data["analysis"]
    ctx = data["context"]
    commit_type = a.get("type", "chore")

    category = TYPE_TO_CATEGORY.get(commit_type)
    if not category:
        return None, None  # Skip types not user-visible

    desc = ctx.get("summary") or a.get("description", "Code updated")
    
    # User-facing phrasing
    if category == "Added":
        entry = f"Add {desc}"
    elif category == "Fixed":
        entry = f"Fix {desc}"
    elif category == "Changed":
        entry = f"Update {desc}"
    elif category == "Removed":
        entry = f"Remove {desc}"
    elif category == "Security":
        entry = f"Fix security issue: {desc}"
    else:
        entry = desc
    
    entry = entry[0].upper() + entry[1:]  # Capitalize first letter

    # Add issue reference
    refs = ctx.get("references", "").strip()
    branch = data.get("branch", "")
    import re
    issue_match = re.search(r"[#/](\d+)", refs + "/" + branch)
    if issue_match:
        entry += f" (#{issue_match.group(1)})"

    return category, f"- {entry}"


def generate_pr_description(data: dict) -> str:
    """Generate PR description markdown."""
    a   = data["analysis"]
    ctx = data["context"]

    title = ctx.get("summary") or a.get("description", "Code change")
    why = ctx.get("why", "_Not provided — add context in .ghost-context._")
    
    files = data.get("files", [])
    changes = []
    for f in files[:10]:
        changes.append(f"- `{f}`")
    if len(files) > 10:
        changes.append(f"- _...and {len(files) - 10} more files_")

    branch = data.get("branch", "")
    import re
    issue_match = re.search(r"[#/](\d+)", branch + ctx.get("references", ""))
    closes_line = f"\nCloses #{issue_match.group(1)}" if issue_match else ""

    has_tests = any(re.search(r"test|spec", f, re.I) for f in files)
    test_check = "- [x] Tests included" if has_tests else "- [ ] Tests needed"

    breaking = a.get("breaking_change", False)
    breaking_section = (
        f"\n## Breaking changes\n\n"
        f"{ctx.get('breaking_description', 'See description above.')}"
        if breaking else
        "\n## Breaking changes\n\nNone."
    )

    return f"""## What does this PR do?

{title[0].upper() + title[1:]}.

## Why?

{why}

## Changes

{"chr(10).join(changes)}

## How to test

{ctx.get('testing', '1. Pull this branch\\n2. Run the test suite\\n3. Verify the described behavior')}

## Checklist

{test_check}
- [ ] No regressions in related functionality
- [ ] Documentation updated (if applicable)
- [ ] Breaking changes documented (if applicable)
{breaking_section}

## References
{closes_line or '_None_'}
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_todos(diff: str) -> list[str]:
    """Extract TODO/FIXME/HACK lines added in the diff."""
    import re
    todos = []
    for line in diff.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            m = re.search(r"(TODO|FIXME|HACK|XXX|NOTE)[:\s]+(.+)", line, re.I)
            if m:
                todos.append(m.group(2).strip()[:120])
    return todos[:5]  # Cap at 5

# ── Presentation & Approval ───────────────────────────────────────────────────

def present_and_approve(
    commit_msg: str,
    decision_log: str,
    changelog_entry: tuple,
    pr_description: str,
    data: dict,
    config: dict,
) -> str:
    """Show all outputs and get developer approval. Returns choice."""

    header("Review generated outputs")

    section("COMMIT MESSAGE")
    print(commit_msg)

    section("DECISION LOG")
    short_hash = data["short_hash"]
    date = data["date"]
    decisions_dir = config["decisions"]["directory"]
    log_path = f"{decisions_dir}/{date}-{short_hash}.md"
    info(f"Will be saved to: {log_path}")
    # Show preview (first 15 lines)
    preview = "\n".join(decision_log.split("\n")[:15])
    print(preview)
    if decision_log.count("\n") > 15:
        print(ansi("  [... truncated — full log saved to file ...]", DIM))

    cat, entry = changelog_entry
    if cat and entry:
        section("CHANGELOG ENTRY")
        changelog_file = config["changelog"]["file"]
        info(f"Will be inserted under [{config['changelog']['section']}] → ### {cat} in {changelog_file}")
        print(entry)

    if pr_description:
        section("PR DESCRIPTION")
        pr_preview = "\n".join(pr_description.split("\n")[:12])
        print(pr_preview)
        if pr_description.count("\n") > 12:
            print(ansi("  [... truncated — full draft will be copied to clipboard ...]", DIM))

    section("ACTION")
    print(f"""
  {ansi('[A]', BOLD + GREEN)} Accept all — apply all outputs
  {ansi('[E]', BOLD + YELLOW)} Edit — open in $EDITOR then re-present
  {ansi('[S]', BOLD + CYAN)} Select — choose which outputs to apply
  {ansi('[R]', BOLD + RED)} Reject — exit, write your own commit message
  {ansi('[?]', DIM)} Help
""")

    try:
        choice = input(f"  {ansi(GHOST, CYAN)} Your choice: ").strip().upper()
    except (EOFError, KeyboardInterrupt):
        print()
        return "R"

    return choice or "A"


def apply_outputs(
    choice: str,
    commit_msg: str,
    decision_log: str,
    changelog_entry: tuple,
    pr_description: str,
    data: dict,
    config: dict,
):
    """Apply chosen outputs to disk."""
    from output_writer import (
        write_decision_log,
        update_changelog,
        copy_to_clipboard,
    )

    if choice == "R":
        warn("Rejected — no outputs applied. Proceeding with manual commit message.")
        return

    apply_commit  = True
    apply_log     = True
    apply_changes = True
    apply_pr      = bool(pr_description)

    if choice == "S":
        print("\nSelect outputs to apply (press Enter to toggle, empty line to confirm):")
        apply_commit  = _confirm(f"  Apply commit message?", True)
        apply_log     = _confirm(f"  Apply decision log?", True)
        apply_changes = _confirm(f"  Apply CHANGELOG entry?", True)
        if pr_description:
            apply_pr = _confirm(f"  Copy PR description to clipboard?", True)

    if choice == "E":
        commit_msg = _edit_in_editor(commit_msg, "commit_message")

    if apply_commit:
        write_commit_msg(commit_msg)
        success("Commit message written")

    if apply_log:
        short_hash = data["short_hash"]
        date = data["date"]
        decisions_dir = config["decisions"]["directory"]
        log_path = write_decision_log(decision_log, decisions_dir, date, short_hash)
        success(f"Decision log saved → {log_path}")

        # Ensure .decisions/ is in .gitignore if configured
        if config["decisions"]["gitignore"]:
            _ensure_gitignore(decisions_dir)

    cat, entry = changelog_entry
    if apply_changes and cat and entry:
        changelog_file = config["changelog"]["file"]
        section_name = config["changelog"]["section"]
        result = update_changelog(entry, cat, changelog_file, section_name)
        if result:
            success(f"CHANGELOG.md updated → {cat}: {entry}")
        else:
            warn(f"Could not update {changelog_file} — check file exists")

    if apply_pr and pr_description:
        copied = copy_to_clipboard(pr_description)
        if copied:
            success("PR description copied to clipboard")
        else:
            info("PR description (copy manually):")
            print(pr_description)


def _confirm(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        resp = input(f"{prompt} {suffix}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default
    if not resp:
        return default
    return resp.startswith("y")


def _edit_in_editor(content: str, suffix: str) -> str:
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=f"_{suffix}.md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        tmp = f.name
    os.system(f"{editor} {tmp}")
    result = Path(tmp).read_text(encoding="utf-8")
    Path(tmp).unlink(missing_ok=True)
    return result


def _ensure_gitignore(path: str):
    gitignore = Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text()
        if path not in content:
            with gitignore.open("a") as f:
                f.write(f"\n# ghost-commit decision logs\n{path}/\n.ghost-context\n")
    else:
        gitignore.write_text(f"# ghost-commit decision logs\n{path}/\n.ghost-context\n")

# ── Context editor ────────────────────────────────────────────────────────────

def open_context_editor(config: dict):
    """Open .ghost-context in $EDITOR for developer to fill in."""
    from context_reader import write_template
    ctx_file = config["context"]["scratchpad_file"]
    write_template(ctx_file)
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))
    os.system(f"{editor} {ctx_file}")

# ── Main entry points ─────────────────────────────────────────────────────────

def run_interactive(config: dict):
    """Full interactive flow — Mode B (manual run)."""
    header("pre-commit analysis")

    skip, reason = should_skip(config)
    if skip:
        info(reason)
        sys.exit(0)

    branch = get_current_branch()
    info(f"Branch: {branch}")
    info(f"Staged: {get_staged_stat().split(chr(10))[0]}")

    print(f"\n{ansi('Analyzing diff...', DIM)}")

    try:
        data = run_analysis()
    except Exception as e:
        error(f"Analysis failed: {e}")
        sys.exit(0)  # Fail open — don't block commit

    config_pr = config["outputs"]["pr_description"]
    generate_pr = config_pr and should_generate_pr(branch, config)

    commit_msg     = generate_commit_message(data, config)
    decision_log   = generate_decision_log(data, config)
    changelog_item = generate_changelog_entry(data)
    pr_desc        = generate_pr_description(data) if generate_pr else None

    choice = present_and_approve(
        commit_msg, decision_log, changelog_item, pr_desc, data, config
    )
    apply_outputs(
        choice, commit_msg, decision_log, changelog_item, pr_desc, data, config
    )


def run_hook_pre(config: dict):
    """Called by pre-commit hook — non-interactive, fast."""
    skip, reason = should_skip(config)
    if skip:
        info(reason)
        sys.exit(0)

    # In hook mode: run analysis, write outputs if confidence is high,
    # otherwise prompt briefly
    try:
        data = run_analysis()
        branch = get_current_branch()
        commit_msg     = generate_commit_message(data, config)
        decision_log   = generate_decision_log(data, config)
        changelog_item = generate_changelog_entry(data)
        pr_desc = generate_pr_description(data) if should_generate_pr(branch, config) else None
        
        choice = present_and_approve(
            commit_msg, decision_log, changelog_item, pr_desc, data, config
        )
        apply_outputs(
            choice, commit_msg, decision_log, changelog_item, pr_desc, data, config
        )
    except Exception as e:
        warn(f"ghost-commit encountered an error: {e}")
        warn("Proceeding with manual commit message.")
        sys.exit(0)  # Always fail open in hook mode


def run_hook_post(config: dict):
    """Called by post-commit hook — update decision log with real hash."""
    from output_writer import update_decision_log_hash
    real_hash = get_full_hash()
    short_hash = real_hash[:7]
    date = datetime.now().strftime("%Y-%m-%d")
    decisions_dir = config["decisions"]["directory"]
    log_path = Path(decisions_dir) / f"{date}-unknown.md"
    if log_path.exists():
        update_decision_log_hash(log_path, real_hash, short_hash)

    ctx_file = config["context"]["scratchpad_file"]
    if config["context"]["clear_after_commit"] and Path(ctx_file).exists():
        from context_reader import write_template
        write_template(ctx_file)

    print(f"{GHOST} ghost-commit: decision log saved to {decisions_dir}/{date}-{short_hash}.md")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=f"{GHOST} ghost-commit — Every commit tells you what. ghost-commit tells you why."
    )
    parser.add_argument("--run", action="store_true", help="Run full interactive flow")
    parser.add_argument("--hook-mode", choices=["pre", "post"], help="Called by git hook")
    parser.add_argument("--context", action="store_true", help="Open .ghost-context in editor")
    parser.add_argument("--print-config", action="store_true", help="Print resolved config")
    parser.add_argument("--status", action="store_true", help="Show current git status for ghost-commit")
    parser.add_argument("--init-changelog", action="store_true", help="Create CHANGELOG.md if missing")

    args = parser.parse_args()

    if not is_git_repo():
        error("Not a git repository. Run from inside a git repo.")
        sys.exit(1)

    config = load_config()

    if args.print_config:
        print(json.dumps(config, indent=2))

    elif args.context:
        open_context_editor(config)

    elif args.status:
        header("status")
        print(f"Branch:      {get_current_branch()}")
        print(f"Staged:      {get_staged_stat() or '(nothing staged)'}")
        ctx_file = config["context"]["scratchpad_file"]
        ctx_exists = Path(ctx_file).exists()
        print(f"Context:     {ctx_file} {'✓' if ctx_exists else '(not found)'}")
        dec_dir = config["decisions"]["directory"]
        n_logs = len(list(Path(dec_dir).glob("*.md"))) if Path(dec_dir).exists() else 0
        print(f"Decisions:   {dec_dir}/ ({n_logs} logs)")
        changelog = config["changelog"]["file"]
        print(f"CHANGELOG:   {changelog} {'✓' if Path(changelog).exists() else '(not found)'}")

    elif args.init_changelog:
        from output_writer import init_changelog
        changelog_file = config["changelog"]["file"]
        if Path(changelog_file).exists():
            warn(f"{changelog_file} already exists")
        else:
            init_changelog(changelog_file)
            success(f"Created {changelog_file}")

    elif args.hook_mode == "pre":
        run_hook_pre(config)

    elif args.hook_mode == "post":
        run_hook_post(config)

    elif args.run or len(sys.argv) == 1:
        run_interactive(config)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
