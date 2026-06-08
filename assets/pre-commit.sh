#!/usr/bin/env bash
# ghost-commit pre-commit hook
# Installed by: python skill/scripts/install_hook.py --install
#
# To skip for a single commit:   git commit --no-verify
# To uninstall:                   python skill/scripts/install_hook.py --uninstall
# To check status:                python skill/scripts/install_hook.py --status

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────

# Path to ghost_commit.py — set by installer, or auto-detected
GHOST_COMMIT="${GHOST_COMMIT_PY:-}"

# Auto-detect if not set
if [ -z "$GHOST_COMMIT" ]; then
    # Try relative to repo root
    REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo '.')"

    # Common install locations (in priority order)
    CANDIDATES=(
        "$REPO_ROOT/.ghost-commit/skill/scripts/ghost_commit.py"
        "$HOME/.ghost-commit/skill/scripts/ghost_commit.py"
        "$HOME/.claude/skills/ghost-commit/skill/scripts/ghost_commit.py"
    )

    for candidate in "${CANDIDATES[@]}"; do
        if [ -f "$candidate" ]; then
            GHOST_COMMIT="$candidate"
            break
        fi
    done
fi

# ── Python detection ──────────────────────────────────────────────────────────

PYTHON="${GHOST_COMMIT_PYTHON:-}"

if [ -z "$PYTHON" ]; then
    for py in python3 python python3.12 python3.11 python3.10; do
        if command -v "$py" &>/dev/null; then
            PYTHON="$py"
            break
        fi
    done
fi

# ── Skip conditions ───────────────────────────────────────────────────────────

# Skip if no ghost_commit.py found
if [ -z "$GHOST_COMMIT" ] || [ ! -f "$GHOST_COMMIT" ]; then
    # Silent skip — don't block commits if ghost-commit isn't installed
    exit 0
fi

# Skip if Python not found
if [ -z "$PYTHON" ]; then
    echo "⚠ ghost-commit: Python not found — skipping"
    exit 0
fi

# Skip merge commits
if [ -f "$(git rev-parse --git-dir)/MERGE_HEAD" ]; then
    exit 0
fi

# Skip revert commits
if [ -f "$(git rev-parse --git-dir)/REVERT_HEAD" ]; then
    exit 0
fi

# Skip if nothing staged
if git diff --staged --quiet; then
    exit 0
fi

# Skip certain branches (configurable in .ghost-commit.yml)
CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || echo '')"
SKIP_BRANCHES="${GHOST_COMMIT_SKIP_BRANCHES:-main,master}"

IFS=',' read -ra SKIP_LIST <<< "$SKIP_BRANCHES"
for skip_branch in "${SKIP_LIST[@]}"; do
    # Support glob patterns
    if [[ "$CURRENT_BRANCH" == $skip_branch ]]; then
        echo "· ghost-commit: skipping on branch '$CURRENT_BRANCH'"
        exit 0
    fi
done

# ── Run ghost-commit ──────────────────────────────────────────────────────────

echo ""
echo "👻 ghost-commit analyzing staged changes..."
echo ""

# Run ghost_commit.py in pre-hook mode
# Always exit 0 — ghost-commit never blocks commits
"$PYTHON" "$GHOST_COMMIT" --hook-mode pre || true

echo ""
exit 0
