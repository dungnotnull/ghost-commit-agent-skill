# Changelog Spec — Keep a Changelog

_Load during Phase 3 when generating CHANGELOG entries._
_Spec: https://keepachangelog.com/en/1.1.0/_

---

## File Structure

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- ...

### Fixed
- ...

## [1.2.0] — 2026-05-10

### Added
- New feature X

### Fixed
- Bug Y

## [1.1.0] — 2026-04-01
...

[Unreleased]: https://github.com/owner/repo/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/owner/repo/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/owner/repo/releases/tag/v1.1.0
```

---

## Category Mapping

| Commit Type | CHANGELOG Category | Description |
|---|---|---|
| `feat` | **Added** | New features, endpoints, capabilities |
| `fix` | **Fixed** | Bug fixes, corrections |
| `perf` | **Changed** | Performance improvements |
| `refactor` | **Changed** | Internal restructuring (if user-visible) |
| `docs` | **Changed** | Documentation updates (if public docs) |
| `security` | **Security** | Vulnerabilities fixed |
| `deprecated` | **Deprecated** | Features being phased out |
| `remove` | **Removed** | Features removed |
| `style` | *(skip)* | Internal formatting — not user-relevant |
| `test` | *(skip)* | Test changes — not user-relevant |
| `build` | *(skip)* | Build system — not user-relevant |
| `ci` | *(skip)* | CI config — not user-relevant |
| `chore` | *(skip)* | Maintenance — not user-relevant |

**Rule:** If skip-category commits are part of a larger feat/fix, they still get no CHANGELOG entry. Only the feat/fix entry appears.

---

## Entry Writing Rules

### Language
- **Added**: present tense — "Add OAuth2 PKCE support for mobile clients"
- **Fixed**: past tense — "Fixed session timeout calculation in Redis TTL"
- **Changed**: past tense — "Improved query performance by adding composite index"
- **Removed**: past tense — "Removed deprecated `/api/v1/users` endpoint"
- **Deprecated**: present tense — "Deprecate `/api/v1/auth` in favor of `/api/v2/auth`"
- **Security**: past tense — "Fixed XSS vulnerability in user-generated content rendering"

### Perspective
- Write from the **user's perspective**, not the developer's
- Describe the **effect** on the user, not the internal implementation
- BAD: "Changed Redis TTL to use milliseconds instead of seconds"
- GOOD: "Fixed sessions expiring prematurely after a few milliseconds"

### Issue References
- Include `(#N)` at the end of the entry if issue number is found
- Source: `.ghost-context` references section, branch name (`fix/847-session`), commit body
- Format: `- Fixed premature session expiry caused by TTL unit mismatch (#847)`

### Length
- One line per entry preferred — max 120 chars
- For complex changes: one summary line + indented sub-bullets
```markdown
### Added
- Add support for OAuth2 PKCE flow for mobile and desktop clients (#234)
  - Supports Authorization Code with PKCE (RFC 7636)
  - Compatible with all existing OAuth2 providers
```

---

## Insertion Rules

### Finding the insertion point

```python
def find_unreleased_section(changelog_content: str) -> int:
    """Returns the line index where new entries should be inserted."""
    lines = changelog_content.split('\n')
    
    # Find ## [Unreleased] header
    for i, line in enumerate(lines):
        if re.match(r'^## \[Unreleased\]', line, re.I):
            # Find the right category subsection
            return i  # caller handles category placement
    
    # [Unreleased] section doesn't exist — create it after the header
    for i, line in enumerate(lines):
        if re.match(r'^## \[', line):  # First versioned section
            return i  # Insert before it
    
    return len(lines)  # Append at end
```

### Finding or creating the category

```python
CATEGORY_ORDER = ['Added', 'Changed', 'Deprecated', 'Removed', 'Fixed', 'Security']

def find_or_create_category(lines: list[str], start: int, category: str) -> int:
    """Returns line index to insert the new entry. Creates category if missing."""
    # Search from [Unreleased] to next ## section
    for i in range(start + 1, len(lines)):
        if re.match(r'^## \[', lines[i]):
            break  # Reached next version section
        if re.match(rf'^### {category}', lines[i]):
            # Find the last entry in this category
            j = i + 1
            while j < len(lines) and not re.match(r'^###|^## \[', lines[j]):
                j += 1
            return j  # Insert before next category or version
    
    # Category not found — create it in the right position
    # Insert after [Unreleased] header or after last existing category
    # Respect CATEGORY_ORDER
    ...
    return insertion_point
```

### Entry format
```python
def format_entry(category: str, description: str, issue_ref: str = None) -> str:
    entry = f"- {description}"
    if issue_ref:
        entry += f" ({issue_ref})"
    return entry
```

---

## CHANGELOG Initialization

When no `CHANGELOG.md` exists:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### {{CATEGORY}}
- {{ENTRY}}
```

Offer to create it: `"No CHANGELOG.md found. Create one? [Y/n]"`

---

## Multiple Entries Per Commit

When a commit changes multiple independent things (bad practice but real):
- Generate one CHANGELOG entry for the primary change (highest impact)
- If secondary changes are user-visible, add them too
- Flag: "This commit affects multiple concerns — consider splitting in future"

---

## Validation Checklist

Before presenting CHANGELOG entry:
- [ ] Category matches commit type mapping
- [ ] Language tense matches category convention
- [ ] Written from user perspective (not implementation perspective)
- [ ] Under 120 characters (or sub-bullets used)
- [ ] Issue reference included if available
- [ ] Not duplicating an existing entry
- [ ] Inserted under `[Unreleased]` section (not under a versioned release)
