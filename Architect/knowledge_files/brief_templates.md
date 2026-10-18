# Brief Templates

User-facing discussion is in Russian by default.
All Codex-ready briefs under `/superpowers:...` must be written in English.

---

## Brainstorm Brief Template

/superpowers:brainstorm

Codex intelligence: high

# Brainstorm Brief

## Objective
## Current Context
## Facts
## Assumptions
## Key Unknowns
## Candidate Directions
## Decision Criteria
## Risks of Premature Implementation
## What Must Be Clarified Next

---

## Execution Brief Template for write-plan

/superpowers:write-plan

Codex intelligence: high

# Execution Brief

## Objective
## Why
## Scope
## Non-goals
## Relevant Context
## Architecture Baseline
Use for greenfield/new-service tasks:
- chosen architecture style
- domain model boundaries
- module/layer structure
- source of truth
- state and side effects
- testing strategy
- observability
- documentation expectations
## Context pointers
- Follow `AGENTS.md` if present.
- Follow repository `docs/agent/*` guidance if present.
- Use `repomix_context_protocol.md` for the compact 3-file review package.
- For long tasks, update `.agent/tasks/<task-id>/state.md` if the repo uses this convention, or include a continuation summary in `task-review-report.md`.

## Facts
## Assumptions
## Likely Affected Areas
## Constraints / Guardrails
## Tests
## Validation
## Stop-and-Ask Conditions
## Risks
## Done When
## Return to Architect Review
After execution, return a compact 3-file review package:
1. `/tmp/task-review-report.md`
2. `/tmp/task.diff`
3. `/tmp/task-review-context.xml`

---

## Execution Brief Template for execute-plan

/superpowers:execute-plan

Codex intelligence: medium

# Execution Brief

## Objective
## Why
## Scope
## Non-goals
## Relevant Context
## Architecture Baseline
Use for greenfield/new-service tasks:
- chosen architecture style
- domain model boundaries
- module/layer structure
- source of truth
- state and side effects
- testing strategy
- observability
- documentation expectations
## Context pointers
- Follow `AGENTS.md` if present.
- Follow repository `docs/agent/*` guidance if present.
- Use `repomix_context_protocol.md` for the compact 3-file review package.

## Facts
## Assumptions
## Likely Affected Areas
## Suggested Execution Sequence
## Constraints / Guardrails
## Tests
## Validation
## Stop-and-Ask Conditions
## Risks
## Done When
## Return to Architect Review
After execution, return a compact 3-file review package:
1. `/tmp/task-review-report.md`
2. `/tmp/task.diff`
3. `/tmp/task-review-context.xml`
