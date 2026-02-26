---
work_package_id: WP04
title: Explicit Legacy Migration Flow
lane: "done"
dependencies:
- WP01
- WP02
base_branch: 041-orphan-branch-spec-storage-WP01
base_commit: 39dbbbf5a59ae9fb1a181a12a5c1a43c87da04e2
created_at: '2026-02-23T15:30:52.927302+00:00'
subtasks:
- T018
- T019
- T020
- T021
- T022
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

# Work Package Prompt: WP04 - Explicit Legacy Migration Flow

## Objectives & Success Criteria

- Implement an explicit migration path for repositories that still track `kitty-specs/` on planning branch.
- Ensure migration creates/validates orphan branch and worktree, moves artifacts, and removes `kitty-specs/` from planning branch via normal commit.
- Ensure migration is idempotent and reports already-migrated state cleanly.
- Preserve git history (no rewrite, no force operations).

**Primary success checks**:
- Migration runs only when upgrade command is invoked.
- Successful migration leaves planning branch HEAD without `kitty-specs/` tracked files.
- Re-running migration yields no-op `already_migrated` result.
- Integration tests verify history preservation and safety behavior.

## Recommended Implementation Command

```bash
spec-kitty implement WP04 --base WP02
```

## Context & Constraints

- Spec references: `FR-006`, `FR-007`, `SC-003` in `spec.md`
- Plan references migration module path: `src/specify_cli/upgrade/migrations/m_0_16_0_spec_branch_worktree.py`
- Research decisions: explicit migration trigger and no history rewrite.

Critical constraints:
- Migration must not auto-trigger during normal command flows.
- Must avoid force pushes or history rewriting.
- Must handle mixed-state repositories gracefully.

## Subtasks & Detailed Guidance

### Subtask T018 - Add and register migration module
- **Purpose**: Introduce formal, versioned migration entrypoint.
- **Steps**:
  1. Create migration module: `src/specify_cli/upgrade/migrations/m_0_16_0_spec_branch_worktree.py`.
  2. Implement migration class/function structure matching existing migration conventions.
  3. Register migration in migration index/registry so upgrade command discovers it.
  4. Add metadata (version key, description, applicability checks).
- **Files**:
  - `src/specify_cli/upgrade/migrations/m_0_16_0_spec_branch_worktree.py`
  - `src/specify_cli/upgrade/migrations/__init__.py`
  - migration registry modules under `src/specify_cli/upgrade/`
- **Parallel?**: No
- **Notes**:
  - Follow naming and logging conventions used by neighboring migration files.

### Subtask T019 - Implement legacy detection and already-migrated no-op
- **Purpose**: Avoid repeated or unsafe migration attempts.
- **Steps**:
  1. Detect legacy layout: `kitty-specs/` tracked on planning branch with no configured spec branch/worktree.
  2. Detect already-migrated layout via config + orphan branch + worktree checks.
  3. Return explicit status (`success`, `already_migrated`, `failed`).
  4. Ensure no file/branch mutations happen in already-migrated path.
- **Files**:
  - `src/specify_cli/upgrade/migrations/m_0_16_0_spec_branch_worktree.py`
  - `src/specify_cli/core/feature_detection.py`
  - `src/specify_cli/core/worktree_topology.py`
- **Parallel?**: Yes
- **Notes**:
  - Detection should use git state and config, not path-only assumptions.

### Subtask T020 - Implement artifact transfer and planning-branch cleanup commit
- **Purpose**: Execute the core migration data movement safely.
- **Steps**:
  1. Create/validate orphan spec branch according to config.
  2. Copy/move legacy `kitty-specs/` content onto orphan branch worktree.
  3. Commit spec-branch artifacts in migrated layout.
  4. Remove `kitty-specs/` from planning branch via normal commit.
  5. Record migration result and updated config values.
- **Files**:
  - `src/specify_cli/upgrade/migrations/m_0_16_0_spec_branch_worktree.py`
  - `src/specify_cli/core/worktree.py`
  - `src/specify_cli/core/git_ops.py`
- **Parallel?**: No
- **Notes**:
  - Keep mutation sequence transactional as much as possible; fail with explicit recovery guidance.

### Subtask T021 - Enforce migration safety guardrails
- **Purpose**: Guarantee migration cannot silently perform irreversible operations.
- **Steps**:
  1. Assert no history-rewrite commands are used.
  2. Block migration when unsafe preconditions are detected (for example, path conflicts).
  3. Emit explicit remediation steps when blocking.
  4. Add safety checks for local dirty state where required.
