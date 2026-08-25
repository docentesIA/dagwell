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

**Status: o core governado (os seis passos incrementais do contrato) está
implementado; ainda sem adapters.** Nada aqui despacha trabalho real nem gasta
— transportes pertencem ao marco Adapter Transport & Capability Model, ainda
por vir. O comportamento normativo é totalmente especificado antes da
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
python3 tools/run_tests.py          # 142 casos, custo zero, sem rede
```

A suíte imprime mensagens de recusa e um evento de exemplo enquanto roda (`refused:
unknown run: …`). É a saída de testes que afirmam que a recusa acontece — não são
erros. A última linha é o veredito.

## O que ele faz hoje, e o que não faz

**Não há adapters.** Nada aqui despacha trabalho para um provedor, sobe processo ou
gasta coisa alguma. Isso é o marco Adapter Transport & Capability Model, ainda à frente.

O que sobra não é nada, e é a parte que vale entender: **você faz o trabalho, o
DAGWELL governa.** Você (um script, uma pessoa, um agente, um job de CI) executa o
passo pelos meios que já usa; o motor decide se podia começar, registra o que voltou,
recusa uma conclusão sem evidência ou sem aprovação, e reconstrói o estado inteiro
só a partir dos eventos.

| Disponível agora | Ainda não |
|---|---|
| Declarar um grafo; validação fail-closed antes de qualquer gasto | Despachar trabalho a um provedor |
| Iniciar um run com identidade de grafo congelada | Transporte, política de retry ou modelo de orçamento |
| Registrar despacho e retorno; recusar evidência malformada na fronteira | Execução automática de verificação |
| Pedir verificações na ordem do contrato; registrar veredito de máquina | Liveness/timeout por transporte |
| Gates humanos: aprovar, reprovar, retentar, escalar, cancelar | |
| Aterrissar um run; retomar após interrupção; detectar órfãos | |
| Estado determinístico via `fold`; checkpoint à prova de adulteração | |

O CLI expõe o lado humano (`dagwell status | decide | human-retry | cancel`), que é a
parte que uma pessoa conduz do terminal. O resto é a API de biblioteca abaixo — uma
fronteira governada, não escrita crua no ledger.

## Início rápido

```python
import json
from pathlib import Path

from dagwell import human, operations, runtime
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

operations.record_return(
    ledger, graph, run_id, "write-report", attempt=1, exit_code=0,
    output_evidence={"type": "artifact", "evidence_id": "sha256:" + "ab" * 32,
                     "output_manifest": [{"name": "report.md",
                                          "artifact_digest": "sha256:" + "ab" * 32}]})

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
| Definições de grafo de exemplo | [examples/](examples/) |
| Schemas embarcados (auxílio de forma — o validador é a autoridade) | [src/dagwell/schemas/](src/dagwell/schemas/) |
| Checagem de integridade dos contratos | `python3 tools/check_contracts.py` |
| Suíte de testes de custo zero | `python3 tools/run_tests.py` |

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
- **A suíte reporta 142 casos em 12 arquivos, 47 deles adversariais** (a matriz
  T1–T22 mais a cobertura de hardening), cada um escrito para falhar se um buraco
  específico reabrir. Só biblioteca padrão, sem rede, sem cota:
  `python3 tools/run_tests.py` imprime as mesmas contagens para quem rodar.
- **Os achados que NÃO foram corrigidos estão escritos nas mensagens de commit**, não
  omitidos. Dois seguem abertos e são acompanhados como issues.

Nada disso torna o código correto. Torna as afirmações sobre ele conferíveis, que é o
máximo que um repositório pode honestamente oferecer.

## Licença

Copyright 2026 Reinaldo Elias.

Licenciado sob a Apache License, Versão 2.0 — ver [LICENSE](LICENSE) e
[NOTICE](NOTICE).
