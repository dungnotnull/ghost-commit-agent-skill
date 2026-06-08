#!/usr/bin/env python3
"""
install_hook.py — Git Hook Installer
Part of the ghost-commit skill.

One-command installer that sets up ghost-commit in any git repository.

Usage:
    python install_hook.py --install              # Install hooks in current repo
    python install_hook.py --uninstall            # Remove hooks
    python install_hook.py --status               # Show installation status
    python install_hook.py --install --repo /path # Install in specific repo
    python install_hook.py --install --global     # Install globally (all repos)
"""

import sys
import os
import stat
import argparse
import subprocess
import shutil
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent  # ghost-commit root
SCRIPTS_DIR = Path(__file__).parent
ASSETS_DIR = SKILL_DIR / "skill" / "assets"

# Hook script content (pre-commit)
PRE_COMMIT_HOOK = """\
#!/usr/bin/env bash
# ghost-commit pre-commit hook
# Installed by ghost-commit skill — https://github.com/your-org/ghost-commit
#
# To skip ghost-commit for a single commit:
#   git commit --no-verify
# To uninstall:
#   python {scripts_dir}/install_hook.py --uninstall

GHOST_COMMIT="{ghost_commit_py}"
PYTHON="{python}"

if [ -f "$GHOST_COMMIT" ]; then
    "$PYTHON" "$GHOST_COMMIT" --hook-mode pre
    EXIT_CODE=$?
    # ghost-commit always exits 0 (fail-open) — never blocks commits
    exit 0
fi

# ghost-commit not found — skip silently
exit 0
"""

POST_COMMIT_HOOK = """\
#!/usr/bin/env bash
# ghost-commit post-commit hook

GHOST_COMMIT="{ghost_commit_py}"
PYTHON="{python}"

if [ -f "$GHOST_COMMIT" ]; then
    "$PYTHON" "$GHOST_COMMIT" --hook-mode post
fi

exit 0
"""

CLAUDE_CODE_HOOKS = """\
{{
  "hooks": {{
    "PreToolUse": [
      {{
        "matcher": "bash",
        "hooks": [
          {{
            "type": "command",
            "command": "python {ghost_commit_py} --hook-mode pre"
          }}
        ]
      }}
    ],
    "Stop": [
      {{
        "hooks": [
          {{
            "type": "command",
            "command": "python {ghost_commit_py} --hook-mode post"
          }}
        ]
      }}
    ]
  }}
}}
"""

ANSI_GREEN  = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_RED    = "\033[31m"
ANSI_BOLD   = "\033[1m"
ANSI_DIM    = "\033[2m"
ANSI_RESET  = "\033[0m"


def ok(msg):  print(f"{ANSI_GREEN}✓{ANSI_RESET} {msg}")
def warn(msg): print(f"{ANSI_YELLOW}⚠{ANSI_RESET} {msg}")
def fail(msg): print(f"{ANSI_RED}✗{ANSI_RESET} {msg}", file=sys.stderr)
def info(msg): print(f"{ANSI_DIM}·{ANSI_RESET} {msg}")


def find_git_dir(repo_path: Path) -> Path | None:
    """Find .git directory for the repo."""
    git_dir = repo_path / ".git"
    if git_dir.is_dir():
        return git_dir
    # Could be a worktree or submodule
    if git_dir.is_file():
        content = git_dir.read_text().strip()
        if content.startswith("gitdir:"):
            return Path(content.split(":", 1)[1].strip())
    return None


def find_python() -> str:
    """Find the current Python interpreter path."""
    return sys.executable


def get_hooks_dir(git_dir: Path) -> Path:
    """Get the hooks directory for this git repo."""
    return git_dir / "hooks"


