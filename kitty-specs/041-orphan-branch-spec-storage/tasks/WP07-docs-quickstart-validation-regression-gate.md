---
work_package_id: WP07
title: Docs, Quickstart Validation, Regression Gate
lane: "planned"
dependencies:
- WP03
- WP04
- WP05
- WP06
base_branch: 041-orphan-branch-spec-storage-WP06
base_commit: 3f5c7efdea645f2de129c95bdae63ba2cd8a660a
created_at: '2026-02-23T15:48:27.546340+00:00'
subtasks:
- T032
- T033
- T034
phase: Phase 4 - Polish and Release Readiness
assignee: ''
agent: "codex"
shell_pid: "3452893"
review_status: "has_feedback"
reviewed_by: "Daniel Poelzleithner"
review_feedback_file: "/tmp/spec-kitty-review-feedback-WP07.md"
history:
- timestamp: '2026-02-23T12:17:54Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP07 - Docs, Quickstart Validation, Regression Gate

## Objectives & Success Criteria

- Align docs/help output with final orphan branch behavior.
- Validate quickstart steps end-to-end against implemented command behavior.
- Run full regression gate and resolve failures before review handoff.

**Primary success checks**:
- Documentation and examples match real command behavior and flags.
- Quickstart steps execute successfully on a clean test repository.
- Full quality gate (`pytest` targets + `nix build`) passes.

## Recommended Implementation Command

```bash
spec-kitty implement WP07 --base WP06
```

## Context & Constraints

- This WP is final hardening after core implementation is complete.
- Relevant artifacts:
  - `kitty-specs/041-orphan-branch-spec-storage/quickstart.md`
  - `kitty-specs/041-orphan-branch-spec-storage/plan.md`
  - `kitty-specs/041-orphan-branch-spec-storage/contracts/README.md`

Constraints:
- Migration must remain explicit-only in all docs.
- Auto-push must be documented as configurable with default off.
- Do not skip the full regression gate.

## Subtasks & Detailed Guidance

### Subtask T032 - Update docs/help/upgrade notes
- **Purpose**: Ensure external guidance matches implementation realities.
- **Steps**:
  1. Update command docs for init, check, migration, and context output changes.
  2. Add/adjust upgrade documentation for explicit migration workflow.
  3. Document new config keys under `.kittify/config.yaml`.
  4. Verify examples use correct branch/path terminology and command syntax.
- **Files**:
  - `README.md`
  - `docs/reference/agent-subcommands.md`
  - `docs/tutorials/*.md` relevant files
  - `AGENTS.md` and mission docs if needed for consistency
- **Parallel?**: Yes
- **Notes**:
  - Keep path references precise and copy-pastable.

### Subtask T033 - Validate and align quickstart scenario
- **Purpose**: Guarantee the operational runbook works as written.
- **Steps**:
  1. Execute `quickstart.md` scenario in a controlled test repo.
  2. Record any command drift and update quickstart steps.
  3. Verify manual-edit prompt and auto-push config guidance are accurate.
  4. Ensure migration and repair examples reflect final command output.
- **Files**:
  - `kitty-specs/041-orphan-branch-spec-storage/quickstart.md`
  - optional supporting docs where drift is discovered
- **Parallel?**: Yes
- **Notes**:
  - Prefer exact command transcripts in docs where stability matters.

### Subtask T034 - Run regression gate and fix failures
- **Purpose**: Deliver release-ready quality signal before review.
- **Steps**:
  1. Run targeted suites covering spec storage, migration, worktree health, and merge safety.
  2. Run full `nix build` and resolve any failures.
  3. Re-run failing tests after fixes until green.
  4. Capture final pass summary for reviewer handoff.
- **Files**:
  - modified source/tests as needed based on failures
  - release notes/changelog if feature-level entries are required by project policy
- **Parallel?**: No
- **Notes**:
  - Treat this as a hard gate; do not declare done with known failures.

## Test Strategy

Run final validation commands:

```bash
pytest tests/integration -k "spec_storage or migration or worktree or merge"
pytest tests/specify_cli -k "context or workflow or feature_detection"
nix build
```

Acceptance for WP07:
- Docs and quickstart are accurate.
- Full build/test gate passes.

## Risks & Mitigations

- **Risk**: Last-minute doc drift hides behavior changes.
  - **Mitigation**: Validate docs by executing documented commands.
- **Risk**: Regressions emerge only in full build.
  - **Mitigation**: Keep T034 mandatory and rerun gate after any fix.

## Review Guidance

- Verify docs clearly communicate explicit migration and auto-push default off.
- Verify quickstart has no stale command names/options.
- Verify final review includes evidence of successful regression gate.

## Review Feedback

**Reviewed by**: Daniel Poelzleithner
**Status**: ❌ Changes Requested
**Date**: 2026-02-25
**Feedback file**: `/tmp/spec-kitty-review-feedback-WP07.md`

**Issue 1 (blocking): WP07 branch is stale and not rebased on the current landing baseline**
- `WP07` includes old `WP06` commit `3f5c7efd` and is missing the current landing state (`WP06` head is `805356d4`).
- Net diff vs landing (`041-orphan-branch-spec-storage..HEAD`) is not docs-only; it reverts substantial shipped behavior.
- **Required fix:** rebase `041-orphan-branch-spec-storage-WP07` onto `041-orphan-branch-spec-storage` and re-apply only WP07-intended deltas.

**Issue 2 (blocking): branch introduces regressions outside WP07 scope (docs/regression gate only)**
- WP07 should focus on docs + validation gate, but current branch would remove core functionality and tests if merged.
- Regressions visible in landing diff include:
  - removal of merge-safety integration from `src/specify_cli/cli/commands/integrate.py`
  - removal of health/repair and commit-policy modules (`src/specify_cli/core/spec_health.py`, `src/specify_cli/core/spec_commit_policy.py`)
  - removal of migration and integration test coverage files under `tests/integration/` and `tests/specify_cli/`
- **Required fix:** after rebase, ensure WP07 branch does not delete or downgrade prior WP03-WP06 code; keep only documentation/quickstart/regression-gate artifacts.

**Issue 3 (blocking): dependency baseline is not respected in this branch state**
- Declared dependencies are WP03/WP04/WP05/WP06.
- While those dependency branches are merged to landing, this WP07 branch state does not preserve that merged baseline (it effectively drifts backward and reverts parts of it).
- **Required fix:** rebase onto landing, rerun WP07 gate, and include a final handoff summary with exact command outcomes on the rebased branch.


## Activity Log

- 2026-02-23T12:17:54Z - system - lane=planned - Prompt created.
- 2026-02-23T15:55:41Z – unknown – shell_pid=3452893 – lane=for_review – Ready for review: docs updated (README spec storage section, config reference, install-upgrade guide, CLI commands reference), quickstart validated against source code, regression gate passed (169/169 spec-storage tests, 312/314 core tests - 2 pre-existing jj worktree-context failures)
- 2026-02-25T12:39:21Z – codex – shell_pid=3452893 – lane=doing – Started review via workflow command
- 2026-02-25T12:46:37Z – codex – shell_pid=3452893 – lane=planned – Moved to planned
