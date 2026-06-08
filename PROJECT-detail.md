# PROJECT-detail.md — ghost-commit

## 1. Core Problem

Software teams lose enormous institutional knowledge because:
- Commit messages describe **what** changed, never **why**
- The reasoning lives in Slack threads, Jira comments, or developer heads
- Six months later, nobody knows why that `timeout = 30` became `timeout = 45`
- PR descriptions are written after the fact with diminished context
- CHANGELOGs are maintained manually and always out of date

ghost-commit intercepts the developer at the only moment they have full context — **right before they commit** — and captures everything automatically.

---

## 2. The .ghost-context Scratchpad

The most important design decision in ghost-commit.

Before committing, a developer can optionally write in `.ghost-context` (a gitignored file in the repo root):

```markdown
# Why I'm making this change
Fixing the session timeout bug reported in #847. The root cause was that
Redis TTL was being set in seconds but the client was reading it as milliseconds.

# What I tried first
Tried patching the client side — didn't work because the value is also
used by the webhook service which we don't control.

# Constraints
Can't change the Redis key format without a migration — doing that in a
separate PR (#851).

# Risk level
Low — only affects new sessions. Existing sessions use cached values.
```

The agent reads this and uses it to generate a decision log that actually makes sense. If `.ghost-context` is empty or absent, the agent falls back to pure diff analysis and makes reasonable inferences.

The template is pre-filled with prompts each time — developers just fill in what they know.

---

## 3. Output Specification

### Output 1: Semantic Commit Message

**Format:** Conventional Commits 1.0.0
```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`

**Rules:**
- Description: imperative mood, lowercase, no period, max 72 chars
- Body: wrap at 100 chars, explain motivation not mechanics
- Footer: `BREAKING CHANGE:`, `Closes #N`, `Refs #N`
- If breaking change detected in diff: must include `BREAKING CHANGE:` footer

**Example:**
```
fix(session): correct Redis TTL unit mismatch for session expiry

TTL was being set in seconds by the server but read as milliseconds
by the client, causing sessions to expire 1000x faster than intended.

Fixed by normalising to milliseconds at the point of write.

Closes #847
```

---

### Output 2: Decision Log Entry

**Location:** `.decisions/YYYY-MM-DD-<short-hash>.md`
**Gitignore or commit:** developer's choice (default: gitignored)
**Format:**

```markdown
# Decision: <title> — <date>

**Commit:** `<full hash>`
**Author:** <name>
**Files changed:** <N files, +X -Y lines>
**Risk level:** Low / Medium / High

## Context
[What situation prompted this change]

## Decision
[What was decided and implemented]

## Alternatives considered
[What else was tried or considered and why rejected]

## Constraints
[What limitations drove the approach]

## Future implications
[What this decision means for future work — tech debt, follow-up PRs, etc.]

## References
[Issue numbers, PRs, Slack threads, docs]
```

---

### Output 3: CHANGELOG.md Entry

