---
description: Execute deep Phase 0 research — evaluate tools, libraries, and architectural options; design data structures; resolve all unknowns with evidence before task generation.
scripts:
  sh: spec-kitty research
  ps: spec-kitty research
---

# /spec-kitty.research - Deep Research Phase

**Path reference rule:** When you mention directories or files, provide either the absolute path or a path relative to the project root (for example, `kitty-specs/<feature>/research.md`). Never refer to a folder by name alone.

## 📍 WORKING DIRECTORY: Stay in planning repository

**IMPORTANT**: Research works in the **planning repository root**. Do NOT cd into any worktree.

**Do NOT cd anywhere.** Stay in the planning repository root.

## Spec Storage: Orphan Branch Architecture

All spec and planning files (`kitty-specs/`) reside on a **detached orphan branch** mounted as a git worktree. This has critical implications:

- **Files are normal files on disk** — read, write, and edit them via `kitty-specs/<feature>/...` as usual.
- **`git log` on main shows NOTHING about spec changes.** The orphan branch shares no history with `main`. This is normal — not an error.
- **`git diff HEAD -- kitty-specs/`** is always empty. Do not use it.
- **To view spec history:** `git -C kitty-specs log --oneline`
- **Do NOT run `git add` or `git commit`** on spec files. The `spec-kitty` CLI handles commits with `--no-verify` (the worktree lacks `.pre-commit-config.yaml`; pre-commit hooks will hang or fail if you commit manually).
- **To verify your edits**, read the files directly. Do not rely on git commands from the main repo.

See AGENTS.md section 5a for full details.

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty). The user may narrow the research scope, specify technologies to evaluate, or provide additional constraints.

---

## Prerequisites — Fail Fast

Verify these conditions first. **Stop immediately** if any check fails.

1. **You are in the main repository root** (NOT inside `.worktrees/`):
   ```bash
   git branch --show-current   # Should be main/bernd/etc., NOT a WP branch
   ls kitty-specs/              # Must exist
   ```

2. **Feature has a filled-in plan.md**:
   ```bash
   ls kitty-specs/<feature>/spec.md kitty-specs/<feature>/plan.md
   ```
   Read the first 40 lines of `plan.md`. If it is still full of `[FEATURE]`, `[DATE]`, or boilerplate `[NEEDS CLARIFICATION]` placeholders, the plan has not been filled in — run `/spec-kitty.plan` first. The `{SCRIPT}` command validates this and **will reject unfilled plans**.

3. **Read the constitution** (if it exists): `.kittify/memory/constitution.md` — research decisions must respect project principles.

If prerequisites pass, proceed.

---

## Goal

You are the research agent. Your job is to do the hard intellectual work that makes implementation planning concrete:

- **Evaluate and recommend** libraries, frameworks, tools, and services
- **Design the architecture** — components, boundaries, data flow, integration patterns
- **Design data structures** — entities, schemas, relationships, validation rules, state machines
- **Resolve every unknown** from the plan with evidence-backed decisions
- **Identify risks** and document mitigation strategies

When you are done, a planning agent reading only your research artifacts should be able to generate precise, implementable work packages without further investigation.

---

## Workflow

### Step 1: Load all context

Read these files thoroughly before doing any research:

1. `kitty-specs/<feature>/spec.md` — what the user wants (requirements, user stories, success criteria)
2. `kitty-specs/<feature>/plan.md` — technical architecture draft, technology choices, open questions
3. `.kittify/memory/constitution.md` — project principles and constraints (if exists)
4. Existing codebase — scan the repository structure, `Cargo.toml` / `package.json` / `pyproject.toml` / etc. to understand the current tech stack, dependencies, and patterns already in use

### Step 2: Scaffold research files

```bash
{SCRIPT}
# Add --force to overwrite existing drafts
# Add --feature <slug> if auto-detection fails
```

This creates template stubs in `kitty-specs/<feature>/`:

| File | Purpose |
|------|---------|
| `research.md` | Decision log — your primary output |
| `data-model.md` | Entity/schema design — your secondary output |
| `research/evidence-log.csv` | Evidence audit trail |
| `research/source-register.csv` | Source tracking for citations |

### Step 3: Build research agenda

Extract every item that needs investigation from the plan and spec:

1. **`[NEEDS CLARIFICATION: ...]` markers** — explicit unknowns deferred during planning
2. **Technology choices without justification** — frameworks, libraries, protocols stated without rationale or comparison
3. **Architectural unknowns** — component boundaries, communication patterns, deployment topology, scaling strategy
4. **Data design gaps** — entities mentioned but not fully specified, unclear relationships, missing validation rules
5. **Dependency assumptions** — external services, APIs, or libraries assumed to work a certain way
6. **Integration points** — anything touching external systems
7. **Performance / scale assumptions** — throughput, latency, storage, concurrency claims without backing data
8. **Security and compliance** — authentication, authorization, data handling, regulatory requirements

Write this agenda as a numbered checklist at the top of `kitty-specs/<feature>/research.md` so your progress is visible.

### Step 4: Conduct research

This is the core of your work. For each item on the research agenda:

#### 4a. Library and tool evaluation

When the plan or spec requires choosing a library, framework, or tool:

