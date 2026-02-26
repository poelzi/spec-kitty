---
work_package_id: "WP01"
subtasks:
  - "T001"
  - "T002"
  - "T003"
  - "T004"
  - "T005"
  - "T006"
title: "Spec Storage Config and Git Primitives"
phase: "Phase 1 - Foundation"
lane: "done"
dependencies: []
assignee: ""
agent: "opencode"
shell_pid: "3009766"
review_status: "approved"
reviewed_by: "Daniel Poelzleithner"
history:
  - timestamp: "2026-02-23T12:17:54Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP01 - Spec Storage Config and Git Primitives

## Objectives & Success Criteria

- Create the base config and git/worktree helper layer required by all later work packages.
- Establish `.kittify/config.yaml` as canonical source for spec branch settings.
- Ensure helper APIs can be reused by init, migrate, check, and spec-writing commands.
- Deliver tests that prove config validation and git topology parsing behavior.

**Primary success checks**:
- `spec_storage.branch_name`, `spec_storage.worktree_path`, and `spec_storage.auto_push` exist with correct defaults.
- Invalid config values fail fast with actionable errors.
- Orphan-branch and worktree-path helper functions return deterministic outputs from git state.
- New unit tests pass under `pytest`.

## Recommended Implementation Command

```bash
spec-kitty implement WP01
```

## Context & Constraints

- Spec: `kitty-specs/041-orphan-branch-spec-storage/spec.md`
- Plan: `kitty-specs/041-orphan-branch-spec-storage/plan.md`
- Data model: `kitty-specs/041-orphan-branch-spec-storage/data-model.md`
- Contracts: `kitty-specs/041-orphan-branch-spec-storage/contracts/config-contracts.md`
- Constitution: `.kittify/memory/constitution.md`

Key constraints to honor:
- Config lives in `.kittify/config.yaml` (not per-feature metadata).
- `auto_push` default is `false`.
- Helpers must be git-native and cross-platform.
- Keep behavior backward-compatible for repos that do not yet have `spec_storage` keys.

## Subtasks & Detailed Guidance

### Subtask T001 - Define `spec_storage` config schema defaults
- **Purpose**: Introduce canonical repository-level settings required by this feature.
- **Steps**:
  1. Identify existing config loading/writing flow in agent config commands and core config utilities.
  2. Add `spec_storage` block defaults:
     - `branch_name: kitty-specs`
     - `worktree_path: kitty-specs`
     - `auto_push: false`
  3. Ensure default insertion occurs when keys are missing in legacy repos.
  4. Keep resulting YAML stable and minimal (no duplicate or reordered unrelated keys).
- **Files**:
  - `src/specify_cli/cli/commands/agent/config.py`
  - `src/specify_cli/core/config.py` (or equivalent canonical config module)
- **Parallel?**: No
- **Notes**:
  - Do not write feature-specific values into `kitty-specs/*/meta.json`.
  - Preserve existing behavior for non-related config keys.

### Subtask T002 - Implement config read/write accessors
- **Purpose**: Avoid duplicated key traversal and guarantee consistent behavior across commands.
- **Steps**:
  1. Add helper accessors for reading and writing spec storage settings.
  2. Return strongly shaped data (dict or typed object) with defaults applied.
  3. Add helper for deriving absolute worktree path from repo root + config value.
  4. Ensure callers can distinguish explicit user values from defaulted values when needed.
- **Files**:
  - `src/specify_cli/core/config.py`
  - `src/specify_cli/core/paths.py` (if path normalization lives there)
- **Parallel?**: No
- **Notes**:
  - Normalize separators and avoid trailing slash ambiguity.

### Subtask T003 - Add strict config validation and user-facing errors
- **Purpose**: Prevent invalid branch names, unsafe paths, and type mismatches from propagating.
- **Steps**:
  1. Validate `branch_name` with git-safe branch name checks.
  2. Validate `worktree_path` resolves under repo root.
  3. Validate `auto_push` is boolean (reject strings like `"yes"`).
  4. Provide clear errors that mention the exact failing key and expected value shape.
- **Files**:
  - `src/specify_cli/core/config.py`
  - `src/specify_cli/cli/commands/agent/config.py`
  - `src/specify_cli/validators/` modules if existing validator pattern should be reused
- **Parallel?**: Yes (after T001/T002 contracts are set)
- **Notes**:
  - Validation should be reused by init, check, and migration paths.

