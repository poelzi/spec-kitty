---
description: Capture a mid-implementation change request and create dependency-safe work packages.
---

# /spec-kitty.change - Mid-Stream Change Command

**Version**: 0.14.0+
**Purpose**: Capture review feedback or implementation pivots as branch-aware, dependency-safe work packages.

## When to Use

Use `/spec-kitty.change` when you need to:
- Capture review feedback as actionable work packages during implementation
- Handle implementation pivots ("use this library instead")
- Add late-stage requirements without disrupting ongoing work
- Create small fixes on `main` with complexity guidance

## Command Surface

### Top-Level Command

```bash
# Direct request
spec-kitty change "use SQLAlchemy instead of raw SQL"

# Preview without creating WPs
spec-kitty change "refactor auth module" --preview

# JSON output for automation
spec-kitty change "add caching layer" --json output.json
```

### Agent Subcommands

For programmatic use by AI agents:

```bash
# Step 1: Preview - validate and classify before writing files
spec-kitty agent change preview "your change request" --json

# Step 2: Apply - create work packages from validated request
spec-kitty agent change apply <request-id> --json

# Stack-first selection - get next doable WP with change priority
spec-kitty agent change next --json

# Reconcile - recompute links and merge coordination jobs
spec-kitty agent change reconcile --json
```

## Workflow

1. **Preview**: Validates the request, routes to correct branch stash, assesses complexity
2. **Decide**: If complexity exceeds threshold, recommends `/spec-kitty.specify` with continue-or-stop choice
3. **Apply**: Creates change work packages with dependencies, documentation links, and testing tasks
4. **Implement**: Change-stack items take priority in `/spec-kitty.implement` selection

## Branch Stash Routing

- **Feature branch**: Routes to feature stash (`kitty-specs/<feature>/tasks/`)
- **Main branch**: Routes to main stash (`kitty-specs/change-stack/main/`)

## Complexity Assessment

Uses deterministic scoring across 5 dimensions:
- Scope breadth (0-3)
- Coupling impact (0-2)
- Dependency churn (0-2)
- Ambiguity (0-2)
- Integration risk (0-1)

Total >= threshold triggers `/spec-kitty.specify` recommendation.

## Key Behaviors

- **Fail-fast**: Ambiguous requests are rejected before any files are created
- **Append-only**: Never rewrites existing WP bodies
- **Link-only for closed WPs**: References closed WPs without reopening them
- **Stack-first ordering**: Ready change WPs execute before normal backlog
- **Testing closure**: Every generated change WP includes a final testing task

## User Input

```text
$ARGUMENTS
```

## Examples

**Simple change on feature branch:**
```bash
spec-kitty change "replace manual JSON parsing with pydantic models"
# Creates WP with dependency on current active WP
```

**Complex change with preview:**
```bash
spec-kitty change "restructure the entire auth flow" --preview
# Shows complexity warning, recommends /spec-kitty.specify
```

**Programmatic flow:**
```bash
# Preview first
spec-kitty agent change preview "add retry logic to API calls" --json > preview.json

# Review the preview, then apply
spec-kitty agent change apply "$(jq -r .requestId preview.json)" --json
```
