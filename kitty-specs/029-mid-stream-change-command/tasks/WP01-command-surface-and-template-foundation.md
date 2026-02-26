---
work_package_id: "WP01"
subtasks:
  - "T001"
  - "T002"
  - "T003"
  - "T004"
  - "T005"
  - "T006"
title: "Command Surface and Template Foundation"
phase: "Phase 1 - Foundation"
lane: "done"
assignee: ""
agent: "opencode"
shell_pid: "1630551"
review_status: "has_feedback"
reviewed_by: "Daniel Poelzleithner"
dependencies: []
history:
  - timestamp: "2026-02-09T04:11:52Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP01 - Command Surface and Template Foundation

**Implementation command:**
```bash
spec-kitty implement WP01
```

## Objectives and Success Criteria

- Introduce `/spec-kitty.change` command wiring at top-level and agent command surfaces.
- Ensure command templates exist and render into agent-specific command files.
- Keep behavior scriptable via JSON output for downstream automation.

Success checks:
- Command is registered and discoverable.
- Template render path includes `spec-kitty.change.*` outputs.
- Smoke tests for command registration pass.

## Context and Constraints

- Spec references: `kitty-specs/029-mid-stream-change-command/spec.md` (FR-001, FR-001A).
- Plan references: `kitty-specs/029-mid-stream-change-command/plan.md` (Implementation Order step 1).
- No implementation behavior (classifier, synthesis) in this package; this package only establishes command and template foundation.

## Subtasks and Detailed Guidance

### Subtask T001 - Create top-level change command module
- **Purpose**: Add `src/specify_cli/cli/commands/change.py` as main command entrypoint.
- **Steps**:
  1. Mirror style from existing command modules (`implement.py`, `research.py`).
  2. Add public command function with optional JSON output path.
  3. Wire preview/apply behavior through helper functions (stubbed in this WP).
- **Files**: `src/specify_cli/cli/commands/change.py`
- **Parallel?**: No

### Subtask T002 - Register change command routers
- **Purpose**: Make command discoverable via CLI app.
- **Steps**:
  1. Register top-level command in `src/specify_cli/cli/commands/__init__.py`.
  2. Register agent-level command module in `src/specify_cli/cli/commands/agent/__init__.py`.
  3. Confirm no collision with existing command names.
- **Files**: `src/specify_cli/cli/commands/__init__.py`, `src/specify_cli/cli/commands/agent/__init__.py`
- **Parallel?**: No

### Subtask T003 - Add agent change command module
- **Purpose**: Provide internal command endpoints used by slash workflows.
- **Steps**:
  1. Create `src/specify_cli/cli/commands/agent/change.py`.
  2. Add subcommands for preview/apply/reconcile placeholders.
  3. Ensure each subcommand can emit JSON for automation tests.
- **Files**: `src/specify_cli/cli/commands/agent/change.py`
- **Parallel?**: No

### Subtask T004 - Add change command templates
- **Purpose**: Ensure new command is available to generated agent assets.
- **Steps**:
  1. Create `src/specify_cli/templates/command-templates/change.md`.
  2. Create mission-specific override `src/specify_cli/missions/software-dev/command-templates/change.md`.
  3. Keep placeholder variables consistent with renderer requirements.
- **Files**: `src/specify_cli/templates/command-templates/change.md`, `src/specify_cli/missions/software-dev/command-templates/change.md`
- **Parallel?**: Yes

### Subtask T005 - Update command discovery/help references
- **Purpose**: Keep workflow documentation consistent with new command.
- **Steps**:
  1. Update command listing/help text where slash command sequences are enumerated.
  2. Ensure references use `/spec-kitty.change` canonical name.
  3. Avoid alias documentation (`changeset`, `changset`) per spec clarification.
- **Files**: likely `src/specify_cli/cli/commands/init.py` and related command docs
- **Parallel?**: Yes

### Subtask T006 - Run command registration smoke tests
- **Purpose**: Verify command registration and template rendering are functional.
- **Steps**:
  1. Run targeted tests for command registration and init asset generation.
  2. Validate that generated command files include `spec-kitty.change` entries.
  3. Record failures and fix blockers before moving WP lane.
- **Files**: `tests/` updates as needed
- **Parallel?**: No

## Test Strategy

- Focused tests around command registration and rendered template presence.
- Suggested commands:
  - `pytest tests/integration/test_init_flow.py -k command`
  - `pytest tests/integration/test_agent_command_wrappers.py`

## Risks and Mitigations

- Risk: command not wired in all entrypoints.
  - Mitigation: verify both top-level and agent command trees.
- Risk: template path mismatch.
  - Mitigation: test `spec-kitty init` generated outputs in a temp fixture.

## Review Guidance

- Confirm command is callable and visible in help.
- Confirm template files are under correct source directories.
- Confirm no legacy alias was introduced.

## Activity Log

- 2026-02-09T04:11:52Z - system - lane=planned - Prompt created.
- 2026-02-09T04:51:16Z – claude-opus – shell_pid=635875 – lane=doing – Started implementation via workflow command
- 2026-02-09T10:43:56Z – claude-opus – shell_pid=635875 – lane=for_review – Ready for review: Command surface with top-level change command, 4 agent subcommands (preview/apply/next/reconcile) with stubbed JSON, base+mission templates, init.py reference, and 19 integration tests. All 200 existing integration tests pass.
- 2026-02-09T11:58:34Z – OpenCode – shell_pid=965482 – lane=doing – Started review via workflow command
- 2026-02-10T11:12:19Z – OpenCode – shell_pid=965482 – lane=for_review – Completed by OpenCode agent, moving to review
- 2026-02-10T19:40:36Z – opencode – shell_pid=1630551 – lane=doing – Started review via workflow command
- 2026-02-10T19:44:26Z – opencode – shell_pid=1630551 – lane=planned – Moved to planned
- 2026-02-10T19:47:00Z – claude – shell_pid=1633229 – lane=doing – Started implementation via workflow command
- 2026-02-10T19:47:17Z – claude – shell_pid=1633229 – lane=done – Moved to done
- 2026-02-10T19:49:20Z – opencode – shell_pid=1630551 – lane=doing – Started review via workflow command
- 2026-02-10T19:51:52Z – opencode – shell_pid=1630551 – lane=done – Review passed: fixed top-level change command markup crash and implemented --json/--preview behavior with regression tests
- 2026-02-10T19:52:41Z – opencode – shell_pid=1630551 – lane=for_review – Moved to for_review
- 2026-02-10T19:53:35Z – opencode – shell_pid=1630551 – lane=doing – Started review via workflow command
- 2026-02-10T19:54:02Z – opencode – shell_pid=1630551 – lane=done – Review passed: command surface and templates validated; top-level --json/--preview fixes and regression tests pass
