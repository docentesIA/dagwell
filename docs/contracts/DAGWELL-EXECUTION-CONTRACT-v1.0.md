# DAGWELL — Execution Contract · v1.0

> **Status: v1.0**
> **Stable**
>
> **Nota de promoção:** este documento é a promoção documental de
> `DAGWELL-EXECUTION-CONTRACT-v1.0-RC2.md` a **Execution Contract v1.0 (Stable)**,
> após o gate humano final ter revisado integralmente o RC2 e emitido o veredito
> **APPROVE — DAGWELL Execution Contract v1.0** (2026-08-23). O v1.0 é
> **normativamente idêntico ao RC2**: nenhuma decisão, regra, invariante ou questão
> aberta foi alterada — as únicas diferenças são estes metadados de status/promoção.
>
> Origem: `DAGWELL-EXECUTION-CONTRACT-v1.0-RC1.md`, que passou pelo gate humano final
> com **APPROVE WITH PATCHES** — um único patch material obrigatório, **P5 — Generic
> Evidence Identity** (ver "Changes from RC1" ao final). O RC2 aplicou exclusivamente
> o P5 e preservou P1–P4 e todas as demais decisões do RC1. Cadeia documental:
> `DAGWELL-CONTRATO-EXECUCAO-v002.md` passou por Gauntlet Loop documental (builder + 3
> críticos frescos + adversarial final check; 0 BLOCKER / 0 MAJOR / 0 MINOR pendentes)
> e foi **APROVADO COM 4 PATCHES** pelo gate humano arquitetural → RC1 aplicou P1–P4
> (ver "Changes from v002" ao final) → RC2 aplicou P5 → gate humano final **APPROVED**
> → **v1.0 (este documento)**. O documento é autocontido: não é preciso ler o v002, o
> RC1 nem o RC2 para entendê-lo. O histórico das emendas H1–H6/legado (v001 → v002)
> permanece registrado no próprio v002; artefatos de revisão em
> `reviews/dagwell-contrato-v002/`.

## Convenção de idioma (emenda H1)

**A prosa deste contrato é em português. Todos os identificadores CANÔNICOS do
protocolo — event types, field names, enum values, nomes de estados — são em inglês,
estáveis, e aparecem em inglês do início ao fim deste documento.**

- O ledger canônico grava **somente** os identificadores em inglês.
- Documentação, CLI e interfaces podem ser **localizadas na camada de exibição**
  (ex.: `approved`/`rejected` podem ser EXIBIDOS como "aprovado"/"reprovado").
- **Nunca** se traduz identificador internamente conforme locale: o que entra no
  ledger é sempre a forma canônica em inglês, independente do idioma da interface.

## Decisão fundadora

**O ledger grava eventos; estado é função pura (fold) dos eventos + declaração congelada
do grafo.** Nenhum estado é campo mutável. Eventos registram **fatos do mundo** (criação
da run, despacho, retorno, veredito, decisão humana, cancelamento, aterrissagem, extensão
de orçamento, pedido de interrupção); transições que são consequência lógica pura desses
fatos **não têm evento** — são recomputáveis a qualquer momento, logo nunca se perdem.
Isso resolve os quatro problemas da auditoria de uma vez e preserva "ledger append-only é
a memória" e "dado derivável não se declara".

A ordenação autoritativa do fold dentro de uma run é o campo `seq` do envelope de evento
(§9) — nunca apenas o timestamp. A identidade imutável da run é materializada no ledger
pelo **evento fundador `run_created`** (§2, §9).

Segunda decisão estrutural: **gate humano é uma verificação obrigatória da família
`human`** — não um mecanismo à parte. O humano entra na mesma máquina de verificações,
com o privilégio exclusivo de assinar.

---

## 1. Definição de run

Uma **run** é a execução de UMA versão congelada de UM grafo sobre UMA pauta congelada,
identificada por `run_id`, composta de **tentativas de nós** (`run_id`, `node_id`,
`attempt`), com todo acontecimento registrado como evento no ledger sob o seu `run_id`.

- A run nasce no **início de execução real explícito** — em oposição a dry-run —, cuja
  realização ATUAL na CLI é o `--go` (único comando que gasta — princípio preservado).
  Tudo sem esse ato é dry-run e **não cria run**. O nascimento é materializado no ledger
  pelo evento fundador **`run_created`** (§2): primeiro evento lógico da run e portador
  autoritativo da identidade congelada.
- No nascimento, a run **congela** `graph_version` e `input_hash` — registrados no
  `run_created`. Editar grafo ou pauta depois do `--go` não afeta a run em curso — afeta
  apenas runs futuras.
- A run **termina** em `completed` (todos os nós aceitos) ou `cancelled` (humano abortou).
  Ela **repousa** em `waiting_human` (gate pendente), `landed` (aterrissou com motivo
  registrado e WIP salvo) ou `stalled` (repouso residual aguardando observação, §3).
  **Não existe run `failed`: aterrissa, nunca morre.**
- Uma **tentativa** terminal é imutável. Retrabalho é sempre tentativa `k+1`, nunca
  ressurreição da anterior.
- A saída de um nó é, canonicamente, **output evidence** (§4): evidência verificável do
  trabalho produzido. O filesystem — arquivo local — é o tipo `artifact`: caso válido e
  primário no Maxwell V1, mas **não o único**; o contrato não exige que toda saída seja
  arquivo.
- Artefatos (evidência do tipo `artifact`) nascem em
  `runs/<operation>/<run_id>/<node_id>/t<k>/`. O layout V1 `runs/<operacao>/<no>/` é lido
  como legado, sem mover histórico. *Conflito de princípio reconhecido e decidido:*
  manter o caminho V1 literal faria duas runs sobrescreverem o mesmo diretório — o que
  quebra "ledger é a memória" no disco (overwrite é apagamento). Entre as duas leituras,
  o contrato preserva a essência do princípio (saída nasce dentro de `runs/<operation>/`,
  separação produto/dados) e refina a granularidade.

## 2. Campos mínimos da identidade da execução

| Campo | Definição | Quando nasce |
|---|---|---|
| `run_id` | identificador **opaco**, único, nunca reutilizado, nunca derivável de conteúdo (não é reproduzível — por definição) | no `--go` |
| `graph_id` | nome estável do grafo (hoje = operação; campo já separado para quando divergirem) | declaração |
| `graph_version` | **digest do conteúdo** da definição executável do grafo no instante do `--go`. Não é git commit, tag, branch nem apelido (`v001` não é versão) — o grafo é dado, armazenado fora do controle de versão do produto (no V1: `MAXWELL_DADOS`) | no `--go` |
| `input_hash` | **digest do conteúdo semântico canonicalizado da pauta efetiva.** O caminho/localização do arquivo **não participa** do hash: o mesmo conteúdo em `/home/reinaldo/a.md` e em `/home/alice/a.md` gera o MESMO `input_hash`. Identidade é conteúdo, nunca máquina. Congelado no `--go` | no `--go` |
| `input_ref` | registro de **origem/caminho** da pauta efetiva, para proveniência e auditoria. **Não participa da identidade**: mudar o caminho muda `input_ref`, nunca `input_hash` | no `--go` |
| `parent_run_id` | preenchido quando a run deriva de outra (re-run deliberado, grafo/pauta alterados); vazio na raiz | na criação da filha |
| estado | **sempre derivado** (fold); materializável em cache, jamais gravado como campo — nem no envelope de identidade | sempre computado |

(Emenda H2: o v001 definia `input_hash` como "caminho + digest de conteúdo". Corrigido —
o caminho contaminaria a identidade com um acidente da máquina. A canonicalização
concreta do conteúdo continua **questão aberta de runtime**, §13.5.)

### `run_created` — evento fundador e âncora autoritativa da identidade (P1)

**`run_created` é o evento fundador e a fonte autoritativa da identidade imutável da run
dentro do ledger.** Além do envelope mínimo comum a todo evento (§9 — `schema_version`,
`event_id`, `run_id`, `seq`, `event_type`, `occurred_at`), `run_created` DEVE carregar:

```
graph_id
graph_version
input_hash
input_ref
parent_run_id
```

```json
{
  "schema_version": "…",
  "event_id": "…",
  "run_id": "…",
  "seq": 1,
  "event_type": "run_created",
  "occurred_at": "2026-08-23T14:00:00-03:00",
  "graph_id": "pesquisa",
  "graph_version": "sha256:…",
  "input_hash": "sha256:…",
  "input_ref": "/home/reinaldo/…/pauta.md",
  "parent_run_id": null
}
```

(`seq: 1` é ilustrativo — o valor concreto do primeiro `seq` pertence ao encoding, §13.2.)

Regras:

- `run_created` é o **primeiro evento lógico** da run e possui o **primeiro `seq`
  válido** da run.
- **Somente um** `run_created` autoritativo pode existir por `run_id`. A unicidade é
  **precondição de escrita** sob a serialização do ledger (§9): tentativa de append de um
  segundo `run_created` para a mesma run é **erro duro de integridade**. Havendo violação
  histórica no ledger, o fold toma o **primeiro** por `seq` como autoritativo e marca os
  posteriores como anomalia de integridade (mesmo padrão da §9).
- Os campos congelados registrados no `run_created` — `graph_version`, `input_hash` e
  demais — **não podem ser substituídos** posteriormente: nem por evento, nem por
  configuração externa. **Nenhuma configuração externa posterior substitui
  silenciosamente a identidade já registrada.**
- `resume` compara os valores atuais com os valores registrados no `run_created` (§8).
- **Não existe segunda tabela/arquivo autoritativo de identidade**: o ledger continua a
  única fonte de verdade (I2); o `run_created` é o ponto, dentro dele, onde a identidade
  nasce.
- Run cujo ledger não contém `run_created` autoritativo não tem identidade validável:
  fica restrita a leitura diagnóstica; ações mutáveis são bloqueadas — mesmo regime da
  lacuna de `seq` não reconciliada (§9).

**Preservação do congelado (pré-condição do fold):** o snapshot da definição do grafo
endereçado por `graph_version` permanece **disponível enquanto a run existir**. O digest
congela a identidade; a preservação congela o conteúdo — sem ela, "fold recomputável a
qualquer momento" (decisão fundadora) seria promessa vazia (I24).

Requisitos do encoding do `run_id` (a escolha concreta é implementação, ver §13.2): único,
ordenável no tempo, gerável sob o lock existente. A CLI pode aceitar **prefixo** do
`run_id`, mas só com resolução única — prefixo ambíguo é erro duro, nunca identidade falsa.

