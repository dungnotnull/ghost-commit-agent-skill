#!/usr/bin/env python3
"""
diff_analyzer.py — Git Diff Parser & Classifier
Part of the ghost-commit skill.

Usage:
    python diff_analyzer.py --staged             # Analyze currently staged diff
    python diff_analyzer.py --json               # Output JSON
    python diff_analyzer.py --file path.diff     # Analyze a diff file
    echo "<diff>" | python diff_analyzer.py --stdin

Output JSON:
    {
        "type": "fix",
        "scope": "session",
        "description": "correct Redis TTL unit mismatch",
        "risk_level": "Medium",
        "breaking_change": false,
        "insertions": 23,
        "deletions": 8,
        "files": [...],
        "file_count": 3,
        "signals": [...],
        "summary": "3 files changed, 23 insertions(+), 8 deletions(-)"
    }
"""

import sys
import re
import json
import subprocess
import argparse
from pathlib import Path
from collections import Counter


# ── Type signal patterns ──────────────────────────────────────────────────────

TYPE_PATTERNS = {
    "feat": {
        "content": [
            r"^\+.*(def|function|class|interface|struct|enum)\s+\w+",
            r"^\+.*@(app\.route|router\.(get|post|put|delete|patch|head))",
            r"^\+.*export\s+(default\s+)?(function|class|const|async)",
            r"^\+.*public\s+(static\s+)?\w+\s+\w+\(",
        ],
        "files": [
            r"^src/(features|modules|components|pages|views|controllers|handlers)/",
            r"^app/(routes|api|endpoints|handlers)/",
            r"new file mode",
        ],
        "score": 3,
    },
    "fix": {
        "content": [
            r"^\+.*\b(fix|correct|resolve|patch|repair|heal)\b",
            r"^\+.*\b(catch|except|rescue|finally)\b",
            r"^\+.*\b(validate|guard|check|assert|ensure|require)\b",
            r"^\+.*\b(fallback|default|retry|recover)\b",
            r"^\-.*(?:None|null|undefined|NaN)\b",
        ],
        "files": [
            r"fix|bug|issue|hotfix|patch",
        ],
        "score": 3,
    },
    "refactor": {
        "content": [
            r"^\+.*(rename|extract|move|split|merge|consolidate|restructure)",
            r"# (Moved|Extracted|Refactored|Renamed) from",
        ],
        "files": [
            r"refactor|restructure",
        ],
        "score": 2,
    },
    "perf": {
        "content": [
            r"^\+.*(cache|Cache|memo|memoize|lazy|lazy_load|lru_cache)",
            r"^\+.*(CREATE INDEX|ADD INDEX)",
            r"^\+.*(batch|bulk|chunk|paginate)",
            r"^\+.*(async|await|concurrent|parallel|thread|worker)",
        ],
        "files": [
            r"perf|optim|cache|index",
        ],
        "score": 3,
    },
    "test": {
        "files": [
            r"test_\w+|_test\.(py|js|ts|go|rb)|\.test\.(js|ts|jsx|tsx)|\.spec\.(js|ts|jsx|tsx)",
            r"^tests?/|^__tests__/|^spec/|^test/",
        ],
        "score": 2,
    },
    "docs": {
        "files": [
            r"\.(md|rst|txt|adoc|rdoc)$",
            r"^docs?/|^documentation/|^wiki/",
        ],
        "content": [
            r'^\+\s+"""',
            r"^\+\s+#\s+\w",
            r"^\+.*README",
        ],
        "score": 2,
    },
    "style": {
        "content": [
            r"^\+\s*$|^\-\s*$",   # blank line changes
        ],
        "files": [
            r"\.(prettierrc|eslintrc|editorconfig|flake8|black)$",
        ],
        "score": 2,
    },
    "build": {
        "files": [
            r"^(package\.json|Cargo\.toml|go\.mod|requirements\.txt|Pipfile|pyproject\.toml|Makefile|CMakeLists\.txt|BUILD|WORKSPACE)$",
            r"\.(gradle|maven|pom)$",
        ],
        "score": 3,
    },
    "ci": {
        "files": [
            r"^\.github/",
            r"^\.gitlab-ci",
            r"Jenkinsfile",
            r"\.circleci/",
            r"\.travis\.yml",
            r"^\.drone\.yml",
        ],
        "score": 3,
    },
    "chore": {
        "files": [
            r"\.(gitignore|gitattributes|npmignore|dockerignore)$",
            r"^\.env\.example$",
            r"LICENSE",
        ],
        "score": 2,
    },
}

