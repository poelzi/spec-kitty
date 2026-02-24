---
description: Implement all remaining planned work packages in dependency order, using parallel subagents where possible.
---

## Overview

Orchestrate **all planned WPs** to `for_review` by launching subagents that each run
`/spec-kitty.implement`. Work packages execute in dependency-respecting waves --
independent WPs run in parallel, dependent WPs wait for their prerequisites.

Each subagent gets the **literal slash command** `/spec-kitty.implement WP##`, ensuring
it reads the implement command template, creates a worktree, and follows the full
isolation protocol. You (the orchestrating agent) never write implementation code
directly -- you only schedule, launch, verify, and report.

---

## Step 1: Get the Execution Schedule

Run the schedule command to compute waves:

```bash
spec-kitty agent workflow schedule --json
```

This returns a JSON object with the structure:

```json
{
  "feature": "<feature-slug>",
  "waves": [
    {
      "wave": 1,
      "work_packages": [
        {"id": "WP01", "base": null, "dependencies": []}
      ]
    },
    {
      "wave": 2,
      "work_packages": [
        {"id": "WP02", "base": "WP01", "dependencies": ["WP01"]},
        {"id": "WP03", "base": "WP01", "dependencies": ["WP01"]}
      ]
    }
  ],
  "total_planned": 5,
  "total_waves": 3
}
```

Parse and retain the full schedule. If `total_planned` is 0, report that all WPs
are already past the `planned` lane and stop.

---

## Step 2: Execute Each Wave

For each wave **in order** (wave 1 first, then wave 2, etc.):

### 2a. Launch Subagents in Parallel

For every WP in the wave, launch a **Task tool subagent** whose prompt is the
literal slash command. Construct the prompt as follows:

- If the WP's `base` field is **null** (no dependency or auto-merge):
  ```
  /spec-kitty.implement <WP_ID>
  ```

- If the WP's `base` field is a **WP ID** (single dependency):
  ```
  /spec-kitty.implement <WP_ID> --base <BASE_WP_ID>
  ```

**Launch ALL WPs in the same wave as parallel Task tool calls in a single message.**
This maximizes throughput for independent work packages.

Example: if wave 2 has WP03 (base: WP02) and WP04 (base: WP02), launch both
subagents simultaneously in one message with two Task tool calls.

### 2b. Wait and Verify

After all subagents in the wave return, run:

```bash
spec-kitty agent tasks status --json
```

Check that **every WP in the wave** has reached `for_review` (or `done`).

- If all succeeded: proceed to the next wave.
- If any WP is still in `doing` or `planned`: the subagent may have failed.
  Report which WPs failed and **ask the user** whether to:
  - Retry the failed WPs (re-launch subagents)
  - Skip them and continue with the next wave
  - Stop entirely

**Do NOT silently continue past failures.**

---

## Step 3: Final Report

After all waves complete (or if stopped early), run:

```bash
spec-kitty agent tasks status --json
```

Print a summary table:

| Wave | WP | Status | Notes |
|------|-----|--------|-------|
| 1    | WP01 | for_review | OK |
| 2    | WP02 | for_review | OK |
| ...  | ...  | ...    | ...   |

Report:
- Total WPs processed
- Total WPs successfully moved to `for_review`
- Any failures or skips
- Time taken (if available)

---

## Critical Rules

1. **Never implement code yourself.** Your role is orchestration only. Each subagent
   handles its own WP via the `/spec-kitty.implement` protocol.

2. **Always pass `/spec-kitty.implement WP##` as the subagent prompt.** This ensures
   the subagent reads the `implement.md` command template, runs the CLI to create a
   worktree, and follows the full isolation protocol. Never give subagents freeform
   coding instructions.

3. **Always pass `--base`** when the schedule specifies a non-null base. This ensures
   the worktree branches from the correct dependency branch.

4. **Verify between waves.** Never launch wave N+1 until wave N is confirmed complete.

5. **Report failures immediately.** If a subagent fails, the user needs to decide
   the next step -- don't guess.
