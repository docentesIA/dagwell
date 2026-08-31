# Model family registry — `model:<family>` namespace

> Governed by DAGWELL-ADAPTER-OUTPUT-EVIDENCE-SPEC-v1.0 (§5), promoted
> 2026-08-31. Canonical family names for verdict
> `family: model:<vendor>-<family>` (I16/R1 operates on these strings). A family
> names a vendor's model family, never a specific model. Changes only by
> reviewed commit.

| Family string | Vendor | Covers (examples, non-exhaustive) |
|---|---|---|
| `anthropic-claude` | Anthropic | haiku, sonnet, opus, fable |
| `openai-gpt` | OpenAI | gpt-*, codex models |
| `xai-grok` | xAI | grok-* |
| `google-gemini` | Google | gemini-* |
| `moonshot-kimi` | Moonshot AI | kimi-* |
| `deterministic` — not here | — | deterministic verifiers are `family: deterministic`, never `model:*` |

Rules:

- Lowercase, hyphen-separated, ASCII. The string after `model:` is
  `<vendor>-<family>`.
- Two adapters MUST NOT label the same model with different family names — this
  file is the tie-breaker (Execution Contract §13.15).
- A new family enters by adding a row here in the same reviewed change that
  introduces its first binding.
