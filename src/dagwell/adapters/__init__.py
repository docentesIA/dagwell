"""Adapters — the edge of the engine (Adapter/Output Evidence Spec v1.0).

Layered composition (spec §2): transports are shared code, platform bindings
are data (the registry, which lives in the DATA area — never in this
repository), capabilities are declarations. Adapters emit transport facts and
output evidence, never verdicts (AGENTS.md §8). The core never imports this
package; this package imports the core.
"""
