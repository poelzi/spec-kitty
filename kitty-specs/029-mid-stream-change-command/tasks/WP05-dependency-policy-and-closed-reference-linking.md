---
work_package_id: WP05
title: Dependency Policy and Closed Reference Linking
lane: "done"
dependencies:
- WP04
base_branch: 029-mid-stream-change-command-WP04
base_commit: 1915b6774f664a2b4e5983ab93a49563c9866eef
created_at: '2026-02-09T11:17:04.589403+00:00'
subtasks:
- T024
- T025
- T026
- T027
- T028
- T029
phase: Phase 2 - Core Behavior
assignee: ''
agent: "claude-opus"
shell_pid: "1347950"
review_status: "has_feedback"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-02-09T04:11:52Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP05 - Dependency Policy and Closed Reference Linking

**Implementation command:**
```bash
spec-kitty implement WP05 --base WP04
```

## Objectives and Success Criteria

- Enforce dependency integrity for generated change WPs.
- Allow change-to-normal dependencies when ordering requires.
- Preserve closed/done WPs while linking them for historical context.
- Emit blocker details when change stack is pending but no item is ready.

## Context and Constraints

- Spec references: FR-005, FR-005A, FR-006, FR-016, FR-017.
- Data model references: `DependencyEdge`, `closed_reference_links`.
- Existing dependency graph utilities should be reused, not reimplemented.

## Subtasks and Detailed Guidance

### Subtask T024 - Extract dependency candidates
- **Purpose**: Build candidate edges from request impact and open WPs.
- **Steps**:
  1. Parse affected open WPs from change planning context.
  2. Build candidate dependency edge list.
  3. Preserve deterministic edge ordering before validation.
- **Files**: `src/specify_cli/core/change_stack.py`
- **Parallel?**: No

### Subtask T025 - Allow change-to-normal dependency rule
- **Purpose**: Implement clarified dependency policy.
- **Steps**:
  1. Add rule that permits `change WP -> normal open WP` edges.
  2. Reject edges to closed/done WPs.
  3. Surface policy in diagnostics and comments.
- **Files**: `src/specify_cli/core/change_stack.py`
- **Parallel?**: No

### Subtask T026 - Validate graph and reject invalid edges
- **Purpose**: Stop invalid dependency states before write.
- **Steps**:
  1. Run existing validators for missing refs, self-edges, cycles.
  2. Return clear, actionable errors.
  3. Ensure apply aborts atomically on validation failure.
- **Files**: `src/specify_cli/core/change_stack.py`, `src/specify_cli/core/dependency_graph.py` (if extension needed)
- **Parallel?**: No

### Subtask T027 - Link closed/done references only
- **Purpose**: Store historical references without reopening completed work.
- **Steps**:
  1. Encode closed references in generated WP metadata/body.
  2. Ensure no lane transition is attempted on closed/done targets.
  3. Add explicit note for reviewer visibility.
- **Files**: `src/specify_cli/core/change_stack.py`
- **Parallel?**: Yes

### Subtask T028 - Emit blocker output for no-ready stack
- **Purpose**: Implement stack behavior when pending items are blocked.
- **Steps**:
  1. Add resolver output for blocked stack state.
  2. Include blocking dependency IDs and missing prerequisites.
  3. Ensure normal backlog is not selected in blocked state.
- **Files**: `src/specify_cli/core/change_stack.py`, `src/specify_cli/cli/commands/agent/change.py`
- **Parallel?**: No

### Subtask T029 - Add dependency policy tests
- **Purpose**: Lock in dependency and closed-reference behavior.
- **Steps**:
  1. Add tests for valid change-to-normal edges.
  2. Add tests for cycle and missing reference rejection.
  3. Add tests for closed-reference metadata and no-reopen guarantees.
- **Files**: `tests/unit/test_change_stack.py`
- **Parallel?**: No

## Test Strategy

- `pytest tests/unit/test_change_stack.py -k "dependency or cycle or closed"`

## Risks and Mitigations

- Risk: subtle cycles introduced by mixed dependency types.
  - Mitigation: validate full graph after every generated edge set.

## Review Guidance

- Verify policy allows only intended dependency types.
- Verify blocked state behavior reports blockers and does not continue normal flow.

## Activity Log

- 2026-02-09T04:11:52Z - system - lane=planned - Prompt created.
- 2026-02-09T11:25:41Z – unknown – shell_pid=909954 – lane=for_review – Ready for review: Dependency policy enforcement (T024-T029), closed reference linking, stack-first selection with blocker output. All 76 tests pass.
- 2026-02-09T11:27:03Z – claude – shell_pid=635875 – lane=doing – Started implementation via workflow command
- 2026-02-09T11:28:51Z – claude – shell_pid=635875 – lane=for_review – WP05 complete: Dependency policy, closed reference linking, stack-first selection with blocker output. 76 tests pass. Rebased on WP04.
- 2026-02-09T14:58:48Z – opencode – shell_pid=979199 – lane=doing – Started review via workflow command
- 2026-02-09T15:17:24Z – opencode – shell_pid=979199 – lane=planned – Moved to planned
- 2026-02-10T11:31:12Z – claude-opus – shell_pid=1347950 – lane=doing – Started implementation via workflow command
- 2026-02-10T11:42:18Z – claude-opus – shell_pid=1347950 – lane=for_review – Review fix: Wire dependency policy helpers into apply path. Extract deps from request text, validate policy/graph, abort on cycles, propagate deps into WP frontmatter. 114 tests pass.
- 2026-02-10T19:47:25Z – claude-opus – shell_pid=1347950 – lane=done – Moved to done
