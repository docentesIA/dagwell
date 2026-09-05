# DAGWELL

> **Tradução informativa.** O original em inglês ([README.md](README.md))
> governa; em caso de divergência, prevalece o texto em inglês. Os
> identificadores canônicos do protocolo permanecem em inglês (contrato,
> emenda H1); a localização vive apenas na camada de exibição.

DAGWELL é um motor de orquestração público e agnóstico de provedor que executa
trabalho de agentes como um grafo governado sobre um **ledger append-only
orientado a eventos**. Estado nunca é armazenado — é um fold determinístico dos
eventos. Verificação e portões humanos são cidadãos de primeira classe:
transporte bem-sucedido sozinho nunca completa nada (`executed != completed`);
completude é
`successful transport + required output evidence + required approvals`.

**Status: o core governado está implementado, a Adapter/Output Evidence
Specification v1.0 está promovida, e o primeiro adapter existe** — o transporte
`subprocess` com um worker de capacidades (`dagwell work`). Nada gasta sozinho:
`work` sem `--go` é um plano, e `--go` é o operador gastando explicitamente a
própria cota. O comportamento normativo é totalmente especificado antes da
implementação, e o código cresce em fases incrementais com portões.

## Instalação

Requer Python 3.11+. Sem dependências de runtime — o motor usa só a biblioteca padrão.

```bash
pipx install git+https://github.com/docentesIA/dagwell.git
```

Isso põe o comando `dagwell` no PATH, sem virtualenv para ativar. Se preferir um
checkout (para rodar a suíte, ler o contrato ou mexer no código):

```bash
git clone https://github.com/docentesIA/dagwell.git && cd dagwell
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python3 tools/check_contracts.py    # o contrato promovido ainda tem o hash de promovido
python3 tools/run_tests.py          # suíte descoberta dinamicamente, custo zero, sem rede
```

Depois veja tudo funcionando, sem precisar preparar nada:

```bash
dagwell demo
```

## O que ele faz hoje, e o que não faz

**Existe um adapter: `subprocess`.** O nó declara um tier de dificuldade e uma
mission; um registry de bindings (dado SEU, fora deste repositório) declara quais
CLIs e modelos servem quais tiers a que custo relativo; `dagwell work --go` faz o
probe, escolhe o modelo declarado mais barato que satisfaz o tier, executa o binding
e registra a evidência do que de fato pousou no disco. **Bloqueio conhecido da
versão:** o transporte v1.0 não passa o modelo selecionado à invocação; a seleção
registrada não prova qual modelo o CLI usou. A
[proposta v1.1](docs/contracts/DAGWELL-ADAPTER-OUTPUT-EVIDENCE-SPEC-v1.1-RC1.md)
aguarda aprovação humana e não está implementada. Transportes remotos, execução
automática de verificadores e qualquer modelo de retry/orçamento continuam à
frente, cada um atrás do próprio portão.

O modelo inverso continua de primeira classe, e continua sendo a parte que vale
entender: **você faz o trabalho, o DAGWELL governa.** Você (um script, uma pessoa, um agente, um job de CI) executa o
passo pelos meios que já usa; o motor decide se podia começar, registra o que voltou,
recusa uma conclusão sem evidência ou sem aprovação, e reconstrói o estado inteiro
só a partir dos eventos.

| Disponível agora | Ainda não |
|---|---|
| Declarar um grafo; validação fail-closed antes de qualquer gasto | Transportes remotos (http, sdk, mcp, a2a) |
| Iniciar um run com identidade de grafo congelada | Política de retry ou modelo de orçamento |
| Despachar para CLIs locais por tier de dificuldade (`dagwell work --go`) | Execução automática de verificação |
| Registrar despacho e retorno; recusar evidência malformada na fronteira | Persistência de sessão por plataforma |
| Pedir verificações na ordem do contrato; registrar veredito de máquina | |
| Gates humanos: aprovar, reprovar, retentar, escalar, cancelar | |
| Aterrissar um run; retomar após interrupção; detectar órfãos | |
| Estado determinístico via `fold`; checkpoint à prova de adulteração | |