# ── Risk signal patterns ──────────────────────────────────────────────────────

RISK_SIGNALS = {
    "High": {
        "files": [
            r"auth|security|password|token|secret|encrypt|decrypt|crypto",
            r"payment|billing|invoice|charge|stripe|paypal",
            r"migration|schema|database|db_schema",
        ],
        "content": [
            r"DELETE\s+FROM|DROP\s+(TABLE|COLUMN|DATABASE)|TRUNCATE",
            r"ALTER\s+TABLE|ALTER\s+COLUMN",
            r"\bCASCADE\b",
            r"os\.system\(|subprocess\.call\(|eval\(|exec\(",
            r"chmod|chown|sudo",
        ],
        "score": 3,
    },
    "Medium": {
        "files": [
            r"config|settings|\.env|environ",
            r"api|endpoint|route|handler|controller",
            r"model|schema|entity|orm",
            r"service|manager|repository",
        ],
        "content": [
            r"timeout\s*=|retry\s*=|MAX_\w+\s*=|LIMIT\s*=",
            r"raise\s+\w+(Error|Exception)",
            r"sys\.exit\(",
            r"\bINSERT\b|\bUPDATE\b|\bDELETE\b",
        ],
        "score": 1,
    },
    "Low": {
        "files": [
            r"test_|_test\.|\.spec\.|__tests__|fixture|mock|stub",
            r"\.(md|rst|txt)$",
        ],
        "content": [
            r"# TODO|# FIXME|pass$|return None$",
        ],
        "score": -1,
    },
}

# ── Breaking change patterns ──────────────────────────────────────────────────

BREAKING_PATTERNS = [
    r"^\-\s*DROP\s+(TABLE|COLUMN|DATABASE)",
    r"^\-\s*RENAME\s+(TABLE|COLUMN)",
    r"^\-\s*ALTER\s+COLUMN.+TYPE",
    r"^\-\s*[A-Z][A-Z0-9_]{3,}\s*=",          # env var removed
    r"^\-\s*['\"]?\w+['\"]?\s*:\s*.+",          # config key removed (loose)
    r"^\-.*@(app|router)\.(route|get|post|put|delete|patch)\(['\"][^'\"]+['\"]",
    r"^\-.*export\s+default\s+",
    r"^\-\s+def\s+\w+\(",                       # public function removed
]


# ── Scope extraction ──────────────────────────────────────────────────────────

SEMANTIC_SCOPE_MAP = {
    frozenset(["api", "routes", "handlers", "controllers", "endpoints"]): "api",
    frozenset(["models", "schemas", "entities", "db", "database"]): "db",
    frozenset(["components", "views", "pages", "ui", "layouts"]): "ui",
    frozenset(["auth", "security", "permissions", "access"]): "auth",
    frozenset(["tests", "__tests__", "spec", "fixtures", "test"]): "test",
    frozenset(["utils", "helpers", "common", "shared", "lib"]): "utils",
    frozenset(["config", "settings", "env", "configuration"]): "config",
    frozenset(["services", "service"]): "service",
    frozenset(["migrations", "migration"]): "migration",
}

STRIP_PREFIX_DIRS = {"src", "lib", "app", "pkg", "source", "core", "internal"}


