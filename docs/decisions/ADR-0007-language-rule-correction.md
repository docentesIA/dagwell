# ADR-0007 — Language Rule Correction in AGENTS.md

- **Status: ACCEPTED — human gate, 2026-08-25**
- **Relates to:** Execution Contract "Convenção de idioma (emenda H1)"; AGENTS.md §2
- **Origin:** independent audit of 2026-08-25 (finding A12, openai auditor)

## Context

`AGENTS.md` stated: *"normative content is written in **English only**"*, attributing
the rule to contract amendment H1.

H1 says something different. Its words are: *"A prosa deste contrato é em português.
Todos os identificadores CANÔNICOS do protocolo — event types, field names, enum
values, nomes de estados — são em inglês."* What H1 makes English-only is the
**canonical vocabulary**, not normative prose. The contract's own prose is Portuguese
and is the supreme normative source.

So the second document in the precedence order contradicted the first about what
counts as normative — in a project whose entire premise is that the contract governs
and documents do not quietly drift from it.

Left standing, the error is self-executing: an agent reading `AGENTS.md` could
conclude that the Portuguese contract is not canonical, or that a future normative
specification written in Portuguese may be disregarded. That is the contract being
weakened by its own operational map.

## Decision

The language rule in `AGENTS.md` is corrected to state what H1 states: the canonical
protocol vocabulary is English and enters the ledger only in canonical form; localized
display is allowed and is never a second source of truth; and the normativity of a
document does not depend on the language of its prose.

No contract text was touched. The contract still hashes to `bd1552a9…9e623a`.

## Consequences

- `AGENTS.md` no longer contradicts the document it is subordinate to.
- The README already described the arrangement correctly ("the Execution Contract's
  prose is Portuguese by design; all canonical protocol identifiers are English") —
  README and AGENTS.md now agree.
- This is a correction, not a new rule: no behavior, no code and no §13 question moves.
