# 👻 ghost-commit

> *Every commit tells you what changed. ghost-commit tells you why.*

A Claude Skill that hooks into your git workflow and automatically generates — before every commit — a semantic commit message, a decision log capturing your reasoning, a CHANGELOG entry, and a PR description draft.

---

## The Problem

```
git log --oneline
a3f9c12  fix stuff
bb823f1  update
c912d44  wip
d8a10f1  final
```

The code tells you what changed. Nobody knows why.

Six months later, you're reading `timeout = 45` and wondering: was that a deliberate choice? A deadline workaround? A bug fix? That context is gone.

**ghost-commit captures it at the exact moment it exists — right before you commit.**

---

## What It Generates

On every `git commit`, ghost-commit produces:

| Output | Example |
|---|---|
| **Commit message** | `fix(session): correct Redis TTL unit mismatch` |
| **Decision log** | `.decisions/2026-06-07-a3f9c12.md` with context, alternatives, constraints |
| **CHANGELOG entry** | `### Fixed` `- Fix sessions expiring prematurely (#847)` |
| **PR description** | Full GitHub/GitLab PR draft, ready to paste |

---

## Install (5 minutes)

### Step 1: Clone or place the skill

```bash
git clone https://github.com/your-org/ghost-commit ~/.ghost-commit
# OR place the skill folder wherever you keep your Claude skills
```

### Step 2: Install in your repo

```bash
cd your-project
python ~/.ghost-commit/skill/scripts/install_hook.py --install
```

This:
- Installs `pre-commit` and `post-commit` git hooks
- Creates `.ghost-commit.yml` config file
- Creates `.ghost-context` template
- Updates `.gitignore` to exclude decision logs and context file

### Step 3: (Optional) Install for Claude Code

```bash
python ~/.ghost-commit/skill/scripts/install_hook.py --install --with-claude-code
```

Adds hooks to `.claude/settings.json` so Claude Code agents also trigger ghost-commit.

---

## Quick Start

```bash
# 1. Make some changes
echo "fix something" >> src/app.py

# 2. Stage them
git add src/app.py

# 3. (Optional but powerful) Add context
python ~/.ghost-commit/skill/scripts/ghost_commit.py --context
# Opens .ghost-context in your $EDITOR — fill in the "why"

# 4. Commit as normal
git commit
# ghost-commit runs automatically and presents its outputs

# 5. Review and accept
# [A]ccept all | [E]dit | [S]elect some | [R]eject
```

---

## The .ghost-context File

The secret weapon. Fill this in before committing and ghost-commit captures your reasoning permanently.

```markdown
## Why I'm making this change
Fixing the session timeout bug from #847. Redis TTL was set in seconds
but PEXPIRE expects milliseconds — sessions expired 1000x too fast.

## What I tried first
Tried patching the client side first but the webhook service also
reads this value and we don't control it.

## Constraints
Can't change the Redis key format without a migration (doing that
in #851). Keeping this change minimal and focused.

## References
Closes #847, Refs #851
```

ghost-commit reads this and produces:

```
fix(session): correct Redis TTL unit mismatch

TTL was set in seconds by the server but read as milliseconds by
the client, causing sessions to expire 1000x faster than intended.

Closes #847
```

And a decision log with all your reasoning captured forever.

---

## Example Outputs

### Commit Message
```
fix(session): correct Redis TTL unit mismatch for session expiry

TTL was being set in seconds by the server but read as milliseconds
by the client, causing sessions to expire 1000x faster than intended.

Closes #847
```

