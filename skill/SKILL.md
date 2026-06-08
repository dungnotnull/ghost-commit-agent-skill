---
name: ghost-commit
description: Generate semantic git commit messages, decision logs, CHANGELOG entries, and PR descriptions automatically from staged git diffs. Use this skill whenever a developer is about to commit code, wants to document why a change was made, needs to update a CHANGELOG, or wants a PR description drafted. Triggers include: "I'm about to commit", "generate a commit message", "write a decision log for this change", "update the CHANGELOG", "draft a PR description", "what should my commit message be", "document this change", or when a pre-commit hook fires. Also triggers when the agent detects git staging activity (git add, git stage) followed by a commit intent. This skill captures developer reasoning at the exact moment it exists — before it's lost.
---

# ghost-commit Skill

You capture what developers know right now — before they commit and forget it. You generate four structured outputs from a git diff and optional context, then present them for approval. You never write anything without the developer's explicit sign-off.

---

## PHASE 0 — TRIGGER DETECTION

Determine which trigger fired:

**Trigger A — Pre-commit hook:**
```bash
python skill/scripts/ghost_commit.py --hook-mode pre
```
Context: files are staged, commit is pending, developer is waiting.

**Trigger B — Manual run:**
```bash
python skill/scripts/ghost_commit.py --run
```
Context: developer explicitly invoked ghost-commit.

**Trigger C — Agent-initiated:**
Agent reads this SKILL.md and runs the analysis itself.
Context: agent is inside a coding session and about to commit.

**Trigger D — Direct call:**
User says "generate commit message / decision log / PR description".

For Trigger C and D: run Phase 1 immediately.

---

## PHASE 1 — GATHER GIT CONTEXT

Run these commands and capture all output:

```bash
git diff --staged --stat          # file list and change stats
git diff --staged                 # full diff content
git log --oneline -5              # recent commit context (infer style)
git branch --show-current         # branch name
git config user.name              # author
git config user.email             # email
git rev-parse --short HEAD        # current HEAD short hash
```

**Skip conditions — exit cleanly with a message:**
```bash
# Check for merge commit in progress
[ -f .git/MERGE_HEAD ] && echo "Merge commit — skipping ghost-commit" && exit 0

# Check for empty diff
git diff --staged --quiet && echo "Nothing staged — nothing to commit" && exit 0

# Check skip patterns from .ghost-commit.yml if present
```

**Load classification:**
Run `scripts/diff_analyzer.py` on the staged diff:
```bash
python skill/scripts/diff_analyzer.py --staged --json
```
This returns: `{type, scope, risk_level, breaking_change, files, stats, signals}`

---

## PHASE 2 — READ DEVELOPER CONTEXT

Run `scripts/context_reader.py`:
```bash
python skill/scripts/context_reader.py --read
```

**If `.ghost-context` has content:**
- Extract: why, what-tried, constraints, risk-assessment, references
- Context quality: HIGH — use verbatim where possible
- Preserve developer's own words in decision log

**If `.ghost-context` is empty or absent:**
- Infer intent from diff analysis alone
- Context quality: MEDIUM/LOW — mark inferences clearly
- In decision log: note "Inferred from diff — no context provided"

**Load project config:**
```bash
python skill/scripts/ghost_commit.py --print-config
```
Reads `.ghost-commit.yml` if present, otherwise uses defaults.

---

## PHASE 3 — GENERATE ALL OUTPUTS

Load `references/conventional-commits-guide.md` for commit message rules.
Load `references/diff-analysis-guide.md` for classification help.
Load `references/decision-log-templates.md` for log format.
Load `references/changelog-spec.md` for CHANGELOG format.

### Output 1: Commit Message

Apply rules from `references/conventional-commits-guide.md`:

```
<type>(<scope>): <description>          ← max 72 chars total

<body>                                   ← wrap at 100 chars, optional

<footer>                                 ← Closes #N, BREAKING CHANGE:, optional
```

**Type selection logic:**
- If `.ghost-context` explicitly states the type → use it
- Else → use `diff_analyzer.py` classification
- When ambiguous between `fix` and `refactor` → `fix` if behavior changes, `refactor` if not
- When test files + source files both changed → use source file type (tests follow the change)

**Scope selection:**
- Single directory changed → directory name
- Multiple directories → most-changed directory or `core`/`api`/`db` by pattern
- Config/tooling only → `config`
- Multiple packages (monorepo) → package name

**Breaking change:**
- If `diff_analyzer.py` returns `breaking_change: true` → add `BREAKING CHANGE:` footer
- Also add `!` after type: `feat!` or `fix!`

**Body:**
- Only include if change complexity warrants explanation
- Explain WHY not WHAT (the diff shows what)
- Use imperative mood: "Fix" not "Fixed" not "Fixes"

---

### Output 2: Decision Log

Apply template from `references/decision-log-templates.md` based on risk level.

Filename: `.decisions/YYYY-MM-DD-<short-hash>.md`

**Population rules:**
- **Context section**: use `.ghost-context` "why" if available; else infer from diff
- **Decision section**: what was actually implemented (from diff)
- **Alternatives considered**: from `.ghost-context` "what-tried" if available; else write "Not documented — add context in .ghost-context before committing"
- **Constraints**: from `.ghost-context` "constraints" if available
- **Risk level**: from `diff_analyzer.py` risk scoring
- **Future implications**: infer from diff — note any TODOs, temporary workarounds, or related areas

