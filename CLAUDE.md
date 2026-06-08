# ghost-commit — Claude Skill

> *"Every commit tells you what changed. ghost-commit tells you why."*

---

## What This Project Does

**ghost-commit** is a Claude Skill that hooks into your git workflow and — before every commit — automatically generates:

1. **Semantic commit message** (Conventional Commits spec)
2. **Decision log entry** (why this approach, what was rejected, what constraint drove it)
3. **CHANGELOG.md update** (Keep a Changelog spec)
4. **PR description draft** (if branch matches a PR pattern)

The agent reads `git diff --staged`, optionally reads a `.ghost-context` scratchpad you fill in, and produces all four outputs for your review. It never auto-commits — you always approve before anything is written.

---

## Why It's Unique

| Tool | Commit Msg | Decision Log | CHANGELOG | PR Draft | Offline |
|---|---|---|---|---|---|
| GitHub Copilot | ✅ | ❌ | ❌ | ✅ | ❌ |
| Commitizen | ✅ (prompt) | ❌ | ✅ | ❌ | ✅ |
| Release-please | ❌ | ❌ | ✅ | ❌ | ❌ |
| **ghost-commit** | ✅ | ✅ | ✅ | ✅ | ✅ |

The critical gap: **no tool captures the developer's reasoning at commit time**. That context lives in someone's head and evaporates. ghost-commit captures it at the exact moment it exists.

---

## Repository Structure

```
ghost-commit/
├── CLAUDE.md                              ← You are here
├── PROJECT-detail.md                      ← Full specification
├── PROJECT-DEVELOPMENT-PHASE-TRACKING.md  ← Phase tracker
├── README.md                              ← Install & quick-start
├── skill/
│   ├── SKILL.md                           ← Main skill harness
│   ├── references/
│   │   ├── conventional-commits-guide.md  ← Commit type rules & examples
│   │   ├── diff-analysis-guide.md         ← How to read & classify diffs
│   │   ├── decision-log-templates.md      ← Decision log format & examples
│   │   └── changelog-spec.md             ← Keep a Changelog format rules
│   ├── scripts/
│   │   ├── ghost_commit.py               ← Main orchestrator
│   │   ├── diff_analyzer.py              ← Git diff parser & classifier
│   │   ├── context_reader.py             ← .ghost-context scratchpad reader
│   │   ├── output_writer.py              ← Write decision log, CHANGELOG, PR draft
│   │   └── install_hook.py              ← One-command git hook installer
│   └── assets/
│       ├── ghost-context-template.md     ← .ghost-context template
│       └── pre-commit.sh                ← Git hook shell script
└── evals/
    └── evals.json                        ← Test cases
```

---

## Integration Points

```
Developer stages files
        │
        ▼
  git commit triggered
        │
        ▼
  pre-commit hook fires
        │
        ▼
  ghost_commit.py runs
  ├── reads git diff --staged
  ├── reads .ghost-context (if present)
  ├── calls Claude agent via SKILL.md
  └── presents outputs for approval
        │
        ▼
  Developer reviews & approves
        │
        ├──► commit message written
        ├──► .decisions/YYYY-MM-DD-{hash}.md created
        ├──► CHANGELOG.md updated
        └──► PR description copied to clipboard
```

---

## Tech Stack

- Python 3.10+ (stdlib only — no pip dependencies required)
- Git hooks (pre-commit)
- Claude Code hooks (optional — deeper integration)
- Markdown output
- Works fully offline / on air-gapped machines
