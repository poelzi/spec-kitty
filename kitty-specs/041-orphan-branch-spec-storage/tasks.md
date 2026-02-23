# Work Packages: Orphan Branch Spec Storage with Worktree

**Inputs**: Design documents from `kitty-specs/041-orphan-branch-spec-storage/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Feature Goal**: Move planning artifacts to a dedicated orphan branch mounted as a managed git worktree, keep `.kittify/` on planning branch, provide explicit migration for legacy repos, and prevent stale branches from reintroducing `kitty-specs/` to `main`.

**Total Work Packages**: 7  
**Total Subtasks**: 34  
**Expected Prompt Size Band**: 260-430 lines per WP

## Work Package Summary

| WP ID | Title | Subtasks | Est. Prompt Lines | Dependencies |
|-------|-------|----------|-------------------|--------------|
| WP01 | Spec Storage Config and Git Primitives | 6 | ~380 | None |
| WP02 | Init Bootstrap for Orphan Spec Worktree | 5 | ~360 | WP01 |
| WP03 | Planning Writes and Commit Policy Routing | 6 | ~430 | WP01, WP02 |
| WP04 | Explicit Legacy Migration Flow | 5 | ~390 | WP01, WP02 |
| WP05 | Worktree Health Check and Repair | 5 | ~370 | WP01, WP02, WP04 |
| WP06 | Merge Safety and Context Path Exposure | 4 | ~320 | WP03, WP05 |
| WP07 | Docs, Quickstart Validation, Regression Gate | 3 | ~260 | WP03, WP04, WP05, WP06 |

---

## Work Package WP01: Spec Storage Config and Git Primitives (Priority: P0)

**Goal**: Establish project-wide config keys and core git/worktree helper primitives that all downstream behavior depends on.
**Independent Test**: Config parsing/validation and git helper unit tests pass without touching command workflows.
**Prompt**: `kitty-specs/041-orphan-branch-spec-storage/tasks/WP01-spec-storage-config-and-git-primitives.md`
**Estimated Prompt Size**: ~380 lines

### Included Subtasks
- [x] T001 Define `spec_storage` config schema with defaults (`branch_name`, `worktree_path`, `auto_push=false`)
- [x] T002 Implement config read/write accessors for spec storage settings
- [x] T003 [P] Add strict validation for branch names, paths, and boolean coercion failures
- [x] T004 [P] Add orphan-branch inspection helpers in git core utilities
- [x] T005 Add git worktree discovery helper that resolves configured spec branch path
- [x] T006 [P] Add unit tests for config + git/worktree helper behaviors

### Implementation Notes
- Keep config source-of-truth in `.kittify/config.yaml`.
- Do not introduce feature-level overrides in `kitty-specs/*/meta.json`.
- Ensure helpers are reusable by init, migrate, check, and command write paths.

### Parallel Opportunities
- T003 and T004 can proceed after T001/T002 interfaces are finalized.
- T006 can be split by module (config tests vs git helper tests).

### Dependencies
Dependencies: None

### Risks & Mitigations
- Risk: Config key drift across call sites.  
  Mitigation: Centralize key access behind typed helpers and update tests accordingly.
- Risk: Non-portable path assumptions.  
  Mitigation: Normalize paths relative to repo root and validate using `pathlib`.

---

## Work Package WP02: Init Bootstrap for Orphan Spec Worktree (Priority: P0)

**Goal**: Make `spec-kitty init` create/validate the orphan spec branch and managed worktree idempotently.
**Independent Test**: Running init on fresh and already-initialized repos produces stable branch/worktree state without duplicate setup.
**Prompt**: `kitty-specs/041-orphan-branch-spec-storage/tasks/WP02-init-bootstrap-for-orphan-spec-worktree.md`
**Estimated Prompt Size**: ~360 lines

### Included Subtasks
- [ ] T007 Update init bootstrap to create or verify configured orphan branch
- [ ] T008 Create or attach configured spec worktree path with idempotent rerun behavior
- [ ] T009 [P] Persist default `auto_push=false` when writing config during init
- [ ] T010 [P] Support custom branch/worktree-path initialization from config
- [ ] T011 Add integration tests for fresh init, rerun, and custom-config bootstrap paths

### Implementation Notes
- Reuse WP01 helpers; do not duplicate git topology logic.
- Preserve `.kittify/` on planning branch while setting up `kitty-specs/` worktree.
- Ensure reruns are no-op when state is already healthy.

### Parallel Opportunities
- T009 and T010 can run in parallel once core bootstrap sequencing in T007/T008 is in place.

### Dependencies
Dependencies: WP01

### Risks & Mitigations
- Risk: Existing directories at worktree path may cause destructive behavior.  
  Mitigation: Detect conflicts and stop with remediation guidance.
- Risk: Branch already exists but not orphan.  
  Mitigation: Explicitly validate branch topology before proceeding.

---

## Work Package WP03: Planning Writes and Commit Policy Routing (Priority: P1) 🎯 MVP

**Goal**: Route all planning-artifact writes/commits to the spec worktree and enforce manual-edit + auto-push policy.
**Independent Test**: specify/plan/clarify/workflow-lane commands update files on orphan branch history while planning branch remains free of spec-file commits.
**Prompt**: `kitty-specs/041-orphan-branch-spec-storage/tasks/WP03-planning-writes-and-commit-policy-routing.md`
**Estimated Prompt Size**: ~430 lines

### Included Subtasks
- [ ] T012 Add centralized planning-artifact root resolver backed by configured spec worktree path
- [ ] T013 [P] Update specify and plan write paths to use resolved spec worktree root
- [ ] T014 [P] Update clarify and workflow lane-update paths to read/write from spec worktree
- [ ] T015 Implement pre-commit detection prompt for manual edits (include/skip/abort)
- [ ] T016 Implement configurable auto-push behavior (`auto_push=false` default)
- [ ] T017 [P] Add integration tests for routing, manual-edit prompt outcomes, and auto-push toggle

### Implementation Notes
- Keep commit behavior local-only unless config explicitly enables push.
- Prompt flow must never silently include unrelated manual edits.
- Ensure behavior is consistent across all spec-modifying command families.

### Parallel Opportunities
- T013 and T014 can run in parallel after T012 resolver lands.
- T017 can be split into prompt behavior and auto-push behavior tracks.

### Dependencies
Dependencies: WP01, WP02

### Risks & Mitigations
- Risk: Partial command migration leaves mixed storage behavior.  
  Mitigation: Enumerate every spec-mutating command path and cover with integration tests.
- Risk: Prompt UX dead-ends in non-interactive contexts.  
  Mitigation: Define deterministic fallback/abort behavior for non-interactive runs.

---

## Work Package WP04: Explicit Legacy Migration Flow (Priority: P1)

**Goal**: Provide safe, explicit migration that moves legacy `kitty-specs/` content to orphan branch with no history rewrite.
**Independent Test**: Running upgrade on a legacy repo migrates content and removes `kitty-specs/` from planning branch HEAD; rerun reports already migrated.
**Prompt**: `kitty-specs/041-orphan-branch-spec-storage/tasks/WP04-explicit-legacy-migration-flow.md`
**Estimated Prompt Size**: ~390 lines

### Included Subtasks
- [ ] T018 Add migration module `src/specify_cli/upgrade/migrations/m_0_16_0_spec_branch_worktree.py` and register in migration pipeline
- [ ] T019 [P] Implement legacy-layout detection and idempotent `already_migrated` branch
- [ ] T020 Implement artifact transfer to orphan branch and cleanup commit removing `kitty-specs/` from planning branch
- [ ] T021 [P] Enforce migration safety checks (no history rewriting, no force operations)
- [ ] T022 Add integration tests for success, idempotence, and history-preservation behavior

### Implementation Notes
- Migration is explicit-only and must not auto-trigger during normal commands.
- Keep behavior deterministic across repositories with mixed historic branch states.

### Parallel Opportunities
- T019 and T021 can proceed in parallel once migration scaffolding in T018 exists.

### Dependencies
Dependencies: WP01, WP02

### Risks & Mitigations
- Risk: Partial migration leaves branch/worktree inconsistent.  
  Mitigation: Validate post-migration topology before success return.
- Risk: Legacy repos with unusual branch naming.  
  Mitigation: Resolve primary/planning branch from project metadata and git checks, not assumptions.

---

## Work Package WP05: Worktree Health Check and Repair (Priority: P1)

**Goal**: Add robust health validation and self-repair for missing/invalid spec worktree states.
**Independent Test**: check and spec commands recover from missing worktree path/registration and report clear remediation for path conflicts.
**Prompt**: `kitty-specs/041-orphan-branch-spec-storage/tasks/WP05-worktree-health-check-and-repair.md`
**Estimated Prompt Size**: ~370 lines

### Included Subtasks
- [ ] T023 Extend `spec-kitty check` to validate configured branch/worktree topology and status categories
- [ ] T024 Implement automatic repair for missing registration/path and fresh-clone bootstrap
- [ ] T025 [P] Add safe conflict handling when configured worktree path is a regular directory
- [ ] T026 Add preflight health enforcement before spec-modifying command execution
- [ ] T027 [P] Add integration tests for healthy, missing-path, missing-registration, wrong-branch, and path-conflict cases

### Implementation Notes
- Use git-native inspection (`git worktree list`) as source of truth.
- Repair only when safe; otherwise return actionable error with exact command guidance.

### Parallel Opportunities
- T025 and parts of T027 can run in parallel after status taxonomy in T023 is finalized.

### Dependencies
Dependencies: WP01, WP02, WP04

### Risks & Mitigations
- Risk: Aggressive repair could overwrite user data in conflicting directories.  
  Mitigation: Hard-stop on non-worktree directory conflicts and require explicit user action.
- Risk: Clone bootstrap differs by local/remote branch availability.  
  Mitigation: Test remote-present and remote-absent scenarios.

---

## Work Package WP06: Merge Safety and Context Path Exposure (Priority: P2)

**Goal**: Prevent stale landing branches from reintroducing `kitty-specs/` into `main` and expose spec worktree location for tooling.
**Independent Test**: Review/merge path ignores `kitty-specs/` content and context command reports spec branch/path accurately.
**Prompt**: `kitty-specs/041-orphan-branch-spec-storage/tasks/WP06-merge-safety-and-context-path-exposure.md`
**Estimated Prompt Size**: ~320 lines

### Included Subtasks
- [ ] T028 Update review/merge flow to exclude `kitty-specs/` paths when integrating to `main`
- [ ] T029 [P] Add regression tests for stale landing branch merge behavior
- [ ] T030 Update context/inspection output to include spec worktree absolute path and branch name
- [ ] T031 [P] Add tests for context output and branch/path mismatch reporting

### Implementation Notes
- Preserve existing review workflow semantics outside `kitty-specs/` path filtering.
- Keep context output scriptable (stable keys in JSON mode where available).

### Parallel Opportunities
- T029 and T031 can be executed in parallel once T028/T030 interfaces are stable.

### Dependencies
Dependencies: WP03, WP05

### Risks & Mitigations
- Risk: Path filtering accidentally excludes legitimate non-spec files.  
  Mitigation: Scope exclusion strictly to configured worktree path.
- Risk: Context output drift across agent adapters.  
  Mitigation: Validate both human-readable and JSON outputs.

---

## Work Package WP07: Docs, Quickstart Validation, Regression Gate (Priority: P2)

**Goal**: Finalize documentation and run full regression gate for release readiness.
**Independent Test**: Quickstart flow passes, docs match behavior, and full build/test pipeline succeeds.
**Prompt**: `kitty-specs/041-orphan-branch-spec-storage/tasks/WP07-docs-quickstart-validation-regression-gate.md`
**Estimated Prompt Size**: ~260 lines

### Included Subtasks
- [ ] T032 [P] Update docs/help/upgrade notes for orphan branch model and config fields
- [ ] T033 [P] Validate quickstart scenarios against final command behavior and correct drift
- [ ] T034 Run regression commands (`pytest` targeted suites + `nix build`) and resolve failures

### Implementation Notes
- Ensure docs explicitly call out explicit migration trigger and auto-push default off.
- Keep examples consistent with final command names and options.

### Parallel Opportunities
- T032 and T033 can run in parallel before final regression run.

### Dependencies
Dependencies: WP03, WP04, WP05, WP06

### Risks & Mitigations
- Risk: Documentation examples lag implementation details.  
  Mitigation: Re-run all documented commands in quickstart validation.
- Risk: Late test failures reveal integration gaps.  
  Mitigation: Treat T034 as mandatory gate before review.

---

## Dependency & Execution Summary

- **Recommended sequence**: `WP01 -> WP02 -> (WP03 + WP04 in parallel where possible) -> WP05 -> WP06 -> WP07`.
- **Primary MVP slice**: `WP01 + WP02 + WP03` (core orphan branch model and command routing).
- **Migration readiness**: `WP04` must complete before declaring legacy support done.
- **Operational readiness**: `WP05 + WP06 + WP07` complete hardening, safety, and release confidence.

### Parallelization Highlights

- After WP02, implementation can split into two tracks:
  - **Track A**: WP03 (write/commit routing)
  - **Track B**: WP04 (legacy migration)
- WP06 can start once WP03 and WP05 are complete.
- Within most WPs, `[P]` subtasks can be assigned to separate contributors with low merge risk.

---

## Subtask Index

| Subtask ID | Summary | Work Package | Priority | Parallel |
|------------|---------|--------------|----------|----------|
| T001 | Define `spec_storage` config schema defaults | WP01 | P0 | No |
| T002 | Implement config read/write accessors | WP01 | P0 | No |
| T003 | Validate branch/path/boolean config values | WP01 | P0 | Yes |
| T004 | Add orphan-branch inspection helpers | WP01 | P0 | Yes |
| T005 | Add worktree path discovery helper | WP01 | P0 | No |
| T006 | Unit tests for config and git helpers | WP01 | P0 | Yes |
| T007 | Init bootstrap creates/verifies orphan branch | WP02 | P0 | No |
| T008 | Init creates/attaches worktree idempotently | WP02 | P0 | No |
| T009 | Persist default `auto_push=false` | WP02 | P0 | Yes |
| T010 | Support custom branch/path bootstrap | WP02 | P0 | Yes |
| T011 | Integration tests for init scenarios | WP02 | P0 | No |
| T012 | Centralize spec artifact root resolver | WP03 | P1 | No |
| T013 | Route specify/plan writes to spec worktree | WP03 | P1 | Yes |
| T014 | Route clarify/workflow-lane writes | WP03 | P1 | Yes |
| T015 | Manual-edit include/skip/abort prompt logic | WP03 | P1 | No |
| T016 | Configurable auto-push behavior | WP03 | P1 | No |
| T017 | Integration tests for routing + commit policy | WP03 | P1 | Yes |
| T018 | Add and register migration module | WP04 | P1 | No |
| T019 | Legacy detection + already-migrated behavior | WP04 | P1 | Yes |
| T020 | Transfer artifacts + cleanup commit | WP04 | P1 | No |
| T021 | Migration safety guardrails | WP04 | P1 | Yes |
| T022 | Migration integration tests | WP04 | P1 | No |
| T023 | Extend check with topology health statuses | WP05 | P1 | No |
| T024 | Auto-repair missing path/registration | WP05 | P1 | No |
| T025 | Path-conflict safe handling and guidance | WP05 | P1 | Yes |
| T026 | Command preflight health enforcement | WP05 | P1 | No |
| T027 | Health/repair integration tests | WP05 | P1 | Yes |
| T028 | Exclude `kitty-specs/` from merge-to-main flow | WP06 | P2 | No |
| T029 | Merge safety regression tests | WP06 | P2 | Yes |
| T030 | Expose spec worktree path in context output | WP06 | P2 | No |
| T031 | Context output tests | WP06 | P2 | Yes |
| T032 | Update docs/help/upgrade notes | WP07 | P2 | Yes |
| T033 | Validate and align quickstart | WP07 | P2 | Yes |
| T034 | Final regression gate and fixes | WP07 | P2 | No |

---

> Each work package has a detailed prompt in `kitty-specs/041-orphan-branch-spec-storage/tasks/WPxx-*.md`. Use those prompts as execution briefs; use this file as dependency-aware planning index.