**Quality rule:** A decision log with no `.ghost-context` input is still valuable — it captures the diff-level facts. Flag clearly what was inferred vs. stated.

---

### Output 3: CHANGELOG Entry

Apply rules from `references/changelog-spec.md`.

**Structure:**
```markdown
## [Unreleased]

### <Category>
- <entry> (#<issue-ref if detected>)
```

**Category from commit type:**
```
feat     → ### Added
fix      → ### Fixed
perf     → ### Changed
refactor → ### Changed
docs     → ### Changed
security → ### Security
remove   → ### Removed
```

**Entry style:**
- User-facing language (not technical)
- Past tense for Fixed/Changed/Removed: "Fixed session timeout bug"
- Present for Added: "Add OAuth2 PKCE support for mobile clients"
- Include issue reference if found in `.ghost-context` or branch name
- Max 120 chars

**If CHANGELOG.md does not exist:**
- Offer to create with `--init-changelog`
- Do not fail — note it in the output

---

### Output 4: PR Description Draft

**Generate only if:**
- Branch name contains `/` (feature/fix/feat/bugfix/hotfix pattern)
- OR `--force-pr` flag was passed
- AND this is NOT a merge commit

**Template:** See `references/decision-log-templates.md` → PR description section.

Populate from:
- What: diff summary
- Why: `.ghost-context` "why" or inferred
- Testing: test files changed → list them; no test files → add "[ ] Tests needed"
- Breaking changes: from diff_analyzer output

---

## PHASE 4 — PRESENTATION & APPROVAL

Display all generated outputs clearly separated. Then prompt:

```
╔══════════════════════════════════════════════════════════╗
║  ghost-commit — review generated outputs                 ║
╚══════════════════════════════════════════════════════════╝

─── COMMIT MESSAGE ─────────────────────────────────────────
fix(session): correct Redis TTL unit mismatch for session expiry

TTL was set in seconds by server but read as milliseconds by
client, causing sessions to expire 1000x faster than intended.

Closes #847
────────────────────────────────────────────────────────────

─── DECISION LOG ───────────────────────────────────────────
→ Will be saved to: .decisions/2026-06-07-a3f9c12.md
[preview of first 20 lines]
────────────────────────────────────────────────────────────

─── CHANGELOG ENTRY ────────────────────────────────────────
### Fixed
- Correct Redis TTL unit mismatch causing premature session expiry (#847)
────────────────────────────────────────────────────────────

─── PR DESCRIPTION ─────────────────────────────────────────
[full draft]
────────────────────────────────────────────────────────────

[A]ccept all  [E]dit  [S]elect  [R]eject  [?]help  >
```

**Accept all (A):**
- Write commit message → git picks it up via `COMMIT_EDITMSG`
- Create decision log file
- Update CHANGELOG.md (insert under `[Unreleased]`)
- Copy PR description to clipboard (pbcopy/xclip/clip)
- Clear `.ghost-context` and restore template

**Edit (E):**
- Open `$EDITOR` with all outputs in one temp file
- Re-parse after save
- Re-present summary

**Select (S):**
- Interactive selection: which outputs to apply
- Apply only selected

**Reject (R):**
- Exit cleanly
- Leave `.ghost-context` intact for next attempt
- Do not block the commit (developer writes their own message)

---

## PHASE 5 — POST-COMMIT CLEANUP

Run via `post-commit` hook (installed separately):
```bash
python skill/scripts/ghost_commit.py --hook-mode post
```

Actions:
1. Update decision log with actual commit hash (now known)
2. Archive `.ghost-context` (clear content, keep template)
3. Print one-line summary: `👻 ghost-commit: decision log saved to .decisions/2026-06-07-a3f9c12.md`

---

## IMPORTANT BEHAVIORS

**Never auto-commit.** You are an advisor, not an executor. Always present for approval.

**Preserve developer voice.** When `.ghost-context` has content, quote it directly in the decision log rather than paraphrasing. The developer's exact words are more valuable than polished prose.

**Be honest about quality.** If generating from diff alone (no context), say so clearly. "Inferred from diff analysis — add context in .ghost-context for a richer decision log."

**Skip gracefully.** Merge commits, reverts, empty diffs — exit with a clear message, never block the workflow.

**Fail open.** If any output generation fails, skip that output and proceed with the others. Never block a commit because the CHANGELOG update failed.

---

## REFERENCE FILES

| File | Load During |
|---|---|
| `references/conventional-commits-guide.md` | Phase 3: commit message |
| `references/diff-analysis-guide.md` | Phase 1–3: diff classification |
| `references/decision-log-templates.md` | Phase 3: decision log + PR draft |
| `references/changelog-spec.md` | Phase 3: CHANGELOG entry |

## SCRIPTS

| Script | When | Key Args |
|---|---|---|
| `scripts/ghost_commit.py` | Phase 0 dispatch | `--run`, `--hook-mode pre/post`, `--print-config` |
| `scripts/diff_analyzer.py` | Phase 1 | `--staged`, `--json`, `--file path` |
| `scripts/context_reader.py` | Phase 2 | `--read`, `--write-template`, `--clear` |
| `scripts/output_writer.py` | Phase 4 accept | `--decision-log`, `--changelog`, `--pr-draft` |
| `scripts/install_hook.py` | Setup | `--install`, `--uninstall`, `--status` |
