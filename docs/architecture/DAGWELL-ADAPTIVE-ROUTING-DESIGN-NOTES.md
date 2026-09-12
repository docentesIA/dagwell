# DAGWELL — Adaptive Cognitive Routing: notas técnicas de design

> Gerado em 2026-09-11 (Belém, -03), a pedido de Reinaldo. **Auditoria + desenho técnico,
> não implementação.** Nenhum arquivo deste repositório foi alterado na sessão que o produziu;
> nenhum commit, branch ou push foi feito. O documento foi escrito fora do repositório e depois
> incorporado a `docs/architecture/`; reaproveita e cita achados de um levantamento interno do
> ecossistema do operador (Hermes/Buzz/ACP), que não faz parte deste repositório.
>
> Método: leitura direta do código (`src/dagwell/`), dos contratos normativos (`docs/contracts/`,
> `docs/decisions/`, `docs/architecture/`) e do registry real em uso
> (um registry de operador, fora do repositório), via três leituras paralelas dedicadas (adapters/seleção;
> ledger/evidência/verificação; grafo/CLI/arquitetura), todas citando arquivo:linha. Nada aqui é
> extrapolado sem fonte — onde a resposta é "não existe hoje", isso está dito explicitamente.

---

## Resumo executivo (respostas diretas A–J da missão)

**A. Quanto da ideia já existe?** Uma fatia relevante, mas mais estreita do que "roteamento
cognitivo" sugere. O Dagwell já separa **o que uma missão precisa** (`tier`, no node) de
**quem serve isso** (bindings/modelos, no registry), escolhe **deterministicamente** o candidato
mais barato que satisfaz o tier, e recusa antes de gastar se ninguém serve. Isso é literalmente
"não matar formiga com bala de canhão" — só que com uma única dimensão de decisão (tier × custo),
sem capability granular, sem risco, sem latência como critério, sem budget real, sem fallback,
sem identidade de agente.

**B. O que falta de verdade?** Cinco lacunas concretas, em ordem de tamanho do gap:
1. **Capability granular** — hoje só existe `tier` (5 valores fechados); não há "esta missão
   precisa de raciocínio matemático" vs. "esta missão precisa de busca web".
2. **Custo no ledger** — `relative_cost` existe no registry mas **nunca é copiado para o evento
   `node_dispatched`**; o ledger hoje não tem `estimated_cost` nem `actual_cost` em lugar nenhum.
3. **Identidade de agente separada de modelo** — não existe. Hoje `agente == binding == modelo`,
   resolvido do zero a cada dispatch, sem memória nem persona.
4. **Fallback/escalonamento** — **proibido explicitamente** na spec atual ("Automatic fallback
   would silently change who executed the work").
5. **Budget policy real** — reservado (§13.12, Runtime Policy Specification) mas deliberadamente
   não escrito ainda.

**C. Dá para implementar sem quebrar compatibilidade?** Sim, para as partes de **dado** (novos
campos opcionais em registry/node/eventos — nada no contrato exige `additionalProperties: false`).
Não, para as partes de **comportamento autônomo** (fallback automático, budget, aprendizado) —
essas exigem um ADR de ativação **antes** de qualquer código, por regra explícita do próprio
projeto (`AGENTS.md` §6/§12/§14; Migration Plan §14).

**D. Onde mora o Cognitive Router?** Na **camada de adapters**, como um novo módulo que
**envolve** `selection.select()` sem substituí-lo — um estágio de filtragem/enriquecimento antes
da escolha determinística por custo, que continua sendo a mesma função pura de hoje. Nunca no
core (`graph.py`, `fold.py`, `ledger/`), nunca dentro do Hermes/Buzz. Ver seção 4.

**E. Introduzir `AgentIdentity`/`Capability`/`ModelCandidate`/`ExecutionPolicy`/`BudgetPolicy`/
`RoutingDecision`/`EvidencePolicy` como abstrações novas?** Só duas merecem existir como conceito
novo no Dagwell: **`Capability`** (tags opcionais além do tier) e **`RoutingDecision`** (o registro
observacional da escolha, estendendo o que `transport` já grava). `ModelCandidate` já existe
implicitamente em `selection.py`. `ExecutionPolicy`/`BudgetPolicy` **não devem ser inventados
agora** — são exatamente o espaço já reservado e deliberadamente vazio do §13.12. `AgentIdentity`
não deve morar no Dagwell — mora na camada de cima (Hermes Bot/Profile, Buzz ACP), e o Dagwell só
enxerga uma referência opaca. `EvidencePolicy` já existe (declaração de `output_evidence` +
`verifications` por node) — não precisa de nome novo.

**F. Mesmo agente, cérebros diferentes por missão, sem destruir memória/identidade?** Mantendo a
persona **inteiramente fora do Dagwell** (memória, tools, permissões na camada Hermes/Buzz), e
passando ao Dagwell só uma referência (`agent_ref`, string opaca) que o registry usa para
restringir/priorizar candidatos. O Dagwell decide "qual modelo para esta missão", nunca "quem
é este agente". Ver seção 11.

**G. Como registrar isso no ledger sem inchar demais?** Estender o dict `transport` (já existe,
já é livre) dentro de `node_dispatched`, com campos opcionais e puramente observacionais:
`candidate_models`, `selected_model` (já implícito em `binding_id`/`model_id`), `reason_for_selection`,
`estimated_cost`. `actual_cost` (se algum dia disponível) vai em `node_returned.transport`. Nenhum
desses campos é lido pelo fold — violaria I3 se fosse. Ver seção 7.

**H. Preservar deterministicidade e auditabilidade?** Sim, porque a proposta **não substitui**
`select()` — ela só reduz o conjunto de candidatos que chega a ele. A escolha final continua
`min(relative_cost, binding_id, model_id)`, reproduzível a partir do registry congelado
(`registry_digest` já existe). Qualquer estágio não-determinístico (ex.: um LLM classificando
capability) precisa gravar sua decisão como fato imutável antes de `select()` rodar — nunca
recalculado a cada fold.

**I. Fallback sem loop nem estouro de orçamento?** Com os mecanismos que **já existem** e nunca
automáticos: `human_retry` (I10 — só um humano abre o attempt k+1), contagem de attempts imutável
(I14) e `budget_extended`/`new_budget` como teto explícito. Escalar de modelo barato para caro é,
hoje, uma decisão humana que abre novo attempt com um registry mais restrito — nunca um loop
automático. Automatizar isso further exigiria revogar a proibição explícita de fallback em
`DAGWELL-ADAPTER-OUTPUT-EVIDENCE-SPEC` §6.7, o que é uma decisão de contrato, não uma feature.

**J. Integrar com Hermes/Buzz/Claude Code/Codex/Kimi/Grok/AGY sem acoplar o core?** Já é o desenho
atual: essas plataformas **escrevem registries e grafos** — "the engine's answer is a pure
function of (graph, registry)" (Adapter Spec v1.0). O Cognitive Router deve seguir a mesma regra:
vive no lado do registry/adapter, nunca importa nada de Hermes/Buzz. E — achado do levantamento
do ecossistema já feito nesta pasta — **não deve reviver o papel de "intermediário
conversacional"**: essa ideia já foi tentada duas vezes fora do Dagwell (bot "Dagwell" da colmeia
Buzz, skill `reel-gauntlet`) e abandonada nas duas por custo/latência de passar por um
intermediário. O router é uma função, não um agente novo competindo por turno de LLM.