### Decision Log (`.decisions/2026-06-07-a3f9c12.md`)
```markdown
# Decision: correct Redis TTL unit mismatch — 2026-06-07

**Commit:** `a3f9c12`
**Author:** Jane Dev <jane@example.com>
**Branch:** `fix/847-session-timeout`
**Files changed:** 2 files, +23 −8 lines
**Risk level:** Medium

## Context
Fixing the session timeout bug from #847. Sessions were expiring
1000x faster than intended because Redis TTL was set in seconds
but PEXPIRE expects milliseconds.

## Decision
Changed `self.redis.expire(key, seconds)` to `self.redis.pexpire(key, seconds * 1000)`.
Normalising to milliseconds at the point of write.

## Alternatives considered
Tried patching the client side but the webhook service also reads
this value and we don't control it.

## Constraints
Can't change the Redis key format without a migration (doing that
in a separate PR #851). Keeping this change minimal.
```

### CHANGELOG.md
```markdown
## [Unreleased]

### Fixed
- Fix sessions expiring prematurely due to Redis TTL unit mismatch (#847)
```

---

## Commands

```bash
# Run manually (without committing)
python ghost_commit.py --run

# Open .ghost-context in editor
python ghost_commit.py --context

# Show current status
python install_hook.py --status

# Create CHANGELOG.md if missing
python ghost_commit.py --init-changelog

# Print resolved config
python ghost_commit.py --print-config

# Skip ghost-commit for one commit
git commit --no-verify

# Uninstall
python install_hook.py --uninstall
```

---

## Configuration (`.ghost-commit.yml`)

```yaml
outputs:
  commit_message: true
  decision_log: true
  changelog: true
  pr_description: true   # Only on feature/fix branches

decisions:
  directory: .decisions
  gitignore: true        # Add to .gitignore (recommended)
  commit_logs: false     # Set true to commit decision logs to repo

changelog:
  file: CHANGELOG.md
  auto_update: true
  section: Unreleased

commit:
  max_subject_length: 72
  enforce_conventional: true

context:
  scratchpad_file: .ghost-context
  clear_after_commit: true  # Wipe .ghost-context after each commit

skip:
  branches: [main, master, "release/*"]
  commit_patterns: ["^Merge", "^Revert", "^WIP"]
```

---

## Integration Options

| Mode | How | Best For |
|---|---|---|
| **Git hook** (default) | `install_hook.py --install` | All git workflows |
| **Claude Code hook** | `--with-claude-code` | AI coding sessions |
| **Manual** | `ghost_commit.py --run` | When you want full control |
| **CI/agent** | `--hook-mode pre` | Automated commit workflows |

---

## Comparison

| | ghost-commit | GitHub Copilot | Commitizen | release-please |
|---|---|---|---|---|
| Commit message | ✅ | ✅ | ✅ | ❌ |
| Decision log | ✅ | ❌ | ❌ | ❌ |
| CHANGELOG | ✅ | ❌ | ✅ | ✅ |
| PR description | ✅ | ✅ | ❌ | ❌ |
| Works offline | ✅ | ❌ | ✅ | ❌ |
| No dependencies | ✅ | ❌ | ❌ | ❌ |
| Captures "why" | ✅ | ❌ | ❌ | ❌ |

---

## File Structure

```
ghost-commit/
├── skill/
│   ├── SKILL.md                     ← Main harness (Claude reads this)
│   ├── references/
│   │   ├── conventional-commits-guide.md
│   │   ├── diff-analysis-guide.md
│   │   ├── decision-log-templates.md
│   │   └── changelog-spec.md
│   ├── scripts/
│   │   ├── ghost_commit.py          ← Main orchestrator
│   │   ├── diff_analyzer.py         ← Diff parser & classifier
│   │   ├── context_reader.py        ← .ghost-context parser
│   │   ├── output_writer.py         ← Writes decision logs, CHANGELOG
│   │   └── install_hook.py          ← One-command installer
│   └── assets/
│       ├── ghost-context-template.md
│       └── pre-commit.sh
└── evals/
    └── evals.json                   ← 10 test cases
```

---

## Requirements

- Python 3.10+ (standard library only — zero pip dependencies)
- Git 2.x+
- macOS, Linux, or Windows 10+

---

*ghost-commit v1.0.0 — Because future you deserves to know why.*