### Migração e runs legadas (emenda de legado)

- Linhas legadas sem `run_id` recebem `run_id = legacy-<operation>` (uma run sintética por
  operação — honesta sobre a indistinguibilidade que de fato havia). Forma legada
  registrada: `legado-<operacao>` → forma canônica `legacy-<operation>`.
- `run_id = legacy-<operation>` é **exceção reconhecida** à regra de opacidade e
  não-derivabilidade do `run_id`: rótulo de agregação de histórico, não identidade de
  execução. O prefixo `legacy-` é **reservado** no espaço de `run_id` (requisito do
  encoding, §13.2).
- Toda run sintética criada para representar histórico indistinguível do Maxwell V1
  carrega explicitamente **`legacy_ambiguous: true`**.
- Se/como o importador materializa um `run_created` sintético para runs
  `legacy-<operation>` pertence à migração física do ledger legado (§13.6) — este
  contrato não o define; runs legadas ambíguas já estão fora do checkpoint operacional
  moderno.
- Regras das runs legadas ambíguas:
  - **Nunca** fingir que registros históricos indistinguíveis pertenciam a runs
    reconstruíveis — a run sintética é um rótulo de agregação, não uma reconstrução.
  - **Não participam** de checkpoint operacional moderno.
  - **Não entram** em aprendizado futuro como runs normais sem tratamento explícito.
  - Os dados brutos continuam **preservados** (campos `legacy_raw`, `legacy_origin`).

## 3. Máquina de estados da run

Estados de run são **projeções dos estados dos nós + eventos de run** — não há tabela de
transição por eventos com prioridades (é isso que gera o deadlock do último gate). A
projeção é definida **apenas sobre fatos materializados em eventos** — nenhum predicado
depende de política de runtime ("despachável" não existe na projeção: dependeria da
política de retry, que é runtime, não fold — I3) — e é avaliada com **precedência
explícita**, nesta ordem (o primeiro predicado verdadeiro decide):

```
1. cancelled      evento run_cancelled presente — terminal absorvente
2. completed      todos os nós do grafo completed (precedência sobre landed)
3. landed         run_landed presente ∧ run não-completed ∧ motivo NÃO removido por
                  evento posterior (budget_extended remove budget_exhausted;
                  human_retry remove human_rejection e retries_exhausted)
4. running        ≥1 tentativa em voo (node_dispatched sem node_returned nem
                  orphan_detected correspondente) ∨ ≥1 verificação em voo
                  (verification_requested de family ≠ human sem verdict_recorded
                  correspondente — correspondência pela mesma verification_attempt,
                  §6; a requisição de family human é o gate, predicado 5)
5. waiting_human  nada em voo ∧ ≥1 nó waiting_human
6. created        run_created presente ∧ nenhum node_dispatched
7. stalled        residual: nada em voo, não completa, sem gate pendente, sem
                  run_landed válido — repouso aguardando observação
```

- `stalled` é o repouso residual derivado (ex.: nós `failed`/`rejected` restantes antes
  do append de `run_landed`): `status`/`resume` sobre run stalled **materializam o
  desfecho** — `run_landed` com motivo, ou novos despachos se a política de retry do
  runtime permitir.
- `run_landed(reason)` tem motivo **fechado**: `reason ∈ {budget_exhausted,
  retries_exhausted, human_rejection}`. É emitido pelo runtime quando nada resta
  despachável **nem em voo**, a run não está completa e não há gate pendente — WIP salvo,
  nunca truncado. (Retorno tardio de nó que estava em voo cai na semântica de
  interrupção/órfão, §10.)
- `landed` é **retomável**: a ação humana que remove o motivo (evento
  `budget_extended {new_budget, actor}` para `budget_exhausted`; `human_retry` para
  `human_rejection` e para `retries_exhausted`) entra no ledger e, a partir dela, a
  projeção **deixa de dar `landed`** — o `resume` então recomputa normalmente (§8).
- `cancelled` é absorvente: retomar run cancelada é proibido; o caminho é run filha.
- Não há corrida "último nó + gate": quando o humano aprova a última verificação do último
  nó, o fold dá `completed` imediatamente — não existe evento de run a ser preterido.
- **Limite reconhecido (não escondido):** um runtime que morre não escreve a própria
  morte. Run com trabalho em voo — tentativa ou verificação — permanece `running` no fold
  até a observação. `status` exibe a idade do voo ("em voo há Δt sem evento") e o humano
  decide — sem timeout inventado; a evidência de órfão é produzida pelo `resume` ou por
  comando humano explícito (§10). Morte é **detectada**, não auto-reportada. A
  formalização completa das duas semânticas de interrupção — graceful interruption vs
  abrupt loss — está na §10.

## 4. Máquina de estados do nó

**7 estados no fold + 3 vistas derivadas.** `pending`, `ready` e `cancelled` não são
estados armazenáveis: os dois primeiros derivam da topologia + estados dos vizinhos; o
terceiro deriva do `run_cancelled` (nó não-terminal aparece `cancelled` na vista, sem
evento por nó).

```
(vista) pending    alguma dependência não-completed                       — sem evento
(vista) ready      todas as dependências completed                        — sem evento

ready          --node_dispatched (attempt k)-->                       running
running        --node_returned transporte bem-sucedido ∧ output evidence
                 exigida presente e válida (caso artifact: output_manifest
                 não-vazio c/ artifact_digest)-->                     executed
running        --node_returned transporte malsucedido | output evidence
                 exigida ausente/inválida-->                          failed
running        --orphan_detected (na observação)-->                   failed
executed       --verification_requested (não-humana)-->               verifying
executed       --sem verificação não-humana ∧ gate humano declarado--> waiting_human (via verification_requested family human)
executed       --declaração no_verification explícita-->              completed   (vácuo declarado; ver §7)
verifying      --verdict approved, restam obrigatórias-->             verifying
verifying      --todas não-humanas approved ∧ resta gate humano-->    waiting_human
verifying      --todas obrigatórias approved (sem gate)-->            completed
verifying      --qualquer obrigatória verdict rejected (family ≠ human)--> failed
verifying      --verification_status ∈ {error, timeout, cancelled} (verdict = null)--> verifying
                 (re-disparo do verificador como NOVA verification_attempt — §6 —,
                  contado e limitado pela política de retry do runtime; esgotada a
                  política → human_escalation → waiting_human)
waiting_human  --verdict approved (family human, última)-->           completed
waiting_human  --verdict approved (family human, via escalada) ∧
                 restam não-humanas obrigatórias-->                   verifying
waiting_human  --verdict rejected (family human)-->                   rejected
waiting_human  --human_retry (só quando o waiting_human veio de
                 human_escalation)-->                                 running (attempt k+1)
failed         --retry automático (política de retry do runtime permite)--> running (attempt k+1)
failed         --human_retry (política de retry esgotada)-->          running (attempt k+1)
rejected       --human_retry (comando humano explícito)-->            running (attempt k+1)

(vista) cancelled  run_cancelled ∧ nó não-terminal                    — sem evento por nó
```

### Output evidence (P4)

Nem todo nó produz arquivo local: o DAGWELL deverá orquestrar CLIs, agents, endpoints
OpenRouter/OpenAI-compatible, remote agents, ações MCP/tool, APIs e operações com efeito
colateral. A saída de um nó é, canonicamente, **`output_evidence`** — evidência
verificável de que o trabalho declarado foi produzido. Conjunto conceitual mínimo de
tipos (é um conjunto conceitual, **não** uma arquitetura de adapters):

- `artifact` — arquivo(s) local(is). Realização: **`output_manifest`** não-vazio com
  `artifact_digest`. É o caso do Maxwell V1 — continua válido e primário, mas não único.
- `structured_value` — valor estruturado retornado (ex.: JSON de resposta de API/tool).
- `remote_receipt` — comprovante verificável de trabalho executado remotamente.
- `side_effect_receipt` — comprovante/prova de efeito externo realizado.

Regras:

- **Cada nó declara**, na definição do grafo, o tipo de output evidence que produz. A
  omissão é **erro duro na validação do `--go`** — mesmo padrão fail-closed da declaração
  obrigatória de verificações (I5, §7).
- Retorno bem-sucedido do transporte **sem a evidência exigida não chega a `executed`**.
  O princípio central permanece e se estende: **retorno bem-sucedido sozinho NÃO
  significa `completed`** — e tampouco significa `executed`.
- **Toda `output_evidence` válida possui uma identidade canônica representável pelo
  campo `evidence_id`** (P5 — ver "Evidence identity" abaixo). Quando houver conteúdo
  digestível, registra-se o digest. Para evidência `artifact` o campo é
  `artifact_digest` — **caso especializado, preservado** — e ele pode participar da
  derivação/validação do `evidence_id`.
- Verificação e human gate vinculam-se ao **`evidence_id` da evidência do nó** — a
  amarração veredito↔`evidence_id` (§5, §6, §7) vale para a evidência do nó, seja ela
  arquivo ou não.
- **Efeito externo só é tratado como trabalho executado com receipt/proof adequado** —
  nunca pela mera ausência de erro no transporte.
- O filesystem continua um caso válido; o contrato **não exige** que toda saída seja
  arquivo.
- Os formatos concretos de cada tipo de evidência — inclusive o
  encoding/canonicalização do `evidence_id` por tipo — pertencem à futura Adapter/Output
  Evidence Specification (§13.17) — este contrato fixa só o conceito, a identidade
  canônica e o fail-closed.

### Evidence identity: `evidence_id` (P5)

**`evidence_id` identifica canonicamente a `output_evidence` produzida pela tentativa
corrente do nó, independentemente do tipo de evidência.** É o campo canônico genérico de
identidade de evidência do protocolo: o que P4 generalizou na SAÍDA (nem toda saída é
arquivo), P5 generaliza na IDENTIDADE (nem toda identidade de evidência é digest de
arquivo) — sem ele, a amarração veredito↔evidência (P2) só era exprimível para o tipo
`artifact`.

Regras:

- Toda `output_evidence` válida precisa possuir uma identidade canônica representável
  por `evidence_id`.
- `evidence_id` é **obrigatório** nos eventos `verification_requested` e
  `verdict_recorded` (§5, §6, §9).
- Todo veredito fica amarrado à identidade completa
  `(run_id, node_id, attempt, verification_id, verification_attempt, evidence_id)` (§6).