### Subtask T004 - Add orphan branch inspection helpers
- **Purpose**: Standardize branch-level checks needed by init, migration, and check commands.
- **Steps**:
  1. Implement helper that confirms branch exists locally/remotely.
  2. Implement helper that verifies branch is orphaned (no shared ancestry with planning branch).
  3. Return structured state (`exists_local`, `exists_remote`, `is_orphan`, `head_commit`).
  4. Keep command wrappers minimal by reusing these helpers.
- **Files**:
  - `src/specify_cli/core/git_ops.py`
  - `src/specify_cli/core/feature_detection.py`
- **Parallel?**: Yes (after T001/T002)
- **Notes**:
  - Handle detached HEAD and shallow clone edge cases gracefully.

### Subtask T005 - Add worktree discovery helper from git metadata
- **Purpose**: Resolve actual spec worktree path from authoritative git metadata, not path assumptions.
- **Steps**:
  1. Parse `git worktree list` output via existing command helper utilities.
  2. Match configured branch to its worktree path.
  3. Return normalized absolute path and health status when missing.
  4. Expose helper for both read-only checks and mutating command preflights.
- **Files**:
  - `src/specify_cli/core/worktree.py`
  - `src/specify_cli/core/worktree_topology.py`
  - `src/specify_cli/core/feature_detection.py`
- **Parallel?**: No
- **Notes**:
  - Keep output deterministic across OS path formats.

### Subtask T006 - Add unit tests for config and helper behavior
- **Purpose**: Lock down foundational behavior before command-level integration work.
- **Steps**:
  1. Add unit tests for missing-key defaulting in config loading.
  2. Add tests for config validation failures (invalid branch/path/type).
  3. Add tests for orphan branch helper outputs (exists/missing/non-orphan).
  4. Add tests for worktree path discovery (found/missing/wrong-branch).
  5. Ensure tests do not depend on global git state and use fixtures/temp repos.
- **Files**:
  - `tests/specify_cli/core/test_feature_detection.py`
  - `tests/specify_cli/core/test_worktree_topology.py` (or nearest equivalent)
  - `tests/specify_cli/cli/commands/agent/test_config.py`
- **Parallel?**: Yes
- **Notes**:
  - Keep tests stable across Linux/macOS/Windows runners.

## Test Strategy

Run focused tests for this WP:

```bash
pytest tests/specify_cli/core -k "config or worktree or feature_detection"
pytest tests/specify_cli/cli/commands/agent -k "config"
```

Acceptance for WP01:
- Tests pass for defaulting, validation, and helper parsing.
- No command-level behavior changes yet beyond foundational helper wiring.

## Risks & Mitigations

- **Risk**: Config schema changes break existing commands.
  - **Mitigation**: Keep backward-compatible defaults and cover legacy missing-key paths in tests.
- **Risk**: Git helper behavior differs across environments.
  - **Mitigation**: Prefer robust parsing and add fixture-based command output tests.
- **Risk**: Foundation APIs drift before downstream WPs start.
  - **Mitigation**: Stabilize helper signatures in this WP and reference them explicitly in downstream prompts.

## Review Guidance

- Verify `spec_storage` keys are centralized and not duplicated in multiple modules.
- Verify validation errors are explicit and actionable.
- Verify helper functions return structured state usable by command flows.
- Verify tests are deterministic and not dependent on developer machine branch names.

## Activity Log

- 2026-02-23T12:17:54Z - system - lane=planned - Prompt created.
- 2026-02-23T13:30:05Z – claude-opus-4-6 – shell_pid=266201 – lane=doing – Started implementation via workflow command
- 2026-02-23T15:04:29Z – claude-opus-4-6 – shell_pid=266201 – lane=for_review – Ready for review: spec_storage config schema (T001), read/write accessors (T002), validation (T003), orphan branch inspection (T004), worktree discovery (T005), and 85 unit tests (T006) all implemented and passing
- 2026-02-23T16:34:00Z – opencode – shell_pid=3009766 – lane=doing – Started review via workflow command
- 2026-02-23T16:37:36Z – opencode – shell_pid=3009766 – lane=done – Review passed: WP01 foundations validated (config schema/accessors/validation, orphan branch inspection, worktree discovery), dependency_check OK, dependent_check noted WP02-WP05 in for_review, and 85 targeted core tests pass.
