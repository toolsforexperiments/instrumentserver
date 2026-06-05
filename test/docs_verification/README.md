# Docs verification scripts

Scripts that back every behavioral claim on the documentation site
(see `PLAN_docs_refactor.md` at the repo root). Nothing is documented without
being executed: each docs page has one script here that exercises the behavior
the page describes, before a word of prose is written.

These scripts are temporary. They live here for the duration of the docs
refactor and are deleted in the final cleanup phase, after the test audit in
`TEST_AUDIT.md` has been fully harvested.

## Conventions

- **One script per page**, named `verify_<page>.py`, placed in a subdirectory
  matching the page's docs area (for example
  `getting_started/verify_quickstart.py`).
- **One clearly marked section per page section**, in the same order as the
  page, with a comment header naming the section.
- **Runnable standalone**: each script asserts the documented behavior and
  exits 0 on success. No pytest required, no arguments required.
- **Use the shared helpers** in `helpers.py` for server startup/shutdown,
  client creation, and Broadcast capture. Scripts never hand-roll server
  startup; if a script needs something the helpers lack, extend the helpers.
- **Terminology** in comments and assertions follows `CONTEXT.md` at the repo
  root.

## Relationship to the test suite

These scripts verify behavior for documentation purposes; they are not the
test suite. At every page section's AUDIT step, the behavior verified here is
checked against the pytest suite under `test/`, and gaps are recorded in
`TEST_AUDIT.md`. Helpers that prove broadly useful are candidates to graduate
into pytest fixtures during the audit harvest.
