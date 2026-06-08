#!/usr/bin/env python3
"""
context_reader.py — .ghost-context Scratchpad Reader
Part of the ghost-commit skill.

Reads and parses the .ghost-context file that developers fill in
before committing to capture the "why" behind their changes.

Usage:
    python context_reader.py --read               # Read and parse .ghost-context
    python context_reader.py --write-template     # Write fresh template
    python context_reader.py --clear              # Clear content, restore template
    python context_reader.py --status             # Show context quality assessment
"""

import sys
import re
import json
import argparse
from datetime import datetime
from pathlib import Path

DEFAULT_CONTEXT_FILE = ".ghost-context"

TEMPLATE = """\
# ghost-context — Developer Intent Scratchpad
# Fill in as much or as little as you know. Everything here is optional.
# This file is gitignored. Your thoughts stay local.
# Clear sections you don't need — ghost-commit handles the rest.
# Generated: {timestamp}

## Why I'm making this change
<!-- What problem, bug, or requirement prompted this change?
     Be as specific as you want — this becomes your decision log. -->


## What I tried first
<!-- What other approaches did you try or consider before this?
     Why did you reject them? This is the most valuable context to capture. -->


## Constraints
<!-- What technical, business, or external constraints shaped your approach?
     Deadlines, existing APIs, backward compatibility, team agreements, etc. -->


## Risk assessment
<!-- Any concerns about this change? Anything that could go wrong?
     Related areas that might be affected? -->


## References
<!-- Issue numbers, PR links, Slack threads, docs, ADRs
     Format: #123, JIRA-456, https://... -->


## Testing notes
<!-- What did you test? What should reviewers verify?
     Any edge cases you're worried about? -->

"""

# Section header patterns to parse
SECTION_PATTERNS = {
    "why":           r"##\s+Why I.?m making this change",
    "tried":         r"##\s+What I tried first",
    "constraints":   r"##\s+Constraints",
    "risk":          r"##\s+Risk assessment",
    "references":    r"##\s+References",
    "testing":       r"##\s+Testing notes",
}


def write_template(filepath: str = DEFAULT_CONTEXT_FILE):
    """Write fresh .ghost-context template."""
    content = TEMPLATE.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    Path(filepath).write_text(content, encoding="utf-8")


def _extract_section(content: str, section_key: str) -> str:
    """Extract text content of a named section."""
    patterns = list(SECTION_PATTERNS.values())
    keys = list(SECTION_PATTERNS.keys())

    try:
        idx = keys.index(section_key)
    except ValueError:
        return ""

    # Find this section's start
    section_pattern = SECTION_PATTERNS[section_key]
    match = re.search(section_pattern, content, re.IGNORECASE)
    if not match:
        return ""

    start = match.end()

    # Find next section's start (or end of file)
    next_start = len(content)
    for other_pattern in patterns:
        if other_pattern == section_pattern:
            continue
        other_match = re.search(other_pattern, content[start:], re.IGNORECASE)
        if other_match:
            candidate = start + other_match.start()
            if candidate < next_start:
                next_start = candidate

    # Extract and clean the section content
    raw = content[start:next_start]

    # Remove HTML comments
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)

    # Remove template placeholder lines
    raw = re.sub(r"^#.*$", "", raw, flags=re.MULTILINE)

    # Strip and clean
    lines = [line for line in raw.split("\n") if line.strip()]
    return "\n".join(lines).strip()


def assess_quality(parsed: dict) -> str:
    """Assess context quality based on populated sections."""
    populated = sum(1 for v in parsed.values() if v and isinstance(v, str) and len(v) > 10)
    total = len([k for k in parsed if k not in ("quality", "raw")])
    if populated >= 4:
        return "HIGH"
    elif populated >= 2:
        return "MEDIUM"
    else:
        return "LOW"