- **Files**:
  - `src/specify_cli/upgrade/migrations/m_0_16_0_spec_branch_worktree.py`
  - `src/specify_cli/core/git_ops.py`
- **Parallel?**: Yes
- **Notes**:
  - This subtask is about guardrails and operator trust, not new feature behavior.

### Subtask T022 - Add integration tests for migration behavior
- **Purpose**: Verify migration works for real repository states and remains idempotent.
- **Steps**:
  1. Add test for successful migration from legacy layout.
  2. Add test for already-migrated rerun path.
  3. Add test ensuring planning branch history is preserved (normal cleanup commit only).
  4. Add test for blocked/failed states with actionable error output.
- **Files**:
  - `tests/integration/test_spec_storage_migration.py`
  - `tests/unit/test_migration_python_only.py` (if migration registry assertions belong there)
- **Parallel?**: No
- **Notes**:
  - Use disposable temp repositories to model legacy state.

## Test Strategy

Run migration-focused tests:

```bash
pytest tests/integration -k "spec_storage_migration"
pytest tests/unit -k "migration"
```

Acceptance for WP04:
- Explicit upgrade command performs safe migration.
- Rerun path is idempotent.
- No history rewriting is required or attempted.

## Risks & Mitigations

- **Risk**: Mixed legacy states produce partial migrations.
  - **Mitigation**: Add detailed preflight checks and clear fail-fast behavior.
- **Risk**: Migration attempts while repository is dirty can cause ambiguous output.
  - **Mitigation**: Require/advise clean state and emit deterministic diagnostics.
- **Risk**: Branch cleanup commit misses some files.
  - **Mitigation**: Validate planning branch tree does not contain `kitty-specs/` after migration.

## Review Guidance

- Confirm migration is explicit-only and not triggered during normal command runs.
- Confirm cleanup on planning branch uses normal commit semantics.
- Confirm rerun behavior produces no additional mutations.
- Confirm tests cover success, idempotence, and blocked/error conditions.

## Activity Log

- 2026-02-23T12:17:54Z - system - lane=planned - Prompt created.
- 2026-02-23T15:36:54Z – unknown – shell_pid=3452893 – lane=for_review – Ready for review: migration module + 32 integration tests, all passing. No regressions in core or upgrade test suites.
- 2026-02-23T16:57:43Z – codex – shell_pid=3452893 – lane=doing – Started review via workflow command
- 2026-02-23T17:02:45Z – codex – shell_pid=3452893 – lane=planned – Moved to planned
- 2026-02-24T17:12:25Z – claude-opus – shell_pid=2952046 – lane=doing – Started implementation via workflow command
- 2026-02-24T17:24:45Z – claude-opus – shell_pid=2952046 – lane=for_review – Review fixes applied: _classify() validates worktree health via discover_spec_worktree(), detect() returns True for already-migrated state enabling upgrade runner round-trip, 22 integration tests added at tests/integration/test_spec_storage_migration.py matching documented discovery pattern. 159 migration/upgrade tests pass, 0 regressions.
- 2026-02-24T19:43:29Z – codex – shell_pid=3452893 – lane=doing – Started review via workflow command
- 2026-02-24T19:46:26Z – codex – shell_pid=3452893 – lane=planned – Moved to planned
- 2026-02-24T19:47:17Z – codex – shell_pid=3452893 – lane=doing – Started implementation via workflow command
- 2026-02-24T19:49:17Z – codex – shell_pid=3452893 – lane=for_review – Ready for review: classify now verifies orphan topology before already_migrated, and migration integration tests cover config+healthy-worktree+non-orphan branch as NOT_APPLICABLE.
- 2026-02-24T19:49:42Z – claude-opus – shell_pid=2952046 – lane=doing – Started review via workflow command
- 2026-02-24T19:52:01Z – claude-opus – shell_pid=2952046 – lane=done – Review passed (round 3): All blocking issues from previous reviews resolved. _classify() validates config+orphan-branch+worktree-health triple. detect() returns True for both legacy and already-migrated states enabling upgrade runner round-trip. Non-orphan branch regression test present. 55 tests pass (23 integration + 32 unit). Rebased onto landing branch (clean), merged via ff-only. [claude-opus]

