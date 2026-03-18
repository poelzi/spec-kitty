# Technical Decisions: [FEATURE]

**Generated from**: [plan.md](plan.md) | **Date**: [DATE]

> **PURPOSE**: This document captures mandatory technical decisions from the plan.
> Implementors MUST follow these decisions. Reviewers MUST verify compliance.
> A required library that appears only as an unused dependency is a review REJECTION.

## Required Libraries & Frameworks

Each entry is a MANDATORY technical decision from the plan.

| ID | Decision | Scope | Verification |
|----|----------|-------|-------------|
| TD-001 | [e.g., Use LangGraph for orchestrator] | [e.g., WP02, WP03 or "All WPs"] | [e.g., langgraph imported AND graph constructed] |
| TD-002 | [e.g., Use Pingora as reverse proxy] | [e.g., WP01] | [e.g., Pingora proxy handler implemented, requests routed through it] |

<!--
  ACTION REQUIRED: Populate from plan.md Technical Context section.
  - Each "Primary Dependencies" entry becomes a TD-xxx row
  - Scope: which WPs need this library (can be "All WPs" or refined during /spec-kitty.tasks)
  - Verification: how to check it's ACTUALLY USED, not just imported/listed as a dependency
-->

## Architecture Patterns

| ID | Pattern | Scope | Verification |
|----|---------|-------|-------------|
| TD-010 | [e.g., Singleton EventEmitter] | [e.g., All WPs] | [e.g., Single get_emitter() accessor, no direct instantiation] |
| TD-011 | [e.g., Offline-first design] | [e.g., WP03-WP05] | [e.g., Network failures never block CLI commands] |

<!--
  ACTION REQUIRED: Extract from plan.md Architecture section.
  - Design patterns, component relationships, data flow decisions
  - Each pattern needs a concrete verification method
-->

## Forbidden Approaches

| ID | Do NOT | Reason | Instead Use |
|----|--------|--------|-------------|
| TF-001 | [e.g., Do NOT implement custom graph execution] | [e.g., Reinvents LangGraph] | [e.g., LangGraph built-in execution engine] |
| TF-002 | [e.g., Do NOT use requests for async HTTP] | [e.g., Blocking] | [e.g., httpx with async] |

<!--
  ACTION REQUIRED: Document anti-patterns and forbidden shortcuts.
  - Common ways agents bypass the required libraries
  - "Use library X" implies "do not reimplement X's functionality by hand"
-->

## Constraints

| ID | Constraint | Scope | Verification |
|----|-----------|-------|-------------|
| TC-001 | [e.g., <100ms event emission overhead] | [e.g., WP02-WP05] | [e.g., Benchmark or profile] |
| TC-002 | [e.g., Cross-platform (Linux, macOS, Windows)] | [e.g., All WPs] | [e.g., No platform-specific code without fallback] |

<!--
  ACTION REQUIRED: Extract from plan.md Technical Context.
  - Performance Goals -> constraint entries
  - Constraints -> constraint entries
  - Target Platform -> cross-platform constraints if applicable
-->
