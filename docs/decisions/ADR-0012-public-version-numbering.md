# ADR-0012 — Public Version Numbering

- **Status: ACCEPTED — human gate, 2026-09-16 (America/Belem), decided by Reinaldo**
- **Relates to:** AGENTS.md §11 (Git & Release Discipline), `pyproject.toml`
  `version`, `src/dagwell/__init__.py` `__version__`, release notes under
  `docs/RELEASE-*.md`, git tags.
- **Origin:** the 0.0.3 publication. The candidate was developed and reviewed
  under the internal label `0.0.3rc1` (see `docs/RELEASE-0.0.3rc1.md`); the
  question of whether that label should ever appear in a public version string
  or tag was decided here, before the first tag of the 0.0.3 line.

## Context

One tag has been published so far (`v0.0.2`; `0.0.1` was the first package
version, never tagged), and the project's practice has been to develop a
candidate under an `rcN` label, review it, and only then publish. The package metadata carried the
`rc` label while the candidate was being reviewed (`dagwell --version` printed
`0.0.3rc1` from the editable install), which raised the question: does a
published version ever carry `rc`?

## Decision

1. **Public versions are `0.0.n` only.** `n` increases by one at each
   publication. There is no other public scheme (no `rc`, `a`, `b`, `post`,
   `dev` suffixes; no minor/major bump) until a separate decision changes it.
2. **`rc` suffixes are internal candidate control.** A candidate under review
   may carry `0.0.nrcK` in the working tree and in commits on `main`, and its
   release-candidate notes are kept as historical record (`docs/RELEASE-0.0.nrcK.md`
   stays as written, with a header pointing to the promoted notes). The `rc`
   label is removed from `pyproject.toml` and `__init__.py` by a **promotion
   commit** before the tag. No `rc` string is ever tagged or published.
3. **Public tags are `v0.0.n`**, annotated, pointing at the promotion commit,
   created only after verifying the tag does not exist locally or on the remote,
   and pushed only under the explicit human publication gate of AGENTS.md §11.
4. **Each public version has its own notes**, `docs/RELEASE-0.0.n.md`: what it
   adds, compatibility and limits, how it was verified, and how to roll back
   without rewriting history.

## Consequences

- The version string a user sees (`dagwell --version`, PyPI-style metadata,
  the tag) is always `0.0.n`. Internal candidate labels never leak into what a
  user installs.
- Promotion is a small, reviewable commit: version strings, release notes,
  public references. It carries no functional change.
- The historical `rc` notes remain in the tree and in history — they are not
  renamed or deleted (AGENTS.md §11: append-only from the first publication).
- Rollback of a version is `git revert` of its commits or installing the
  previous tag; never a history rewrite.