---

## 1. Estado atual

Versão instalada: `0.0.2` (`pyproject.toml`), HEAD local = `origin/main` = `94ab327` = tag
`v0.0.2`. Stdlib puro, sem dependências de runtime. Um único adapter implementado: `subprocess`
(local, um processo por tentativa). O ciclo de vida completo (declarar grafo → `start` → `work`/
`dispatch` → `return` → `request-verification`/`verdict` → `decide` humano → `completed`) já
rodou em produção real (EP16, "Física em Segundos", citado no README e no levantamento).

Achado concreto desta auditoria: o registry compartilhado em uso real pelo operador
(fora do repositório) estava, na data desta análise, **quebrado** contra a própria spec v1.1 do
projeto — o binding `claude-cli` declara 2 modelos (`sonnet`, `opus`) mas sua `invocation`
(`"claude -p {mission}"`) não contém `{model_id}`, exigido desde 2026-09-04 para bindings
multimodelo. Qualquer plano que use esse registry é recusado inteiro. Isso é dívida operacional
pré-existente, não uma consequência desta proposta — mas qualquer evolução de schema deveria
corrigi-la primeiro, ou herda um registry inválido.

## 2. O que já existe (mapa por assunto)

| Assunto | Existe? | Onde |
|---|---|---|
| Difficulty/tier | **Sim** | `capability_requirements.tier` no node (`graph.py:106-119`); `CAPABILITY_TIERS = ("trivial","simple","standard","complex","frontier")` (`graph.py:32`) |
| Bindings/registry | **Sim** | dado do operador, fora do repo; schema validado em `adapters/registry.py`; cada modelo declara `tiers`, `family`, `relative_cost` |
| Seleção cheapest-satisfying | **Sim** | `adapters/selection.py:18-46` — `min(relative_cost, binding_id, model_id)` sobre candidatos que servem o tier e estão disponíveis (probe) |
| Fail-closed antes do gasto | **Sim, em várias camadas** | sem candidato → `SelectionError` (`selection.py:35-38`); sem `timeout_seconds` → registry recusado no load; sem `output_evidence`/verificações declaradas → grafo recusado no `start` (I5/I28) |
| `{model_id}` chega à invocação real | **Sim, desde v1.1** | `subprocess_transport.build_argv` (linhas 32-61); obrigatório em bindings multimodelo |
| Namespace canônico de família de modelo | **Sim** | `docs/registries/model-families.md`, `model:<vendor>-<family>`, I16/R1 |
| Ledger event-sourced, fold puro | **Sim** | `ledger/events.py` (12 event types), `fold.py` — nada de estado é armazenado, tudo é recomputado |
| `executed != completed` | **Sim, implementado com precisão** | `fold.py:158-177`: `executed` = transporte OK + evidência válida; `completed` exige adicionalmente todos os vereditos obrigatórios `approved` |
| Evidência com `evidence_id` derivado e auto-validado | **Sim** | `evidence.py` — `evidence_id` é recomputado e comparado, nunca aceito como declaração livre (ADR-0008) |
| Human gate como trava real | **Sim** | `human.py` — único caminho para `family: human`; silêncio nunca aprova; rejeição humana nunca auto-retenta (I9/I10) |
| Orphan detection sem timeout universal | **Sim** | `runtime.observe_orphans`, via callback de liveness injetado; nunca inventa órfão sem esse callback (ADR-0005) |
| Modelo de 3 camadas Platform/Transport/Capability | **Sim, e já cita Hermes/Buzz nominalmente** | `docs/architecture/DAGWELL-ARCHITECTURE-MIGRATION-PLAN-v1.md` §3: "Hermes, OpenClaw and Buzz are platforms/agents, not transport types" |
| Fallback entre modelos/transportes | **Explicitamente proibido em v1** | Adapter Spec §6.7: "none in v1 ... would silently change who executed the work" |
| Roteamento adaptativo/aprendizado | **Explicitamente adiado, com trava de processo** | Migration Plan §14: exige ADR de critérios de ativação antes de qualquer desenho |
| Custo no ledger (`estimated_cost`/`actual_cost`) | **Não existe** | `relative_cost` só existe no registry; nunca é copiado para dentro de um evento |
| `reason_for_selection` | **Não existe** | seleção é 100% determinística e sem histórico gravado — só o resultado (`binding_id`/`model_id`/`family`) fica no ledger |
| Capability granular além de tier | **Não existe** | nenhum campo de "tipo de habilidade" no node ou no registry |
| Risco (declarado) | **Não existe** | nenhum campo |
| Latência como critério de seleção | **Não existe** | `duration_seconds` é só registrado depois do fato, nunca influencia seleção |
| Disponibilidade histórica/SLA | **Não existe** | só o probe binário momentâneo antes do lote |
| Budget policy concreta | **Não existe** | `budget_extended`/`new_budget` é só um teto numérico abstrato; fórmula de retry/budget é §13.12, aberto |
| Identidade de agente separada de modelo | **Não existe** | `actor` é string livre sem estado (§13.8 aberto); "Platform/Agent" no Migration Plan trata agente = binding, não uma 4ª camada |
| Integração nativa com Hermes/Buzz/ACP | **Não existe — hoje é um LLM operando a CLI por fora** | `docs/THREE-WORLDS.md`: "the conversational front-end is an LLM with its hands on the CLI"; `dagwell acp` é proposto, não implementado |