def extract_scope(files: list[str]) -> str | None:
    import os
    if not files:
        return None

    # Check monorepo packages
    pkg_patterns = [
        r"^packages/([^/]+)/",
        r"^apps/([^/]+)/",
        r"^libs/([^/]+)/",
        r"^modules/([^/]+)/",
    ]
    for pattern in pkg_patterns:
        packages = set()
        for f in files:
            m = re.match(pattern, f)
            if m:
                packages.add(m.group(1))
        if len(packages) == 1:
            return list(packages)[0]

    # Extract directories
    dirs = []
    for f in files:
        parts = Path(f).parts
        # Strip leading src/ lib/ app/ etc.
        filtered = [p for p in parts[:-1] if p not in STRIP_PREFIX_DIRS]
        if filtered:
            dirs.append(filtered[0])  # First meaningful dir

    if not dirs:
        return None

    dir_counts = Counter(dirs)
    total = len(dirs)

    # Single dominant directory
    top_dir, top_count = dir_counts.most_common(1)[0]
    if top_count >= total * 0.6:
        return top_dir

    # Semantic grouping
    dir_set = set(d.lower() for d in dir_counts)
    for pattern_set, scope in SEMANTIC_SCOPE_MAP.items():
        if dir_set & pattern_set:
            return scope

    return None


# ── Description generation ────────────────────────────────────────────────────

def generate_description(commit_type: str, files: list[str], diff: str) -> str:
    """Generate a short, specific description from the diff."""
    # Try to extract the most meaningful changed identifier
    changed_names = []

    if commit_type == "feat":
        # Find new function/class names
        for line in diff.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                m = re.search(r"(?:def|function|class|interface)\s+(\w+)", line)
                if m:
                    changed_names.append(m.group(1))

    elif commit_type == "fix":
        # Find what was corrected
        for line in diff.split("\n"):
            if line.startswith("-") and not line.startswith("---"):
                m = re.search(r"(\w+)\s*[=:]\s*(\S+)", line)
                if m:
                    changed_names.append(f"{m.group(1)} value")

    if changed_names:
        primary = changed_names[0]
        # Convert snake_case/camelCase to words
        words = re.sub(r"([A-Z])", r" \1", primary).replace("_", " ").strip().lower()
        return words

    # Fallback to file-based description
    if files:
        base = Path(files[0]).stem
        words = re.sub(r"([A-Z])", r" \1", base).replace("_", " ").strip().lower()
        action = {
            "feat": f"add {words}",
            "fix": f"fix {words}",
            "refactor": f"refactor {words}",
            "perf": f"improve {words} performance",
            "test": f"add tests for {words}",
            "docs": f"update {words} documentation",
            "chore": f"update {words}",
            "build": f"update build config",
            "ci": f"update CI config",
        }.get(commit_type, f"update {words}")
        return action

    return "update code"


# ── Main analysis ─────────────────────────────────────────────────────────────

