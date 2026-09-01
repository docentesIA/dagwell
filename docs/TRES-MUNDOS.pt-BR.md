# Relato de campo: um motor, três mundos

> Primeiro dia de uso real em produção, 2026-08-31. Tudo abaixo aconteceu contra
> ledgers vivos; nada é simulação. Detalhes de infraestrutura (hosts, chaves,
> identificadores de canal) foram omitidos de propósito.
>
> *Tradução informativa — o original canônico é [THREE-WORLDS.md](THREE-WORLDS.md).*

## A tese, reafirmada

**Agente executar não é agente entregar.** O DAGWELL governa trabalho de agentes
como um grafo sobre um ledger append-only e só chama de *completo* o que passou
pela verificação declarada. `executed != completed` é a tese do motor virada em
código — e no primeiro dia ela pagou o próprio salário.

## O que o motor garante (observado, não prometido)

1. **Ledger append-only, event-sourced.** Cada despacho, retorno, veredito e
   decisão humana é um evento imutável com sequência e timestamp. O estado é uma
   projeção (fold) dos eventos — não existe estado escondido para dessincronizar.
   Auditar = ler um arquivo.
2. **Falha honesta.** No primeiríssimo run de produção, um agente saiu com exit
   `0` sem produzir nada — um bug de permissão headless o fazia voltar vazio
   parecendo sucesso. O DAGWELL registrou `failed — evidence none` em vez de um
   verde de mentira. O bug foi achado *porque* o motor se recusou a ser educado.
3. **Fail-closed em todas as portas.** Nó sem verificação declarada (ou um
   `no_verification: <motivo>` explícito)? Recusado antes de começar. Nenhum
   binding capaz de servir o tier? **Recusa antes de gastar.** Probe falhou?
   Binding indisponível.
4. **Evidência com hash.** Todo artefato de retorno entra no ledger com `sha256`
   — o que foi entregue é verificável byte a byte, para sempre.
5. **Verificações em ordem de contrato.** Determinísticas (scripts que rodam e
   registram veredito) e **gates humanos** que bloqueiam os nós dependentes no
   motor até a pessoa decidir. Gate humano não é aviso; é trava.
6. **Despacho com custo consciente.** Bindings declaram tiers e custo relativo;
   o seletor escolhe o mais barato capaz, e `work` sem `--go` é dry-run de custo
   zero que mostra o plano inteiro antes de qualquer gasto.
7. **Retry governado.** Refazer um nó não apaga o erro: é um evento
   `human_retry` no ledger. A história completa — falhas incluídas — permanece.

## Mundo um — a colmeia de agentes 24/7 atrás de um relay

Agentes de quatro famílias de modelos diferentes rodam 24/7 contra um relay de
mensagens auto-hospedado, de protocolo aberto, e respondem a @menções.

O que o DAGWELL acrescenta:

- **Menção como transporte.** Um script de borda de ~20 linhas posta a missão do
  nó no canal, espera a resposta do agente e a transforma em evidência. O motor
  nunca aprende o protocolo do relay — fronteiras vivem em scripts de borda
  trocáveis, exatamente como a arquitetura exige (nenhum código de provedor no
  núcleo).
- **Famílias independentes de verificação.** Quem produz não avalia a própria
  obra; com quatro famílias de fornecedores na colmeia, o nó feito por uma é
  verificado por outra — a custo marginal de assinatura fixa (~zero por
  despacho).
- **Equipes encadeadas com contrato.** As equipes de agentes seguem conversando
  livres nos canais; o DAGWELL entra quando o trabalho exige evidência,
  verificação e gate humano antes de qualquer publicação.

## Mundo dois — CLIs locais headless

Os mesmos modelos como processos locais one-shot.

O que o DAGWELL acrescenta:

- **Registry de bindings.** Cada CLI entra com template de invocação, probe de
  disponibilidade, tiers que serve e custo relativo. Trocar de fornecedor é uma
  linha de registry, nunca uma mudança no motor.
- **Lições de headless viradas em configuração.** As flags de permissão que cada
  CLI exige para rodar sem TTY ficam gravadas no binding — o conhecimento
  operacional para de morar na cabeça de alguém.
- **Seleção com recusa honesta.** `trivial` vai para o binding mais barato
  capaz; se ninguém serve o tier, o motor recusa *antes* do gasto e diz por quê.

## Mundo três — um agente autônomo com casa própria

Um agente residente com usuário próprio sem privilégios, diretório próprio e
cron próprio — por desenho.

O que o DAGWELL acrescenta, nas duas direções:

- **O orquestrador despacha *para dentro* da casa do agente.** Um binding
  one-shot roda a missão como aquele usuário, no diretório dele, no provedor de
  modelo dele. Provado com um nó de grafo que pediu ao agente para inspecionar o
  próprio cron — a resposta voltou como evidência com hash no ledger.
- **O agente dirige os próprios grafos.** Com o DAGWELL instalado system-wide, o
  usuário do agente cria run, despacha para si mesmo e fecha o ciclo inteiro na
  própria pasta — sem sudo, sem invadir área de ninguém. A primeira frase
  registrada no ledger dele: *"Confirmo que este run foi dirigido por MIM mesmo
  via dagwell."*
- **O próximo passo natural:** as rotinas de cron do agente deixam de ser
  scripts soltos e viram runs governados — evidência, verificação e histórico
  auditável, todos os dias.

## Disciplina operacional que nasceu no primeiro dia

- **Um piloto por run.** Dois loops de `work --go` no mesmo run pagam a mesma
  missão duas vezes. Um wrapper com trava de arquivo já barra o segundo piloto
  com mensagem clara; a trava nativa no `work` está no roadmap.
- **Run fantasma recusado.** Run id ausente do ledger deve ser rejeitado antes
  de qualquer coisa — descoberto em teste, proposto como fail-closed nativo.

## Próximo: DAGWELL como agente ACP

Hoje a frente conversacional é um LLM com as mãos no CLI: uma persona que roda
`work`/`status` quando o dono pede, e responde com fatos do ledger. O passo
seguinte é o motor falar o **Agent Client Protocol** nativamente — um subcomando
`dagwell acp` via JSON-RPC/stdio:

- **Plug em qualquer cliente ACP** — pontes de relay, editores, outros
  harnesses: mencionar o orquestrador vira abrir uma sessão com ele.
- **Respostas determinísticas com zero tokens.** Estado do run, vereditos
  pendentes, próximo gate — direto do fold, sem LLM, sem alucinação, sem custo.
- **LLM só onde ele ganha o lugar:** interpretar linguagem natural e redigir
  resumos. A verdade continua vindo do ledger.
- **Gates humanos no chat.** Uma aprovação vira um evento `verdict` assinado —
  conversa e governança param de ser mundos separados.