## 3. Gap analysis

Ordenado por esforço de fechamento (menor primeiro):

1. **Custo no ledger** (`estimated_cost`, `reason_for_selection`) — trivial: copiar um valor que
   já existe no registry para dentro de um evento que já aceita campos livres. Zero risco de
   invariante.
2. **Capability granular** (`capability_tags`) — pequeno: um campo opcional a mais em node e em
   registry, um filtro a mais em `select()`. Precisa de um arquivo canônico de vocabulário
   (análogo a `model-families.md`) para não virar Torre de Babel.
3. **Agent identity como referência opaca** (`agent_ref`) — pequeno no Dagwell (é só mais um
   filtro de elegibilidade no registry), mas depende de uma decisão **fora** do Dagwell (Hermes
   Bot/Profile vs. Buzz ACP vs. híbrido) que a própria missão diz não estar tomada ainda.
4. **Escalonamento humano-gated** (barato → caro) — médio: não precisa de mecanismo novo no
   core (human_retry + registry mais restrito já bastam), mas precisa de uma convenção
   operacional documentada (como o humano expressa "tente de novo, mas só com modelos acima de
   tier X") — hoje isso seria feito manualmente editando o registry entre tentativas.
5. **Budget policy real, aprendizado/scoring** — grande e **deliberadamente fora de escopo** até
   que existam ADRs de ativação. Não é gap técnico, é gap de decisão de processo — o projeto já
   decidiu não resolver isso ainda.

## 4. Arquitetura proposta

```
                         ┌─────────────────────────────────────┐
                         │           GRAPH (node)               │
                         │  capability_requirements:             │
                         │    tier: "standard"                   │
                         │    capability_tags: ["web-research"]  │   ← NOVO, opcional
                         │  mission: "..."                       │
                         │  agent_ref: "zara"                    │   ← NOVO, opcional, opaco
                         └───────────────┬───────────────────────┘
                                         │
                                         ▼
                         ┌─────────────────────────────────────┐
                         │   COGNITIVE ROUTER (novo módulo)      │
                         │   adapters/routing.py                 │
                         │                                       │
                         │  1. resolve agent_ref → subconjunto   │
                         │     de bindings permitidos (ACL leve, │
                         │     dado do registry, não do core)    │
                         │  2. filtra por capability_tags         │
                         │     (declarativo; LLM-judge é opção   │
                         │     futura, opcional, cacheada)        │
                         │  3. NUNCA decide o modelo final —      │
                         │     só reduz o conjunto de candidatos  │
                         └───────────────┬───────────────────────┘
                                         │  subconjunto elegível de bindings
                                         ▼
                         ┌─────────────────────────────────────┐
                         │   SELECTION (existente, intocado)     │
                         │   adapters/selection.py:select()      │
                         │                                       │
                         │   min(relative_cost, binding_id,      │
                         │       model_id) sobre o subconjunto   │
                         │   → fail-closed se vazio               │
                         └───────────────┬───────────────────────┘
                                         │  {binding_id, model_id, family,
                                         │   registry_digest, + observacionais:
                                         │   candidate_models, reason_for_selection,
                                         │   estimated_cost}
                                         ▼
                         ┌─────────────────────────────────────┐
                         │  operations.dispatch → node_dispatched│
                         │  (ledger, event-sourced, fold nunca lê│
                         │   os campos observacionais — I3)      │
                         └───────────────┬───────────────────────┘
                                         ▼
                    adapter executa (subprocess hoje; http/sdk/mcp/a2a/acp = candidatos futuros)
                                         ▼
                         node_returned → evidence → verification → human gate → completed
```

Segundo diagrama — onde isso se encaixa no ecossistema (sem acoplar nenhum produto externo ao
core):

```
Hermes / Buzz / Claude Code / Codex / Kimi / Grok / AGY
        (Platform/Agent — mesmo nível, nenhum privilegiado)
                    │
                    │  escreve registries + grafos (dado, não código)
                    ▼
        ┌───────────────────────────────┐
        │   DAGWELL adapter layer        │
        │   (registry.py + routing.py +  │
        │    selection.py)               │
        │   — única camada que conhece   │
        │     capability_tags/agent_ref  │
        └───────────────┬───────────────┘
                         ▼
        DAGWELL core (graph, fold, ledger, evidence, verification, human)
                — nunca importa nada de Hermes/Buzz/Claude/etc.
```

## 5. Componentes que NÃO precisam mudar

- `fold.py` — a lógica de estados (`executed`/`completed`/etc.) já é exatamente o "checkpoint"
  necessário; roteamento não deveria influenciar states, só *quais fatos* aparecem no dispatch.
- `evidence.py`, `verification.py` — evidência e verificação já são agnósticas ao mecanismo de
  seleção; nada aqui precisa saber de capability/agent_ref.
- `human.py` — os verbos humanos (`decide`, `human_retry`, `cancel_run`) já são exatamente o
  mecanismo de escalonamento gated que a missão pede (item I); não precisam de verbo novo.
- `ledger/ledger.py`, `ledger/preconditions.py` — o motor de append-only, locks e invariantes
  I1-I29 continua intocado; os novos campos são dados dentro de eventos já existentes.
- `canonical.py`, `ids.py`, `checkpoint.py`, `snapshots.py` — infraestrutura de identidade/digest,
  ortogonal a roteamento.
- `cli.py` — os 13 comandos já cobrem o ciclo; roteamento cognitivo entra como parâmetro/
  configuração do `work`, não como comando novo (mas ver §17 sobre uma flag nova, opcional).
- Modelo de 3 camadas Platform/Transport/Capability do Migration Plan — a "4ª camada" de agente
  proposta aqui é deliberadamente **externa**, não uma revisão desse modelo.

## 6. Componentes que precisariam evoluir

| Componente | Mudança | Tipo |
|---|---|---|
| `graph.py` (`_validate_node`) | aceitar `capability_requirements.capability_tags` (lista opcional) e `agent_ref` (string opaca opcional) | aditivo, retrocompatível |
| `schemas/graph.schema.json` | atualizar para refletir `capability_requirements`/`mission`/`x_command` que **já existem em código mas não no schema** (dívida pré-existente, independente desta proposta) + os dois campos novos | correção de dívida + aditivo |
| `adapters/registry.py` | aceitar `capability_tags` por modelo e um bloco opcional `agent_permissions` (agent_ref → lista de binding_ids permitidos) | aditivo, retrocompatível |
| `adapters/selection.py` | nenhuma mudança na função `select()` em si — ela continua recebendo `available` (hoje: quais bindings passaram no probe); o router calcula um `available` mais restrito antes de chamar | zero mudança, reuso |
| `adapters/routing.py` (**novo**) | módulo do Cognitive Router — filtragem por `agent_ref`/`capability_tags`, produção do registro observacional (`candidate_models`, `reason_for_selection`, `estimated_cost`) | novo, isolado |
| `ledger/events.py` (`node_dispatched`) | nenhuma mudança de *validação* necessária — `transport` já é um dict livre; documentar a convenção dos novos campos observacionais | zero mudança de código, convenção documentada |
| `docs/registries/` | novo arquivo `capability-tags.md` (vocabulário canônico, mesmo padrão de `model-families.md`) | novo doc, sem tocar código |
| `docs/contracts/` | eventualmente, uma emenda formal se os campos observacionais precisarem virar parte normativa da Adapter Spec (hoje são opcionais e não normativos, então não é estritamente necessário de início) | doc, com ADR |

## 7. Modelo de dados

Nenhuma tabela nova — extensão do dict `transport` já existente em `node_dispatched` e
`node_returned` (ambos já aceitam `transport` como dict livre, `events.py:121-135`):

```jsonc
// node_dispatched.transport (hoje)
{
  "binding_id": "claude-cli",
  "model_id": "opus",
  "family": "anthropic-claude",
  "transport": "subprocess",
  "registry_digest": "sha256:..."
}

// node_dispatched.transport (proposto, campos novos em negrito conceitual — todos opcionais)
{
  "binding_id": "claude-cli",
  "model_id": "opus",
  "family": "anthropic-claude",
  "transport": "subprocess",
  "registry_digest": "sha256:...",

  "candidate_models": [                       // NOVO — observacional
    {"binding_id": "kimi-cli", "model_id": "default", "relative_cost": 3, "eligible": true},
    {"binding_id": "claude-cli", "model_id": "opus", "relative_cost": 25, "eligible": true}
  ],
  "reason_for_selection": "cheapest eligible candidate for tier=complex, tags=[web-research]",
  "estimated_cost": 25,                        // NOVO — copiado de relative_cost no momento do dispatch
  "agent_ref": "zara"                          // NOVO — referência opaca, nunca resolvida pelo core
}

// node_returned.transport (proposto — só se o adapter souber reportar)
{
  "exit_code": 0,
  "duration_seconds": 42.1,
  "timed_out": false,
  "actual_cost": 25.3                          // NOVO — opcional, nunca inventado se ausente
}
```

Regra inegociável: **nenhum desses campos é lido por `fold.py`**. Eles existem para auditoria e
para relatórios (ex.: custo total de um run), nunca para computar estado — isso preservaria I3
("dado derivável não se declara" / nenhuma segunda fonte de verdade). O fold continua sendo
função pura de `(graph, events)`.

Conceitos-abstração e onde cada um deveria (ou não) existir:

| Conceito pedido pela missão | Decisão | Onde |
|---|---|---|
| `AgentIdentity` | **Não introduzir no Dagwell** | mora em Hermes Bot/Profile ou Buzz ACP; o Dagwell só vê `agent_ref: string` |
| `Capability` | **Introduzir, mínimo** | `capability_tags: list[str]` opcional em node + registry; tier continua a dimensão dominante |
| `ModelCandidate` | **Já existe implicitamente** | a tupla de `selection.py`; formalizar como registro observacional em `candidate_models`, não como classe nova obrigatória |
| `ExecutionPolicy` | **Não introduzir agora** | é o espaço do §13.12 (Runtime Policy Specification), deliberadamente aberto |
| `BudgetPolicy` | **Não introduzir agora** | idem — `budget_extended`/`new_budget` já cobrem o mínimo necessário até que §13.12 seja escrito |
| `RoutingDecision` | **Introduzir como extensão de dado, não classe nova de domínio** | os campos observacionais de `transport` acima |
| `EvidencePolicy` | **Já existe** | `output_evidence` + `verifications` do node |

## 8. Algoritmo de roteamento

Dois estágios, o segundo sendo o que já existe hoje sem mudança:

```
route(node, registry, agent_directory, available_from_probe):
    # Estágio 1 — FILTRAGEM (novo, cognitivo, sempre determinístico por padrão)
    eligible = available_from_probe

    if node.agent_ref is not None:
        allowed = agent_directory.permissions_for(node.agent_ref)   # dado externo, ACL leve
        eligible = eligible ∩ allowed
        # agent_directory É EXTERNO ao Dagwell — pode ser um arquivo simples mantido
        # pelo operador, análogo ao registry. Se ausente, agent_ref é só metadado (no-op).

    if node.capability_tags:
        eligible = { b for b in eligible if binding_serves_tags(b, node.capability_tags) }
        # binding_serves_tags é comparação de conjuntos, declarativa — SEM LLM por padrão.
        # Um classificador semântico (LLM-judge) é uma OPÇÃO FUTURA, opt-in, cujo resultado
        # é gravado como fato imutável (ex.: uma verificação prévia, com seu próprio
        # evidence_id) ANTES de chegar aqui — nunca invocado dentro do fold, nunca
        # recalculado a cada leitura.

    if eligible == ∅:
        raise SelectionError("no eligible binding after routing filters — refusing before spend")
        # mesmo padrão de selection.py:35-38 — fail-closed idêntico ao já existente

    # Estágio 2 — SELEÇÃO (existente, intocado)
    return selection.select(node.tier, registry, available=eligible)
```

Propriedade central: **o Estágio 2 nunca muda**. Todo o "cognitivo" está em reduzir o conjunto
`available` antes de chamar a mesma função pura de sempre. Isso significa que o roteador nunca
pode *piorar* a garantia de custo mínimo dentro do que é elegível — ele só pode restringir, nunca
escolher por si.

## 9. Budget/fallback/escalation

Nada disto exige mecanismo novo — a composição do que já existe já resolve o pedido "cheapest → 
falhou/verificação insuficiente → superior → nova evidência, sem loop nem estouro":

```
attempt 1: route() escolhe o candidato mais barato elegível (ex.: kimi-cli, relative_cost=3)
   → dispatch → execute → return → evidence
   → request_verification → verdict: rejected (ou verification_status: error/timeout)

   (I10: rejeição humana NUNCA auto-retenta)

human decide: human_retry(actor)                    # único verbo que abre attempt k+1
   [operador ajusta o registry/agent_directory para excluir bindings já tentados
    e/ou elevar o tier mínimo aceito — decisão humana, fora do core]

attempt 2: route() agora só enxerga candidatos mais caros (ex.: claude-cli/opus)
   → dispatch → execute → return → nova evidence (novo evidence_id, I29 — veredito
     antigo nunca valida evidência nova)
   → request_verification → verdict: approved → completed

Teto duro contra loop infinito/estouro: attempts são imutáveis e contados (I14);
budget_extended/new_budget já é o mecanismo de teto explícito; esgotado →
run_landed(reason=retries_exhausted | budget_exhausted) — nunca ciclo automático,
porque human_retry é sempre uma ação humana explícita.
```

Isto respeita a proibição atual de fallback **automático** (Adapter Spec §6.7) porque a escalada
nunca acontece sozinha — é sempre um humano decidindo abrir o próximo attempt, exatamente como o
projeto já exige para toda rejeição. Automatizar a escalada (sem humano no meio) exigiria revogar
essa proibição formalmente — decisão de contrato, fora do escopo de uma implementação.

## 10. Evidência/verificação

Sem mudança necessária. A escolha de modelo é ortogonal à evidência/verificação declaradas pelo
node — o acoplamento correto (se algum dia desejado, ex.: "modelo mais barato exige verificação
humana extra") já é expressável **hoje**, no autoring do grafo: um node pode declarar quantas
verificações quiser, independente de qual modelo o serviu. Não introduzir uma dependência de
código entre `routing.py` e `verification.py` — o grafo, não o motor, é quem decide "quanto de
verificação uma escolha barata exige".

## 11. Integração com agentes (identidade persistente, cérebros diferentes por missão)

```
┌─────────────────────────────────────────────┐
│  Camada de identidade (FORA do Dagwell)       │
│  Hermes Bot/Profile  OU  Buzz ACP identity     │
│                                                 │
│  Zara: persona, SOUL, memória, skills,         │
│  ferramentas, permissões — tudo aqui           │
└──────────────────┬──────────────────────────┘
                    │  agent_ref: "zara"  (string opaca — só isso atravessa a fronteira)
                    ▼
┌─────────────────────────────────────────────┐
│  Dagwell                                       │
│  — não sabe o que é "zara", só sabe que        │
│    recebeu essa referência                     │
│  — usa agent_ref só para filtrar bindings      │
│    elegíveis (ACL leve, dado do operador)      │
│  — decide, a cada missão, qual (binding,       │
│    model) serve — nunca decide "quem é Zara"   │
└─────────────────────────────────────────────┘
```

Isso resolve o pedido "mesmo agente, cérebros diferentes por missão, sem destruir memória/
identidade/contexto": a persona nunca é recriada nem tocada pelo Dagwell — ela vive inteira do
lado de fora, e o que muda missão a missão é só a resposta de `route()`. É também a razão pela
qual `AgentIdentity` não deve ser uma classe do Dagwell: criá-la ali duplicaria uma fonte de
verdade que já mora, por decisão ainda não tomada por Reinaldo, em Hermes ou em Buzz.

## 12. Integração Hermes/Buzz/ACP

- O Migration Plan já é explícito: "Hermes, OpenClaw and Buzz are platforms/agents, not transport
  types. No one-platform = one-transport assumption is encoded anywhere." — a proposta aqui não
  precisa (e não deve) resolver essa questão; só precisa não fechar nenhuma porta.
- O ponto de integração real, hoje e no futuro, é o mesmo: **essas plataformas escrevem
  registries e grafos** (Adapter Spec v1.0: "Hermes and Buzz consume it by writing registries and
  graphs"). O Cognitive Router estende o registry (capability_tags, agent_permissions) — continua
  sendo consumido do mesmo jeito, por fora.
- **Restrição aprendida (não teórica) do próprio ecossistema**: o levantamento já em disco
  (levantamento interno, seção 1) documenta que o bot "Dagwell" da
  colmeia Buzz e a skill `reel-gauntlet` foram tentados como **intermediário conversacional** e
  abandonados nas duas vezes pelo mesmo motivo: falar direto custa 1 turno de LLM, passar por um
  intermediário custa 2. Isso é evidência empírica de que o Cognitive Router **não deve virar um
  agente conversacional novo** — deve continuar sendo uma função determinística de biblioteca,
  chamada por quem já orquestra (Reinaldo direto, ou o Hermes emergente), nunca um LLM adicional
  no meio do caminho.
- `dagwell acp` (motor falando Agent Client Protocol nativamente) segue como está: um mecanismo
  candidato, não uma arquitetura decidida (§10 do Migration Plan lista ACP entre 7 mecanismos
  candidatos, "every one of these is a candidate mechanism, not an architectural commitment").
  Se/quando isso for especificado, o Cognitive Router deve ser algo que o `dagwell acp` **chama**,
  não algo reimplementado dentro dele.
- O achado do mesmo levantamento de que **o kanban do Hermes já é conceitualmente parecido com o
  Dagwell** (ledger append-only, claims atômicos, honestidade de falha) é uma questão de
  arquitetura em aberto que esta análise não resolve — nenhum handoff lido resolve se `dagwell
  acp` deveria se integrar a esse kanban ou permanecer como camada de governança por cima. Fica
  registrada na seção 19.

## 13. Compatibilidade

- **Registry**: todos os campos novos (`capability_tags`, `agent_permissions`) são opcionais;
  um registry existente sem eles continua validando e funcionando exatamente como hoje —
  `select()` não muda de assinatura nem de comportamento quando chamado sem filtro adicional.
- **Grafo**: `capability_tags`/`agent_ref` opcionais no node; grafos existentes (nenhum exemplo
  atual usa `capability_requirements` sequer) continuam válidos sem alteração.
- **Ledger**: `transport` já é um dict livre — adicionar chaves não quebra `validate_event`
  (que não tem whitelist fechada, confirmado por leitura de `events.py`). Eventos antigos sem
  esses campos continuam foldando exatamente igual.
- **Processo**: apesar de tecnicamente compatível, o próprio `AGENTS.md` (§6) exige que toda
  mudança de schema de evento seja uma decisão arquitetural registrada (ADR) antes que código
  dependa dela — isto é uma trava de governança, não uma trava técnica, mas é inegociável dentro
  das regras que o próprio projeto se deu.

## 14. Riscos

1. **Reviver o papel de intermediário conversacional** — já falhou duas vezes no ecossistema
   real (seção 12). Risco de repetir o mesmo erro sob um nome novo ("Cognitive Router" em vez de
   "bot Dagwell").
2. **Registry compartilhado já quebrado** (`claude-cli` sem `{model_id}`) — qualquer evolução de
   schema herda essa dívida se não for corrigida antes.
3. **`capability_tags` como vocabulário livre e não governado** — sem um arquivo canônico
   (análogo a `model-families.md`), viraria uma segunda fonte de verdade confusa, exatamente o
   tipo de coisa que o projeto já tem regra explícita contra evitar (I16/R1 para `family`).
4. **Fallback automático mal disfarçado** — a tentação de "automatizar" a escalada de custo viola
   I10 e a proibição explícita de fallback (§6.7); precisa ficar claro, em qualquer implementação,
   que a escalada é sempre gated por `human_retry`.
5. **LLM-judge de capability introduzindo custo e não-determinismo** onde hoje é grátis e
   determinístico (probe) — se usado, precisa ser opt-in, cacheado, e seu resultado gravado como
   evidência imutável, nunca recalculado a cada fold.
6. **Duas sessões mexendo no mesmo repositório sem se avisar** — já aconteceu uma vez
   (dois checkouts paralelos, seção 1 do levantamento interno); qualquer implementação real
   desta proposta deveria checar a outra trilha antes de começar.

## 15. Segurança

- `agent_ref` e `actor` continuam **sem autenticação forte** — §13.8 permanece aberto; não fingir
  identidade forte onde não existe. Se `agent_ref` carregar permissões (`agent_permissions`), é
  uma ACL leve declarativa, não RBAC formal — declarar isso como limitação explícita, não como
  segurança real.
- Nenhum segredo literal entra no registry nem no `agent_directory` — regra já existente
  (`AGENTS.md` §9) continua valendo integralmente para os novos arquivos de configuração.
- `capability_tags`/`agent_ref` são **dados**, nunca instruções executáveis — tratamento
  consistente com a regra já existente de nunca executar instruções embutidas em conteúdo
  processado.

## 16. Estratégia de testes

- Suite zero-custo continua obrigatória (`tools/run_tests.py`) — nenhum teste do router pode
  chamar um LLM real.
- `adapters/routing.py` testado com fixtures determinísticas: registry com `capability_tags`,
  node com/sem tags, `agent_permissions` presente/ausente — casos de recusa antes do gasto
  (conjunto vazio após filtro) são o caso mais importante a cobrir, espelhando
  `test_selection_cheapest_satisfying_and_tiebreak` já existente.
- Se um classificador semântico opcional for adicionado no futuro, ele precisa de um dublê
  determinístico nos testes (nunca invocar API paga na suite).
- Testes de regressão garantindo que `transport` com os novos campos observacionais **não muda
  nenhum resultado de fold** — isto é, um teste que injeta `candidate_models`/`estimated_cost` em
  um evento e confirma que o estado computado é idêntico ao mesmo evento sem esses campos.

## 17. Migração incremental

Cada etapa é retrocompatível e útil sozinha (mesmo princípio do "Incremental implementation
order" do próprio contrato):

1. Corrigir o registry compartilhado quebrado (`claude-cli` sem `{model_id}`) — dívida
   pré-existente, destrava qualquer uso real antes de qualquer coisa nova.
2. Adicionar campos observacionais (`estimated_cost`, `reason_for_selection`) ao `transport` de
   `node_dispatched`, copiando `relative_cost` do registry no momento da seleção — zero mudança
   de comportamento, só mais dado auditável.
3. Adicionar `capability_tags` opcional ao registry e ao node; estender `available` antes de
   `select()` com um filtro declarativo por tags — sem tags, comportamento idêntico a hoje.
4. Publicar `docs/registries/capability-tags.md` como vocabulário canônico, mesmo padrão de
   `model-families.md`.
5. Adicionar `agent_ref` opaco ao node e um `agent_directory` externo opcional (ACL leve) —
   sem agent_ref, comportamento idêntico a hoje.
6. Documentar a convenção operacional de escalonamento humano-gated (como o operador re-executa
   `work` após `human_retry` restringindo candidatos) — sem mudança de código, só de processo.
7. Só depois de dados reais de uso das etapas 1-6: avaliar, com ADR de ativação explícito (regra
   já existente do projeto), se cabe um classificador semântico opcional de capability.

## 18. MVP experimental

O menor recorte que já demonstra a hipótese central da missão ("não matar formiga com bala de
canhão", agora com capability além de tier) sem tocar em nenhum invariante:

- Corrigir o registry quebrado (pré-requisito prático).
- Adicionar `capability_tags` opcional (etapas 2-4 da migração acima) a **um** grafo de teste
  real (ex.: reaproveitar um EP já rodado) e observar `route()` escolher entre dois bindings do
  mesmo tier mas tags diferentes.
- Adicionar os campos observacionais de custo ao dispatch e produzir, pela primeira vez, um
  relatório de "custo total estimado de um run" a partir do ledger — algo que hoje é impossível
  de calcular sem essa mudança.
- Não incluir `agent_ref`/`agent_directory` no MVP — depende de uma decisão externa (Hermes vs.
  Buzz vs. híbrido) que a missão explicitamente marca como não tomada.

## 19. Questões ainda abertas

1. Quando `dagwell acp` for especificado, o Cognitive Router deveria ser parte dele, ou continuar
   uma função de biblioteca chamada de fora? (Nenhum handoff resolve isso.)
2. Quem é o dono real de `agent_ref`/persona — Hermes Bot/Profile, Buzz ACP identity, ou uma
   terceira estrutura ainda sem nome? A própria missão diz que essa decisão não foi tomada.
3. `dagwell acp` deveria se integrar ao kanban já existente no Hermes (ledger append-only, claims
   atômicos, conceitualmente parecido) ou o Dagwell continua como camada de governança separada,
   com o Hermes como só mais um binding? (Achado do levantamento do ecossistema, sem resposta.)
4. Vale gravar latência/disponibilidade histórica como **dado de configuração** (média móvel
   mantida fora do ledger, atualizada por um processo externo) sem que isso vire "scoring"
   disfarçado — e portanto sujeito à mesma trava do §14 (ADR de ativação antes de desenhar)?
5. O escalonamento custo-para-cima deveria ser sempre gated por humano (mais simples, mais
   alinhado a I10), ou existe um caso de uso legítimo para autorização antecipada ("pode escalar
   até custo X sem novo gate")? Isso é território do §13.12 (Runtime Policy Specification), ainda
   não escrito — não deveria ser resolvido por esta proposta.
6. Vale a pena nomear/desambiguar formalmente a homonímia "Dagwell" (motor vs. bot da colmeia,
   já desinstalado, vs. identificador de pasta em produção de vídeo) antes de introduzir
   "Cognitive Router" como termo novo, para não criar uma quarta acepção do mesmo nome?

---

## Sequência de implementação proposta (NÃO executar nesta sessão)

1. Corrigir o registry de operador em uso (`{model_id}` no binding `claude-cli`).
2. ADR curto formalizando os campos observacionais de custo em `transport` (etapa 2 da migração).
3. Implementar e testar os campos observacionais (`estimated_cost`, `reason_for_selection`) —
   sem `routing.py` ainda, só copiar `relative_cost` no momento da seleção existente.
4. ADR formalizando `capability_tags` (schema de registry e de node) + publicar
   `docs/registries/capability-tags.md`.
5. Implementar `adapters/routing.py` com filtro por tags, reaproveitando `selection.select()`
   sem alterá-lo; testes espelhando os de `test_adapters.py`.
6. Atualizar `schemas/graph.schema.json` para refletir o que `graph.py` já valida (dívida
   pré-existente) + os campos novos.
7. Documentar a convenção operacional de escalonamento humano-gated em `docs/USAGE.md`.
8. Só então, com um ADR de ativação dedicado: avaliar `agent_ref`/`agent_directory`, condicionado
   à decisão externa (ainda não tomada) sobre onde mora a identidade de agente.

**Fim. Nenhuma dessas etapas foi executada nesta sessão — nenhum código foi alterado, nenhum
commit, branch ou push foi feito no repositório `dagwell/`.**
