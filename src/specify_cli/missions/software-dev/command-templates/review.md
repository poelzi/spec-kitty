---
description: Perform structured code review and kanban transitions for completed task prompt files
---

**IMPORTANT**: After running the command below, you'll see a LONG work package prompt (~1000+ lines).

**You MUST scroll to the BOTTOM** to see the completion commands!

Run this command to get the work package prompt and review instructions:

```bash
spec-kitty agent workflow review $ARGUMENTS --agent __AGENT__
```

Optional: if you explicitly want to merge approved WP branches into upstream instead of the feature landing branch, add:

```bash
--merge-target upstream
```

Default merge target is the feature's local landing branch (`--merge-target landing`).

**CRITICAL**: Use the prefilled `--agent __AGENT__` value to track who is reviewing!

If no WP ID is provided, it will automatically find the first work package with `lane: "for_review"` and move it to "doing" for you.

## Technical Compliance (MANDATORY -- CHECK FIRST)

Before approving, you MUST verify all items in the **TECHNICAL COMPLIANCE CHECKLIST** section injected into the review prompt by the workflow command. These are mandatory decisions from the plan's `tech-decisions.md` that the implementor was required to follow.

**Automatic rejection triggers**:
- A required library is listed as a dependency but NOT meaningfully used in the implementation code (just adding it to `requirements.txt`/`Cargo.toml`/`package.json` is NOT compliance)
- A required architecture pattern is not followed (e.g., plan says "use Singleton pattern" but implementation creates multiple instances)
- A forbidden approach was used (e.g., plan says "use LangGraph" but implementation reimplements graph execution by hand)
- A required constraint is violated without documented justification

**How to verify**: For each Required Library entry in the checklist, grep the implementation diff for actual usage patterns (function calls, class instantiation, method invocations) -- not just import statements or dependency declarations.

If no TECHNICAL COMPLIANCE CHECKLIST appears in the prompt (tech-decisions.md may not exist for older features), read `kitty-specs/<feature>/tech-decisions.md` or `plan.md` Technical Context section directly and verify the same way.

---

## Dependency checks (required)

- dependency_check: If the WP frontmatter lists `dependencies`, confirm each dependency WP is merged to the landing branch before you review this WP.
- dependent_check: Identify any WPs that list this WP as a dependency and note their current lanes.
- rebase_warning: If you request changes AND any dependents exist, warn those agents to rebase and provide a concrete command (example: `cd .worktrees/FEATURE-WP02 && git rebase FEATURE-WP01`).
- verify_instruction: Confirm dependency declarations match actual code coupling (imports, shared modules, API contracts).

**After reviewing, scroll to the bottom and run ONE of these outcomes**:
- ✅ Approve:
  1. Rebase WP branch onto the selected merge target if `git merge --ff-only` fails (command shown in prompt). If the rebase is clean or conflicts are trivial, resolve them and continue. If conflicts are complex/non-trivial, reject instead.
  2. Merge approved WP branch into the selected merge target branch using the command shown in the prompt (defaults to landing branch unless `--merge-target upstream` is set).
  3. Then mark done: `spec-kitty agent tasks move-task WP## --to done --note "Review passed: <summary>"`
- ❌ Reject: Write feedback to the temp file path shown in the prompt, then run `spec-kitty agent tasks move-task WP## --to planned --review-feedback-file <temp-file-path>`

**A missing rebase alone is NOT grounds for rejection** - if the implementation passes review, perform the rebase yourself before merging.

**The prompt will provide a unique temp file path for feedback - use that exact path to avoid conflicts with other agents!**

**The Python script handles all file updates automatically - no manual editing required!**

**If the WP got approved, merging to the selected merge target is required before moving to `done`, then ensure dependent WPs are rebased as needed.**

**Note**: `kitty-specs/` is a git worktree on an orphan branch. Commits to spec files will NOT appear in `git log` on main. Use `git -C kitty-specs log` to see spec history. Do NOT manually `git commit` inside `kitty-specs/` — the spec-kitty CLI handles this. See AGENTS.md section 5a for details.