O CLI conduz o ciclo inteiro — `start`, `ready`, `dispatch`, `return`,
`request-verification`, `verdict`, `decide`, `human-retry`, `land`, `resume`,
`cancel`, `status` — então você nunca precisa escrever Python para usá-lo. As mesmas
operações existem como biblioteca. **[Manual completo: docs/USAGE.pt-BR.md](docs/USAGE.pt-BR.md)**.

## Relato de campo: um motor, três mundos

No primeiro dia de uso real em produção, o motor governou o mesmo tipo de
trabalho em três territórios: uma colmeia de agentes 24/7 atrás de um relay de
mensagens (despacho por @menção, respostas viradas em evidência com hash), os
CLIs headless locais de uma máquina (registry de bindings com tiers, probes e
custos relativos) e um agente residente autônomo que tanto recebeu despachos
*dentro da própria casa* quanto dirigiu ali os próprios runs governados — sem
sudo, sem fronteiras cruzadas.

O dia também produziu o melhor argumento do motor a favor de si mesmo: um agente
saiu com exit `0` sem entregar nada, e o ledger registrou `failed — evidence
none` em vez de um verde de mentira — foi assim que um bug real de permissão
headless foi pego. **[Relato completo: docs/TRES-MUNDOS.pt-BR.md](docs/TRES-MUNDOS.pt-BR.md)**
([original em inglês](docs/THREE-WORLDS.md)).

## Início rápido

```python
import json
from pathlib import Path

from dagwell import human, operations, runtime
from dagwell.canonical import json_digest
from dagwell.fold import fold
from dagwell.ledger import Ledger

GRAPH = json.dumps({"graph_id": "hello", "nodes": [
    {"id": "write-report", "deps": [], "output_evidence": "artifact",
     "verifications": [{"verification_id": "review", "family": "human"}]}]})

Path("graph.json").write_text(GRAPH)          # the graph is a file you keep
ledger = Ledger("run.jsonl")
graph, founding = runtime.start_run(ledger, graph_text=GRAPH,
                                    input_text="the task", input_ref="local://task")
run_id = founding["run_id"]
print("run:", run_id)

operations.dispatch(ledger, graph, run_id, "write-report")

# ---- you, your script, or an agent does the actual work here ----

manifest = [{"path": "report.md", "artifact_digest": "sha256:" + "ab" * 32,
             "size_bytes": 2}]
operations.record_return(
    ledger, graph, run_id, "write-report", attempt=1, exit_code=0,
    output_evidence={"type": "artifact", "evidence_id": json_digest(manifest),
                     "output_manifest": manifest})

print(fold(graph, ledger.run(run_id), run_id)["nodes"]["write-report"]["state"])
# executed   <- transport succeeded AND evidence is present. Still not completed.

operations.request_verification(ledger, graph, run_id, "write-report",
                                verification_id="review")
human.decide(ledger, graph, run_id, "write-report", "approved", actor="you")

print(fold(graph, ledger.run(run_id), run_id)["nodes"]["write-report"]["state"])
# completed  <- only now.
```

O `run.jsonl` guarda agora todos os eventos, e `graphs/` o grafo congelado. Não apague
nada: o ledger é append-only e o estado é um fold dele. Para inspecionar o run:

```bash
dagwell status --ledger run.jsonl --graph graph.json --run <the run id printed above>
```

## Onde está o quê

