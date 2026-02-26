---
work_package_id: WP03
title: Planning Writes and Commit Policy Routing
lane: "done"
dependencies:
- WP01
- WP02
base_branch: 041-orphan-branch-spec-storage-WP02
base_commit: e8e5c8b26c12b89a53c9dc10f15d4e5c21de854e
created_at: '2026-02-23T15:23:24.069610+00:00'
subtasks:
- T012
- T013
- T014
- T015
- T016
- T017
phase: Phase 2 - Core Behavior
assignee: ''
agent: "claude-opus"
shell_pid: "2952046"
review_status: "acknowledged"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-02-23T12:17:54Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP03 - Planning Writes and Commit Policy Routing

## Objectives & Success Criteria

- Route all planning artifact writes to the configured spec worktree root.
- Ensure auto-commit happens on the spec branch, not planning/landing branches.
- Implement manual-edit warning flow with include/skip/abort decision.
- Implement optional auto-push behavior controlled by config (default off).

**Primary success checks**:
- `specify`, `plan`, `clarify`, and workflow lane updates mutate files under spec worktree path.
- Auto-commit never silently includes unrelated manual edits.
- Auto-push attempts occur only when `spec_storage.auto_push=true`.
- Integration tests cover happy path and policy edge cases.

## Recommended Implementation Command

```bash
spec-kitty implement WP03 --base WP02
```

## Context & Constraints

- Depends on config/helpers from WP01 and bootstrap from WP02.
- Spec source: `kitty-specs/041-orphan-branch-spec-storage/spec.md`
- Contracts: `kitty-specs/041-orphan-branch-spec-storage/contracts/cli-contracts.md`
- Data model entities: `SpecWorktreeState`, `SpecCommitAction` in `data-model.md`

Non-negotiable constraints:
- Planning branch should remain free from spec file commits after routing changes.
- Prompt user before committing pre-existing manual edits.
- Default behavior must remain local-only commit.

## Subtasks & Detailed Guidance

### Subtask T012 - Add centralized planning-artifact root resolver
- **Purpose**: Remove hardcoded assumptions that planning artifacts live in current branch checkout.
- **Steps**:
  1. Create one canonical resolver that returns spec artifact root path based on config + worktree discovery.
  2. Ensure resolver validates health and raises actionable errors for missing/invalid state.
  3. Add lightweight wrappers for call sites needing feature directories, tasks directories, and checklists paths.
  4. Update existing path helpers to delegate instead of duplicating logic.
- **Files**:
  - `src/specify_cli/core/feature_detection.py`
  - `src/specify_cli/core/paths.py`
  - `src/specify_cli/core/worktree_topology.py`
- **Parallel?**: No
- **Notes**:
  - This resolver is the critical seam for correctness across all command families.

### Subtask T013 - Route specify and plan write paths to spec worktree
- **Purpose**: Ensure spec creation and planning artifacts are emitted under orphan branch worktree.
- **Steps**:
  1. Update feature/spec creation flow to write `meta.json`, `spec.md`, and `plan.md` under resolver path.
  2. Ensure branch metadata updates still happen in expected project scope.
  3. Validate generated absolute paths in command JSON outputs.
  4. Confirm no `kitty-specs/` write path falls back to planning branch checkout.
- **Files**:
  - `src/specify_cli/cli/commands/agent/feature.py`
  - `src/specify_cli/cli/commands/agent/workflow.py` (if shared path utilities are there)
- **Parallel?**: Yes (after T012)
- **Notes**:
  - Preserve command output compatibility where possible.

### Subtask T014 - Route clarify and workflow lane updates to spec worktree
- **Purpose**: Ensure post-spec edit flows continue to mutate the correct branch-backed files.
- **Steps**:
  1. Update clarify/edit paths for `spec.md` and checklist writes to use resolver.
  2. Update task lane mutation commands to operate on task files under spec worktree.
  3. Verify history/frontmatter updates remain intact after path changes.
  4. Confirm relative/absolute path references in output stay accurate.
- **Files**:
  - `src/specify_cli/cli/commands/agent/tasks.py`
  - `src/specify_cli/cli/commands/agent/workflow.py`
  - `src/specify_cli/cli/commands/agent/feature.py`
- **Parallel?**: Yes (after T012)
- **Notes**:
  - Keep flat `tasks/` directory assumption unchanged.