- **Veredito de uma evidência antiga jamais valida evidência nova** — mesma força da
  amarração por tentativa do produtor e por tentativa do verificador (§6, §7).
- Para evidência `artifact`, `artifact_digest` e `output_manifest` **continuam
  existindo** como campos especializados — nada do caso `artifact` é removido — e
  `artifact_digest` pode participar da derivação/validação do `evidence_id`.
- Para `structured_value`, `remote_receipt` e `side_effect_receipt`, a forma concreta de
  geração/canonicalização do `evidence_id` **NÃO é definida neste contrato** — pertence
  à futura Adapter/Output Evidence Specification (§13.17). Nada aqui é resolvido por
  invenção.
- `evidence_id` **não precisa ser um hash**: o contrato exige identidade
  **estável/verificável**; o encoding concreto pertence à especificação futura (§13.17).

O princípio do checkpoint permanece:

```
successful transport + required output evidence + required approvals = completed
```

Semântica dos dois terminais negativos — **partição por autor**:

- `failed` = a máquina não aceitou: transporte malsucedido, órfão detectado (crash
  aparece como órfão na observação — §10), output evidence exigida ausente/inválida
  (caso `artifact`: manifest ausente, vazio ou inválido), **ou verificação obrigatória
  com `verdict: rejected` por família não-humana**. Elegível a retentativa
  **automática** sob a política de retry do runtime (sempre com limite e orçamento
  explícito — §11, I13).
- `rejected` = **o humano reprovou**. Bloqueado para retentativa automática; só um evento
  humano explícito (`human_retry`) destrava. O sistema nunca decide sozinho reexecutar o
  que o humano recusou. (A distinção reprovação-de-mérito vs falha-técnica, que importa
  para agregação, vive nos campos `verdict`+`family` do ledger — o estado carrega só o
  que muda comportamento.)

Regras complementares:

- `executed ≠ completed` é o coração do contrato: retorno bem-sucedido do transporte
  **com a output evidence exigida** só chega a `executed`; sem a evidência exigida, não
  chega nem a `executed`.
- Ordem das verificações: **não-humanas primeiro**; a família `human` só é solicitada
  quando toda verificação não-humana obrigatória está `approved` (não se gasta atenção
  humana antes das máquinas). **Exceção única:** a escalada por esgotamento
  (`human_escalation`, abaixo) é o único caminho legítimo de solicitação humana com
  verificações não-humanas pendentes.
- Re-disparo de verificador cujo `verification_status` não é `completed` (ex.: `error`,
  `timeout`) abre uma **nova `verification_attempt`** (§6) da mesma `verification_id`
  sobre a mesma tentativa do produtor e a mesma evidência — tentativas do verificador
  nunca se confundem entre si nem com o `attempt` do produtor. O re-disparo é **contado
  e limitado pela política de retry do runtime** — nenhuma fórmula específica é parte
  deste contrato (emenda H6). `verification_status: cancelled` por interrupção graciosa
  (§10) **não conta** contra essa política. Esgotada a política, o runtime emite
  `human_escalation {reason}` com motivo **fechado** — `reason ∈ {verifier_error}`,
  versionado via `schema_version` (mesmo padrão do `run_landed`) — e o nó vai a
  `waiting_human`. As saídas do humano na escalada: **assumir a verificação** (veredito
  com `family: human`, referenciando a verificação substituída), **`human_retry`**, ou
  **cancelar a run**. A substituição pode criar consecutividade efetiva human→human
  (verificação substituída + gate declarado); a própria `human_escalation` registrada no
  ledger é a **exceção auditável** dessa consecutividade — o espírito do escape escrito
  (`r1_exception`), não uma preservação incondicional de R1.
- `orphan_detected` só tem efeito sobre tentativa em `running` no instante do fold; sobre
  tentativa em qualquer outro estado é evento **inerte** — o retorno registrado vence
  (evidência mais forte que ausência observada).
- **Verificação órfã**: verificação requisitada sem veredito e cujo trabalho **não está
  mais em andamento** (constatado na observação — `resume` ou comando humano explícito,
  §10) é evidenciada como `verdict_recorded {verification_status: error, verdict: null,
  reason: orphaned}` **sobre a `verification_attempt` específica que estava em voo** e
  cai na política de re-disparo acima (nova `verification_attempt`) — nenhum nó fica
  `verifying` para sempre por morte silenciosa.
- **`human_retry` tem um só significado**: é O comando humano explícito de abrir a
  tentativa `k+1` do produtor. Definido sobre: nó `rejected`; nó `failed` cuja política
  de retry se esgotou — inclusive quando o esgotamento aterrissou a run
  (`retries_exhausted`): nesse caso o mesmo evento remove o motivo do `landed` (§3); e
  `waiting_human` vindo de `human_escalation`. No gate humano **normal** (declarado no
  grafo, sem escalada) `human_retry` não se aplica — o caminho auditável é decidir
  (`rejected` com `reason`, e então `human_retry`). Re-armar o verificador **não** é
  significado de `human_retry` em lugar nenhum.
- `completed` é terminal absoluto. `failed`/`rejected` são terminais **da tentativa** e
  repousam no nó até retry ou aterrissagem da run.
- Tentativas: `(run_id, node_id, attempt)` é único; tentativa terminal nunca muda de estado.

## 5. Eventos de human gate

O gate é declarado no grafo como verificação obrigatória com `family: human`. Ele usa os
**mesmos event types** de toda verificação: `verification_requested` e `verdict_recorded`
também são emitidos pelo runtime para verificadores de máquina (§4, §6) — exclusivo do
gate é apenas o **privilégio de escrita** do veredito `family: human` (I8). Ambos
append-only, ambos com o envelope mínimo da §9 mais os campos de domínio (`node_id`,
`attempt`, `verification_attempt`, `evidence_id`, …). No gate:

1. **`verification_requested`** — escrito pelo **runtime** quando toda verificação
   não-humana obrigatória do nó está aprovada. O estado derivado vira `waiting_human`; a
   run estaciona nesse ramo.

   ```json
   {
     "schema_version": "…",
     "event_id": "…",
     "run_id": "…",
     "seq": 42,
     "event_type": "verification_requested",
     "occurred_at": "2026-08-23T14:07:00-03:00",
     "node_id": "sintese",
     "attempt": 2,
     "verification_id": "gate-humano-final",
     "verification_attempt": 1,
     "family": "human",
     "evidence_id": "…",
     "artifact_digest": "sha256:…"
   }
   ```

   (`evidence_id` é obrigatório para qualquer tipo de evidência; `artifact_digest`
   aparece neste exemplo porque a evidência do nó é do tipo `artifact` — é metadado
   especializado, presente apenas nesse caso.)

2. **`verdict_recorded`** — quando `family: human`, escrito **exclusivamente pelo
   comando humano dedicado**
   (ex.: `dagwell decide <run_id> <node_id> approved|rejected --reason "..."`; a CLI pode
   aceitar e exibir formas localizadas como "aprovado"/"reprovado", mas o ledger grava a
   forma canônica). `reason` é obrigatório na reprovação, opcional na aprovação. Agente
   nenhum tem esse verbo; adapter nenhum o emite; o runtime valida `actor` e precondições
   antes do append.

   ```json
   {
     "schema_version": "…",
     "event_id": "…",
     "run_id": "…",
     "seq": 57,
     "event_type": "verdict_recorded",
     "occurred_at": "2026-08-23T15:12:00-03:00",
     "node_id": "sintese",
     "attempt": 2,
     "verification_id": "gate-humano-final",
     "verification_attempt": 1,
     "family": "human",
     "actor": "reinaldo",
     "verification_status": "completed",
     "verdict": "rejected",
     "reason": "…",
     "evidence_id": "…",
     "artifact_digest": "sha256:…"
   }
   ```

Regras duras:

- A decisão só vale para a **tentativa corrente** e o **`evidence_id` corrente**:
  decisão sobre tentativa substituída ou evidência de identidade divergente é recusada
  por precondição.
  A decisão refere-se explicitamente a uma `verification_attempt` (§6): veredito de
  tentativa de verificação antiga não conclui tentativa nova. Decisão duplicada idêntica
  é no-op; decisão conflitante com uma já registrada é recusada — caso humano da
  precondição geral de escrita de veredito (§6), que vale para toda `family`.
  Reconsiderar uma **reprovação** tem verbo: `human_retry` (nova tentativa). Uma
  **aprovação é irrevogável dentro da run** (`completed` é terminal absoluto) —
  reconsiderá-la exige run filha.
- Precondições adicionais de escrita do veredito humano: a run não pode estar
  `cancelled` **nem conter lacuna de `seq` não reconciliada** (§9 — decisão humana é
  ação mutável e fica bloqueada até a reconciliação).
- **Ausência de decisão → `waiting_human` para sempre.** Silêncio não é aprovação. Não
  existe timeout que aprove, nem timeout que "suspenda": o único relógio é o humano,
  que pode decidir, cancelar a run ou deixá-la em repouso indefinido.
- O evento humano usa **o mesmo vocabulário e o mesmo tipo de evento** das demais
  verificações (§6) — o que muda é a `family` e o privilégio de escrita. Não há segundo
  jornal: decisões humanas entram no **mesmo ledger de eventos** de tudo o mais.
- Human verification usa somente `verdict ∈ {approved, rejected}` com
  `verification_status: completed` — **por construção**, não por validação a posteriori:
  o comando humano só sabe registrar decisões concluídas (§6).

## 6. Dois eixos: verification status e semantic verdict

O v001 dizia "exit code não é veredito" mas colocava `erro` DENTRO do conjunto de
vereditos — misturando o eixo de processo com o eixo semântico. O gate humano corrigiu a
contradição (emenda H5). São **dois eixos separados**, ambos presentes no evento
`verdict_recorded`:

**(a) `verification_status` — eixo de processo.** Conjunto fechado:

```
verification_status ∈ { completed, error, timeout, cancelled }
```

- `completed` — o verificador rodou até o fim e emitiu decisão.
- `error` — o verificador quebrou, perdeu insumo, ou não decidiu.
- `timeout` — o verificador estourou o tempo.
- `cancelled` — a verificação foi cancelada antes de concluir. Produtor legítimo: o
  runtime, durante interrupção graciosa (§10), ao cancelar verificador em voo.
  Cancelamento por interrupção **não conta** contra a política de re-disparo — não é
  falha do verificador (evita esgotar a política com interrupções repetidas).

