---
work_package_id: WP06
title: Merge Safety and Context Path Exposure
lane: "done"
dependencies:
- WP03
- WP05
base_branch: 041-orphan-branch-spec-storage-WP03
base_commit: f14330792e4ab76cc2b9c548c66c7c1bda4cdac2
created_at: '2026-02-23T15:43:42.500610+00:00'
subtasks:
- T028
- T029
- T030
- T031
phase: Phase 3 - Operational Hardening
assignee: ''
agent: "codex"
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

# Work Package Prompt: WP06 - Merge Safety and Context Path Exposure

## Objectives & Success Criteria

- Prevent stale landing branches from reintroducing `kitty-specs/` files into `main` during review/merge.
- Expose configured spec worktree branch/path in context outputs for tooling and diagnostics.
- Add regression tests for both merge safety and context reporting.

**Primary success checks**:
- Merge/review workflow excludes configured spec path when integrating to `main`.
- Context command reports absolute spec worktree path and branch name.
- Tests prove stale branches cannot re-add spec files through merge flow.

## Recommended Implementation Command

```bash
spec-kitty implement WP06 --base WP05
```

## Context & Constraints

- Clarification requirement: stale landing branches must not re-add `kitty-specs/` on merge.
- Routing and topology behavior from WP03/WP05 are prerequisites.
- Relevant docs:
  - `kitty-specs/041-orphan-branch-spec-storage/spec.md`
  - `kitty-specs/041-orphan-branch-spec-storage/contracts/cli-contracts.md`

Constraints:
- Keep existing merge/review behavior unchanged except for spec-path exclusion.
- Respect configurable worktree path, not only hardcoded `kitty-specs`.
- Preserve scriptable output from context commands.

## Subtasks & Detailed Guidance

### Subtask T028 - Update merge/review flow to exclude spec path
- **Purpose**: Enforce integration-boundary protection against stale branch contamination.
- **Steps**:
  1. Identify merge/review code path used when integrating landing branch into planning/main branch.
  2. Add filter logic to exclude configured spec worktree path from merge set.
  3. Ensure exclusion path is derived from config and normalized.
  4. Keep non-spec files unaffected by filter.
- **Files**:
  - `src/specify_cli/cli/commands/agent/workflow.py`
  - `src/specify_cli/cli/commands/merge.py`
  - supporting merge helpers under `src/specify_cli/merge/`
- **Parallel?**: No
- **Notes**:
  - Confirm behavior on both default and custom worktree paths.

### Subtask T029 - Add merge safety regression tests
- **Purpose**: Make sure this protection cannot regress silently.
- **Steps**:
  1. Create test scenario with stale landing branch still containing legacy `kitty-specs/` tree.
  2. Execute merge/review flow and verify `main` does not gain `kitty-specs/` files.
  3. Verify code changes outside spec path still merge correctly.
  4. Add variant for custom worktree path if practical.
- **Files**:
  - `tests/integration/test_review_merge_excludes_kitty_specs.py`
  - `tests/specify_cli/test_review_warnings.py` (if warnings/output assertions are needed)
- **Parallel?**: Yes
- **Notes**:
  - Keep tests deterministic; use fixture repos and explicit branch setup.

### Subtask T030 - Expose spec worktree path and branch in context output
- **Purpose**: Make path discovery available for operators, scripts, and agents.
- **Steps**:
  1. Extend context output to include configured spec branch and absolute worktree path.
  2. Ensure values come from resolved topology, not static defaults.
  3. Include health hint when context is unresolved or mismatched.
  4. Preserve backward compatibility for existing context fields.
- **Files**:
  - `src/specify_cli/cli/commands/agent/context.py`
  - `src/specify_cli/core/feature_detection.py`
  - `src/specify_cli/core/worktree_topology.py`
- **Parallel?**: No
- **Notes**:
  - Update JSON output shape docs/tests if new fields are added.

### Subtask T031 - Add context output tests
- **Purpose**: Ensure field availability and shape stability for automation.
- **Steps**:
  1. Add tests for context output with healthy spec topology.
  2. Add tests for unresolved/mismatch cases and expected warnings.
  3. Add JSON-mode assertions for new fields.
  4. Verify no regression in existing context command behavior.
- **Files**:
  - `tests/specify_cli/cli/commands/agent/test_context.py`
  - `tests/integration/test_spec_storage_context_output.py`
- **Parallel?**: Yes
- **Notes**:
  - If context command has multiple modes, cover both human-readable and JSON outputs.

## Test Strategy

Run focused suites:

```bash
pytest tests/integration -k "merge_excludes_kitty_specs or context_output"
pytest tests/specify_cli/cli/commands/agent -k "context"
```

Acceptance for WP06:
- Merge safety protection blocks spec-path reintroduction.
- Context output reliably exposes spec branch/path.

## Risks & Mitigations

- **Risk**: Overbroad exclusion removes legitimate code paths.
  - **Mitigation**: Scope filter strictly to configured spec worktree path.
- **Risk**: Context output schema changes break downstream scripts.
  - **Mitigation**: Add explicit tests for field presence and backwards compatibility.