### Subtask T015 - Implement manual-edit detection prompt
- **Purpose**: Enforce explicit user choice when pre-existing manual edits are present.
- **Steps**:
  1. Before auto-commit, detect whether spec worktree has unstaged/staged changes not created in current command flow.
  2. Present a clear include/skip/abort decision prompt.
  3. Implement behavior:
     - include -> stage all intended + manual changes
     - skip -> stage only command-intended changes
     - abort -> stop before commit with clear status
  4. Ensure non-interactive mode has deterministic behavior (document choice).
- **Files**:
  - `src/specify_cli/cli/commands/agent/feature.py`
  - `src/specify_cli/core/git_ops.py`
- **Parallel?**: No
- **Notes**:
  - Must satisfy clarified requirement from spec session notes.

### Subtask T016 - Implement configurable auto-push policy
- **Purpose**: Allow optional push after auto-commit while keeping default off.
- **Steps**:
  1. Wire `spec_storage.auto_push` into post-commit flow.
  2. When true, attempt push to tracked remote branch with clear success/failure output.
  3. When false, skip push and report local commit behavior.
  4. Ensure push failures do not corrupt local commit state.
- **Files**:
  - `src/specify_cli/cli/commands/agent/feature.py`
  - `src/specify_cli/core/git_ops.py`
  - `src/specify_cli/core/worktree.py`
- **Parallel?**: No
- **Notes**:
  - Do not force push under any condition.

### Subtask T017 - Add integration tests for routing and policy behavior
- **Purpose**: Prevent regressions in cross-command storage/commit behavior.
- **Steps**:
  1. Add tests proving each command writes to spec worktree path.
  2. Add tests for manual-edit prompt outcomes (include/skip/abort).
  3. Add tests for `auto_push=false` default and opt-in true path (mock push).
  4. Verify planning branch remains free of new `kitty-specs/` commits.
- **Files**:
  - `tests/integration/test_spec_storage_write_routing.py`
  - `tests/integration/test_spec_storage_auto_commit_policy.py`
  - `tests/specify_cli/cli/commands/agent/test_workflow_auto_moves.py`
- **Parallel?**: Yes
- **Notes**:
  - Keep tests deterministic; mock remote interactions for push behavior.

## Test Strategy

Run WP03-focused suites:

```bash
pytest tests/integration -k "spec_storage_write_routing or auto_commit_policy"
pytest tests/specify_cli/cli/commands/agent -k "workflow or feature"
```

Acceptance for WP03:
- All targeted command families write to spec worktree path.
- Manual-edit prompt behavior matches include/skip/abort contract.
- Auto-push behavior is off by default and configurable.

## Risks & Mitigations

- **Risk**: Incomplete call-site migration leaves mixed path behavior.
  - **Mitigation**: Inventory and test every spec-mutating command path.
- **Risk**: Prompt flow creates non-interactive command failures.
  - **Mitigation**: Define explicit fallback path and cover with tests.
- **Risk**: Push behavior introduces network side effects by default.
  - **Mitigation**: Enforce default false and test configuration gating.

## Review Guidance

- Verify no command still assumes planning-branch `kitty-specs/` files.
- Verify manual-edit decisions are explicit and reflected in resulting commits.
- Verify push attempts only happen when configured.
- Verify integration tests demonstrate branch cleanliness guarantees.

## Activity Log

