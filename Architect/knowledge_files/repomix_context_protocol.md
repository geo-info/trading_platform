# Repomix Context Protocol

Use Repomix as the default repository-context transfer tool in the Architect → Codex workflow.

Repomix is used for:
- understanding existing repositories or services
- architectural analysis before planning
- debugging and investigation planning
- preparing better Codex briefs
- reviewing Codex results after implementation
- comparing intended behavior with actual implementation
- collecting focused context for affected files and nearby code

Do not assume repository context is always required.

Codex-facing instructions and review package requirements should be written in English.

---

## Before planning

If the user provides Repomix context:
- first build a mental map of the relevant code
- identify entry points, API routes, use cases, DB/repository layer, workers, clients, tests and config boundaries
- then choose the mode: Brainstorm, Investigation Planning, or Codex-ready Transition

If the user does not provide context:
- continue normally if the task is understandable without repo context
- ask for focused Repomix context if the task depends on existing code, tests, DB models, APIs, workers, integrations, or architecture
- provide exact shell commands and briefly explain why those paths or keywords are needed

---

## Preferred format

Use XML:

    repomix --style xml --output /tmp/context.xml

For large repositories, inspect token distribution first:

    repomix --token-count-tree

For broad service familiarization:

    repomix --style xml --output /tmp/service-context.xml

or compressed:

    repomix --compress --style xml --output /tmp/service-compressed-context.xml

---

## Focused context for known paths

Use this when relevant files/directories are already known:

    git ls-files \
      path/to/a \
      path/to/b \
      tests/relevant_test.py \
      | repomix --stdin --style xml --output /tmp/task-context.xml

---

## Focused context when relevant files are unknown

Use search-based context when the relevant files are not yet known:

    rg -l "keyword1|keyword2|keyword3" \
      | repomix --stdin --style xml --output /tmp/task-context.xml

If the search result is too broad, narrow the keywords or manually choose the relevant paths.

---

## Review requirement

For every non-trivial Codex task, review artifacts are required unless the user explicitly disables review.

Return no more than 3 uploadable files:

1. `/tmp/task-review-report.md`
2. `/tmp/task.diff`
3. `/tmp/task-review-context.xml`

Do not request many separate artifact files unless the user explicitly asks for them.

---

## Review package file 1: task-review-report.md

This file should contain:

- original Codex brief or short objective
- Codex result summary
- commands run
- test output
- git status
- git diff stat
- current branch
- recent git log
- known risks
- open questions
- whether Repomix context was generated
- continuation summary or task-state notes for long tasks, if relevant

Recommended command:

    {
      echo "# Task Review Report"
      echo
      echo "## Original Objective / Brief"
      echo "TODO: paste the short objective or original Codex brief here."
      echo
      echo "## Summary"
      echo "TODO: summarize changes here."
      echo
      echo "## Commands Run"
      echo "TODO: paste commands and results here."
      echo
      echo "## Test Output"
      echo "TODO: paste test output here."
      echo
      echo "## Git Status"
      git status --short
      echo
      echo "## Git Diff Stat"
      git diff --stat
      echo
      echo "## Branch"
      git branch --show-current
      echo
      echo "## Recent Log"
      git log --oneline --decorate -20
      echo
      echo "## Risks / Open Questions"
      echo "TODO: list known risks or unresolved questions."
      echo
      echo "## Continuation Notes"
      echo "TODO: for long tasks, add next action, current phase, and state summary."
    } > /tmp/task-review-report.md

---

## Review package file 2: task.diff

This file should contain the full diff:

    git diff > /tmp/task.diff

---

## Review package file 3: task-review-context.xml

This file should contain focused Repomix context for changed and neighboring files:

    {
      git diff --name-only
      git diff --name-only | xargs -r dirname
    } | sort -u \
      | xargs -r git ls-files \
      | sort -u \
      | repomix --stdin --style xml --output /tmp/task-review-context.xml

If the directory context is too broad, narrow the context manually:

    git ls-files path/to/relevant/files \
      | repomix --stdin --style xml --output /tmp/task-review-context.xml

For very large contexts, use compressed Repomix output if needed:

    git ls-files path/to/relevant/files \
      | repomix --stdin --compress --style xml --output /tmp/task-review-context.xml

---

## Return to Architect Review

Every non-trivial Codex brief should usually end with this section:

    ## Return to Architect Review

Ask Codex/user to return the compact 3-file review package:

1. `/tmp/task-review-report.md`
2. `/tmp/task.diff`
3. `/tmp/task-review-context.xml`

The review package must include:
- summary of changes
- commands run
- test output
- git status
- git diff stat
- full diff
- focused Repomix context
- risks / open questions
- continuation notes for long tasks, if relevant

Do not prepare a follow-up Codex brief immediately after review unless follow-up work is actually needed.

For non-trivial follow-ups, prefer `/superpowers:write-plan`.

Use `/superpowers:execute-plan` only for small, clear, low-risk fixes.
