# DAGWELL — Manual de uso

Como conduzir o DAGWELL depois de instalar. Para saber o que o projeto *é*, leia o
[README](../README.pt-BR.md); para o que ele *garante*, quem governa é o
[Contrato de Execução](contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md).

> Documento de exibição. Os identificadores canônicos (nomes de evento, campo,
> estado) são em inglês e assim entram no ledger — nunca traduzidos.

## 1. Instalação

Python 3.11+. Sem dependências de runtime.

```bash
pipx install git+https://github.com/docentesIA/dagwell.git
dagwell --version
```

O `pipx` põe o `dagwell` no PATH e não há virtualenv para ativar. Se quiser também a
suíte de testes e o contrato, clone:

```bash
git clone https://github.com/docentesIA/dagwell.git && cd dagwell
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python3 tools/run_tests.py
```

Com um clone, `.venv/bin/dagwell` funciona sem ativar nada.

## 2. O modelo mental

**Você faz o trabalho. O DAGWELL governa.**

Ainda não há adapters: o DAGWELL nunca sobe processo, nunca chama provedor, nunca
gasta nada. Você executa cada passo do jeito que já executa — um script, uma CLI, um
agente, uma pessoa — e o DAGWELL decide se aquilo podia começar, registra o que
voltou, e recusa dar por concluído sem a evidência e as aprovações que o grafo exige.

A regra que vale internalizar:

```
executed != completed
completed = transporte bem-sucedido + evidência de saída exigida + aprovações exigidas
```

Um passo que sai com código 0 e produz a saída está `executed`. **Não** está pronto.
Ele vira `completed` só depois que as verificações declaradas concluírem.

Estado nunca é armazenado. Toda projeção que você vê é recalculada a partir dos eventos.

## 3. Um minuto de demonstração

```bash
dagwell demo
```

Roda o ciclo inteiro numa pasta descartável e narra cada passo. Nada é escrito fora
da pasta temporária e nada é gasto.

## 4. Um run de verdade, passo a passo

### 4.1 Declare o grafo

O grafo é um arquivo JSON seu. Cada nó declara suas dependências, o **tipo de
evidência** que vai produzir e as **verificações** por que precisa passar.

```json
{
  "graph_id": "release",
  "nodes": [
    {"id": "build", "deps": [], "output_evidence": "artifact",
     "verifications": [{"verification_id": "tests", "family": "deterministic"}]},
    {"id": "ship", "deps": ["build"], "output_evidence": "artifact",
     "verifications": [{"verification_id": "signoff", "family": "human"}]}
  ]
}
```

O que o carregador exige antes que qualquer coisa rode:

- Todo nó declara `output_evidence`: `artifact`, `structured_value`,
  `remote_receipt` ou `side_effect_receipt`. Omitir é erro duro.
- Todo nó declara verificações, **ou** dispensa com um
  `"no_verification": "<motivo>"` explícito. A dispensa só existe para `artifact`,
  o único tipo que o motor sabe validar sozinho (ver ADR-0008).
- Duas verificações consecutivas da mesma família exigem
  `"r1_exception": "<motivo>"` — verificador da própria família do produtor vale
  pouco, e dizer isso em voz alta é o preço de fazer assim mesmo.
- Ids de nó únicos, dependências existentes, grafo acíclico.

### 4.2 Inicie o run

```bash
echo "cortar release 1.4" > input.txt
RUN=$(dagwell start --ledger run.jsonl --graph graph.json --input input.txt)
echo $RUN
```

O `start` valida o grafo fail-closed **antes** de criar qualquer coisa, congela o
grafo por hash de conteúdo e imprime o id do run. A identidade vem do conteúdo, nunca
de caminhos — mover os arquivos depois não muda o run.

### 4.3 Veja o que é despachável

```bash
dagwell ready --ledger run.jsonl --graph graph.json --run $RUN
# build (next attempt 1)
```

O `ship` não aparece: a dependência dele ainda não foi satisfeita.

### 4.4 Entregue o trabalho — e então faça

```bash
dagwell dispatch --ledger run.jsonl --graph graph.json --run $RUN --node build
```

Isso registra que `build` foi entregue. **Não roda nada.** Agora vá executar —
`make build`, um agente, o que quer que o nó signifique no seu mundo.

### 4.5 Registre o que voltou

```bash
dagwell return --ledger run.jsonl --graph graph.json --run $RUN \
  --node build --attempt 1 --exit-code 0 \
  --evidence '{"type":"artifact","evidence_id":"sha256:...","output_manifest":[{"path":"app.bin","artifact_digest":"sha256:...","size_bytes":4096}]}'
```

