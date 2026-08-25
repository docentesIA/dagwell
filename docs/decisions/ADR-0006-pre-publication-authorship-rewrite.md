# ADR-0006 — Pre-Publication Authorship Rewrite

- **Status: ACCEPTED — human gate, 2026-08-25**
- **Relates to:** AGENTS.md §11 (Git & Release Discipline)
- **Supersedes:** the authorship note in the commit message of
  `chore: prepare the repository for a first publication`, which asserted that
  the preceding nine commits would not be rewritten. That assertion was true
  when written and is no longer true. The message is left as it stands —
  amending it would be a second rewrite performed to hide the first.

## Context

The repository carried two author identities: nine commits under one personal
address and the tenth under another. On publication both would become
permanently public and neither would necessarily match the account that owns
the published repository.

At this moment the repository is local, has never been pushed, has no remote,
no forks, no collaborators and no downstream consumer. There is exactly one
window in which authorship can be unified at zero cost to anyone, and it closes
at the first push.

## Decision

The whole history was rewritten with `git filter-branch` to carry a single
author and committer identity, `reinaldoefc@gmail.com`, across all ten commits.

**Every tree is byte-identical to its pre-rewrite counterpart.** The rewrite
touched author and committer identity only; commit messages, authored dates and
committed dates are preserved. `git diff 9d7b6a9 d275cb8` is empty.

Commit correspondence (pre-rewrite → post-rewrite), oldest first:

| Before | After | Commit |
|---|---|---|
| `4f5538c` | `e66be0b` | bootstrap: DAGWELL repository foundation (Phase 1) |
| `456eb48` | `f186969` | feat: add run identity and event foundation |
| `6676b0b` | `9f6d266` | feat: add verification event semantics |
| `2069bfd` | `11d31fd` | feat: add graph and evidence declarations |
| `b55a6c4` | `4b51ea8` | feat: add deterministic fold and checkpoint |
| `8c123d0` | `a4dda46` | feat: add human decision workflow |
| `0283e87` | `e30ef15` | feat: add resume and interruption recovery |
| `71ce897` | `11e94ec` | fix: harden governed core (independent audit remediation) |
| `8c955fd` | `4d76e59` | fix: complete governed core hardening remediation |
| `9d7b6a9` | `d275cb8` | chore: prepare the repository for a first publication |

The pre-rewrite chain is retained locally at `refs/original/refs/heads/main`.
It is not pushed and not published; it exists so the correspondence above can
be verified rather than believed.

## Consequences

- **AGENTS.md §11 is amended, not violated.** The old wording forbade history
  rewriting unconditionally, which made no distinction between rewriting
  *content* (destroys the audit trail) and unifying *identity metadata* before
  anyone has ever seen the repository. The rule now names the window explicitly
  and closes it at the first push. The ledger stays append-only always — that
  invariant (I2) is untouched and admits no window.
- **The independent audit's central claim survives, restated.** The claim was
  that the hardening remediation was *appended*, never squashed into or amended
  onto the audited commit. That remains verifiable: `11e94ec` (H1–H4) is an
  ancestor of `4d76e59` (H5–H9), the two are distinct commits, and no content
  changed. The auditor verifies the shape of the chain, not the spelling of an
  email address.
- **Audit bundles generated before 2026-08-25 cite pre-rewrite SHAs** and are
  superseded. They must be regenerated against the current history before being
  submitted to any auditor.
- This is a one-time exercise of a window that is now closed by the first push.