def analyze_diff(diff: str, files: list[str] = None) -> dict:
    """Classify a git diff and return structured analysis."""
    if files is None:
        # Extract from diff
        files = []
        for line in diff.split("\n"):
            m = re.match(r"^diff --git a/(.+) b/", line)
            if m:
                files.append(m.group(1))

    # Parse stats
    insertions = sum(
        1 for line in diff.split("\n")
        if line.startswith("+") and not line.startswith("+++")
    )
    deletions = sum(
        1 for line in diff.split("\n")
        if line.startswith("-") and not line.startswith("---")
    )

    # Score each type
    type_scores: dict[str, int] = {t: 0 for t in TYPE_PATTERNS}

    for commit_type, signals in TYPE_PATTERNS.items():
        score_val = signals["score"]

        # File pattern signals
        for pattern in signals.get("files", []):
            if any(re.search(pattern, f, re.I) for f in files):
                type_scores[commit_type] += score_val

        # Content pattern signals
        for pattern in signals.get("content", []):
            matches = re.findall(pattern, diff, re.MULTILINE)
            if matches:
                type_scores[commit_type] += score_val

    # Special heuristic: if test files are ALL files → test
    if files and all(
        re.search(r"test_\w+|_test\.|\.test\.|\.spec\.|^tests?/|^spec/", f, re.I)
        for f in files
    ):
        type_scores["test"] += 5

    # Special heuristic: if only docs → docs
    if files and all(
        re.search(r"\.(md|rst|txt|adoc)$", f, re.I)
        for f in files
    ):
        type_scores["docs"] += 5

    # Refactor heuristic: similar ins/del count, no new exports
    if insertions > 0 and deletions > 0:
        balance = abs(insertions - deletions) / max(insertions, deletions)
        if balance < 0.25:  # Very balanced — likely refactor
            type_scores["refactor"] += 2

    # Pick highest-scored type
    commit_type = max(type_scores, key=lambda t: type_scores[t])
    if type_scores[commit_type] == 0:
        commit_type = "chore"  # Default

    # Risk scoring
    risk_score = 0
    matched_signals = []

    for risk_level, signals in RISK_SIGNALS.items():
        for pattern in signals.get("files", []):
            if any(re.search(pattern, f, re.I) for f in files):
                risk_score += signals["score"]
                matched_signals.append(f"file:{pattern}")
        for pattern in signals.get("content", []):
            if re.search(pattern, diff, re.MULTILINE | re.IGNORECASE):
                risk_score += signals["score"]
                matched_signals.append(f"content:{pattern[:30]}")

    if risk_score >= 5:
        risk_level = "High"
    elif risk_score >= 2:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    # Breaking change detection
    breaking_change = False
    for pattern in BREAKING_PATTERNS:
        if re.search(pattern, diff, re.MULTILINE):
            breaking_change = True
            matched_signals.append(f"breaking:{pattern[:40]}")
            break

    # Scope extraction
    scope = extract_scope(files)

    # Description
    description = generate_description(commit_type, files, diff)

    return {
        "type": commit_type,
        "scope": scope,
        "description": description,
        "risk_level": risk_level,
        "breaking_change": breaking_change,
        "insertions": insertions,
        "deletions": deletions,
        "files": files,
        "file_count": len(files),
        "type_scores": type_scores,
        "signals": matched_signals[:10],
        "summary": f"{len(files)} files changed, {insertions} insertions(+), {deletions} deletions(-)",
    }


def analyze_staged() -> dict:
    """Analyze currently staged diff."""
    result = subprocess.run(
        ["git", "diff", "--staged"], capture_output=True, text=True
    )
    diff = result.stdout

    files_result = subprocess.run(
        ["git", "diff", "--staged", "--name-only"], capture_output=True, text=True
    )
    files = [f for f in files_result.stdout.strip().split("\n") if f]

    return analyze_diff(diff, files)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Analyze a git diff and classify it.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--staged", action="store_true", help="Analyze staged diff")
    group.add_argument("--file", type=str, help="Path to diff file")
    group.add_argument("--stdin", action="store_true", help="Read diff from stdin")

    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    args = parser.parse_args()

    if args.staged:
        result = analyze_staged()
    elif args.file:
        diff = Path(args.file).read_text(encoding="utf-8", errors="ignore")
        result = analyze_diff(diff)
    else:
        diff = sys.stdin.read()
        result = analyze_diff(diff)

    if args.json or args.pretty:
        indent = 2 if args.pretty else None
        print(json.dumps(result, indent=indent))
    else:
        print(f"Type:     {result['type']}")
        print(f"Scope:    {result['scope'] or '(none)'}")
        print(f"Desc:     {result['description']}")
        print(f"Risk:     {result['risk_level']}")
        print(f"Breaking: {result['breaking_change']}")
        print(f"Stats:    {result['summary']}")


if __name__ == "__main__":
    main()