O `--evidence` aceita JSON inline ou `@caminho/para/evidencia.json`. O
`evidence_id` não é escolhido — é o sha256 do JSON canônico do manifest
(Adapter/Output Evidence Spec §4; `dagwell.canonical.json_digest` o calcula, como
mostra o `examples/runner.sh`). Evidência
malformada é recusada **antes** de chegar ao ledger; um `evidence_id` escolhido à
mão conta como malformado; evidência de tipo diferente do
que o nó declarou também.

Confira o estado:

```bash
dagwell status --ledger run.jsonl --graph graph.json --run $RUN
# build: executed
```

Código de saída 0, evidência presente — e ainda não concluído. É esse o ponto.

Se o passo **falhou**, registre isso honestamente: `--exit-code 1`, sem
`--evidence`. Evidência ausente é legal e faz a tentativa terminar como `failed`.
O que é recusado é mentir, não falhar.

### 4.6 Verifique

```bash
dagwell request-verification --ledger run.jsonl --graph graph.json --run $RUN \
  --node build --verification tests

# rode seus testes e então registre o resultado
dagwell verdict --ledger run.jsonl --graph graph.json --run $RUN \
  --node build --verification tests --status completed --verdict approved
```

São dois eixos, e não são a mesma pergunta:

- `--status` é o que aconteceu com o **processo de verificação**: `completed`,
  `error`, `timeout`, `cancelled`.
- `--verdict` é a **resposta**: `approved` ou `rejected`. Só existe quando o status
  é `completed`.

"Não consegui verificar" não é "reprovado". Um verificador que quebrou produz
`--status error` e nenhum veredito, e o nó não avança por causa disso.

As verificações seguem a ordem que o contrato exige: famílias de máquina primeiro, o
gate humano por último. Pedir fora de ordem é recusado.

### 4.7 O gate humano

```bash
dagwell decide --ledger run.jsonl --graph graph.json --run $RUN \
  --node ship approved --actor rey
```

O `decide` é o **único** caminho pelo qual um veredito humano entra no ledger. A
superfície de máquina (`verdict`) recusa `family: human`, e a escrita crua também.
Uma reprovação exige motivo:

```bash
dagwell decide ... --node ship rejected --reason "assinatura ausente"
```

Depois de uma reprovação o nó não roda de novo sozinho. Reabrir é ato humano:

```bash
dagwell human-retry --ledger run.jsonl --graph graph.json --run $RUN --node ship --actor rey
```

Isso abre a tentativa *k+1*. Tentativas anteriores nunca são reescritas — ficam no
ledger como o que aconteceu.

### 4.8 Encerrando o run

Um run termina de três formas:

```bash
# tudo concluído: nada a fazer, a projeção diz completed

# resta trabalho mas você vai parar: aterrisse (o WIP é salvo, nunca truncado)
dagwell land --ledger run.jsonl --graph graph.json --run $RUN --reason budget_exhausted

# abandonar (terminal absorvente; run concluído nunca vira cancelado)
dagwell cancel --ledger run.jsonl --graph graph.json --run $RUN --actor rey
```

O `land` recusa enquanto houver trabalho despachável, trabalho em voo, gate pendente
ou nó que ainda deve sua verificação. Os motivos `human_rejection` e
`retries_exhausted` precisam ter lastro no que a projeção realmente mostra;
`budget_exhausted` é asserido por você, porque o motor não tem modelo de orçamento
(a §13.12 está aberta).

### 4.9 Depois de uma interrupção

```bash
dagwell resume --ledger run.jsonl --graph graph.json --run $RUN --input input.txt
```

O resume continua **o mesmo run**, validando que grafo e entrada ainda batem com a
identidade congelada no `start`. Um grafo diferente é recusado, não aceito em
silêncio. O snapshot do grafo congelado fica ao lado do ledger, então o resume
funciona mesmo se você perdeu o arquivo original.

## 5. Amarrando aos CLIs de verdade

Esta é a pergunta que todo mundo faz depois de instalar: **como o DAGWELL chama o
claude, o codex, o grok?**

Ele não chama. E não é omissão deste manual — é o estado do projeto. Adapters são o
marco seguinte. O que existe hoje é o modelo inverso, e ele já é útil:

> **Você chama o CLI. O DAGWELL decide se podia, registra o que voltou, e recusa dar
> por concluído o que não tem prova.**