**(b) `verdict` — eixo semântico. BINÁRIO:**

```
verdict ∈ { approved, rejected }        (null quando verification_status ≠ completed)
```

- `approved` — a verificação concluiu e aceitou o trabalho.
- `rejected` — a verificação concluiu e não aceitou.

**Regra de amarração dos eixos:** `verdict` é não-nulo **se e somente se**
`verification_status = completed`. Verificador que crashou, estourou timeout, perdeu
insumo ou não decidiu **NÃO produziu `rejected`**: produziu
`verification_status = error/timeout/…` com `verdict = null`. **"Não conseguiu verificar"
≠ "reprovou".** Falha técnica gera re-disparo do verificador — nova
`verification_attempt`, contada e limitada pela política de retry do runtime (§4) —,
nunca retentativa do produtor.

`family: human` só produz `verification_status: completed` com
`verdict ∈ {approved, rejected}` — o humano sempre conclui, e isso agora vale **por
construção** (o comando humano não tem como expressar outra coisa), não como validação
sobre um valor `error` que não existe mais no eixo semântico.

### Identidade de tentativa do verificador: `verification_attempt` (P2)

`attempt` identifica a tentativa do **PRODUTOR**. Mas o contrato permite re-disparo do
mesmo verificador após `error`, `timeout`, `cancelled` e verificação órfã — e essas
tentativas do **VERIFICADOR** precisam de identidade própria. Campo canônico:

```
verification_attempt
```

`verification_attempt` identifica a tentativa daquele `verification_id` sobre aquela
tentativa/evidência do produtor. A identidade completa de uma tentativa de verificação
passa a incluir, conceitualmente:

```
run_id
node_id
attempt
verification_id
verification_attempt
evidence_id
```

(P5: a componente de evidência da identidade é o campo genérico `evidence_id` — §4.
Para evidência `artifact`, `artifact_digest` permanece como campo especializado e pode
participar da derivação/validação do `evidence_id`; a identidade da verificação, porém,
nunca exige universalmente `artifact_digest`.)

Exemplo:

```
producer attempt: 2

verification_id: security-review
verification_attempt: 1
→ verification_status: timeout, verdict: null

verification_id: security-review
verification_attempt: 2
→ verification_status: completed, verdict: approved
```

Regras:

- `verification_attempt` inicia em valor definido pela futura especificação de
  encoding/runtime (§13.18) e é **monotônico** dentro da identidade
  `(run_id, node_id, attempt, verification_id)`.
- Cada `verification_requested` refere-se explicitamente a uma `verification_attempt`;
  cada `verdict_recorded` refere-se à **mesma** `verification_attempt` que conclui.
- `timeout`/`error`/`cancelled` de uma tentativa de verificação **nunca se confunde com
  a seguinte**; **veredito atrasado de tentativa antiga não pode concluir tentativa
  nova** — um `verdict_recorded` só é válido para a `verification_attempt` que
  referencia, e uma tentativa de verificação já encerrada (desfecho registrado) não
  aceita segundo desfecho: duplicata idêntica é no-op, desfecho conflitante é recusado
  na escrita; violação histórica → o primeiro por `seq` é autoritativo, posteriores são
  inertes e sinalizados (mesmo padrão da §9).
- A detecção de verificação órfã (§4, §10) opera sobre uma `verification_attempt`
  **específica** — a que estava em voo.
- Métricas futuras podem medir latência/custo/sucesso **por tentativa de verificação**.
- A retry policy concreta (quantos re-disparos, com que espaçamento) continua **FORA
  deste contrato** (I13, §13.12).

Por que UM vocabulário de veredito e não dois (máquina vs humano): a distinção
máquina/humano **não se perde — muda de coluna**. Todo evento de veredito carrega
`family ∈ {deterministic, model:<family>, human}` e `actor`, campos obrigatórios e
fechados **na forma** — o parâmetro `<family>` de `model:<family>` aguarda registro
canônico (namespace, abertura §13.15). Dois conjuntos de palavras para o mesmo eixo
semântico seria o problema 3 preservado com boas maneiras: toda consulta futura pagaria
a junção. Os dois eixos desta seção **não** são dois vocabulários para o mesmo eixo — são
eixos diferentes (processo vs mérito), cada um com um campo próprio e um conjunto fechado
próprio.

**Exit code não é veredito**: é fato de transporte, gravado em campo próprio (`exit_code`)
do evento `node_returned`. Nenhum componente traduz exit em veredito.

Campos de domínio do evento `verdict_recorded` (além do envelope §9): `node_id`,
`attempt`, `verification_id`, `verification_attempt`, `verification_status`, `verdict`,
`family`, `actor`, `evidence_id`, `artifact_digest?`, `reason?`. Validação dura na
escrita: valor fora dos conjuntos fechados é recusado antes de gastar. (`evidence_id`
amarra o veredito à identidade canônica da evidência de saída do nó — qualquer tipo de
`output_evidence`; `artifact_digest` é metadado especializado, presente quando a
evidência é do tipo `artifact`, e pode participar da derivação/validação do
`evidence_id`; o encoding/canonicalização do `evidence_id` por tipo pertence à
Adapter/Output Evidence Specification, §13.17.)

**Precondição de escrita de todo `verdict_recorded` (qualquer `family`):** para uma
`(verification_id, attempt, evidence_id)` que já tem veredito **autoritativo** com
`verification_status: completed` registrado — em qualquer `verification_attempt` —,
duplicata idêntica é **no-op** e veredito conflitante é **recusado**. Um verificador
original ainda vivo que conclui tarde, após timeout e re-disparo, não grava segundo
veredito: sua `verification_attempt` já foi encerrada pelo timeout, e desfecho tardio
sobre tentativa encerrada é recusado (regra P2 acima) — mesmo antes de a tentativa nova
concluir. Conduta do fold para violação histórica (ledger que já contenha o conflito): o
**primeiro** `verdict_recorded` com `verification_status: completed` por `seq` daquela
`(verification_id, attempt, evidence_id)` é o **autoritativo**; posteriores são
inertes e sinalizados como anomalia de integridade (mesmo padrão da §9).

### Mapeamento do legado

| Legado | Novo (canônico) | Status |
|---|---|---|
| `pass` | `verdict: approved` | direto |
| `fail` | `verdict: rejected` | direto |
| `aprovado` / `reprovado` | `verdict: approved` / `verdict: rejected` | tradução mecânica para a forma canônica em inglês (H1) |
| `pass-ok` | `verdict: approved` | **hipótese — não congelar**: auditar os componentes que os escrevem antes de rodar a migração |
| `pass-falhou` | `verdict: rejected` | idem |
| exit≠0 sem linha de veredito / timeout / ausência | `verification_status: error` (ou `timeout`) com `verdict: null` | **não é um terceiro valor de verdict** — é eixo de processo; o legado não distinguia "não concluiu" de "reprovou" |
| valor/contexto ambíguo | `unmapped` (camada de migração, **fora** dos campos canônicos) | nunca fabrica veredito, nunca habilita checkpoint |

O importador preserva `legacy_raw` e `legacy_origin` em campos próprios. A tabela acima
é **proposta condicionada à auditoria** de `pass-ok`/`pass-falhou` (§13.1) — está no
contrato como plano de migração com portão, não como fato consumado.

## 7. Regra de checkpoint

**Resposta explícita à pergunta E da spec: SIM — e por definição, não por procedimento.**

> `completed(node_id)` ⇔ na **tentativa corrente** `k`:
> (1) `node_returned` com **retorno bem-sucedido do transporte** (successful transport
> return; realização atual em processos locais: `exit_code = 0`) **∧** a **output
> evidence exigida pela declaração do nó, presente e válida**, com digest quando houver
> conteúdo digestível (realização para evidência `artifact`: `output_manifest`
> **não-vazio** com `artifact_digest`);
> (2) **∀** verificação obrigatória **declarada** no grafo: `verdict_recorded`
> **autoritativo** (§6) com `verification_status: completed` **∧** `verdict: approved`
> registrado **para a tentativa `k` e para o `evidence_id` corrente da evidência**;
> (3) se gate humano declarado: `verdict: approved` de `family: human`, idem amarrado
> a tentativa e `evidence_id`.
>
> Checkpoint da run = `{ node_id : estado_derivado_do_ledger(node_id) = completed }`.

Correções que fecham os furos provados pelo red-team (preservadas do v001):

- **Quantificadores amarrados**: não é `∃ despacho com retorno bem-sucedido` — é a
  tentativa corrente; não é `∀ verdict approved` solto — é veredito da tentativa corrente
  sobre a evidência corrente. Retorno bem-sucedido antigo, veredito órfão e aprovação de
  artefato velho não fecham a conjunção.
- **Evidência exigida, não presença de handoff**: "handoff existe" era predicado de
  presença; o predicado é de conteúdo/prova — transporte bem-sucedido + evidência
  ausente, vazia ou sem o receipt/proof exigido → `failed`, não `executed` (§4, output
  evidence). Para evidência `artifact` isso realiza-se como manifest não-vazio com
  digest; para os demais tipos, como a evidência declarada pelo nó. **Nenhuma regra de
  checkpoint exige universalmente arquivo local.**
- **Vácuo sem testemunha eliminado por declaração obrigatória**: todo nó **deve declarar**
  seu conjunto de verificações obrigatórias na definição do grafo; conjunto vazio só é
  aceito com `no_verification: <reason>` explícito. A omissão é **erro duro na validação
  do `--go`** (recusar antes de gastar) — o problema 4 não pode voltar como esquecimento
  de grafo: ou há verificações (fail-closed sobre elas) ou há renúncia assinada no grafo
  (vácuo legítimo, auditável, e o fold completa sem evento porque é consequência lógica
  de fatos declarados). O mesmo padrão fail-closed vale para a declaração do tipo de
  output evidence (§4, P4).
- Só `verdict: approved` fecha a conjunção: `verification_status ∈ {error, timeout,
  cancelled}` com `verdict: null` **nunca** conta como aprovação nem como reprovação —
  deixa a verificação pendente (re-disparo como nova `verification_attempt`, pela
  política de retry, §4).
- O checkpoint materializado é **cache** do fold: contém `run_id`, `graph_version`,
  `input_hash` e marca d'água do ledger; em divergência é descartado e recomputado. O
  despachante jamais acrescenta nó a uma lista de concluídos — quem "conclui" é o fold.
