# Repomix Review Protocol

At the end of every non-trivial task, prepare review artifacts for Architect.

## Required artifacts

    git status --short > /tmp/task-status.txt
    git diff --stat > /tmp/task-diff-stat.txt
    git diff > /tmp/task.diff
    git branch --show-current > /tmp/task-branch.txt
    git log --oneline --decorate -20 > /tmp/task-log.txt

## Focused Repomix context

    {
      git diff --name-only
      git diff --name-only | xargs -r dirname
    } | sort -u \
      | xargs -r git ls-files \
      | sort -u \
      | repomix --stdin --style xml --output /tmp/task-review-context.xml

If this is too broad, narrow the context manually:

    git ls-files path/to/relevant/files \
      | repomix --stdin --style xml --output /tmp/task-review-context.xml

## Return summary

Return:
- summary of changes
- commands run
- test output
- files changed
- known risks
- artifacts created
- whether review context was generated
