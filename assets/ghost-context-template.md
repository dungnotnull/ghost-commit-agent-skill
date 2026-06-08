# ghost-context — Developer Intent Scratchpad
# Fill in as much or as little as you know. Everything here is optional.
# This file is gitignored. Your raw thoughts stay local.
# ghost-commit reads this before every commit to generate your decision log.
# Clear sections you don't need — ghost-commit handles the rest from the diff.

## Why I'm making this change
<!-- What problem, bug, or requirement prompted this change?
     Be as specific as you want — this is the most important section.
     Example: "Fixing the session timeout bug reported in #847. Root cause was
     that Redis TTL was set in seconds but the client was reading milliseconds." -->


## What I tried first
<!-- What other approaches did you try or consider before this one?
     Why did you reject them? This context vanishes after you commit.
     Example: "Tried patching the client side but it's also used by the webhook
     service we don't control. Tried increasing the TTL value but that would
     affect all sessions, not just the broken ones." -->


## Constraints
<!-- What technical, business, or external factors shaped your approach?
     Deadlines, existing APIs, backward compatibility, team decisions, etc.
     Example: "Can't change the Redis key format without a migration script.
     Doing that in a separate PR (#851) to keep this change minimal." -->


## Risk assessment
<!-- Any concerns about this change? Areas that might be affected?
     Things reviewers should pay special attention to?
     Example: "Low risk — only affects new sessions. Existing sessions
     use cached values and will naturally expire on their old schedule." -->


## References
<!-- Issue numbers, PR links, Slack threads, docs, ADRs, tickets.
     Format: #123, JIRA-456, https://...
     Example: Closes #847, Refs #851, Slack: #backend-2026-06-07 -->


## Testing notes
<!-- What did you test? What should reviewers verify?
     Any edge cases you're worried about?
     Example: "Tested with 30-second sessions — confirmed still active at 29s.
     Did not test concurrent session creation — should be fine but worth verifying." -->