- Um `approved` isolado nunca completa: a conjunção é sobre **todo** o conjunto declarado,
  e nós sem verificador completam pelo vácuo **declarado**.
- Runs com `legacy_ambiguous: true` **não participam** de checkpoint operacional moderno
  (§2) — nenhum nó de run legada ambígua entra no conjunto `completed` de uma run moderna.

O problema 4 (retorno bem-sucedido + verificador reprovado + nó "concluído") torna-se
**inexprimível**: com `verdict: rejected` **autoritativo** (§6) registrado na tentativa
corrente, o fold dá `failed`/`rejected`, e não existe outro caminho de entrada no
checkpoint. A conjunção — e a inexprimibilidade — valem sobre vereditos **autoritativos**
(amarrados à `verification_attempt` e ao `evidence_id`, §6): veredito não-autoritativo
(conflito histórico, desfecho tardio de tentativa encerrada, evidência de identidade
divergente) é inerte e sinalizado, nunca computado.

## 8. Regra de resume

**Retomar É a mesma run.**

- `resume <run_id>` é permitido ⇔ `graph_version` e `input_hash` atuais conferem com os
  congelados **registrados no evento fundador `run_created`** (§2, P1) — é o
  `run_created` a referência autoritativa da comparação, nunca configuração externa.
  Divergência → **recusa dura** com instrução de criar run filha. (É esta validação que
  mata o cenário "checkpoint do pai contra pauta nova".)
- **`resume` é bloqueado enquanto houver lacuna de `seq` não reconciliada** (§9, P3):
  lacuna nunca concede capacidade nova — a run fica restrita a leitura diagnóstica até a
  reconciliação explícita (§13.16). O mesmo vale para run sem `run_created` autoritativo
  (§2).
- Herda **tudo**: checkpoint (nós `completed` são pulados), orçamento consumido (mesmo
  teto B — retomar não zera o freio), contadores de tentativa.
- É refeito: `failed` (nova tentativa, se a política de retry permite) e órfãos — nó
  despachado sem retorno cuja **não-continuidade do trabalho é constatada na observação**
  (§10) gera `orphan_detected` → tentativa `failed` → política normal; trabalho em voo
  ainda em andamento **não é orfanado** (a precondição de unicidade da §9 já impede
  re-despachar o mesmo triple). Verificação requisitada sem veredito e não mais em
  andamento (constatado na observação) é evidenciada como **verificação órfã** (§4, §10)
  — sobre a `verification_attempt` específica — e cai na política de re-disparo.
- Resume de run `landed` por `retries_exhausted` exige `human_retry` prévio (§3) — é ele
  que remove o motivo e devolve o nó esgotado à tentativa `k+1`.
- Não é destravado: `waiting_human` continua esperando; `rejected` continua bloqueado até
  `human_retry`. Resume não decide nada — só recomputa o fold e continua o que era
  continuável.
- `resume` é idempotente: sobre uma run sem trabalho pendente, não muda o fold nem duplica
  artefato.
- Resume de run `landed` exige a ação humana que remove o motivo (§3).

**Rodar de novo é run nova**: `run_id` novo, `parent_run_id` apontando para a antiga,
orçamento B novo, **nenhuma herança de checkpoint** (herança seletiva exigiria hash de
insumo por nó — aberta, §13.3). Herda-se apenas proveniência. Mudança incompatível de
grafo ou pauta **exige** run nova — nunca se retoma contra congelados divergentes.

Diferenciador operacional nítido: *retomar herda o consumo; rodar de novo zera*. Sobre o
"bypass do freio": criar run nova é ato humano deliberado via `--go` — o freio B existe
contra retentativa automática desenfreada, não contra o dono do sistema. O que o contrato
garante é **visibilidade**: a linhagem `parent_run_id` torna o gasto por linhagem e por
operação agregável no ledger. Limite reconhecido: o humano pode contornar o próprio
freio; nenhum contrato local impede o dono de gastar — ele impede a máquina de gastar
sozinha.

## 9. Envelope mínimo de todo evento (emenda H3)

Todo evento canônico do ledger carrega, no mínimo:

```
schema_version   versão do esquema do evento
event_id         identificador globalmente único do evento
run_id           run à qual o evento pertence — obrigatório em todo evento
seq              número de sequência, monotônico dentro da run
event_type       tipo do evento — enum versionado
occurred_at      timestamp observacional de quando o fato ocorreu
```

Regras:

- **`run_created` é o evento fundador da run (P1, §2):** primeiro evento lógico e
  detentor do primeiro `seq` válido da run; carrega, além do envelope, os campos de
  identidade congelada (`graph_id`, `graph_version`, `input_hash`, `input_ref`,
  `parent_run_id`). A unicidade de `run_created` por `run_id` é **precondição de
  escrita** sob o mecanismo de serialização do ledger: append de segundo `run_created`
  para a mesma run é **recusado** — erro duro de integridade. Violação histórica → o
  fold toma o **primeiro** por `seq` como autoritativo e sinaliza os posteriores como
  anomalia de integridade.
- `event_id` é **globalmente único**. É ele que torna **evento duplicado detectável**:
  o mesmo `event_id` aparecendo duas vezes é duplicata por definição. Conduta do fold:
  a **primeira** ocorrência por `seq` é a autoritativa; a duplicata é **ignorada** pelo
  fold e **sinalizada** como anomalia de integridade.
- `run_id` é obrigatório em todo evento; nenhuma decisão de estado usa `(operacao, no)`
  (forma V1) sem ele.
- `seq` é monotônico dentro da run. **A ordenação AUTORITATIVA dentro da run é `seq`,
  não timestamp.** O fold ordena por `seq`.
- Integridade de `seq`: **colisão ou regressão** de `seq` é erro duro de integridade — o
  fold **recusa computar** (fail-closed). **Lacuna** de `seq` tem dois regimes (P3):

  - **Leitura diagnóstica.** Uma run com lacuna de `seq` pode ser projetada por
    `status`/`inspect`/`audit`, para diagnóstico. Essa projeção é obrigatoriamente
    marcada com o rótulo canônico **`integrity: degraded`**. O rótulo é uma **VISTA
    derivada** — nunca um novo estado persistido da run (I3 preservado). O
    **checkpoint** continua fail-closed: lacuna nunca fabrica `completed`.
  - **Ação mutável.** Enquanto existir lacuna de `seq` NÃO reconciliada, é **bloqueada**
    qualquer ação que possa modificar a execução — no mínimo: `resume`, novo
    `node_dispatched`, retry automático, `human_retry`, decisão/veredito humano
    (`verdict_recorded` de `family: human`), `budget_extended`, `run_cancelled`
    adicional, e **qualquer comando que acrescente eventos operacionais** à run.
    Motivo: o evento perdido pode ser restritivo (ex.: `run_cancelled` perdido devolve
    retomabilidade aparente; `verdict_recorded` humano `rejected` perdido re-pergunta o
    gate) — computar "com o que há" ampliaria a capacidade aparente da run. Regra
    fundadora:

    > **An unresolved sequence gap may reduce observability, but MUST NEVER increase
    > operational authority.**

    A lacuna pode ser observada; nunca pode conceder capacidade nova.
  - **Reconciliação.** A liberação de ações mutáveis exige reconciliação de integridade
    por mecanismo futuro **explicitamente definido** em especificação de
    runtime/migração — não definido neste contrato (abertura §13.16). Toda lacuna
    continua obrigatoriamente **sinalizada** como anomalia de integridade — nunca
    tratada como benigna.
- `occurred_at` é observacional: relógio pode atrasar, adiantar ou divergir entre
  máquinas — **timestamp não resolve causalidade sozinho** e nunca é usado como critério
  de ordenação autoritativo.
- `event_type` é enum versionado (`schema_version` permite evoluir o esquema sem
  reinterpretar o histórico).
- O append e a atribuição de `seq` respeitam o **mecanismo de serialização do ledger**
  (hoje `flock`). Este contrato **contrata** a serialização — o mecanismo concreto é
  implementação de runtime.
- Unicidade de `(run_id, node_id, attempt)` é **precondição de escrita** sob o mesmo
  mecanismo de serialização: append de `node_dispatched` para triple já despachado e
  não-terminal é **recusado** — dois `resume` concorrentes não despacham a mesma
  tentativa duas vezes. Havendo violação histórica no ledger, o fold toma o **primeiro**
  evento por `seq` de cada fato e marca anomalia de integridade.

Campos de domínio (ex.: `node_id`, `attempt`, `verification_id`, `verification_attempt`,
`family`, `actor`, `verdict`, `verification_status`, `evidence_id`, `artifact_digest`,
`reason`, `exit_code`) acompanham o envelope conforme o `event_type` — ver exemplos nas
§2 e §5. `evidence_id` é obrigatório em `verification_requested` e `verdict_recorded`
(P5, §4); `artifact_digest` acompanha quando a evidência é do tipo `artifact`.

Event types canônicos deste contrato: `run_created`, `node_dispatched`, `node_returned`,
`verification_requested`, `verdict_recorded`, `orphan_detected`, `budget_extended`,
`human_escalation`, `human_retry`, `run_interrupt_requested`, `run_landed`,
`run_cancelled`.

## 10. Interrupção do orquestrador e perda abrupta (emenda H4)

Caso real que motivou esta seção: Ctrl+C no orquestrador matou o processo pai, os filhos
continuaram rodando, locks ficaram para trás, e a recuperação foi feita pelo ledger. O
contrato formaliza **duas semânticas DISTINTAS** — comportamento conceitual apenas;
gerenciamento de processos é runtime:

**(a) Graceful interruption (SIGINT/SIGTERM).** Quando o orquestrador recebe um sinal de
interrupção e ainda está vivo para reagir:

- não iniciar novos despachos, quando possível;
- registrar a **intenção** de interrupção como evento próprio: `run_interrupt_requested`;
- solicitar cancelamento/encerramento dos filhos em voo;
- permitir um grace period para término limpo;
- registrar o que **realmente terminou** (os `node_returned` que chegarem dentro do
  grace period entram no ledger normalmente);
- deixar a run **recuperável por `resume`** — interrupção não é término de run: não cria
  estado terminal novo; o fold continua dando o estado derivado, e `resume` retoma o que
  era continuável;
- `run_interrupt_requested` é **inerte para o fold de estado**: registro probatório da
  intenção — é ele que distingue interrupção graciosa de perda abrupta —, nunca gatilho
  de transição;
- verificador em voo cancelado pela interrupção registra `verification_status: cancelled`
  (§6) na `verification_attempt` em voo, sem consumo da política de re-disparo.

