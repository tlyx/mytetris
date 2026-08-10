# RULES — hard rules that stay active across long sessions

These are re-attached near the current turn, so they survive even after the
opening context (AGENTS.md) has been pushed far up a long transcript.

- Never amend, rebase, or force-push commits that have been pushed — pushed
  history is frozen; small follow-ups become new commits.
- Comments and docstrings in Chinese; commit messages in English with a
  conventional prefix; append a `Co-authored-by: Name <email>` trailer for
  AI-assisted work.
- Rule changes are test-first; `pytest`, `ruff`, and `basedpyright` must all
  be green before committing.
- Keep comments and docstrings in sync with the code when renaming or
  refactoring.
