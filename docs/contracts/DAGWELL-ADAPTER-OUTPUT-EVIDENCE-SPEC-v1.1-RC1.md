# DAGWELL — Adapter / Output Evidence Specification · v1.1-RC1

> Status: PROPOSED, NON-NORMATIVE. Awaiting explicit human promotion.
> This is a narrow addendum to the preserved v1.0 specification. The
> Execution Contract v1.0 remains supreme. All v1.0 provisions not amended
> below remain unchanged.

## Model invocation amendment to §3.2–§3.3

The selected model must reach the subprocess invocation. In addition to
`{mission}` and exported `$OUT`, `invocation` may contain `{model_id}` as
one complete argument. Split the template into argv before substituting;
replace the marker with exactly the selector's `model_id` as one argument.
Never interpret the selected value as shell text or another template.

A binding declaring multiple models MUST contain `{model_id}`. Refuse a
multimodel binding without it before probing or dispatch. Single-model
bindings may retain literal invocations: the operator remains responsible
for matching that invocation to the one declared model. This compatibility
mode is a declaration, not remote attestation of provider behavior.

The marker cannot be the executable or embedded within another argument.
An invocation containing it requires an explicit selected model at execution.
The graph, tiers, cost ordering, family namespace, registry provenance,
verification gates and absence of fallback are unchanged.

Example migration:

```text
claude -p {mission}
→ claude --model {model_id} -p {mission}
```

## Conformance and compatibility

Use a zero-cost fake executor to capture argv: selecting different models
must change the model argument and match the dispatch event. Mission and
model strings containing spaces or shell metacharacters remain single
arguments. Invalid templates fail before dispatch. Old multimodel registries
need the marker; do not silently default to a provider model. Preserve old
ledgers and the original v1.0 normative file and its hash.

## Promotion record

Pending. This proposal must not be used as implementation authority until
Reinaldo explicitly approves promotion. The promoted copy and its SHA-256
will be added separately, preserving this proposal intact.
