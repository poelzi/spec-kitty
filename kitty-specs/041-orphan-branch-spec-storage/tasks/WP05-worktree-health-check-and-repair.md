---
work_package_id: WP05
title: Worktree Health Check and Repair
lane: "done"
dependencies:
- WP01
- WP02
- WP04
base_branch: 041-orphan-branch-spec-storage-WP04
base_commit: fb7439a36f44b89b5af3a55dc174bcbdfdc04139
created_at: '2026-02-23T15:37:18.091711+00:00'
subtasks:
- T023
- T024
- T025
- T026
- T027
phase: Phase 3 - Operational Hardening
assignee: ''
agent: "claude-opus"
shell_pid: "3452893"
review_status: "acknowledged"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-02-23T12:17:54Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP05 - Worktree Health Check and Repair

## Objectives & Success Criteria

- Add robust health classification for configured spec branch/worktree topology.
- Auto-repair safe states (missing worktree path, missing registration, clone bootstrap gap).
- Block unsafe path-conflict states with exact remediation guidance.
- Enforce preflight health checks before spec-modifying commands execute.

**Primary success checks**:
- `spec-kitty check` reports health states with actionable messages.
- Commands self-heal safe failure modes within one invocation where feasible.
- Unsafe conflicts do not mutate user data.
- Integration tests cover all key state transitions.

## Recommended Implementation Command

```bash
spec-kitty implement WP05 --base WP04
```

## Context & Constraints

- Depends on migration flow readiness from WP04 and helper layer from WP01/WP02.
- Relevant docs:
  - `kitty-specs/041-orphan-branch-spec-storage/spec.md`
  - `kitty-specs/041-orphan-branch-spec-storage/data-model.md`
  - `kitty-specs/041-orphan-branch-spec-storage/contracts/cli-contracts.md`

Constraints:
- Use git-native topology as source of truth.
- Repair only safe states automatically.
- Keep CLI output explicit about performed repairs vs required manual actions.

## Subtasks & Detailed Guidance

### Subtask T023 - Extend check command with topology health statuses
- **Purpose**: Expose a consistent diagnostic layer for operators and automated command preflights.
- **Steps**:
  1. Define status taxonomy (healthy, missing_path, missing_registration, wrong_branch, path_conflict).
  2. Wire `spec-kitty check` to evaluate status from config + git topology.
  3. Include branch/path context in output for easier triage.
  4. Provide JSON-compatible status fields where command supports JSON output.
- **Files**:
  - `src/specify_cli/cli/commands/check.py` (or equivalent check command module)
  - `src/specify_cli/core/worktree_topology.py`
  - `src/specify_cli/core/feature_detection.py`
- **Parallel?**: No
- **Notes**:
  - Keep status labels stable; later tooling may depend on them.

### Subtask T024 - Implement auto-repair for safe states
- **Purpose**: Reduce operational friction for common breakages.
- **Steps**:
  1. Implement repair path for missing worktree directory with valid branch registration.
  2. Implement repair path for missing registration when branch and path are recoverable.
  3. Implement clone-bootstrap repair when orphan branch exists but local worktree is absent.
  4. Record whether repair succeeded and expose result in command output.
- **Files**:
  - `src/specify_cli/core/worktree.py`
  - `src/specify_cli/core/worktree_topology.py`
  - `src/specify_cli/core/feature_detection.py`
- **Parallel?**: No
- **Notes**:
  - Keep repair idempotent and avoid duplicate worktree registrations.

### Subtask T025 - Add safe handling for path-conflict states
- **Purpose**: Prevent accidental data loss when configured worktree path is occupied by regular directory.
- **Steps**:
  1. Detect conflict when configured worktree path exists but is not registered as worktree.
  2. Stop mutating flow and emit remediation options.
  3. Ensure message includes exact path and required user action.
  4. Add exit codes/structured error fields as appropriate.
- **Files**:
  - `src/specify_cli/core/worktree_topology.py`
  - `src/specify_cli/cli/commands/check.py`
  - command preflight modules in `src/specify_cli/cli/commands/agent/`
- **Parallel?**: Yes
- **Notes**:
  - Never auto-delete or move conflict directory contents.

### Subtask T026 - Enforce command preflight health checks
- **Purpose**: Ensure spec-modifying commands are routed through health validation before writing.
- **Steps**:
  1. Add preflight call to relevant spec-modifying command entry points.
  2. Attempt repair for safe states before command body proceeds.
  3. Abort command with clear message if unrecoverable conflict remains.
  4. Keep behavior consistent across specify, plan, clarify, and workflow paths.
- **Files**:
  - `src/specify_cli/cli/commands/agent/feature.py`
  - `src/specify_cli/cli/commands/agent/workflow.py`
  - `src/specify_cli/cli/commands/agent/tasks.py`
- **Parallel?**: No
- **Notes**:
  - Avoid repeated expensive checks inside a single command run.