**(b) Abrupt loss (SIGKILL, queda de energia, crash, falha do host).** Nenhum processo
registra a própria morte:

- não existe evento de "morri" — o ledger simplesmente para de receber eventos daquele
  processo;
- `status` é **leitura pura**: detecta e **exibe** trabalho em voo sem conclusão — nunca
  produz evento. Sobre run com lacuna de `seq` não reconciliada, `status` exibe a
  projeção diagnóstica marcada `integrity: degraded` (§9) — leitura pura não destrava
  ação mutável. A evidência (`orphan_detected`) é produzida pelo **`resume`** ou por
  **comando humano explícito**, emitida **na observação**, nunca retroativamente
  fabricada — e só para tentativa/verificação em voo cuja **não-continuidade do trabalho
  é constatada** na observação, nunca por idade sozinha. Trabalho em voo ainda em
  andamento não é orfanado (a unicidade da §9 já impede re-despachar o mesmo triple); a
  constatação concreta de "não está mais em andamento" é runtime (abertura §13.4). O
  mesmo critério vale para **verificações órfãs**: requisitada sem veredito e não mais
  em andamento → `verdict_recorded {verification_status: error, verdict: null,
  reason: orphaned}` sobre a `verification_attempt` específica em voo (§4);
- **não existe timeout universal de órfão** — `status` exibe a idade do voo e o humano
  decide (número sem dado é precisão inventada; calibração do alerta é abertura §13.4).

**`run_interrupt_requested` (intenção registrada) e `orphan_detected` (evidência
observada) são fatos DIFERENTES e eventos DIFERENTES.** Uma run graciosamente
interrompida tem a intenção no ledger; uma run abruptamente perdida não tem nada — e é
exatamente essa ausência que a observação converte em evidência de órfão. Confundir os
dois seria fabricar história.

## 11. Invariantes (frases verificáveis)

- I1. Todo evento do ledger carrega `run_id`; nenhuma decisão de estado usa `(operacao, no)` (forma V1) sem ele.
- I2. O ledger é append-only e é a única fonte de verdade; nada se apaga ou reescreve; decisões humanas entram no mesmo jornal — não existe segundo arquivo autoritativo.
- I3. Estado nunca é gravado como campo (nem no envelope de identidade); é fold determinístico de grafo congelado + eventos, ordenado por `seq`. Eventos registram fatos do mundo; consequência lógica pura não tem evento e é recomputável. A projeção de estados usa apenas fatos materializados em eventos — nenhuma política de runtime participa do fold. O rótulo `integrity: degraded` (§9) é vista derivada, nunca estado persistido.
- I4. `completed` só é derivável com: retorno bem-sucedido do transporte (realização atual: `exit_code = 0`) + **output evidence exigida pela declaração do nó, presente e válida, com digest quando houver conteúdo digestível** (realização para evidência `artifact`: `output_manifest` não-vazio com `artifact_digest`) **na tentativa corrente**, e toda verificação obrigatória declarada com `verification_status: completed` ∧ `verdict: approved` **na tentativa corrente sobre o `evidence_id` corrente da evidência**.
- I5. Todo nó declara seu conjunto de verificações obrigatórias; vazio exige `no_verification: <reason>`; omissão é erro duro na validação do início de execução real (`--go` hoje).
- I6. Exit code nunca aparece no campo `verdict`.
- I7. `verdict ∈ {approved, rejected}` — binário, sem terceiro valor; `verdict` é não-nulo ⇔ `verification_status: completed`; `verification_status ∈ {completed, error, timeout, cancelled}` — conjunto fechado; `family` e `actor` obrigatórios; `family: human` ⇒ `verification_status: completed` ∧ `verdict ∈ {approved, rejected}`, por construção. Validação dura na escrita.
- I8. Só o comando humano dedicado grava veredito de `family: human`; reprovação exige `reason`; agente e adapter não têm esse verbo.
- I9. Ausência de decisão humana nunca destrava `waiting_human`; não existe timeout que aprove nem que suspenda.
- I10. Nó `rejected` nunca é re-despachado automaticamente; só `human_retry` explícito destrava. Reprovação humana nunca provoca retry automático. `human_retry` é o único verbo humano de nova tentativa do produtor — válido também sobre nó `failed` com política de retry esgotada (inclusive removendo o motivo `retries_exhausted` de run landed, §3) e sobre `waiting_human` vindo de escalada; nunca re-arma verificador.
- I11. `resume` mantém o `run_id` e exige `graph_version` e `input_hash` idênticos aos congelados registrados no `run_created`; divergência → recusa e run filha com `parent_run_id`.
- I12. Retomar herda orçamento consumido e contadores; run filha recebe B novo e não herda checkpoint.
- I13. Toda tentativa nova custa orçamento explícito; todo retry tem limite; todo retry gera novos eventos; a tentativa anterior permanece imutável; retry automático nunca ocorre após reprovação humana; o esgotamento da política leva a estado recuperável/escalada definido pelo runtime (`run_landed`, `human_escalation` — nunca truncamento); nenhuma política pode produzir gasto ilimitado silencioso. A fórmula concreta (geométrica, `max_attempts`, budget-based ou outra) **não é parte deste contrato** — pertence à futura Runtime Policy Specification (§13.12). O re-disparo de verificador é contado e limitado pela mesma política; `verification_status: cancelled` por interrupção graciosa não conta (§6, §10).
- I14. `(run_id, node_id, attempt)` é único — e a unicidade é precondição de escrita sob a serialização do ledger: despacho duplicado de triple não-terminal é recusado; violação histórica → o fold toma o primeiro evento por `seq` e marca anomalia. Tentativa terminal é imutável; vereditos não atravessam tentativas, `evidence_id`s nem `verification_attempt`s.
- I15. `pending`/`ready`/`cancelled`-de-nó são vistas derivadas — nunca gravadas.
- I16. Toda verificação obrigatória declara `family`; duas consecutivas da mesma família exigem `r1_exception: <reason>` (validação dura).
- I17. Run não tem estado `failed`; términos são `completed`/`cancelled`; repousos são `waiting_human`/`landed`/`stalled`; `run_landed` tem motivo fechado `{budget_exhausted, retries_exhausted, human_rejection}`.
- I18. Artefatos de runs e tentativas distintas nunca compartilham diretório — append-only vale também para o disco.
- I19. O checkpoint materializado é cache com marca d'água; em divergência, o ledger vence e o cache é recomputado.
- I20. Todo evento carrega o envelope mínimo (`schema_version`, `event_id`, `run_id`, `seq`, `event_type`, `occurred_at`); `event_id` é globalmente único; `seq` é monotônico e é a ordenação autoritativa dentro da run; timestamp nunca decide ordem; duplicata é detectável por `event_id` — a primeira ocorrência por `seq` é autoritativa, a duplicata é ignorada e sinalizada; colisão/regressão de `seq` → o fold recusa computar (fail-closed); lacuna de `seq` é obrigatoriamente sinalizada como anomalia, restringe a run a leitura diagnóstica marcada `integrity: degraded` e **bloqueia toda ação mutável** até reconciliação explícita (§9, I27) — o checkpoint permanece fail-closed e lacuna de evento restritivo nunca amplia a capacidade da run.
- I21. `input_hash` é função apenas do conteúdo semântico canonicalizado da entrada — o caminho/máquina não participa; proveniência vive em `input_ref` e não altera identidade.
- I22. Interrupção graciosa registra intenção (`run_interrupt_requested`) e deixa a run recuperável; perda abrupta não gera evento próprio — órfão é evidência produzida na observação (`orphan_detected`), pelo `resume` ou por comando humano explícito, mediante não-continuidade constatada; `status` é leitura pura e nunca produz evento; trabalho ainda em andamento não é orfanado; os dois fatos nunca se confundem e não existe timeout universal de órfão.
- I23. Run sintética legada carrega `legacy_ambiguous: true`; não participa de checkpoint operacional moderno; não entra em aprendizado futuro como run normal sem tratamento explícito; dados brutos preservados.
- I24. O snapshot da definição do grafo endereçado por `graph_version` permanece disponível enquanto a run existir — pré-condição de o fold ser recomputável a qualquer momento.
- I25. **(P1)** A identidade imutável da run (`graph_id`, `graph_version`, `input_hash`, `input_ref`, `parent_run_id`) nasce no evento fundador `run_created` — primeiro evento lógico e primeiro `seq` válido da run; existe **um só** `run_created` autoritativo por `run_id` (segundo append é recusado como erro duro; violação histórica → primeiro por `seq` + anomalia); nenhum evento posterior nem configuração externa substitui a identidade registrada; `resume` valida contra os valores do `run_created`; não existe segunda tabela/arquivo autoritativo de identidade — o ledger continua a única fonte de verdade.
- I26. **(P2)** Toda tentativa de verificação carrega `verification_attempt`, monotônico dentro de `(run_id, node_id, attempt, verification_id)`; cada `verification_requested` e cada `verdict_recorded` referem-se explicitamente à mesma `verification_attempt`; veredito atrasado de tentativa antiga nunca conclui tentativa nova; a detecção de verificação órfã opera sobre uma tentativa específica; `attempt` (produtor) e `verification_attempt` (verificador) nunca se confundem.
- I27. **(P3)** Lacuna de `seq` não reconciliada **nunca amplia autoridade operacional**: a run fica restrita a leitura diagnóstica (`status`/`inspect`/`audit`) marcada `integrity: degraded` — vista derivada, jamais persistida — e **toda ação mutável é bloqueada** (no mínimo: `resume`, novo `node_dispatched`, retry automático, `human_retry`, decisão/veredito humano, `budget_extended`, `run_cancelled` adicional, qualquer comando que acrescente eventos operacionais) até reconciliação por mecanismo explícito de especificação futura (§13.16). *An unresolved sequence gap may reduce observability, but MUST NEVER increase operational authority.*
- I28. **(P4)** Todo nó declara o tipo de `output_evidence` que produz (omissão = erro duro na validação do `--go`); retorno bem-sucedido do transporte sem a evidência exigida não chega a `executed` — muito menos a `completed`; quando há conteúdo digestível registra-se digest; efeito externo só conta como trabalho executado com receipt/proof adequado; o filesystem (`artifact`/`output_manifest`/`artifact_digest`) é caso especializado válido, nunca exigência universal; `successful transport + required output evidence + required approvals = completed`.
- I29. **(P5)** Toda `output_evidence` válida possui identidade canônica `evidence_id`, independente do tipo; `evidence_id` é obrigatório em `verification_requested` e `verdict_recorded`; todo veredito amarra-se a `(run_id, node_id, attempt, verification_id, verification_attempt, evidence_id)`; veredito de evidência antiga jamais valida evidência nova; nenhuma regra canônica de verificação exige universalmente `artifact_digest` — para evidência `artifact`, `artifact_digest` e `output_manifest` permanecem como campos especializados e `artifact_digest` pode participar da derivação/validação do `evidence_id`; `evidence_id` não precisa ser um hash — o contrato exige identidade estável/verificável; o encoding/canonicalização por tipo pertence à Adapter/Output Evidence Specification (§13.17).

