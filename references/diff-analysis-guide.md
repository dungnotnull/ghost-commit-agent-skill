# Diff Analysis Guide

_Load during Phase 1–3. Guides classification of git diffs into type, scope, risk, and breaking change._

---

## Reading a Git Diff

### Stat output (`git diff --staged --stat`)
```
 src/auth/session.py      | 23 +++++++++++++++--------
 src/auth/middleware.py   |  4 ++--
 tests/test_session.py    | 15 +++++++++++++++
 3 files changed, 34 insertions(+), 10 deletions(-)
```
Extract: file paths, change direction (+/-), line counts.

### Full diff structure
```diff
diff --git a/src/auth/session.py b/src/auth/session.py
index abc123..def456 100644
--- a/src/auth/session.py
+++ b/src/auth/session.py
@@ -45,7 +45,8 @@ class SessionManager:
     def set_ttl(self, key: str, seconds: int) -> None:
-        self.redis.expire(key, seconds)
+        ttl_ms = seconds * 1000
+        self.redis.pexpire(key, ttl_ms)
```

Lines starting with:
- `+` (not `+++`) → added
- `-` (not `---`) → removed
- ` ` → context (unchanged)

---

## Change Type Classification

Run signals in order — first match wins for the primary type.

### FEAT signals
```python
FEAT_PATTERNS = [
    r"^\+.*(def|function|class|interface|struct)\s+\w+",  # new function/class
    r"^\+.*@(app\.route|router\.(get|post|put|delete|patch))",  # new endpoint
    r"^\+.*export\s+(default\s+)?(function|class|const)",  # new export
    r"^\+.*public\s+(static\s+)?\w+\s+\w+\(",  # new public method
    r"new file mode",  # entirely new file
]
FEAT_FILE_PATTERNS = [
    r"^src/(features|modules|components|pages|views|controllers)/",
    r"^app/(routes|handlers|endpoints)/",
]
```

### FIX signals
```python
FIX_PATTERNS = [
    r"^\+.*\b(fix|bug|error|issue|problem|correct|patch)\b",
    r"^\+.*\b(catch|except|rescue)\b",          # error handling added
    r"^\+.*\b(if|guard|check|validate)\b",       # defensive check added
    r"^-.*\b(None|null|undefined|NaN)\b",        # null check removed (was wrong)
    r"off.by.one|boundary|edge case",
    r"^\+.*\b(fallback|default|retry)\b",
]
# Also: function body changed but signature unchanged → likely fix
```

### REFACTOR signals
```python
REFACTOR_PATTERNS = [
    r"Rename|rename|Extract|extract|Move|move|Split|split",
    r"^\+.*def \w+.*:.*$\n.*^\+",  # function moved (new location)
    r"# Moved from|# Extracted from|# Refactored",
]
# Key: total lines added ≈ total lines removed (restructure, not new content)
# Heuristic: abs(insertions - deletions) / max(insertions, deletions) < 0.3
```

### PERF signals
```python
PERF_PATTERNS = [
    r"cache|Cache|memo|memoize|lazy|lazy_load",
    r"index|Index|CREATE INDEX",
    r"batch|bulk|chunk",
    r"async|await|concurrent|parallel",
    r"O\(n\)|O\(1\)|complexity",
    r"benchmark|profile|optimize",
]
```

### TEST signals
```python
TEST_FILE_PATTERNS = [
    r"test_\w+\.py|_test\.py|\.test\.(js|ts)|\.spec\.(js|ts)",
    r"tests/|__tests__/|spec/",
    r"fixtures/|mocks/|stubs/",
]
# If ALL changed files match test patterns → type = test
```

### DOCS signals
```python
DOCS_FILE_PATTERNS = [
    r"\.md|\.rst|\.txt|\.adoc",
    r"docs/|documentation/|wiki/",
]
DOCS_CONTENT_PATTERNS = [
    r"^\+\s+\"\"\"",       # docstring added
    r"^\+\s+#\s+\w",       # comment added
    r"^\+.*README",
]
# If ALL changed files are docs → type = docs
```

### STYLE signals
```python
STYLE_PATTERNS = [
    r"^\+\s+$|^-\s+$",         # whitespace only line changes
    r"Prettier|Black|gofmt|rustfmt",
    r"\.prettierrc|\.eslintrc|pyproject\.toml.*format",
]
# Heuristic: many lines changed but actual tokens unchanged
```

---

## Scope Extraction

```python
def detect_scope(changed_files: list[str]) -> str | None:
    # 1. Extract directories
    dirs = [os.path.dirname(f) for f in changed_files]
    dir_counts = Counter(dirs)
    
    # 2. Check for monorepo packages
    pkg_patterns = [r"packages/(\w[\w-]*)/", r"apps/(\w[\w-]*)/", r"libs/(\w[\w-]*)/"]
    for pattern in pkg_patterns:
        matches = [re.search(pattern, f) for f in changed_files]
        packages = set(m.group(1) for m in matches if m)
        if len(packages) == 1:
            return list(packages)[0]
    
    # 3. Single dominant directory
    if dir_counts and dir_counts.most_common(1)[0][1] >= len(dirs) * 0.6:
        dominant = dir_counts.most_common(1)[0][0]
        # Clean up: strip src/ prefix, take leaf
        parts = [p for p in dominant.split('/') if p not in ('src', 'lib', 'app', 'pkg', '.')]
        return parts[-1] if parts else None
    
    # 4. Semantic grouping by known directory names
    SEMANTIC_MAP = {
        frozenset(['api', 'routes', 'handlers', 'controllers']): 'api',
        frozenset(['models', 'schemas', 'entities', 'db']): 'db',
        frozenset(['components', 'views', 'pages', 'ui']): 'ui',
        frozenset(['auth', 'security', 'permissions']): 'auth',
        frozenset(['tests', '__tests__', 'spec', 'fixtures']): 'test',
    }
    dir_set = set(os.path.basename(d) for d in dirs)
    for pattern_set, scope in SEMANTIC_MAP.items():
        if dir_set & pattern_set:
            return scope
    
    return None  # Omit scope from commit message
```