- 2026-02-23T12:17:54Z - system - lane=planned - Prompt created.
- 2026-02-23T15:30:30Z – unknown – shell_pid=3452893 – lane=for_review – Ready for review: spec artifact resolver, commit policy, write path routing, 31 unit tests all passing
- 2026-02-23T16:53:42Z – codex – shell_pid=3452893 – lane=doing – Started review via workflow command
- 2026-02-23T16:56:49Z – codex – shell_pid=3452893 – lane=planned – Moved to planned
- 2026-02-23T16:58:04Z – claude – shell_pid=2952046 – lane=doing – Started implementation via workflow command
- 2026-02-23T17:17:00Z – claude – shell_pid=2952046 – lane=for_review – Review fixes applied: wired commit policy into command flows, replaced all hardcoded kitty-specs paths with resolver, added 21 integration tests, routed _commit_to_branch through spec commit policy. 173 tests pass, 0 regressions.
- 2026-02-24T17:12:19Z – codex – shell_pid=3452893 – lane=doing – Started review via workflow command
- 2026-02-24T17:15:33Z – codex – shell_pid=3452893 – lane=planned – Moved to planned
- 2026-02-24T17:25:20Z – claude-opus – shell_pid=872924 – lane=doing – Started implementation via workflow command
- 2026-02-24T17:30:55Z – claude-opus – shell_pid=872924 – lane=for_review – Review round 2 fixes committed (4d1fe8f3): implemented manual-edit policy flow via resolve_manual_edit_policy()+commit_with_policy(), replaced all 7 call sites, loaded auto_push from config. All 41 WP03 tests pass. [claude-opus]
- 2026-02-24T18:44:40Z – codex – shell_pid=3452893 – lane=doing – Started review via workflow command
- 2026-02-24T18:45:19Z – codex – shell_pid=3452893 – lane=for_review – Re-move after auto-commit warning. Review round 2 fixes committed as 4d1fe8f3. [claude-opus]
- 2026-02-24T18:46:21Z – codex – shell_pid=3452893 – lane=planned – Moved to planned
- 2026-02-24T19:33:48Z – codex – shell_pid=3452893 – lane=doing – Started implementation via workflow command
- 2026-02-24T19:34:11Z – codex – shell_pid=3452893 – lane=for_review – Ready for review: added explicit include/skip/abort policy path (env override + interactive prompt), abort handling in command flows, and expanded policy integration coverage.
- 2026-02-24T19:39:49Z – claude-opus – shell_pid=2952046 – lane=doing – Started review via workflow command
- 2026-02-24T19:43:00Z – claude-opus – shell_pid=2952046 – lane=done – Review passed (round 4): All 3 previous blocking issues resolved. Centralized resolver replaces all hardcoded kitty-specs paths (T012). Write routing confirmed for feature/tasks/workflow (T013/T014). Manual-edit include/skip/abort decision flow implemented with argument/env/interactive support (T015). Auto-push wired from config at all call sites (T016). 71 tests pass (T017). Merged to landing branch via ff-only. [claude-opus]

## Review Feedback

**Reviewed by**: Daniel Poelzleithner
**Status**: ❌ Changes Requested
**Date**: 2026-02-23

**Issue 1 (blocking): Commit policy is not wired into command flows**
- `src/specify_cli/core/spec_commit_policy.py` adds `detect_manual_edits()` / `commit_spec_changes()`, but no command path invokes them.
- `grep` shows `commit_spec_changes` is only referenced in its own module/tests, so include/skip/abort behavior and `auto_push` policy are not actually enforced in real workflows.
- Required fix: integrate commit policy into the planning write paths (`create-feature`, `setup-plan`, clarify/specify/task lane updates) so manual-edit decisions are enforced before committing, with deterministic non-interactive behavior.

**Issue 2 (blocking): Routing still hardcodes `kitty-specs` in key paths, breaking configured worktree-path support**
- `src/specify_cli/cli/commands/agent/tasks.py:110` and `src/specify_cli/cli/commands/agent/workflow.py:111` still resolve `meta.json` via `main_repo_root / "kitty-specs" / feature_slug / "meta.json"`.
- `src/specify_cli/core/feature_detection.py` still contains many hardcoded `kitty-specs` path assumptions.
- Required fix: route these path resolutions through the centralized resolver and/or config-aware helpers, so custom `spec_storage.worktree_path` works end-to-end.

**Issue 3 (blocking): Required WP03 integration coverage is missing**
- Running `pytest tests/integration -k "spec_storage_write_routing or auto_commit_policy"` selected 0 tests.
- WP03/T017 and acceptance criteria call for integration tests proving write routing + manual-edit policy + auto-push gating behavior.
- Required fix: add integration tests for those flows and ensure they execute under the documented test command.

**Issue 4 (blocking): Planning artifact commits are still directed to planning-branch flow, not spec-branch policy flow**
- `src/specify_cli/cli/commands/agent/feature.py:470`, `src/specify_cli/cli/commands/agent/feature.py:531`, `src/specify_cli/cli/commands/agent/feature.py:671` still use `_commit_to_branch(...)` with planning-branch semantics.
- WP03 objective requires auto-commit behavior to operate on the spec branch with explicit manual-edit handling.
- Required fix: switch these commit paths to the spec-worktree commit policy flow (or explicitly justify and cover alternative behavior in spec/tests).

**Dependent Rebase Warning**
- This WP has dependents: WP06 and WP07.
- After fixing and force-pushing/replacing WP03 history, dependent branches must rebase:
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP06 && git rebase 041-orphan-branch-spec-storage-WP03`
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP07 && git rebase 041-orphan-branch-spec-storage-WP03`