## 12. Alternativas descartadas (com motivo)

| Alternativa | Origem | Motivo do descarte |
|---|---|---|
| `(operacao, no)` como identidade | V1 | colide entre rodadas; retomar e rodar de novo indistinguíveis (problema 1) |
| resume = sempre run filha | kimi | herança de checkpoint contra pauta possivelmente nova; B indefinido ou exigindo merge de cadeia; fragmenta auditoria; encarece o caso comum |
| resume in-place sem validação de congelados | — | aceitaria artefato de outra versão; I11 existe para isso |
| run `failed`/`rejected` | codex, muse | contradiz "aterrissa, nunca morre"; `landed(reason fechado)` cobre com continuação definida |
| tabela de transição da run por eventos com prioridade | muse | gera o deadlock do último gate; projeção dos nós não tem corrida |
| dois vocabulários de veredito (máquina/humano) | muse, agy | mesmo eixo, duas colunas agregáveis pela metade — problema 3 preservado; a distinção vive em `family`/`actor`. (Não confundir com os DOIS EIXOS da §6 — processo e mérito são eixos diferentes, não dois vocabulários do mesmo eixo) |
| **vocabulário canônico em português** | v001 (descartava "vocabulário em inglês" citando codex, agy, muse) | **REVERTIDO pelo gate humano (emenda H1).** O v001 argumentava que gate e ledger eram em português e que dois idiomas convivendo foram causa direta do problema 3. O gate humano reverteu: o DAGWELL será público e internacional; **um idioma canônico único — inglês — elimina exatamente o mesmo risco de dois vocabulários**; a localização (PT ou qualquer outra) vive só na camada de exibição e nunca entra no ledger. O que o problema 3 provou foi o custo de DOIS vocabulários para o mesmo eixo — não a superioridade do português |
| `EXIT_OK`/`EXIT_ERROR` como veredito | agy | exit é transporte; categoria que o checkpoint mistura de volta |
| **veredito ternário com `erro` (`{aprovado, reprovado, erro}`)** | v001 (que por sua vez descartava "veredito binário sem erro" de codex/muse) | **REVERTIDO pelo gate humano (emenda H5): o binário venceu.** O terceiro valor misturava o eixo de processo com o eixo semântico — "não conseguiu verificar" não é um veredito, é um status de execução do verificador. A distinção que o v001 queria preservar ("reprovou" ≠ "não concluiu") não se perde: muda de eixo — vive em `verification_status`, com `verdict = null`. O que o v001 temia (`erro→fail` gerando retentativa errada do produtor) continua impossível: falha técnica re-dispara o verificador, nunca o produtor |
| timeout que aprova ou suspende o gate | agy | silêncio não é aprovação; `SUSPENDED` era estado sem transições |
| estado gravado no envelope; `pending`/`ready` persistidos | agy | dado derivável não se declara; campo que o executor computa é campo que diverge |
| `cancelled` por nó (evento próprio) | — | derivável do `run_cancelled`; N eventos para 1 fato |
| checkpoint como arquivo fonte-de-verdade | V1 | segunda fonte de verdade; a memória é o ledger |
| fundir `executed`/`verifying` (cortar `verifying`) | kimi | morte silenciosa do verificador em voo — verificador assíncrono de outra família **existe hoje** |
| fundir `failed`/`rejected` | muse | retentativa automática de reprovação humana — bug de governança |
| retry automático de `rejected` | claude (original) | idem; corrigido: só `human_retry` destrava |
| `graph_version` = git commit/tag ou apelido | muse, agy | grafo é dado fora do git do produto (separação produto/dados); apelido não é versão |
| `run_id` derivado/reproduzível ou hash de `(grafo, input)` | muse | run_id nunca foi função de conteúdo; hash impede duas runs deliberadas da mesma entrada |
| caminho de arquivo dentro do `input_hash` | v001 §2 | **corrigido pela emenda H2**: caminho é acidente da máquina, não identidade — o mesmo conteúdo em máquinas/paths diferentes deve dar o mesmo `input_hash`; proveniência vive em `input_ref` |
| fórmula de retry congelada no contrato (série geométrica `b·r^(k−1)`) | v001 I13 | **removida pela emenda H6**: política concreta de retry é decisão de runtime (futura Runtime Policy Specification); o contrato fixa apenas os princípios — orçamento explícito, limite, novos eventos, imutabilidade da tentativa anterior, nunca-retry-após-reprovação-humana, esgotamento recuperável, nunca gasto ilimitado silencioso |
| timeout universal de órfão | — | número sem dado é precisão inventada; órfão é detectado na observação e o humano decide (emenda H4) |
| motivo `verification_impossible` em `run_landed` | v002 draft (pré-round 1) | removido no round 1 da revisão: motivo sem produtor definido — a condição de emissão do `run_landed` exige "sem gate pendente", mas o único cenário que o geraria repousa em `waiting_human`, e "aterrissar" não é verbo humano; cenário coberto por `waiting_human` + cancelamento + observação de verificação órfã |
| `rejected` tardio vence o conflito de vereditos (fail-closed retroativo) | v002 round 2 | permitiria a um verificador zumbi (concluindo após timeout + re-disparo) derrubar terminal imutável — retroatividade sobre `completed` viola I14; o autoritativo é o primeiro `verification_status: completed` por `seq` (§6). Com P2, o desfecho tardio sobre `verification_attempt` encerrada é adicionalmente recusado na escrita |
| sufixo curto (4 hex) como identidade na CLI | kimi | 16⁴ colide; substituído por prefixo com resolução única obrigatória |
| "teto SPRT" como nome do limite de tentativas | muse | precisão emprestada — SPRT é teste sequencial, não contador; o freio é o orçamento contado |
| `submission_key`, claims, leases, CAS nesta rodada | codex | contrato de sistema distribuído sobre runtime sequencial com `flock`; prematuro — registrado como consequência para paralelismo real |
| desenhar SSE/webhooks/MCP/A2A no contrato | agy | a spec proíbe desenhar superfícies; só consequências registradas |
| FSM única run+nó | muse (acatado) | estados-produto inalcançáveis; projeção resolve |
| gate humano como mecanismo à parte | — | como família de verificador entra de graça em R1, no vocabulário único e na mesma máquina |
| layout V1 compartilhado entre runs | claude, kimi, muse | duas runs sobrescrevem o mesmo diretório — checkpoint correto no fold e falso no filesystem |

## 13. Questões ainda abertas (não resolvidas por invenção)

Todas as aberturas do v002 continuam abertas — nenhum patch as resolveu por completo;
onde um patch tocou, a nota diz o quê. Os patches acrescentaram as aberturas 16–18.

1. **Semântica exata de `pass-ok`/`pass-falhou` no V1**: auditar os componentes que os
   escrevem **antes** de rodar a migração; a tabela de §6 é hipótese com portão, não fato.
2. **Encoding do `run_id`** (sequencial sob flock vs ULID vs UUID): implementação.
   Requisitos conceituais fixados em §2.
3. **Herança seletiva de checkpoint pai→filha**: exigiria hash de insumo **por nó**; sem
   isso, herdar é chute. Critério de reativação: quando houver hash por nó.
4. **Critério de sinalização de órfão no `status`**: hoje exibe idade do voo e o humano
   decide; calibrar limiar de alerta com as latências já medidas no ledger (dispersão de
   26× entre harnesses) — número sem dado é precisão inventada. (A emenda H4 formalizou a
   SEMÂNTICA de órfão vs interrupção, mas manteve esta calibração aberta — e proibiu
   timeout universal.) A constatação concreta de "trabalho não mais em andamento", que
   habilita o `resume`/comando humano a produzir a evidência (§10), também é runtime e
   vive nesta abertura.
5. **Canonicalização exata** de `graph_version` e `input_hash` (algoritmo, quais arquivos
   entram no digest, como se canonicaliza o conteúdo semântico): especificação de runtime.
   (A emenda H2 fixou O QUE o `input_hash` identifica — conteúdo, nunca caminho — mas a
   canonicalização concreta continua aberta.)
6. **Migração física do ledger legado** (script que aplica §6 ao histórico): outra rodada,
   condicionada à abertura 1. Inclui decidir se/como o importador materializa
   `run_created` sintético para runs `legacy-<operation>` (P1, §2).
7. **Concorrência real** (claims/leases, múltiplos writers): consequência registrada — o
   contrato de eventos sobrevive; o mecanismo pertence à rodada de paralelismo.
8. **Autenticação do `actor` humano** quando houver interface remota: hoje o autor é o
   usuário local sob controle do processo; identidade forte fica aberta.
9. **`cancelled` no denominador** das taxas de erro (agregação R2): decidir com dados.
10. **Verificadores compostos** (ex.: `verificar.py` + `gitleaks` no mesmo portão): uma
    família ou tupla — decidir quando houver segundo caso real.
11. **Nós opcionais**: o V1 não os tem; `run.completed = todos os nós` até que exista
    caso de uso.
12. **Runtime Policy Specification** (decorrente da emenda H6): a política concreta
    de retry — fórmula (geométrica, `max_attempts`, budget-based ou outra), parâmetros e
    calibração — sai do contrato fundador e ganha especificação própria futura. O
    contrato fixa só os princípios (I13).
13. **Mecanismo concreto de detecção de duplicata e atribuição de `seq`** (decorrente da
    emenda H3): o contrato exige detectabilidade e serialização (hoje `flock`); índice,
    verificação no fold ou na escrita é runtime.
14. **Duração e mecânica do grace period** da interrupção graciosa (decorrente da emenda
    H4): o contrato fixa a semântica; sinalização de filhos, tempo de espera e limpeza
    de locks são runtime.