## Review Feedback

**Reviewed by**: Daniel Poelzleithner
**Status**: ❌ Changes Requested
**Date**: 2026-02-23

**Issue 1 (blocking): already-migrated detection does not validate worktree state (requirement mismatch)**
- In `src/specify_cli/upgrade/migrations/m_0_16_0_spec_branch_worktree.py:572`, `_classify()` treats `has_spec_storage_config + branch exists` as `already_migrated` without checking that the configured worktree exists and is registered/healthy.
- WP04 T019 explicitly requires already-migrated detection via config + orphan branch + worktree checks. Current logic can silently no-op on broken states (e.g., config + branch exists but worktree missing/conflicted).
- **Fix**: include explicit worktree verification in `_classify()` (ideally via the existing spec-worktree discovery helpers), and only return `already_migrated` when branch orphan-ness and worktree health are both valid.

**Issue 2 (blocking): detect/apply flow does not expose explicit already_migrated rerun result through upgrade runner**
- `detect()` returns `status == STATUS_SUCCESS` only (`src/specify_cli/upgrade/migrations/m_0_16_0_spec_branch_worktree.py:292`).
- The upgrade runner gates on `detect()` (`src/specify_cli/upgrade/runner.py:159`), so reruns through normal `upgrade` flow are marked "not needed" rather than passing through `apply()`'s explicit already-migrated path.
- WP04 success criteria call out a clean, explicit already-migrated rerun outcome.
- **Fix**: align detect/apply semantics so reruns via upgrade path surface the intended already-migrated no-op behavior (without mutating state).

**Issue 3 (coverage gap): documented migration test command does not execute migration tests**
- Running `pytest tests/integration -k "spec_storage_migration"` selects 0 tests.
- WP04 test strategy and acceptance wording expect migration-focused integration coverage under that route.
- **Fix**: either move/add migration integration tests to match the documented command pattern, or update the documented test strategy so it executes the real migration test suite used in CI/review.

**Dependent Rebase Warning**
- This WP has dependents: WP05 and WP07.
- After WP04 is updated, dependent branches should rebase onto updated WP04 branch:
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP05 && git rebase 041-orphan-branch-spec-storage-WP04`
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP07 && git rebase 041-orphan-branch-spec-storage-WP04`

- [x] DONE: Feedback addressed by claude-opus. <!-- done: addressed by claude-opus at 2026-02-24T17:24:45Z -->

---

**Reviewed by**: Daniel Poelzleithner
**Status**: ❌ Changes Requested
**Date**: 2026-02-24

**Issue 1 (blocking): already-migrated classification still does not verify orphan-branch topology**
- WP04/T019 requires already-migrated detection to validate **config + orphan branch + worktree health**.
- Current `_classify()` path checks config + branch existence + worktree health, but does **not** verify that `kitty-specs` is actually orphaned.
- In `src/specify_cli/upgrade/migrations/m_0_16_0_spec_branch_worktree.py:587` onward, `_classify()` returns `STATUS_ALREADY_MIGRATED` when `discover_spec_worktree()` reports healthy, even if the branch is non-orphan.
- Reproduction used in review: create `kitty-specs` as a normal branch from `main`, add a registered worktree, save `spec_storage` config; `_classify()` still returns `already_migrated` with reason "orphan branch is present".
- **Required fix**: in `_classify()`, explicitly verify orphan-ness (e.g., `_is_orphan_branch(project_path, self.SPEC_BRANCH, _resolve_primary_branch(project_path))` or equivalent branch-state helper) before returning `STATUS_ALREADY_MIGRATED`. If non-orphan, return `STATUS_NOT_APPLICABLE` with repair guidance.

**Issue 2 (blocking): missing regression test for non-orphan branch in already-migrated path**
- Current new tests cover missing worktree and path conflict, but do not cover the non-orphan branch case.
- **Required fix**: add test coverage in migration suite proving config + registered worktree + non-orphan branch is **not** classified as `already_migrated`.

**Dependent Rebase Warning**
- This WP has dependents: WP05 and WP07.
- After WP04 is updated, dependent branches should rebase onto updated WP04:
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP05 && git rebase 041-orphan-branch-spec-storage-WP04`
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP07 && git rebase 041-orphan-branch-spec-storage-WP04`

- [x] DONE: Feedback addressed by codex. <!-- done: addressed by codex at 2026-02-24T19:49:17Z -->

