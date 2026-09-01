# Field report: one engine, three worlds

> First day of real production use, 2026-08-31. Everything below happened against
> live ledgers; nothing is a mock. Infrastructure details (hosts, keys, channel
> ids) are omitted on purpose.

## The claim, restated

**An agent that executed is not an agent that delivered.** DAGWELL governs agent
work as a graph over an append-only ledger and only calls *completed* what passed
its declared verification. `executed != completed` is the engine's thesis turned
into code — and on day one it earned its keep.

## What the engine guarantees (as observed, not as promised)

1. **Append-only, event-sourced ledger.** Every dispatch, return, verdict and
   human decision is an immutable event with a sequence and timestamp. State is a
   fold of events — there is no hidden state to drift. Auditing = reading a file.
2. **Honest failure.** On the very first production run, an agent exited `0`
   having produced nothing — a headless permission bug made it return empty while
   looking successful. DAGWELL recorded `failed — evidence none` instead of a
   false green. The bug was found *because* the engine refused to be polite.
3. **Fail-closed at every door.** A graph node without declared verifications (or
   an explicit `no_verification: <reason>`) is refused before the run starts. No
   binding capable of serving a node's tier? **Refusal before spend.** A binding
   whose probe fails is simply unavailable.
4. **Evidence with a hash.** Every returned artifact enters the ledger with a
   `sha256` digest — what was delivered is verifiable byte-for-byte, forever.
5. **Verifications in contract order.** Deterministic ones (scripts that run and
   record a verdict) and **human gates** that block dependent nodes in the engine
   until a person decides. A human gate is not a warning; it is a lock.
6. **Cost-conscious dispatch.** Bindings declare tiers and relative cost; the
   selector picks the cheapest capable one, and `work` without `--go` is a
   zero-cost dry-run that shows the whole plan before anything is spent.
7. **Governed retry.** Redoing a node does not erase the error: it is a
   `human_retry` event in the ledger. The full history — failures included —
   remains.

## World one — a hive of always-on agents behind a relay

Agents from four different model families run 24/7 against a self-hosted,
open-protocol message relay and answer @mentions.

What DAGWELL adds:

- **Mention-as-transport.** A ~20-line edge script posts the node's mission into
  a channel, waits for the agent's reply, and turns it into evidence. The engine
  never learns the relay protocol — boundaries live in replaceable edge scripts,
  exactly as the architecture demands (no provider code in the core).
- **Independent verification families.** The producer must not grade its own
  work; with four vendor families in the hive, a node made by one family is
  verified by another — at flat-subscription marginal cost (~zero per dispatch).
- **Chained teams with a contract.** Agent teams keep talking freely in their
  channels; DAGWELL steps in when the work needs evidence, verification and a
  human gate before anything ships.

## World two — local headless CLIs

The same models as one-shot local processes.

What DAGWELL adds:

- **A binding registry.** Each CLI enters with an invocation template, an
  availability probe, the tiers it serves and a relative cost. Switching vendors
  is a registry line, never an engine change.
- **Headless lessons turned into configuration.** The permission flags each CLI
  needs to run without a TTY are recorded in the binding — operational knowledge
  stops living in someone's head.
- **Selection with honest refusal.** `trivial` goes to the cheapest capable
  binding; if none serves the tier, the engine refuses *before* the spend and
  says why.

## World three — an autonomous agent with a home of its own

A resident agent with its own unprivileged user, directory and cron — by design.

What DAGWELL adds, in both directions:

- **The orchestrator dispatches *into* the agent's home.** A one-shot binding
  runs the mission as that user, in that user's directory, on that user's model
  provider. Proven with a graph node that asked the agent to inspect its own
  cron — the answer came back as hashed evidence in the ledger.
- **The agent drives its own graphs.** With DAGWELL installed system-wide, the
  agent's user creates a run, dispatches to itself and closes the whole cycle in
  its own folder — no sudo, no crossing into anyone else's area. The first
  sentence recorded in its ledger, translated: *"I confirm this run was driven
  by ME, via dagwell."*
- **The natural next step:** the agent's cron routines stop being loose scripts
  and become governed runs — evidence, verification and an auditable history,
  every day.

## Operational discipline that emerged from day one

- **One pilot per run.** Two `work --go` loops on the same run pay the same
  mission twice. A file-lock wrapper now refuses the second pilot with a clear
  message; a native lock in `work` is on the roadmap.
- **Ghost runs refused.** A run id absent from the ledger must be rejected before
  anything happens — discovered in testing, proposed as native fail-closed.

## Next: DAGWELL as an ACP agent

Today the conversational front-end is an LLM with its hands on the CLI: a
persona that runs `work`/`status` when the owner asks, and answers with ledger
facts. The next step is the engine speaking the **Agent Client Protocol**
natively — a `dagwell acp` subcommand over JSON-RPC/stdio:

- **Plug into any ACP client** — relay bridges, editors, other harnesses:
  mentioning the orchestrator becomes opening a session with it.
- **Deterministic answers with zero tokens.** Run state, pending verdicts, the
  next gate — straight from the fold, no LLM, no hallucination, no cost.
- **An LLM only where it earns its place:** interpreting natural language and
  writing summaries. The truth keeps coming from the ledger.
- **Human gates in the chat.** An approval becomes a signed `verdict` event —
  conversation and governance stop being separate worlds.