15. **Canonicalização/namespace do parâmetro `<family>`** em `model:<family>` (round 1):
    sem registro canônico, dois adapters podem rotular o mesmo modelo com nomes
    diferentes, enfraquecendo R1 em silêncio. `family` é fechado na forma; o parâmetro
    aguarda registro.
16. **Sequence-gap reconciliation mechanism** (nova, P3): o mecanismo explícito de
    reconciliação de integridade que libera ações mutáveis após lacuna de `seq` —
    inspeção assistida, atestado humano, reparo auditável de ledger, ou outro — pertence
    à futura especificação de runtime/migração. Este contrato fixa apenas o bloqueio
    fail-closed, o rótulo diagnóstico `integrity: degraded` e a exigência de que a
    liberação seja explícita — o mecanismo em si NÃO está definido aqui.
17. **Adapter/Output Evidence Specification** (nova, P4; ampliada por P5): formatos
    concretos de cada tipo de `output_evidence` (`artifact`, `structured_value`,
    `remote_receipt`, `side_effect_receipt`), **`evidence_id`
    encoding/canonicalization per output evidence type** — valor concreto, algoritmo de
    canonicalização por tipo e, para `artifact`, como `artifact_digest` participa da
    derivação/validação do `evidence_id` —, validação de receipts/proofs de efeitos
    externos e o mapeamento por adapter (CLIs, OpenRouter/OpenAI-compatible, remote
    agents, MCP/A2A, APIs). Este contrato fixa só o conceito, a identidade canônica
    (`evidence_id`, P5), a declaração obrigatória por nó e o fail-closed.
18. **Valor inicial e encoding de `verification_attempt`** (nova, P2): o contrato fixa
    semântica, referência explícita por evento e monotonicidade dentro de
    `(run_id, node_id, attempt, verification_id)`; o valor inicial e a representação
    concreta pertencem à especificação de encoding/runtime.

## Consequências registradas para superfícies futuras (sem desenhá-las)

- **Paralelismo real**: eventos append-only sob o mecanismo de serialização existente
  toleram despacho concorrente; `ready` é computável por qualquer worker; claims/leases
  entram aí. O envelope (§9) — `event_id` único + `seq` autoritativo — já é o alicerce.
- **Adapters/OpenRouter/OpenAI-compatible/remote agents**: I6 isola o transporte —
  adapter emite eventos de retorno e a output evidence apropriada (`structured_value`,
  `remote_receipt`, `side_effect_receipt`), jamais vereditos. Os formatos concretos
  pertencem à Adapter/Output Evidence Specification (§13.17) — o contrato já não exige
  arquivo local, então nenhuma dessas superfícies precisará dobrar a regra de checkpoint.
- **MCP/A2A**: veredito com `family`/`actor` abre espaço para identidade/assinatura sem
  mudar o contrato; eventos nomeados tornam o fluxo observável de fora; ações de
  tool/efeito externo entram como `side_effect_receipt`/`remote_receipt` (§4).
- **Aprendizado (camada 3)**: veredito fechado + família por evento é o rótulo agregável
  de que o critério de reativação precisa; `verification_attempt` (P2) permite medir
  latência/custo/sucesso por tentativa de verificação. Runs `legacy_ambiguous: true` só
  entram com tratamento explícito (I23).
- **Internacionalização**: com o protocolo canônico em inglês (H1), localizar CLI e
  documentação é trabalho de camada de exibição — nenhuma mudança de contrato.

## Ordem de implementação incremental sobre o V1 (sem código)

1. Envelope mínimo de evento (§9) + evento fundador `run_created` (§2) + coluna `run_id`
   no ledger + runs sintéticas `legacy-<operation>` com `legacy_ambiguous: true`.
2. Vocabulário canônico em inglês com validação dura na escrita — dois eixos
   `verification_status`/`verdict`, com `verification_attempt` (migração após auditoria
   de §13.1).
3. Declaração obrigatória de verificações e de tipo de output evidence por nó
   (validação do `--go`).
4. Checkpoint recomputado do fold, amarrado a tentativa+evidência (o arquivo atual vira
   cache).
5. Comando humano de decisão + `human_retry` gravando eventos de `family: human`.
6. `resume` com validação de congelados contra o `run_created`, detecção de órfãos e
   bloqueio por lacuna de `seq`; semântica de interrupção (§10); layout por
   `run_id`/tentativa.

Cada passo é útil sozinho e nenhum exige reescrever o runtime que já funciona.

---

## Changes from v002 (aplicados no RC1 — registro histórico)

Quatro patches vinculantes do gate humano arquitetural — nada mais foi alterado:

- **P1 — `run_created` anchors immutable run identity.** `run_created` é definido como o
  evento fundador e a fonte autoritativa da identidade imutável da run dentro do ledger:
  primeiro evento lógico, primeiro `seq` válido, portador obrigatório de `graph_id`,
  `graph_version`, `input_hash`, `input_ref`, `parent_run_id`; um só autoritativo por
  `run_id` (segundo append = erro duro); identidade nunca substituível por evento
  posterior nem configuração externa; `resume` valida contra ele. Sem segunda
  tabela/arquivo autoritativo — o ledger continua a única fonte de verdade. (§1, §2, §8,
  §9; novo I25; exemplo de evento em §2.)
- **P2 — `verification_attempt` added.** Novo campo canônico distinguindo a tentativa do
  VERIFICADOR (`verification_attempt`) da tentativa do PRODUTOR (`attempt`). Identidade
  completa da tentativa de verificação: `(run_id, node_id, attempt, verification_id,
  verification_attempt, artifact_digest)` *(componente de evidência posteriormente
  generalizada por P5: `artifact_digest` → `evidence_id`; ver "Changes from RC1")*.
  Monotônico; referenciado explicitamente por
  `verification_requested` e `verdict_recorded`; veredito atrasado de tentativa antiga
  não conclui tentativa nova; órfã detectada por tentativa específica; métricas por
  tentativa habilitadas; retry policy continua fora do contrato. (§3, §4, §5, §6, §7,
  §9, §10; novo I26; I14 estendido; exemplos atualizados.)
- **P3 — unresolved seq gaps block mutable operations.** Lacuna de `seq` não
  reconciliada passa a ter dois regimes: leitura diagnóstica (`status`/`inspect`/`audit`)
  marcada `integrity: degraded` (vista derivada, nunca estado persistido) e **bloqueio
  de toda ação mutável** — `resume`, novo despacho, retries, `human_retry`,
  decisão/veredito humano, `budget_extended`, `run_cancelled` adicional, qualquer evento
  operacional — até reconciliação por mecanismo futuro explícito. Regra fundadora: *an
  unresolved sequence gap may reduce observability, but MUST NEVER increase operational
  authority.* (§5, §8, §9, §10; I20 endurecido; novo I27; nova abertura §13.16.)
- **P4 — filesystem manifest generalized to output evidence.** O conceito de saída de nó
  é generalizado de "manifest não-vazio com arquivo local" para **`output_evidence`**
  (tipos conceituais mínimos: `artifact`, `structured_value`, `remote_receipt`,
  `side_effect_receipt`), com declaração obrigatória por nó (fail-closed no `--go`),
  digest quando digestível e receipt/proof para efeitos externos. `artifact_digest` e
  `output_manifest` preservados como caso especializado do tipo `artifact`. O princípio
  central permanece: retorno bem-sucedido sozinho NÃO significa `completed` — nem
  `executed`; `successful transport + required output evidence + required approvals =
  completed`. (§1, §4, §5, §6, §7; I4 generalizado; novo I28; consequências futuras e
  nova abertura §13.17.)

Tudo o mais — ledger append-only orientado a eventos; estado como fold determinístico;
`run_id` opaco; resume = mesma run; nova execução = nova run; tentativa identificada por
`(run_id, node_id, attempt)`; `executed ≠ completed`; checkpoint derivado do ledger e
amarrado a tentativa+evidência; human gate no mesmo ledger com `approved`/`rejected`;
dois eixos `verification_status` × `verdict`; reprovação humana sem retry automático;
retry policy fora do contrato; protocolo canônico em inglês; `legacy_ambiguous`;
artefatos separados por run e tentativa; produto separado dos dados; dry-run separado de
execução real; nenhum estado derivável como segunda fonte autoritativa — permanece como
no v002.

---

## Changes from RC1

Um único patch material vinculante do gate humano final — nada mais foi alterado:

- **P5 — Generic Evidence Identity.** Novo campo canônico genérico **`evidence_id`**:
  identifica canonicamente a `output_evidence` produzida pela tentativa corrente do nó,
  independentemente do tipo de evidência. Resolve a incompatibilidade P2×P4 do RC1: a
  identidade da tentativa de verificação e a precondição de autoritatividade de
  `verdict_recorded` usavam `artifact_digest` universalmente, o que só era exprimível
  para evidências do tipo `artifact`. A identidade conceitual completa da tentativa de
  verificação passa a ser `(run_id, node_id, attempt, verification_id,
  verification_attempt, evidence_id)`; `evidence_id` é obrigatório em
  `verification_requested` e `verdict_recorded`; todo veredito amarra-se a ele; veredito
  de evidência antiga jamais valida evidência nova; a chave de conflito/autoritatividade
  de `verdict_recorded` passa de `(verification_id, attempt, artifact_digest)` para
  `(verification_id, attempt, evidence_id)`. Para evidência `artifact`,
  `artifact_digest` e `output_manifest` são **preservados** como campos especializados e
  `artifact_digest` pode participar da derivação/validação do `evidence_id`. Para
  `structured_value`, `remote_receipt` e `side_effect_receipt`, a
  geração/canonicalização concreta do `evidence_id` NÃO é definida aqui — pertence à
  Adapter/Output Evidence Specification (§13.17, ampliada para incluir explicitamente
  *evidence_id encoding/canonicalization per output evidence type*). `evidence_id` não
  precisa ser um hash: o contrato exige identidade estável/verificável; o encoding
  concreto é da especificação futura. A lógica de checkpoint permanece:
  `successful transport + required output evidence + required approvals = completed`.
  (§4, §5, §6, §7, §9; I4 e I14 atualizados; novo I29; exemplos JSON atualizados;
  abertura §13.17 ampliada.)

Tudo o mais — P1 (`run_created` como âncora da identidade imutável da run), P2
(`verification_attempt`), P3 (lacuna de `seq` bloqueia ações mutáveis), P4
(`output_evidence` generalizada) e todas as demais decisões do RC1 — permanece como no
RC1.