É o mesmo desenho de um `despachar.sh`: quem executa é o seu script; quem governa é o
ledger. A diferença é que aqui a governança é o produto, não um efeito colateral.

### 5.1 Declare o comando no próprio grafo

O motor **ignora campos que não conhece**, e isso é útil: dá para o nó carregar o
comando que o executa. Por convenção, prefixe com `x_`:

```json
{
  "id": "roteiro",
  "deps": [],
  "output_evidence": "artifact",
  "verifications": [{"verification_id": "tem-fontes", "family": "deterministic"}],
  "x_harness": "claude",
  "x_command": "claude -p \"Escreva o roteiro a partir de briefing.md. Grave em $OUT.\""
}
```

Esses campos entram no hash do grafo — **mudar o comando muda a identidade do run**,
que é o comportamento correto: é outro trabalho. Exemplo completo em
[`examples/graph-with-commands.json`](../examples/graph-with-commands.json).

### 5.2 O laço

[`examples/runner.sh`](../examples/runner.sh) é o laço inteiro em ~110 linhas de
shell, feito para você copiar e adaptar:

```bash
./examples/runner.sh run.jsonl graph.json "$RUN" out
```

O que ele faz, e por que cada parte importa:

1. `dagwell ready` — pergunta o que a topologia liberou. Nunca decide isso sozinho.
2. `dagwell dispatch` — registra que o nó **foi entregue**, antes de qualquer coisa
   acontecer. Se a máquina cair aqui, o ledger sabe que havia trabalho em voo.
3. Roda o `x_command` **num subshell**, com `$OUT` exportado apontando para o arquivo
   que aquele nó deve produzir.
4. `dagwell return` — registra o código de saída e o **digest do que foi realmente
   escrito**. Não o que o comando disse ter feito: o que está no disco.
5. Verificações de máquina, na ordem do contrato, cada uma com seu veredito.
6. Gate humano: o laço **abre** a verificação e **para**. Abrir não é decidir.

### 5.3 O caso que justifica tudo isso

```bash
x_command: "echo 'pronto, gerei o arquivo' && exit 0"
```

O comando afirma ter feito o trabalho e sai com código zero. Nenhum arquivo aparece.

```
-> gera (attempt 1)
   exit 0, no usable output -> recording the failure
   gera is now: failed
```

**`failed`.** Não `completed`. Esse é o modo de falha caro de qualquer orquestração de
agentes — o agente que relata sucesso sem produzir — e é pego por evidência, não por
confiança. Um orquestrador que só olha o código de saída teria marcado sucesso.

### 5.4 Invocações headless

Um agente interativo trava esperando terminal. Estas são as formas não-interativas
verificadas:

| CLI | Invocação |
|---|---|
| claude | `claude -p "<missão>"` |
| codex | `codex exec --sandbox workspace-write "<missão>"` |
| grok | `grok -p "<missão>" --output-format plain --always-approve --max-turns 25` |
| shell/make | qualquer comando; o `$OUT` é o contrato |

Para os demais (kimi, agy, muse e afins), confira a flag headless no `--help` de cada
um antes de pôr no grafo — o padrão é sempre o mesmo: modo não-interativo, missão como
argumento, e o arquivo em `$OUT` como prova.

### 5.5 Custo

O DAGWELL não gasta nada. **Seu `x_command` gasta.** Cada nó despachado é uma chamada
paga ou uma cota consumida, e o motor não tem modelo de orçamento — a §13.12 está
aberta e nenhuma fórmula foi inventada.

Consequências práticas:

- Rode `dagwell ready` antes do runner para ver **quantos** nós vão disparar.
- Um grafo com 10 nós são 10 chamadas, e uma retentativa é mais uma.
- `dagwell land --reason budget_exhausted` existe justamente para parar sem truncar
  trabalho: o que estava em voo continua registrado, e o `resume` retoma do ponto.

### 5.6 Onde isso se encaixa no que você já faz

O padrão vale para qualquer pipeline em que passos dependem uns dos outros e alguém
precisa aprovar antes do resultado sair:

| Pipeline | Nós típicos |
|---|---|
| Vídeo (HyperFrames) | roteiro → composição → render → aprovação humana |
| Site | pesquisa → copy → build → verificador determinístico → gate |
| Animação | storyboard → keyframes → render → revisão |

Em todos, o ganho é o mesmo: **um nó não avança porque o comando disse que deu certo,
e sim porque a evidência está lá e a verificação passou.** O que muda de um para o
outro é só o `x_command`.

## 6. Referência de comandos