def make_executable(path: Path):
    """Make a file executable."""
    current = path.stat().st_mode
    path.chmod(current | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def backup_existing_hook(hook_path: Path) -> Path | None:
    """Backup an existing hook file. Returns backup path or None."""
    if not hook_path.exists():
        return None
    backup = hook_path.with_suffix(".pre-ghost-commit.bak")
    shutil.copy2(hook_path, backup)
    return backup


def is_ghost_commit_hook(hook_path: Path) -> bool:
    """Check if a hook file was installed by ghost-commit."""
    if not hook_path.exists():
        return False
    content = hook_path.read_text(errors="ignore")
    return "ghost-commit" in content


def append_to_existing_hook(hook_path: Path, ghost_commit_py: str, python: str, hook_type: str):
    """Append ghost-commit call to an existing hook file."""
    existing = hook_path.read_text()
    if "ghost-commit" in existing:
        warn(f"ghost-commit already present in {hook_path.name}")
        return

    append_content = f"""
# ghost-commit — appended by installer
GHOST_COMMIT="{ghost_commit_py}"
if [ -f "$GHOST_COMMIT" ]; then
    "{python}" "$GHOST_COMMIT" --hook-mode {hook_type}
fi
"""
    with hook_path.open("a") as f:
        f.write(append_content)
    ok(f"Appended ghost-commit to existing {hook_path.name}")


def install_hooks(repo_path: Path, ghost_commit_py: str):
    """Install pre-commit and post-commit hooks."""
    git_dir = find_git_dir(repo_path)
    if not git_dir:
        fail(f"No .git directory found in {repo_path}")
        sys.exit(1)

    hooks_dir = get_hooks_dir(git_dir)
    hooks_dir.mkdir(exist_ok=True)
    python = find_python()

    for hook_name, template, hook_type in [
        ("pre-commit",  PRE_COMMIT_HOOK,  "pre"),
        ("post-commit", POST_COMMIT_HOOK, "post"),
    ]:
        hook_path = hooks_dir / hook_name
        content = template.format(
            ghost_commit_py=ghost_commit_py,
            python=python,
            scripts_dir=str(SCRIPTS_DIR),
        )

        if hook_path.exists() and not is_ghost_commit_hook(hook_path):
            # Existing hook not from us — ask what to do
            print(f"\n{ANSI_YELLOW}Existing {hook_name} hook found.{ANSI_RESET}")
            print(f"  Options:")
            print(f"  [B]ackup and replace  [A]ppend ghost-commit  [S]kip")
            try:
                choice = input(f"  Your choice [B/a/s]: ").strip().upper() or "B"
            except (EOFError, KeyboardInterrupt):
                choice = "S"

            if choice == "S":
                info(f"Skipped {hook_name}")
                continue
            elif choice == "A":
                append_to_existing_hook(hook_path, ghost_commit_py, python, hook_type)
                continue
            else:  # B — backup and replace
                bak = backup_existing_hook(hook_path)
                if bak:
                    info(f"Backed up existing hook to {bak.name}")

        hook_path.write_text(content, encoding="utf-8")
        make_executable(hook_path)
        ok(f"Installed {hook_name} hook → {hook_path}")


def setup_gitignore(repo_path: Path, decisions_dir: str = ".decisions"):
    """Add ghost-commit entries to .gitignore."""
    gitignore = repo_path / ".gitignore"
    entries = [
        "# ghost-commit",
        f"{decisions_dir}/",
        ".ghost-context",
        ".ghost-commit-cache/",
    ]

    if gitignore.exists():
        content = gitignore.read_text()
        if "ghost-commit" in content:
            info(".gitignore already has ghost-commit entries")
            return
        with gitignore.open("a") as f:
            f.write("\n" + "\n".join(entries) + "\n")
    else:
        gitignore.write_text("\n".join(entries) + "\n")

    ok(f".gitignore updated with ghost-commit entries")


def write_ghost_context_template(repo_path: Path, context_file: str = ".ghost-context"):
    """Write .ghost-context template to repo root."""
    ctx_path = repo_path / context_file
    if ctx_path.exists():
        info(f"{context_file} already exists — skipping")
        return

    # Copy from assets
    template_src = ASSETS_DIR / "ghost-context-template.md"
    if template_src.exists():
        shutil.copy2(template_src, ctx_path)
    else:
        # Inline fallback
        from context_reader import write_template
        write_template(str(ctx_path))

    ok(f"Created {context_file} template")


def write_config(repo_path: Path):
    """Write default .ghost-commit.yml to repo."""
    config_path = repo_path / ".ghost-commit.yml"
    if config_path.exists():
        info(".ghost-commit.yml already exists — skipping")
        return

    config_content = """\
# ghost-commit configuration
# See skill/SKILL.md for full documentation.

outputs:
  commit_message: true
  decision_log: true
  changelog: true
  pr_description: true

decisions:
  directory: .decisions
  gitignore: true
  commit_logs: false

changelog:
  file: CHANGELOG.md
  auto_update: true
  section: Unreleased

commit:
  max_subject_length: 72
  enforce_conventional: true
  require_scope: false

context:
  scratchpad_file: .ghost-context
  clear_after_commit: true
  template_reprompt: true

skip:
  branches:
    - main
    - master
    - "release/*"
  commit_patterns:
    - "^Merge"
    - "^Revert"
    - "^WIP"
  file_patterns:
    - "*.lock"
    - "*.min.js"
    - "dist/*"
"""
    config_path.write_text(config_content, encoding="utf-8")
    ok("Created .ghost-commit.yml")


def write_claude_code_hooks(repo_path: Path, ghost_commit_py: str):
    """Write Claude Code hooks config."""
    claude_dir = repo_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.json"

    content = CLAUDE_CODE_HOOKS.format(ghost_commit_py=ghost_commit_py)

    if settings_path.exists():
        import json
        try:
            existing = json.loads(settings_path.read_text())
            if "hooks" not in existing:
                existing["hooks"] = json.loads(content)["hooks"]
                settings_path.write_text(json.dumps(existing, indent=2))
                ok("Added ghost-commit hooks to .claude/settings.json")
            else:
                info(".claude/settings.json already has hooks — skipping (add manually)")
        except Exception:
            info("Could not update .claude/settings.json — add hooks manually")
    else:
        settings_path.write_text(content)
        ok("Created .claude/settings.json with ghost-commit hooks")


def uninstall_hooks(repo_path: Path):
    """Remove ghost-commit hooks from the repo."""
    git_dir = find_git_dir(repo_path)
    if not git_dir:
        fail(f"No .git directory found in {repo_path}")
        sys.exit(1)

    hooks_dir = get_hooks_dir(git_dir)

    for hook_name in ["pre-commit", "post-commit"]:
        hook_path = hooks_dir / hook_name
        if not hook_path.exists():
            info(f"{hook_name}: not installed")
            continue

        if is_ghost_commit_hook(hook_path):
            hook_path.unlink()
            ok(f"Removed {hook_name} hook")

            # Restore backup if exists
            bak = hook_path.with_suffix(".pre-ghost-commit.bak")
            if bak.exists():
                shutil.copy2(bak, hook_path)
                make_executable(hook_path)
                bak.unlink()
                ok(f"Restored original {hook_name} from backup")
        else:
            # Hook exists but was appended — remove just the ghost-commit section
            content = hook_path.read_text()
            if "ghost-commit" in content:
                # Remove appended section
                lines = content.split("\n")
                clean = []
                skip = False
                for line in lines:
                    if "# ghost-commit — appended by installer" in line:
                        skip = True
                    if not skip:
                        clean.append(line)
                hook_path.write_text("\n".join(clean))
                ok(f"Removed ghost-commit section from existing {hook_name}")
            else:
                info(f"{hook_name}: ghost-commit not found in hook")


def show_status(repo_path: Path):
    """Show installation status."""
    print(f"\n{ANSI_BOLD}👻 ghost-commit status{ANSI_RESET} — {repo_path}\n")

    git_dir = find_git_dir(repo_path)
    if not git_dir:
        fail("Not a git repository")
        return

    hooks_dir = get_hooks_dir(git_dir)

    # Hook status
    for hook_name in ["pre-commit", "post-commit"]:
        hook_path = hooks_dir / hook_name
        if not hook_path.exists():
            print(f"  {ANSI_RED}○{ANSI_RESET} {hook_name}: not installed")
        elif is_ghost_commit_hook(hook_path):
            print(f"  {ANSI_GREEN}✓{ANSI_RESET} {hook_name}: installed")
        else:
            print(f"  {ANSI_YELLOW}⚠{ANSI_RESET} {hook_name}: exists (not ghost-commit)")

    # Config file
    config_path = repo_path / ".ghost-commit.yml"
    icon = f"{ANSI_GREEN}✓{ANSI_RESET}" if config_path.exists() else f"{ANSI_YELLOW}○{ANSI_RESET}"
    print(f"  {icon} .ghost-commit.yml: {'found' if config_path.exists() else 'not found (using defaults)'}")

    # .ghost-context
    ctx_path = repo_path / ".ghost-context"
    icon = f"{ANSI_GREEN}✓{ANSI_RESET}" if ctx_path.exists() else f"{ANSI_YELLOW}○{ANSI_RESET}"
    print(f"  {icon} .ghost-context: {'found' if ctx_path.exists() else 'not found'}")

    # .decisions/
    dec_path = repo_path / ".decisions"
    n = len(list(dec_path.glob("*.md"))) if dec_path.exists() else 0
    icon = f"{ANSI_GREEN}✓{ANSI_RESET}" if dec_path.exists() else f"{ANSI_DIM}○{ANSI_RESET}"
    print(f"  {icon} .decisions/: {'found' if dec_path.exists() else 'not found'} ({n} logs)")

    # CHANGELOG.md
    cl_path = repo_path / "CHANGELOG.md"
    icon = f"{ANSI_GREEN}✓{ANSI_RESET}" if cl_path.exists() else f"{ANSI_YELLOW}○{ANSI_RESET}"
    print(f"  {icon} CHANGELOG.md: {'found' if cl_path.exists() else 'not found'}")

    # Claude Code hooks
    cc_settings = repo_path / ".claude" / "settings.json"
    if cc_settings.exists():
        try:
            import json
            s = json.loads(cc_settings.read_text())
            if "hooks" in s:
                print(f"  {ANSI_GREEN}✓{ANSI_RESET} .claude/settings.json: hooks configured")
            else:
                print(f"  {ANSI_YELLOW}○{ANSI_RESET} .claude/settings.json: exists but no hooks")
        except Exception:
            print(f"  {ANSI_YELLOW}○{ANSI_RESET} .claude/settings.json: found (unreadable)")
    else:
        print(f"  {ANSI_DIM}○{ANSI_RESET} .claude/settings.json: not configured")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="👻 ghost-commit — Install git hooks for automatic commit documentation"
    )
    parser.add_argument("--install", action="store_true", help="Install hooks in repo")
    parser.add_argument("--uninstall", action="store_true", help="Remove hooks from repo")
    parser.add_argument("--status", action="store_true", help="Show installation status")
    parser.add_argument("--repo", type=str, default=".", help="Target repository path")
    parser.add_argument("--global", dest="global_", action="store_true",
                        help="Install globally (git config --global)")
    parser.add_argument("--with-claude-code", action="store_true",
                        help="Also write .claude/settings.json hooks")
    parser.add_argument("--ghost-commit-path", type=str,
                        default=str(SCRIPTS_DIR / "ghost_commit.py"),
                        help="Path to ghost_commit.py")
    parser.add_argument("--skip-gitignore", action="store_true",
                        help="Don't modify .gitignore")
    parser.add_argument("--skip-config", action="store_true",
                        help="Don't create .ghost-commit.yml")

    args = parser.parse_args()
    repo_path = Path(args.repo).resolve()
    ghost_commit_py = args.ghost_commit_path

    if args.status:
        show_status(repo_path)

    elif args.uninstall:
        print(f"\n{ANSI_BOLD}👻 ghost-commit — Uninstalling{ANSI_RESET}\n")
        uninstall_hooks(repo_path)
        print("\nDone. ghost-commit hooks removed.")

    elif args.install:
        print(f"\n{ANSI_BOLD}👻 ghost-commit — Installing{ANSI_RESET}\n")
        print(f"  Repo: {repo_path}")
        print(f"  Script: {ghost_commit_py}\n")

        if args.global_:
            # Global install — set core.hooksPath
            global_hooks_dir = Path.home() / ".git-hooks"
            global_hooks_dir.mkdir(exist_ok=True)
            install_hooks(repo_path, ghost_commit_py)
            subprocess.run(
                ["git", "config", "--global", "core.hooksPath", str(global_hooks_dir)],
                check=True
            )
            ok("Global git hooks path configured")
        else:
            install_hooks(repo_path, ghost_commit_py)

        if not args.skip_gitignore:
            setup_gitignore(repo_path)

        if not args.skip_config:
            write_config(repo_path)

        write_ghost_context_template(repo_path)

        if args.with_claude_code:
            write_claude_code_hooks(repo_path, ghost_commit_py)

        print(f"\n{ANSI_GREEN}{ANSI_BOLD}✓ ghost-commit installed!{ANSI_RESET}\n")
        print("  Quick start:")
        print("  1. Stage some files:     git add .")
        print("  2. Add context (optional): python ghost_commit.py --context")
        print("  3. Commit:               git commit")
        print("  4. ghost-commit runs automatically before the commit\n")
        print(f"  Tip: Run {ANSI_BOLD}python install_hook.py --status{ANSI_RESET} to verify\n")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