1. **Identify candidates** — find 2-5 realistic options. Consider: maturity, maintenance activity, community size, license compatibility, integration fit with the existing codebase.
2. **Compare** — evaluate each candidate against project-specific criteria (performance, API ergonomics, dependency footprint, compatibility with existing stack).
3. **Test compatibility** — check that the candidate works with the project's language version, build system, and existing dependencies. Look at the codebase to verify there are no conflicts.
4. **Recommend** — pick one with clear rationale. Document why the alternatives were rejected.

#### 4b. Architecture design

When the plan has structural unknowns:

1. **Identify architectural patterns** that fit the problem (event-driven, layered, hexagonal, microservices, monolith modules, etc.)
2. **Design component boundaries** — what are the modules/crates/packages, what does each own, how do they communicate
3. **Map data flow** — how does data enter, transform, persist, and exit the system
4. **Define integration contracts** — API shapes, message formats, error handling between components
5. **Consider failure modes** — what happens when each component fails, how does the system recover

#### 4c. Data structure design

When entities or schemas need definition:

1. **Enumerate entities** from requirements — every noun in the spec that persists or has state
2. **Define fields and types** — be specific (not just "string" but "VARCHAR(255)" or "uuid" or "DateTime<Utc>")
3. **Map relationships** — foreign keys, join tables, ownership, cascading behavior
4. **Define state machines** — if entities have lifecycle states, document all transitions and guards
5. **Specify validation rules** — constraints that come from business requirements, not just type system
6. **Consider indexing and query patterns** — what queries will the application run, what needs to be fast

#### 4d. Record everything

For every decision you make:

1. **Add evidence rows** to `kitty-specs/<feature>/research/evidence-log.csv`:
   - Evidence ID (E001, E002, ...)
   - Source (URL, doc reference, codebase path)
   - Date accessed
   - Key finding
   - Relevance (which decision this supports)

2. **Register sources** in `kitty-specs/<feature>/research/source-register.csv`

3. **Write the decision** to `kitty-specs/<feature>/research.md`:

   ```markdown
   ### [Decision Title]

   **Question**: What was unclear or unresolved?
   **Decision**: What was chosen
   **Rationale**: Why — cite evidence (e.g., "E001, E003")
   **Alternatives considered**: What else was evaluated and why rejected
   **Status**: final | follow-up-needed | deferred
   **Impact**: What downstream work this affects
   ```

4. **Update plan.md**: Replace the corresponding `[NEEDS CLARIFICATION: ...]` with the resolution and a back-reference (e.g., "See research.md: Decision Title").

### Step 5: Write data-model.md

Consolidate all data design work into `kitty-specs/<feature>/data-model.md`:

- Entity definitions with fields, types, and constraints
- Relationship diagram (can be text/ASCII or mermaid)
- State machine definitions (if applicable)
- Index and query pattern notes
- Migration considerations (if touching existing data)

This document should be specific enough that an implementer can create database migrations and type definitions directly from it.

### Step 6: Verify completeness

Check every item — do not skip this:

- [ ] Research agenda checklist in research.md has every item resolved or explicitly deferred with justification
- [ ] Every `[NEEDS CLARIFICATION]` from plan.md is resolved or replaced with a decision reference
- [ ] Every decision in research.md cites at least one evidence reference
- [ ] Library/tool recommendations include comparison with alternatives
- [ ] Architecture design covers component boundaries and data flow
- [ ] data-model.md has concrete entity definitions (not placeholders)
- [ ] evidence-log.csv has entries
- [ ] source-register.csv tracks all sources
- [ ] No `<!-- placeholder -->` or `<!-- e.g., ... -->` HTML comments remain
- [ ] Risks and follow-up items are listed in research.md "Next Actions" section

**If any item fails, fix it before stopping.**

---

## Verifying Your Work

Because spec files live on an orphan branch, normal git verification does not work:

```bash
# WRONG — these show nothing:
git log --oneline -5                  # main history only
git diff HEAD -- kitty-specs/         # always empty

# CORRECT — verify directly:
head -40 kitty-specs/<feature>/research.md    # real decisions, not boilerplate?
head -20 kitty-specs/<feature>/data-model.md  # real entities, not placeholders?
wc -l kitty-specs/<feature>/research/evidence-log.csv  # has entries?
git -C kitty-specs log --oneline -5   # spec branch commits
```

Do not panic if `git log` or `git status` on main shows no changes — that is expected with orphan branch storage.

---

## Success Criteria

- **research.md** contains substantive, evidence-backed decisions — not template boilerplate. A reader can understand every technology choice, architectural decision, and trade-off.
- **data-model.md** describes concrete entities with real field names, types, relationships, and constraints — ready for an implementer to write migrations from.
- **plan.md** has zero remaining `[NEEDS CLARIFICATION]` markers (all resolved or replaced with decision references).
- **CSV logs** provide an auditable evidence trail.
- **Risks and open items** are explicitly documented, not hidden.
- A planning agent reading only these artifacts can generate implementable work packages without further research.

---

## Workflow Position

**Before this**: `/spec-kitty.plan` (creates plan.md, identifies unknowns and technology choices)

**This command**: Deep research — evaluate options, design architecture, design data structures, resolve all unknowns

**After this**: The user runs `/spec-kitty.tasks` to generate work packages from the completed plan + research.

**Do NOT proceed to task generation.** Your job ends when research artifacts are complete.
