---
description: Capture a mid-implementation change request and create dependency-safe work packages.
---

# /spec-kitty.change - Mid-Stream Change Command

Submit a change request to create branch-aware, dependency-safe work packages.

## Quick Start

```bash
# Direct request
spec-kitty change "use SQLAlchemy instead of raw SQL"

# Preview without creating WPs
spec-kitty change "refactor auth module" --preview
```

## Agent Workflow

For programmatic use:

```bash
# Step 1: Preview and classify
spec-kitty agent change preview "$ARGUMENTS" --json

# Step 2: Apply validated request
spec-kitty agent change apply <request-id> --json

# Get next doable WP (change-stack priority)
spec-kitty agent change next --json

# Reconcile links and merge jobs
spec-kitty agent change reconcile --json
```

## Key Rules

- **Fail-fast**: Ambiguous requests are rejected before file writes
- **Append-only**: Never rewrites existing WP content
- **Stack-first**: Change WPs execute before normal backlog
- **Testing closure**: Every change WP includes a final test task
- **Link-only**: Closed WPs are referenced, never reopened

## User Input

```text
$ARGUMENTS
```