| O quê | Onde |
|---|---|
| Instruções para agentes (canônica, agnóstica de ferramenta) | [AGENTS.md](AGENTS.md) |
| Contrato normativo (supremo) | [docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md](docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md) |
| Manifesto de documentos promovidos | [docs/contracts/MANIFEST.sha256](docs/contracts/MANIFEST.sha256) |
| Plano de Arquitetura & Migração | [docs/architecture/](docs/architecture/) |
| Registros de decisão (ADRs) | [docs/decisions/](docs/decisions/) |
| **Como usar, comando a comando** | **[docs/USAGE.pt-BR.md](docs/USAGE.pt-BR.md)** |
| Definições de grafo de exemplo | [examples/](examples/) |
| Schemas embarcados (auxílio de forma — o validador é a autoridade) | [src/dagwell/schemas/](src/dagwell/schemas/) |
| Checagem de integridade dos contratos | `python3 tools/check_contracts.py` |
| Suíte de testes de custo zero | `python3 tools/run_tests.py` |

## O nome

**O demônio de Maxwell** — e o motivo pelo qual ele falha.

O demônio é um experimento mental: um agente que observa moléculas, usa
**informação** para separar as rápidas das lentas e reduz a **entropia** de um gás,
pagando um custo energético por bit adquirido (Landauer). Não é uma metáfora
escolhida por soar bem. É o **mesmo problema formal**, com as mesmas grandezas:

| Demônio de Maxwell | Orquestrador de agentes |
|---|---|
| observa moléculas | observa o estado da tarefa |
| usa informação para separar rápidas de lentas | usa informação para rotear ao agente certo |
| reduz a entropia do gás | reduz a incerteza sobre o artefato |
| paga energia por bit (Landauer) | paga tokens por bit de incerteza removida |
| o limite é termodinâmico | o limite é o orçamento |

E a lição do demônio é o ponto inteiro: **o demônio só funciona se de fato medir.**
Um demônio que separa moléculas sem observá-las não reduz entropia nenhuma — apenas
gasta energia.

Isso é o `executed != completed`, enunciado pela física um século antes de alguém
despachar um agente. Um passo que rodou, saiu com código zero e nunca foi verificado
é um demônio que separou sem olhar: tokens gastos, incerteza intacta. O protocolo
inteiro existe para recusar chamar aquilo de concluído.

O antecessor se chamava **Maxwell**. Este motor mantém o `well` e troca `MAX` por
**DAG** — o grafo dirigido acíclico que virou a estrutura sobre a qual tudo se
apoia. O demônio ficou; o que mudou é que o trabalho dele agora é um grafo, e o que
ele mede está escrito onde qualquer um confere.

## Como isto foi feito, e como foi conferido

Este código foi escrito por agentes de IA sob gate humano, e os rodapés dos commits
dizem isso. Está declarado aqui em vez de ficar para ser descoberto: um projeto sobre
governar trabalho de agentes não tem por que ser vago sobre a própria produção.

O que o torna conferível não é quem digitou:

- O **contrato normativo veio antes**. `docs/contracts/` guarda um documento promovido,
  travado por SHA-256 e verificado a cada push; a implementação segue a ordem
  incremental dele e nunca o edita no lugar.
- **Duas auditorias independentes**, por modelos de famílias diferentes da que escreveu
  o core — a regra do próprio projeto de que o verificador não pode ser da mesma família
  do produtor. As duas devolveram REWORK REQUIRED.
- **Cada achado foi reproduzido** no interpretador antes de virar correção. Duas
  afirmações não sobreviveram à reprodução e foram descartadas — uma de cada auditor.
- **A suíte de custo zero descobre os arquivos de teste dinamicamente**, incluindo
  a matriz T1–T22, hardening e regressões. Só biblioteca padrão, sem rede, sem cota:
  `python3 tools/run_tests.py` informa os resultados atuais.
- **Achados abertos continuam documentados.** Nesta candidata, invocar o modelo
  selecionado depende da decisão humana sobre a especificação vinculada acima.

Nada disso torna o código correto. Torna as afirmações sobre ele conferíveis, que é o
máximo que um repositório pode honestamente oferecer.

## Licença

Copyright 2026 Reinaldo Elias.

Licenciado sob a Apache License, Versão 2.0 — ver [LICENSE](LICENSE) e
[NOTICE](NOTICE).
