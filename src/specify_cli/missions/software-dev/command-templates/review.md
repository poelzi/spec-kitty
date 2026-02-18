---
description: Perform structured code review and kanban transitions for completed task prompt files
---

**IMPORTANT**: After running the command below, you'll see a LONG work package prompt (~1000+ lines).

**You MUST scroll to the BOTTOM** to see the completion commands!

Run this command to get the work package prompt and review instructions:

```bash
spec-kitty agent workflow review $ARGUMENTS --agent <your-name>
```

**CRITICAL**: You MUST provide `--agent <your-name>` to track who is reviewing!

If no WP ID is provided, it will automatically find the first work package with `lane: "for_review"` and move it to "doing" for you.

## Dependency checks (required)

- dependency_check: If the WP frontmatter lists `dependencies`, confirm each dependency WP is merged to main before you review this WP.
- dependent_check: Identify any WPs that list this WP as a dependency and note their current lanes.
- rebase_warning: If you request changes AND any dependents exist, warn those agents to rebase and provide a concrete command (example: `cd .worktrees/FEATURE-WP02 && git rebase FEATURE-WP01`).
- verify_instruction: Confirm dependency declarations match actual code coupling (imports, shared modules, API contracts).

**After reviewing, scroll to the bottom and run ONE of these outcomes**:
- ✅ Approve:
  1. Rebase WP branch onto base if `git merge --ff-only` fails (command shown in prompt). If the rebase is clean or conflicts are trivial, resolve them and continue. If conflicts are complex/non-trivial, reject instead.
  2. Merge approved WP branch to `master` using the command shown in the prompt (uses `git merge --ff-only`).
  3. Then mark done: `spec-kitty agent tasks move-task WP## --to done --note "Review passed: <summary>"`
- ❌ Reject: Write feedback to the temp file path shown in the prompt, then run `spec-kitty agent tasks move-task WP## --to planned --review-feedback-file <temp-file-path>`

**A missing rebase alone is NOT grounds for rejection** - if the implementation passes review, perform the rebase yourself before merging.

**The prompt will provide a unique temp file path for feedback - use that exact path to avoid conflicts with other agents!**

**The Python script handles all file updates automatically - no manual editing required!**

**If the WP got approved, merging to `master` is required before moving to `done`, then ensure dependent WPs are rebased as needed.**