def read_context(filepath: str = DEFAULT_CONTEXT_FILE) -> dict:
    """
    Read and parse .ghost-context.
    Returns dict with all sections and quality assessment.
    """
    path = Path(filepath)

    if not path.exists():
        return {
            "quality": "LOW",
            "why": "",
            "tried": "",
            "constraints": "",
            "risk": "",
            "references": "",
            "testing": "",
            "summary": "",
            "breaking_description": "",
            "implications": "",
            "decision": "",
            "security": "",
            "raw": "",
        }

    content = path.read_text(encoding="utf-8", errors="ignore")

    # Check if it's just the blank template (no real content)
    meaningful_lines = [
        line for line in content.split("\n")
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith("<!--")
        and len(line.strip()) > 3
    ]

    if not meaningful_lines:
        return {
            "quality": "LOW",
            "why": "",
            "tried": "",
            "constraints": "",
            "risk": "",
            "references": "",
            "testing": "",
            "summary": "",
            "breaking_description": "",
            "implications": "",
            "decision": "",
            "security": "",
            "raw": "",
        }

    parsed = {}
    for key in SECTION_PATTERNS:
        parsed[key] = _extract_section(content, key)

    # Generate a summary (first meaningful sentence of "why")
    why = parsed.get("why", "")
    summary = ""
    if why:
        sentences = re.split(r"[.!?]\s+", why)
        if sentences:
            summary = sentences[0].strip()
            if len(summary) > 72:
                summary = summary[:69] + "..."

    parsed["summary"] = summary
    parsed["quality"] = assess_quality(parsed)
    parsed["raw"] = content

    # Additional fields for template usage
    parsed.setdefault("breaking_description", "")
    parsed.setdefault("implications", "")
    parsed.setdefault("decision", "")
    parsed.setdefault("security", "")

    return parsed


def clear_context(filepath: str = DEFAULT_CONTEXT_FILE):
    """Clear content and restore template."""
    write_template(filepath)


def format_quality_report(parsed: dict) -> str:
    """Format a human-readable quality report."""
    quality = parsed.get("quality", "LOW")
    colors = {"HIGH": "\033[32m", "MEDIUM": "\033[33m", "LOW": "\033[31m"}
    reset = "\033[0m"
    color = colors.get(quality, "")

    lines = [f"Context Quality: {color}{quality}{reset}\n"]

    sections = {
        "why":         "Why / motivation",
        "tried":       "What was tried first",
        "constraints": "Constraints",
        "references":  "References",
        "testing":     "Testing notes",
    }

    for key, label in sections.items():
        val = parsed.get(key, "")
        icon = "✓" if val and len(val) > 10 else "○"
        preview = val[:60].replace("\n", " ") + ("..." if len(val) > 60 else "") if val else "(empty)"
        lines.append(f"  {icon} {label}: {preview}")

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=".ghost-context scratchpad reader.")
    parser.add_argument("--read", action="store_true", help="Read and parse .ghost-context")
    parser.add_argument("--write-template", action="store_true", help="Write fresh template")
    parser.add_argument("--clear", action="store_true", help="Clear and restore template")
    parser.add_argument("--status", action="store_true", help="Show quality assessment")
    parser.add_argument("--file", default=DEFAULT_CONTEXT_FILE, help="Path to .ghost-context file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    args = parser.parse_args()

    if args.write_template:
        write_template(args.file)
        print(f"Template written to {args.file}")

    elif args.clear:
        clear_context(args.file)
        print(f"Cleared {args.file} and restored template")

    elif args.status:
        parsed = read_context(args.file)
        print(format_quality_report(parsed))

    elif args.read or True:  # default action
        parsed = read_context(args.file)
        # Remove raw content from JSON output (too verbose)
        output = {k: v for k, v in parsed.items() if k != "raw"}
        if args.json or args.pretty:
            indent = 2 if args.pretty else None
            print(json.dumps(output, indent=indent))
        else:
            print(format_quality_report(parsed))
            if parsed.get("summary"):
                print(f"\nSummary: {parsed['summary']}")


if __name__ == "__main__":
    main()
