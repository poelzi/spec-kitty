---
work_package_id: WP02
title: Init Bootstrap for Orphan Spec Worktree
lane: "done"
dependencies:
- WP01
base_branch: 041-orphan-branch-spec-storage-WP01
base_commit: 39dbbbf5a59ae9fb1a181a12a5c1a43c87da04e2
created_at: '2026-02-23T15:16:11.571195+00:00'
subtasks:
- T007
- T008
- T009
- T010
- T011
phase: Phase 1 - Foundation
assignee: ''
agent: "codex"
shell_pid: "3452893"
review_status: "approved"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-02-23T12:17:54Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP02 - Init Bootstrap for Orphan Spec Worktree

## Objectives & Success Criteria

- Make `spec-kitty init` establish the orphan spec branch and worktree from day one.
- Ensure setup is idempotent for reruns and safe for pre-existing valid topology.
- Persist config defaults, including `auto_push: false`, in `.kittify/config.yaml`.
- Validate custom branch/worktree path configurations.

**Primary success checks**:
- Fresh init creates orphan branch and worktree at configured path.
- Re-running init does not recreate or break existing healthy setup.
- Custom config values work without falling back silently to defaults.
- Integration tests verify fresh, rerun, and custom-path scenarios.

## Recommended Implementation Command

```bash
spec-kitty implement WP02 --base WP01
```

## Context & Constraints

- Depends on foundation helpers from `WP01`.
- Spec constraints: `kitty-specs/041-orphan-branch-spec-storage/spec.md`
- Plan details: `kitty-specs/041-orphan-branch-spec-storage/plan.md`
- Config contract: `kitty-specs/041-orphan-branch-spec-storage/contracts/config-contracts.md`

Key constraints:
- `.kittify/` stays on planning branch.
- Branch creation must not assume `main`; honor project metadata/planning branch resolution.
- No destructive overwrite when configured worktree path already exists as non-worktree directory.

## Subtasks & Detailed Guidance

### Subtask T007 - Update init bootstrap to create or verify orphan branch
- **Purpose**: Ensure new projects are created in the desired topology automatically.
- **Steps**:
  1. Locate init/bootstrap flow where project structure and agent files are created.
  2. Insert branch setup call that uses configured `spec_storage.branch_name`.
  3. If branch exists, verify it is suitable (orphan + usable) before reusing.
  4. Emit clear logs for created vs reused branch states.
- **Files**:
  - `src/specify_cli/__init__.py`
  - `src/specify_cli/cli/commands/agent/feature.py`
  - `src/specify_cli/core/feature_detection.py`
- **Parallel?**: No
- **Notes**:
  - Reuse WP01 helpers; do not duplicate git command logic.

### Subtask T008 - Create or attach configured worktree path idempotently
- **Purpose**: Ensure `kitty-specs/` (or configured equivalent) is a managed worktree checkout.
- **Steps**:
  1. Add worktree bootstrap in init flow after branch validation.
  2. If path is missing, create/register worktree.
  3. If worktree exists and points to configured branch, leave unchanged.
  4. If path conflict exists (regular directory), stop safely with actionable guidance.
- **Files**:
  - `src/specify_cli/core/worktree.py`
  - `src/specify_cli/core/worktree_topology.py`
  - `src/specify_cli/__init__.py`
- **Parallel?**: No
- **Notes**:
  - Keep this idempotent and safe for repeated init runs.

### Subtask T009 - Persist default auto-push setting in config
- **Purpose**: Align init behavior with clarified policy (`auto_push` configurable, default off).
- **Steps**:
  1. Ensure init writes `spec_storage.auto_push: false` when key absent.
  2. Preserve user-configured `auto_push` value if key already exists.
  3. Add CLI output line indicating whether auto-push is enabled or disabled.
- **Files**:
  - `src/specify_cli/core/config.py`
  - `src/specify_cli/__init__.py`
- **Parallel?**: Yes
- **Notes**:
  - This is config persistence only; push behavior implementation is in WP03.

### Subtask T010 - Support custom branch/worktree path bootstrap
- **Purpose**: Ensure non-default settings are first-class and validated early.
- **Steps**:
  1. Detect custom `spec_storage.branch_name` and `spec_storage.worktree_path` values.
  2. Drive branch creation/lookup and worktree creation from those values.
  3. Ensure command output clearly reports selected branch/path.
  4. Verify custom path handling uses repo-relative normalization.
- **Files**:
  - `src/specify_cli/__init__.py`
  - `src/specify_cli/core/config.py`
  - `src/specify_cli/core/worktree.py`
- **Parallel?**: Yes (after T007/T008 path contracts are set)
- **Notes**:
  - Avoid introducing hidden fallback to hardcoded `kitty-specs` when custom value is valid.

### Subtask T011 - Integration tests for init bootstrap scenarios
- **Purpose**: Prove initialization behavior in realistic repo lifecycle scenarios.
- **Steps**:
  1. Add fresh-repo test: branch + worktree created and config written.
  2. Add rerun test: no duplicate setup or destructive branch/worktree operations.
  3. Add custom-config test: branch/path values from config are honored.
  4. Add conflict test: existing regular directory at worktree path fails safely.
- **Files**:
  - `tests/integration/test_spec_storage_branch_init.py`
  - `tests/specify_cli/cli/commands/agent/test_feature.py` (if command-level coverage needed)
- **Parallel?**: No
- **Notes**:
  - Build temp repos in tests; do not depend on current project branch names.

## Test Strategy

Execute relevant integration and command tests:

```bash
pytest tests/integration -k "spec_storage_branch_init or init"
pytest tests/specify_cli/cli/commands/agent -k "feature"
```

Acceptance for WP02:
- Fresh init bootstraps orphan branch and worktree.
- Rerun is idempotent.
- Custom branch/path bootstrap behaves correctly.

## Risks & Mitigations

- **Risk**: Bootstrap order causes partial setup when one step fails.
  - **Mitigation**: Validate config first, then branch, then worktree, with explicit rollback messaging.
- **Risk**: Existing branch reused incorrectly despite non-orphan history.
  - **Mitigation**: Call orphan verification helper before considering branch healthy.
- **Risk**: Cross-platform path behavior drift.
  - **Mitigation**: Normalize path handling and verify with integration tests.

## Review Guidance

- Confirm idempotent behavior and no duplicate worktree registration.
- Confirm custom config values are honored and surfaced in CLI output.
- Confirm conflict cases fail safely and do not delete user files.
- Confirm tests assert expected git topology after init.

## Activity Log

- 2026-02-23T12:17:54Z - system - lane=planned - Prompt created.
- 2026-02-23T15:22:19Z – unknown – shell_pid=3452893 – lane=for_review – Ready for review: bootstrap_spec_storage() creates orphan branch + worktree during init, with idempotent rerun support, custom config, path conflict safety. 14 unit tests + 18 integration tests passing.
- 2026-02-23T16:36:37Z – codex – shell_pid=3452893 – lane=doing – Started review via workflow command
- 2026-02-23T16:40:16Z – codex – shell_pid=3452893 – lane=done – Review passed: bootstrap flow is idempotent, honors custom branch/worktree config, and conflict safety is covered by passing unit/integration tests.