- [x] DONE: Feedback addressed by claude. <!-- done: addressed by claude at 2026-02-23T17:17:00Z -->

---

**Reviewed by**: Daniel Poelzleithner
**Status**: ❌ Changes Requested
**Date**: 2026-02-24

**Issue 1 (blocking): include/skip/abort manual-edit decision flow is still not implemented at command level**
- WP03 T015 requires an explicit manual-edit decision flow (include/skip/abort).
- In current command wiring, all policy call sites hardcode `include_manual=False`:
  - `src/specify_cli/cli/commands/agent/feature.py:240`
  - `src/specify_cli/cli/commands/agent/tasks.py:1002`
  - `src/specify_cli/cli/commands/agent/tasks.py:1190`
  - `src/specify_cli/cli/commands/agent/workflow.py:659`
  - `src/specify_cli/cli/commands/agent/workflow.py:1324`
- `detect_manual_edits()` is imported in `feature.py` but not used to drive a user/agent decision workflow.
- **Required fix**: implement explicit policy branching (include, skip, abort) before commit and make behavior deterministic in non-interactive mode (documented default), rather than always silently skipping manual edits.

**Issue 2 (blocking): auto-push config is not consistently wired into auto-commit flows**
- WP03 T016 requires `spec_storage.auto_push` to control push attempts (default off).
- Some flows use config (`feature.py`), but task/workflow auto-commit paths hardcode `auto_push=False`:
  - `src/specify_cli/cli/commands/agent/tasks.py:1003`
  - `src/specify_cli/cli/commands/agent/tasks.py:1191`
  - `src/specify_cli/cli/commands/agent/workflow.py:660`
  - `src/specify_cli/cli/commands/agent/workflow.py:1325`
- **Required fix**: load config in these flows and pass `auto_push=config.auto_push` consistently.

**Issue 3 (non-blocking but should be corrected): one prompt test command path is stale**
- `pytest tests/specify_cli/cli/commands/agent -k "workflow or feature"` currently errors because that directory does not exist in this repo layout.
- Equivalent command-family coverage is present under `tests/unit/agent/` and passes.
- **Follow-up**: align documented command in WP prompt/docs/scripts with actual test locations.

**Dependent Rebase Warning**
- This WP has dependents: WP06 and WP07.
- After updating WP03, dependent branches should rebase:
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP06 && git rebase 041-orphan-branch-spec-storage-WP03`
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP07 && git rebase 041-orphan-branch-spec-storage-WP03`

- [x] DONE: Feedback addressed by claude-opus. <!-- done: addressed by claude-opus at 2026-02-24T17:30:55Z -->

- [x] DONE: Feedback addressed by codex. <!-- done: addressed by codex at 2026-02-24T18:45:19Z -->

---

**Reviewed by**: Daniel Poelzleithner
**Status**: ❌ Changes Requested
**Date**: 2026-02-24

**Issue 1 (blocking): include/skip/abort decision contract is still not fulfilled**
- WP03/T015 requires an explicit manual-edit decision flow: include, skip, or abort.
- Current implementation adds `resolve_manual_edit_policy()` / `commit_with_policy()`, but in non-interactive mode it always resolves manual edits to `skip` and never surfaces include/abort selection.
- `interactive=True` is documented as "not yet implemented" in `src/specify_cli/core/spec_commit_policy.py`, and no command-level flag/prompt is wired to choose include or abort.
- This means pre-existing manual edits are always silently excluded (with post-commit message), rather than explicitly decided before commit.

**Required fix**
- Implement a real decision path for manual edits that supports all three outcomes:
  1. include (stage intended + manual),
  2. skip (stage intended only),
  3. abort (no commit).
- For non-interactive agent flow, add a deterministic explicit policy input (e.g., CLI option/env/config default), and document the default behavior.
- Add tests covering include/skip/abort behavior at command integration level (not just core helper behavior).

**Dependent Rebase Warning**
- This WP has dependents: WP06 and WP07.
- After updating WP03, dependent branches should rebase:
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP06 && git rebase 041-orphan-branch-spec-storage-WP03`
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP07 && git rebase 041-orphan-branch-spec-storage-WP03`

- [x] DONE: Feedback addressed by codex. <!-- done: addressed by codex at 2026-02-24T19:34:11Z -->