## Review Guidance

- Verify merge filter keying uses config path and not hardcoded literals.
- Verify stale-branch test reproduces the real regression hazard.
- Verify context output adds required information without removing existing keys.

## Activity Log

- 2026-02-23T12:17:54Z - system - lane=planned - Prompt created.
- 2026-02-23T15:48:04Z – unknown – shell_pid=3452893 – lane=for_review – Ready for review: merge safety utilities, context path exposure, 39 tests all passing
- 2026-02-24T19:53:16Z – opencode – shell_pid=3009766 – lane=doing – Started review via workflow command
- 2026-02-24T19:56:29Z – opencode – shell_pid=3009766 – lane=planned – Moved to planned
- 2026-02-24T20:05:11Z – claude-opus – shell_pid=2952046 – lane=doing – Started implementation via workflow command
- 2026-02-24T20:14:34Z – claude-opus – shell_pid=2952046 – lane=for_review – Moved to for_review
- 2026-02-24T20:15:25Z – codex – shell_pid=3452893 – lane=doing – Started review via workflow command
- 2026-02-24T20:18:44Z – codex – shell_pid=3452893 – lane=done – Review passed: merge-safety exclusions now protect integration for default/custom spec paths, context exposes branch/path/health, and focused integration+unit suites pass.

## Review Feedback

**Reviewed by**: Daniel Poelzleithner
**Status**: ❌ Changes Requested
**Date**: 2026-02-24

**Issue 1 (Blocker): dependency gate failed (`WP05` is not merged to landing branch)**

- `WP06` declares dependencies on `WP03` and `WP05` (`kitty-specs/041-orphan-branch-spec-storage/tasks/WP06-merge-safety-and-context-path-exposure.md` frontmatter).
- `WP05` is still not merged into `041-orphan-branch-spec-storage` (current `WP05` head `5a0b7329` is only on `041-orphan-branch-spec-storage-WP05`).
- `WP06` is based on `WP03` (`f1433079`) and does not include `WP05` branch state.

Why this matters:
- `WP06` review must run on the merged dependency baseline; otherwise we validate against stale behavior.

Requested fix:
- Merge `WP05` first, then rebase `WP06` onto the updated landing branch and re-run the WP06 test set.

---

**Issue 2 (Blocker): WP06 branch reverts already merged behavior from WP03/WP04 scope**

- Diff vs landing removes substantial existing functionality unrelated to WP06 scope:
  - Deletes `src/specify_cli/core/spec_commit_policy.py`.
  - Deletes migration module `src/specify_cli/upgrade/migrations/m_0_16_0_spec_branch_worktree.py`.
  - Deletes associated tests under `tests/integration/` and `tests/specify_cli/core/` and `tests/specify_cli/upgrade/`.
- Command paths are reverted from resolver/config-aware logic back to hardcoded `kitty-specs` and direct git commit behavior in:
  - `src/specify_cli/cli/commands/agent/workflow.py`
  - `src/specify_cli/cli/commands/agent/tasks.py`
  - `src/specify_cli/cli/commands/agent/feature.py`
  - `src/specify_cli/core/feature_detection.py`

Why this matters:
- WP06 is scoped to merge-safety + context exposure, not rollback of prior merged capability.
- This creates regression risk and violates "keep existing behavior unchanged except spec-path exclusion".

Requested fix:
- Rebase onto current landing branch and re-apply only WP06-intended deltas.
- Ensure no previously merged files/features are removed unless explicitly justified and covered by updated spec/plan.

---

**Issue 3 (Blocker): required integration regression coverage is missing**

- WP06 subtasks call for merge-safety/context regression tests in integration locations (`tests/integration/test_review_merge_excludes_kitty_specs.py` and context-output integration checks).
- Current branch adds core unit tests (`tests/specify_cli/core/test_spec_merge_safety.py`, `tests/specify_cli/core/test_spec_context_exposure.py`) but no equivalent integration merge-flow test artifacts.
- Running the prompt-provided integration selector currently matches 0 tests in this branch.

Why this matters:
- Without integration coverage, the stale-landing reintroduction hazard is not validated at the workflow boundary.

Requested fix:
- Add integration tests that exercise the real review/merge flow and prove configured spec path cannot be reintroduced.

---

**Dependency/coupling verification (`verify_instruction`)**

- Declarations are directionally correct: WP06 couples to WP03/WP05-level behavior (artifact resolution, topology/context, and merge/review safety plumbing).
- Current implementation branch is not aligned with that dependency baseline because it is stale and regresses merged paths.

**Dependent check + rebase warning**

- Dependent detected: `WP07` depends on `WP06` and is currently `for_review`.
- If WP06 is revised, dependent branch must rebase:

`cd /data/home/poelzi/Projects/spec-kitty/.worktrees/041-orphan-branch-spec-storage-WP07 && git rebase 041-orphan-branch-spec-storage-WP06`

- [x] DONE: Feedback addressed by claude-opus. <!-- done: addressed by claude-opus at 2026-02-24T20:14:34Z -->

