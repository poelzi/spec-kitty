---
description: Create an isolated workspace (worktree) for implementing a specific work package.
---

## ⚠️ CRITICAL: Working Directory Requirement

**After running `spec-kitty implement WP##`, you MUST:**

1. **Run the cd command shown in the output** - e.g., `cd .worktrees/###-feature-WP##/`
2. **ALL file operations happen in this directory** - Read, Write, Edit tools must target files in the workspace
3. **NEVER write deliverable files to the main repository** - This is a critical workflow error

**Why this matters:**
- Each WP has an isolated worktree with its own branch
- Changes in main repository will NOT be seen by reviewers looking at the WP worktree
- Writing to main instead of the workspace causes review failures and merge conflicts

---

**IMPORTANT**: After running the command below, you'll see a LONG work package prompt (~1000+ lines).

**You MUST scroll to the BOTTOM** to see the completion command!

Run this command to get the work package prompt and implementation instructions:

```bash
spec-kitty agent workflow implement $ARGUMENTS --agent __AGENT__
```

<details><summary>PowerShell equivalent</summary>

```powershell
spec-kitty agent workflow implement $ARGUMENTS --agent __AGENT__
```

</details>

**CRITICAL**: Use the prefilled `--agent __AGENT__` value to track who is implementing!

**CRITICAL**: Pass `--feature <feature-slug>` when multiple features are in progress to avoid cross-feature status updates. Prefer the full slug; unique numeric shorthand like `--feature 018` also works.

If no WP ID is provided, it will automatically find the first work package with `lane: "planned"` and move it to "doing" for you.

**Note**: `kitty-specs/` is a git worktree on an orphan branch. Commits to spec files will NOT appear in `git log` on main. Use `git -C kitty-specs log` to see spec history. Do NOT manually `git commit` inside `kitty-specs/` — the spec-kitty CLI handles this. See AGENTS.md section 5a for details.

---

## Lane Contract (Implementers)

**Implementation is complete when the WP is moved to `for_review`, not `done`.**

- Implementer flow: `planned -> doing -> for_review`
- Reviewer flow: `for_review -> done` (or back to `planned` with feedback)
- Do **not** move a WP to `done` from `/spec-kitty.implement`

If you accidentally moved to `done`, immediately fix it:

```bash
spec-kitty agent tasks move-task WP## --to for_review --note "Accidental done transition corrected; pending review"
```

<details><summary>PowerShell equivalent</summary>

```powershell
spec-kitty agent tasks move-task WP## --to for_review --note "Accidental done transition corrected; pending review"
```

</details>

---

## Commit Workflow

**BEFORE moving to for_review**, you MUST commit your implementation:

```bash
cd .worktrees/###-feature-WP##/
# Stage only expected deliverables for this WP (never use `git add -A`)
git add <deliverable-path-1> <deliverable-path-2> ...
git commit -m "feat(WP##): <describe your implementation>"
```

<details><summary>PowerShell equivalent</summary>

```powershell
Set-Location .worktrees\###-feature-WP##\
# Stage only expected deliverables for this WP (never use `git add -A`)
git add <deliverable-path-1> <deliverable-path-2> ...
git commit -m "feat(WP##): <describe your implementation>"
```

</details>

**Then move to review:**
```bash
spec-kitty agent tasks move-task WP## --to for_review --note "Ready for review: <summary>"
```

**Do not run:**

```bash
spec-kitty agent tasks move-task WP## --to done
```

<details><summary>PowerShell equivalent</summary>

```powershell
spec-kitty agent tasks move-task WP## --to done
```

</details>

**Why this matters:**
- `move-task` validates that your worktree has commits beyond main
- Uncommitted changes will block the move to for_review
- This prevents lost work and ensures reviewers see complete implementations

---

**The Python script handles all file updates automatically - no manual editing required!**

**NOTE**: If `/spec-kitty.status` shows your WP in "doing" after you moved it to "for_review", don't panic - a reviewer may have moved it back (changes requested), or there's a sync delay. Focus on your WP.