### Subtask T027 - Add integration tests for health and repair flows
- **Purpose**: Validate real-world failure/recovery behavior across expected breakage patterns.
- **Steps**:
  1. Add test for healthy topology pass-through.
  2. Add tests for missing path and missing registration auto-repair.
  3. Add test for clone bootstrap setup on first command run.
  4. Add test for path-conflict failure with remediation text.
  5. Add test verifying preflight blocks writes when health cannot be restored.
- **Files**:
  - `tests/integration/test_spec_worktree_repair.py`
  - `tests/integration/test_spec_storage_health_check.py`
- **Parallel?**: Yes
- **Notes**:
  - Use temp repo fixtures that model each topology state directly.

## Test Strategy

Run health/repair suites:

```bash
pytest tests/integration -k "worktree_repair or health_check"
pytest tests/specify_cli/core -k "worktree_topology"
```

Acceptance for WP05:
- Check command reports stable, actionable status taxonomy.
- Safe states self-repair.
- Unsafe conflict state blocks with clear guidance.

## Risks & Mitigations

- **Risk**: Repair logic behaves differently across OS/filesystem semantics.
  - **Mitigation**: Use cross-platform-safe file operations and normalized paths.
- **Risk**: Preflight checks add command latency.
  - **Mitigation**: Cache topology checks within invocation and keep git calls minimal.
- **Risk**: False-positive conflict detection blocks valid scenarios.
  - **Mitigation**: Distinguish registered worktree directories from plain directories via git metadata.

## Review Guidance

- Verify health states map directly to remediation paths.
- Verify auto-repair is conservative and non-destructive.
- Verify preflight enforcement is applied uniformly across command families.
- Verify integration tests represent real topology breakages.

## Activity Log

- 2026-02-23T12:17:54Z - system - lane=planned - Prompt created.
- 2026-02-23T15:43:18Z – unknown – shell_pid=3452893 – lane=for_review – Ready for review: health check, auto-repair, path conflict handling, preflight function, verify-setup integration, 33 tests all passing
- 2026-02-24T19:50:00Z – codex – shell_pid=3452893 – lane=doing – Started review via workflow command
- 2026-02-24T19:53:29Z – codex – shell_pid=3452893 – lane=planned – Moved to planned
- 2026-02-24T19:54:19Z – claude-opus – shell_pid=2952046 – lane=doing – Started implementation via workflow command
- 2026-02-24T20:02:09Z – claude-opus – shell_pid=2952046 – lane=for_review – All blocking issues resolved: preflight wired into 6 command handlers (feature create/plan, tasks move/mark, workflow implement/review), 26 integration tests added (15 health check + 11 repair). 59 tests total pass (28 unit + 15 health + 11 repair + 5 pre-existing).
- 2026-02-24T20:04:53Z – codex – shell_pid=3452893 – lane=doing – Started review via workflow command
- 2026-02-24T20:05:59Z – claude-opus – shell_pid=3452893 – lane=done – Reviewed and merged to landing branch via ff-only
- 2026-02-24T20:07:40Z – claude-opus – shell_pid=3452893 – lane=done – Review passed: preflight is now enforced in feature/workflow/tasks entrypoints, health/repair integration suites are discoverable, and all targeted unit/integration tests pass.

## Review Feedback

**Reviewed by**: Daniel Poelzleithner
**Status**: ❌ Changes Requested
**Date**: 2026-02-24

**Issue 1 (blocking): preflight health enforcement is not wired into spec-mutating command entrypoints**
- WP05/T026 requires command-level preflight checks before writes in feature/workflow/tasks paths.
- `ensure_spec_storage_ready()` is implemented in `src/specify_cli/core/spec_health.py` but is not called by command handlers.
- Search shows no usages in `src/specify_cli/cli/commands/agent/*.py`; only `verify`/health module references exist.
- **Required fix**: wire preflight into relevant write paths (specify/plan/clarify/workflow/task mutations), attempt safe repair once per invocation, and abort with explicit remediation when unrecoverable.

**Issue 2 (blocking): required WP05 integration coverage is missing**
- WP05/T027 and test strategy call for integration coverage discoverable via:
  - `pytest tests/integration -k "worktree_repair or health_check"`
- Current run selects 0 tests, so key state-transition behavior is not validated at integration level.
- Existing coverage is concentrated in `tests/specify_cli/core/test_spec_health.py` with heavy mocking; this does not satisfy the integration requirement for real topology breakages.
- **Required fix**: add integration suites (e.g. `tests/integration/test_spec_worktree_repair.py`, `tests/integration/test_spec_storage_health_check.py`) and ensure the documented command executes them.

**Dependent Rebase Warning**
- This WP has dependents: WP06 and WP07.
- After updating WP05, dependent branches should rebase:
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP06 && git rebase 041-orphan-branch-spec-storage-WP05`
  - `cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP07 && git rebase 041-orphan-branch-spec-storage-WP05`

- [x] DONE: Feedback addressed by claude-opus. <!-- done: addressed by claude-opus at 2026-02-24T20:02:09Z -->

