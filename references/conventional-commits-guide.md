# Conventional Commits Guide

_Load during Phase 3 when generating commit messages._

---

## Spec: Conventional Commits 1.0.0

Full format:
```
<type>[optional !][(<scope>)]: <description>

[optional body]

[optional footer(s)]
```

---

## Type Reference

| Type | When to Use | CHANGELOG Category |
|---|---|---|
| `feat` | A new feature or capability added | Added |
| `fix` | A bug fix — corrects wrong behavior | Fixed |
| `docs` | Documentation only (README, docstrings, comments) | Changed |
| `style` | Formatting, whitespace, semicolons — no logic change | — (omit from CHANGELOG) |
| `refactor` | Code restructured, same behavior — no feat or fix | Changed |
| `perf` | Performance improvement — measurable speedup | Changed |
| `test` | Adding or correcting tests | — (omit from CHANGELOG) |
| `build` | Build system, package manager, dependencies | — |
| `ci` | CI/CD config files and scripts | — |
| `chore` | Maintenance tasks not fitting above | — |
| `revert` | Reverts a previous commit | Fixed |

**Rule: when in doubt between fix and refactor:**
- Did the observable behavior change? → `fix`
- Same behavior, better structure? → `refactor`

**Rule: when test files AND source files both changed:**
- Use the type that reflects the source file change
- Tests are a consequence, not the subject

---

## Scope Detection Rules

Load after getting `diff_analyzer.py` output.

**Single directory changed:**
```
src/auth/         → auth
api/v2/users/     → users  (use leaf directory name)
lib/database/     → db
```

**Multiple directories — use most-changed:**
```
src/auth/ (8 files) + src/utils/ (1 file) → auth
```

**Multiple directories — use semantic grouping:**
```
src/components/ + src/styles/   → ui
src/api/ + src/models/          → api
src/tests/ + src/fixtures/      → test
```

**Special scopes by file pattern:**
```
package.json, Cargo.toml, go.mod      → deps
.github/, .gitlab-ci.yml             → ci
*.config.js, *.config.ts, .env.*     → config
README.md, docs/                      → docs
*.test.*, *_test.*, spec/             → test
```

**Monorepo — use package name:**
```
packages/auth-service/  → auth-service
apps/dashboard/         → dashboard
```

**When scope adds no value:** omit it entirely — `fix: correct typo in error message` is cleaner than `fix(misc): correct typo`.

---

## Description Rules

- Imperative mood: "add", "fix", "update", "remove" — not "added", "fixing", "updates"
- Lowercase first letter
- No period at end
- Max 72 chars total including `type(scope): ` prefix
- Describe WHAT changed, not HOW or WHY (body handles that)
- Specific: "correct Redis TTL unit" not "fix bug"

**Good examples:**
```
feat(auth): add OAuth2 PKCE flow for mobile clients
fix(session): correct Redis TTL unit mismatch
refactor(parser): extract token validation into dedicated service
perf(search): add composite index on (user_id, created_at)
docs(api): document rate limiting headers in OpenAPI spec
test(checkout): add integration tests for payment failure scenarios
chore(deps): upgrade pytest from 7.2 to 8.1
```

**Bad examples (avoid):**
```
fix: fixed the thing            ← past tense, vague
feat: Added new feature         ← past tense, vague, capital
update stuff                    ← missing type, vague
fix(auth): Fix the auth bug.    ← capital, period, vague
```

---

## Body Rules

Include body when:
- The change requires explanation of motivation
- The "why" is not obvious from the description
- There are important details that reviewers need

Skip body for:
- Simple, self-explanatory changes
- Documentation-only changes
- Style/formatting changes

**Body format:**
```
<blank line>
<body — wrap at 100 characters>
<each paragraph separated by blank line>
```

**Good body:**
```
fix(session): correct Redis TTL unit mismatch

TTL was being set in seconds by the server but read as milliseconds
by the client, causing sessions to expire 1000x faster than intended.
The bug was introduced in #821 when the client library was upgraded.
```

---

## Footer Rules

**Issue references:**
```
Closes #123          ← closes the issue on merge
Fixes #123           ← same as Closes
Refs #123            ← just references, doesn't close
```

**Multiple issues:**
```
Closes #123
Closes #124
Refs #87
```

**Breaking changes (two formats — use BOTH):**
```
feat!(auth): change token format to JWT

Migrate existing sessions using the provided migration script.

BREAKING CHANGE: Bearer tokens are now JWT format. Existing tokens
will be invalidated. Run `npm run migrate:tokens` before deploying.
```

---

## Breaking Change Detection

Flag `BREAKING CHANGE:` when diff shows:
- **API endpoints:** path changed, method changed, required params removed, response schema changed
- **Functions:** parameter removed, parameter reordered, return type changed incompatibly
- **Database:** column removed, column type changed, table renamed
- **Config:** required env var removed or renamed, config key removed
- **Packages:** major version bump with known breaking changes

**Signals in diff:**
```python
BREAKING_PATTERNS = [
    r"^-\s+def\s+\w+\([^)]+\)",      # function signature removed
    r"^-.*DROP\s+COLUMN",             # database column dropped
    r"^-.*RENAME\s+TABLE",            # table renamed
    r"^-\s+[A-Z_]+=",                # env var removed
    r"^-.*@app\.route\(",             # route removed
    r"^-.*\"version\":",              # version field changed (package.json)
]
```

---

## Style Calibration by Project

Read last 5 commits to infer project conventions:
```bash
git log --oneline -5
```

**If project already uses Conventional Commits:** match exactly.

**If project uses plain messages:** note this and generate conventional format anyway (ghost-commit upgrades the style).

**If project has mixed style:** use conventional format, mention the inconsistency in the decision log.

---

## Revert Commits

When `git revert` was run:
```
revert: <original commit description>

This reverts commit <full hash>.
<Reason for revert from .ghost-context if available>
```

---

## Commit Message Checklist

Before presenting the commit message, verify:
- [ ] Type is one of the defined types
- [ ] Description is imperative mood
- [ ] Description is lowercase start
- [ ] Description has no trailing period
- [ ] Total first line ≤ 72 characters
- [ ] Body wrapped at 100 characters (if present)
- [ ] Footer present if issues mentioned in context
- [ ] BREAKING CHANGE footer present if breaking change detected