| Comando | O que faz |
|---|---|
| `demo` | ciclo completo numa pasta temporária, narrado. Não precisa de ledger |
| `start` | valida o grafo, congela a identidade, cria o run. Imprime o id |
| `ready` | nós que a topologia desbloqueou |
| `status` | a projeção: estado do run, cada nó, anomalias |
| `dispatch` | registra que um nó foi entregue (**não o executa**) |
| `return` | registra o retorno do transporte e, quando houve, a evidência |
| `request-verification` | abre a verificação que a ordem exige em seguida |
| `verdict` | registra veredito NÃO humano |
| `decide` | registra o veredito humano (único caminho para `family: human`) |
| `human-retry` | abre a tentativa *k+1* após reprovação ou falha |
| `land` | encerra o run com trabalho pendente, preservando o WIP |
| `cancel` | cancela o run (terminal absorvente) |
| `resume` | continua o mesmo run após interrupção |

Todos os comandos, menos `demo` e `start`, recebem `--ledger`, `--graph` e `--run`.

## 7. Lendo um status

Estados de nó:

| Estado | Significado |
|---|---|
| `pending` | dependências não satisfeitas |
| `ready` | despachável agora |
| `running` | entregue, nada de volta ainda |
| `executed` | voltou bem, com a evidência — **não está pronto** |
| `verifying` | há uma verificação de máquina aberta |
| `waiting_human` | esperando um gate humano |
| `completed` | transporte + evidência + aprovações, tudo presente |
| `failed` | a máquina não aceitou: transporte ruim, evidência ausente, órfão |
| `rejected` | um humano reprovou |
| `cancelled` | o run foi cancelado |

Estados de run: `created`, `running`, `stalled` (nada em voo e nenhum gate pendente),
`waiting_human`, `completed`, `landed`, `cancelled`.

Uma linha começando com `!` é uma **anomalia**: algo no ledger que o fold tornou
inerte em vez de obedecer — um veredito sem pedido, um fundador duplicado, um evento
num schema que esta versão não interpreta. Anomalias nunca são apagadas; o ledger
guarda os erros como dado histórico.

`(integrity: degraded)` significa que o fold não pode atestar a identidade deste run
— um buraco no `seq`, ou nenhum `run_created` autoritativo. O run continua
**legível**, mas toda mutação é recusada até um humano reconciliar.

## 8. Quando algo é recusado

Recusa é o produto funcionando, não falhando. Aparece como `refused: <motivo>` e sai
com código diferente de zero. As mais comuns:

| Recusa | O que significa |
|---|---|
| `node X is pending — dispatch requires the ready derived state` | uma entrada de `deps` ainda não foi concluída |
| `node X is running — dispatch requires the ready derived state` | esse nó já tem tentativa aberta |
| `node X is executed, not waiting_human — nothing to decide` | você está decidindo um gate que não está aberto |
| `unresolved seq gap` | o ledger tem um buraco; mutação bloqueada até reconciliar |
| `evidence type ... does not match the node's declaration` | o nó declarou outro tipo |
| `verification is still owed` | aterrissar sobre um nó cuja verificação nunca rodou |
| `run is cancelled` / `run is completed` | estado terminal é terminal |

Nada disso se força com uma flag. Se a recusa está errada, quem está errado é o grafo
ou o ledger — conserte isso, não o guarda.

## 9. O que fica em disco

| Caminho | O quê |
|---|---|
| `run.jsonl` | o ledger: todos os eventos, append-only, um objeto JSON por linha |
| `graphs/` | snapshots de grafo congelado, endereçados por hash de conteúdo |

Nunca edite nem apague nenhum dos dois. Estado é um fold determinístico do ledger:
remover uma linha é mudar a história, não consertar. O checkpoint é sempre
recalculado dos eventos, então adulterar um cache não muda nada além da prova da
adulteração.

Os dois caminhos são seus — versione, faça backup ou mantenha privado, conforme o
trabalho exigir.

## 10. Usando a biblioteca em vez do CLI

Tudo acima existe como API Python, e algumas coisas só existem lá
(`observe_orphans`, `advance_verifications`, `extend_budget`). O início rápido do
README é o exemplo completo mais curto; os módulos são `dagwell.runtime`,
`dagwell.operations`, `dagwell.human` e `dagwell.fold`.

Não escreva direto no ledger. `Ledger.append` é armazenamento, não superfície de
protocolo: ele recusa veredito humano de saída, e as precondições que tornam as
outras operações seguras vivem na camada governada acima dele.