**Format:** Keep a Changelog (https://keepachangelog.com)
**Placement:** Under `## [Unreleased]` section, correct category

```markdown
## [Unreleased]

### Fixed
- Correct Redis TTL unit mismatch causing sessions to expire prematurely (#847)

### Added
- ...

### Changed
- ...
```

**Category mapping from commit type:**
| Commit type | CHANGELOG category |
|---|---|
| `feat` | Added |
| `fix` | Fixed |
| `refactor`, `perf` | Changed |
| `docs` | Changed |
| `security` | Security |
| `deprecated` | Deprecated |
| `remove` | Removed |

---

### Output 4: PR Description Draft

**Generated when:** branch name contains `/`, `-`, or matches patterns like `feature/`, `fix/`, `feat/`, `bugfix/`
**Format:** GitHub/GitLab PR description markdown

```markdown
## What does this PR do?
[1–3 sentence summary]

## Why?
[Context from .ghost-context or inferred from diff]

## Changes
- [Bullet list of key changes]

## Testing
- [ ] Unit tests pass
- [ ] Manual testing: [what to test]
- [ ] Edge cases considered: [list]

## Breaking changes
[None / description]

## Screenshots / recordings
[If applicable]

## References
Closes #N
```

---

## 4. Diff Classification System

`diff_analyzer.py` classifies every staged diff along 4 axes:

### 4.1 Change Type
| Type | Signal patterns |
|---|---|
| `feat` | New functions/classes/endpoints/routes added; new files in feature dirs |
| `fix` | Bug fix patterns; error handling; condition corrections; off-by-one fixes |
| `refactor` | Same behavior, restructured code; extract method; rename; move |
| `perf` | Caching added; algorithm changed; N+1 queries fixed; indexes added |
| `test` | Only `*.test.*`, `*_test.*`, `*spec*`, `tests/` changed |
| `docs` | Only `*.md`, `*.rst`, `*.txt`, docstrings, comments changed |
| `style` | Whitespace, formatting, semicolons — no logic change |
| `build` | `package.json`, `Cargo.toml`, `requirements.txt`, `Makefile` changed |
| `ci` | `.github/`, `.gitlab-ci.yml`, `Jenkinsfile` changed |
| `chore` | Config files, `.env.example`, gitignore, tooling config |

### 4.2 Scope
Detected from directory structure:
- Single directory → that directory name
- Multiple directories → most common ancestor or `core`/`api`/`db`/etc. by pattern
- Single file → file name without extension (for small repos)

### 4.3 Risk Level
```python
RISK_SIGNALS = {
    "high": [
        "auth", "security", "password", "token", "secret", "encrypt",
        "payment", "billing", "database", "migration", "schema",
        "delete", "drop", "truncate", "CASCADE",
    ],
    "medium": [
        "api", "endpoint", "route", "model", "service",
        "config", "settings", "env", "timeout", "retry",
    ],
    "low": [
        "test", "spec", "fixture", "mock", "stub",
        "readme", "docs", "comment", "style", "format",
    ]
}
```

### 4.4 Breaking Change Detection
Signals that trigger `BREAKING CHANGE:` in commit footer:
- Public API function signature changed (parameters removed/reordered)
- Database schema column removed or type changed
- Environment variable removed or renamed
- Config key removed
- HTTP endpoint path or method changed
- Return type changed in a breaking-compatible way

---

## 5. Workflow Phases

### Phase 0: Trigger Detection
```
Trigger A: git pre-commit hook (automatic on every commit attempt)
Trigger B: Manual run — python ghost_commit.py --run
Trigger C: Claude Code PreToolUse hook (when agent is about to commit)
```

### Phase 1: Diff Analysis
```
git diff --staged --stat        → file list and stats
git diff --staged               → full diff content
git log --oneline -5            → recent commit context
git branch --show-current       → branch name (for PR draft decision)
git config user.name/email      → author info
```

### Phase 2: Context Reading
```
IF .ghost-context exists AND has content:
    Read and parse all sections
    Merge with diff analysis
    Context quality: HIGH

ELSE IF recent commit messages exist:
    Use last 5 commits to infer project style
    Context quality: MEDIUM

ELSE:
    Pure diff analysis
    Context quality: LOW (note this in outputs)
```

### Phase 3: Generation
```
Generate all applicable outputs in parallel:
1. Commit message (always)
2. Decision log (always)
3. CHANGELOG entry (always, if CHANGELOG.md exists or --init-changelog flag)
4. PR description (if branch name suggests feature/fix work)
```

### Phase 4: Presentation & Approval
```
Display all outputs in terminal with clear sections.
Ask: Accept all [A] / Edit [E] / Reject [R] / Accept some [S]?

Accept all:
    - Write commit message to git COMMIT_EDITMSG
    - Create .decisions/YYYY-MM-DD-{hash}.md
    - Update CHANGELOG.md
    - Copy PR description to clipboard (if applicable)

Edit:
    - Open preferred editor with generated content
    - Re-present after edit

Reject:
    - Exit cleanly, let developer write their own message
    - Optionally: still save decision log draft for later

Accept some:
    - Interactive selection of which outputs to apply
```

### Phase 5: Post-Commit (optional)
```
After successful commit:
    - Update decision log with actual commit hash
    - Archive .ghost-context (clear it for next commit)
    - Optional: print summary of what was written
```

---

## 6. Installation Modes

### Mode A: Standalone (any git repo)
```bash
cd your-repo
python /path/to/ghost-commit/skill/scripts/install_hook.py --install
# Installs .git/hooks/pre-commit
# Creates .ghost-context template
# Adds .decisions/ to .gitignore (optional)
```

### Mode B: Claude Code Hook
Add to `.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "bash",
        "hooks": [{
          "type": "command",
          "command": "python /path/to/ghost_commit.py --hook-mode pre"
        }]
      }
    ]
  }
}
```

### Mode C: Manual (run when you want)
```bash
python ghost_commit.py --run
# Runs analysis on current staged files
# Presents all outputs for approval
```

---

## 7. Configuration (.ghost-commit.yml)

```yaml
# .ghost-commit.yml (repo root, committed)

# Outputs to generate
outputs:
  commit_message: true
  decision_log: true
  changelog: true
  pr_description: true   # Only if on feature/fix branch

# Decision log settings
decisions:
  directory: .decisions    # Where to store decision logs
  gitignore: true          # Add to .gitignore automatically
  commit_logs: false       # Commit them to the repo (if false: gitignored)

# CHANGELOG settings
changelog:
  file: CHANGELOG.md
  auto_update: true
  section: Unreleased      # Section to append to

# Commit message settings
commit:
  max_subject_length: 72
  enforce_conventional: true
  require_scope: false     # Prompt for scope if not detected

# Context settings
context:
  scratchpad_file: .ghost-context
  clear_after_commit: true  # Wipe .ghost-context after successful commit
  template_reprompt: true   # Re-fill template after clearing

# Skip patterns (don't run ghost-commit for these)
skip:
  branches: ["main", "master", "release/*"]
  commit_patterns: ["^Merge", "^Revert", "^WIP"]
  file_patterns: ["*.lock", "*.min.js", "dist/*"]
```

---

## 8. Edge Cases

| Situation | Handling |
|---|---|
| Merge commit | Skip ghost-commit entirely (detect via `MERGE_HEAD`) |
| Revert commit | Detect `git revert` pattern, use `revert` type, reference original commit |
| Empty diff (amended commit) | Use previous commit message as base, note as amendment |
| Binary files only | Note binary changes, use `chore` type, skip diff analysis |
| 500+ line diff | Summarize by file/directory, warn about large commit scope |
| No CHANGELOG.md | Offer to create one with `--init-changelog` |
| Monorepo | Detect multiple packages, scope commit to affected package(s) |
| Squash commits | Option to merge multiple `.ghost-context` files |
| No git repo | Exit gracefully with helpful error |
| Hook already exists | Offer to append rather than overwrite |