---

## Risk Level Scoring

Score accumulates across all changed files and content.

```python
RISK_SCORES = {
    # HIGH RISK signals (+3 each)
    "high": {
        "files": [r"auth", r"security", r"payment", r"billing", r"crypto",
                  r"password", r"token", r"secret", r"migration", r"schema"],
        "content": [r"DELETE\s+FROM", r"DROP\s+(TABLE|COLUMN|DATABASE)",
                    r"ALTER\s+TABLE", r"TRUNCATE", r"CASCADE",
                    r"os\.system\(", r"eval\(", r"exec\("],
    },
    # MEDIUM RISK signals (+1 each)
    "medium": {
        "files": [r"config", r"settings", r"env", r"api", r"endpoint",
                  r"route", r"model", r"service", r"timeout", r"retry"],
        "content": [r"timeout\s*=", r"retry\s*=", r"MAX_", r"LIMIT\s*=",
                    r"raise\s+\w+Error", r"sys\.exit"],
    },
    # LOW RISK signals (-1 each, these reduce score)
    "low": {
        "files": [r"test_", r"_test\.", r"\.spec\.", r"__tests__",
                  r"README", r"\.md", r"fixture", r"mock", r"stub"],
        "content": [r"#\s+TODO", r"#\s+FIXME", r"pass$"],
    }
}

def calculate_risk(files, diff_content):
    score = 0
    for pattern in RISK_SCORES["high"]["files"]:
        if any(re.search(pattern, f, re.I) for f in files): score += 3
    for pattern in RISK_SCORES["high"]["content"]:
        if re.search(pattern, diff_content): score += 3
    for pattern in RISK_SCORES["medium"]["files"]:
        if any(re.search(pattern, f, re.I) for f in files): score += 1
    for pattern in RISK_SCORES["medium"]["content"]:
        if re.search(pattern, diff_content): score += 1
    for pattern in RISK_SCORES["low"]["files"]:
        if any(re.search(pattern, f, re.I) for f in files): score -= 1
    
    if score >= 5: return "High"
    if score >= 2: return "Medium"
    return "Low"
```

---

## Breaking Change Detection

```python
BREAKING_PATTERNS = [
    # Function signatures — parameter removed or reordered
    (r"^-\s+def\s+(\w+)\(([^)]+)\)", r"^\+\s+def\s+\1\(([^)]+)\)"),
    # Database
    r"^\-.*DROP\s+COLUMN",
    r"^\-.*RENAME\s+(TABLE|COLUMN)",
    r"^\-.*ALTER\s+COLUMN.*TYPE",
    # Environment variables
    r"^\-\s+[A-Z][A-Z0-9_]+=",
    # HTTP routes
    r"^\-.*@(app|router)\.(route|get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]",
    # Exports removed
    r"^\-.*export\s+(default\s+)?(function|class|const)\s+(\w+)",
    # Config keys removed (JSON/YAML/TOML)
    r"^\-\s+['\"]?\w+['\"]?\s*[:=]",
]

def detect_breaking_change(diff: str) -> bool:
    for pattern in BREAKING_PATTERNS:
        if isinstance(pattern, tuple):
            # Signature comparison — more complex
            removed = re.findall(pattern[0], diff, re.MULTILINE)
            added = re.findall(pattern[1], diff, re.MULTILINE)
            if removed and not added:
                return True  # Function removed entirely
        else:
            if re.search(pattern, diff, re.MULTILINE):
                return True
    return False
```

---

## Large Diff Handling (500+ lines)

When `insertions + deletions > 500`:

1. Summarize by file rather than line-by-line analysis
2. Group files by directory
3. Focus classification on the highest-risk files
4. Add warning in decision log: "Large commit — consider splitting into smaller atomic commits"
5. In commit message body: "Affects N files across X modules"

---

## Binary File Handling

Detect binary files:
```
diff --git a/assets/logo.png b/assets/logo.png
Binary files differ
```

For binary-only diffs:
- Type: `chore` (unless in `assets/` → `feat` if new)
- Skip content pattern analysis
- In commit message: "update binary asset <filename>"
- Decision log: note file sizes if available

---

## Diff Quality Checks

Before generating outputs, verify:
- [ ] At least one staged file found
- [ ] Not a merge commit (no `MERGE_HEAD`)
- [ ] Not an empty diff
- [ ] Diff is parseable (not corrupted)
- [ ] File count is reasonable (warn if > 50 files)
