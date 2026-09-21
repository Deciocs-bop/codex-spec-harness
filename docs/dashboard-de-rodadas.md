# Dashboard de fechamento de rodadas

O dashboard é uma visão derivada dos artefatos canônicos. Ele não substitui os pacotes em `tasks/`, a rastreabilidade ou os registros de decisão. A consulta não grava arquivos; o fechamento explícito cria um snapshot YAML versionável em `rounds/`.

## Unidade de progresso

A unidade de etapa e de escopo total é o pacote de tarefa folha. Um pacote referenciado pelo campo `parent` de outra tarefa é agregador e não entra no denominador, evitando contar o grupo e suas subtarefas ao mesmo tempo. Cada entrega tem peso igual nesta versão.

O progresso da tarefa atual usa apenas critérios estruturados em `acceptance_criteria`: critérios `met` com referência de evidência existente contam como concluídos; `pending` permanece no denominador; `not_applicable` não entra no cálculo. Textos livres em `acceptance` nunca são interpretados como conclusão.

O progresso da etapa considera tarefas folha do mesmo `stage`. O total considera todas as tarefas folha do escopo, inclusive `blocked`; `cancelled` fica fora do denominador e exige motivo no fechamento da rodada. Ausência de critérios ou de estados estruturados produz `não calculável`, não zero. O resultado é provisório quando `dashboard.scope_complete` não é `true` ou existe tarefa sem estado.

Estados de tarefa aceitos:

| Estado | Categoria do painel | Denominador de progresso |
|---|---|---|
| `completed` | concluída | sim, como concluída |
| `in_progress` | em andamento | sim, como não concluída |
| `pending` | pendente | sim, como não concluída |
| `blocked` | bloqueada | sim, como não concluída |
| `cancelled` | cancelada | não |
| campo ausente em pacote legado | sem estado | não; torna o total provisório |

Estados desconhecidos são erros de validação. Os campos novos são opcionais para pacotes legados, mas, quando presentes, devem ser consistentes.

## Campos estruturados da tarefa

Use o modelo em [`templates/task-packet.yaml`](../templates/task-packet.yaml). `owner`, `depends_on`, `status`, `stage`, `acceptance_criteria`, `parent` e `resume` alimentam o painel. `blockers` e `open_decisions` aceitam estruturas com motivo, responsável, impacto e tarefas afetadas. O histórico não deve ser copiado para o pacote; ele permanece nos snapshots de rodada.

Um critério `met` precisa apontar, em `evidence`, para um arquivo versionado existente. Isso comprova somente o critério documental descrito. Não transforma uma evidência documental em teste executado, implementação ou release.

## Consultar e registrar

Consulte o estado atual sem alterar o projeto:

```bash
python -m harness.spec_harness dashboard --root examples/minimal --task TASK-001
```

Visualize o fechamento proposto usando [`round-input.yaml`](../templates/round-input.yaml):

```bash
python -m harness.spec_harness dashboard --root examples/minimal --round-file examples/minimal/round-input.yaml
```

Registre a rodada somente depois de revisar a prévia:

```bash
python -m harness.spec_harness close-round --root examples/minimal --round-file examples/minimal/round-input.yaml
```

`close-round` executa as mesmas validações de `check`, rejeita fontes alteradas ou estrutura inválida e grava `rounds/<id>.yaml`. Repetir o comando com o mesmo identificador e a mesma entrada não altera o arquivo. O mesmo identificador com dados diferentes gera `round_conflict`.

Consulte uma rodada registrada:

```bash
python -m harness.spec_harness dashboard --root examples/minimal --round ROUND-001
```

O snapshot registra a versão das fontes, as métricas, contagens, bloqueios, decisões abertas, gates e ponto de retomada. Se a versão atual das fontes for diferente, o painel histórico informa que a validação se refere a uma versão anterior.

## Mudanças de escopo

Quando a lista de entregas mudar depois da primeira rodada, declare cada inclusão ou remoção em `scope_changes`, com `task`, `change` e `reason`. Use `cancelled` para uma tarefa cancelada. O fechamento é bloqueado se detectar uma mudança não documentada. O painel mostra as bases anterior e atual e não trata a variação percentual como produtividade isolada.

## Gates e limites

O painel mostra separadamente especificação, prontidão para implementação e prontidão para release. Os estados apresentados são evidência documental; não constituem aprovação de negócio. Requisitos `implemented` ou `released` continuam exigindo contrato aprovado, teste executado e evidência executada, e essas condições não substituem aprovações humanas configuradas pelo projeto.

O dashboard deve ser apresentado ao final de toda rodada, mesmo com trabalho parcial ou bloqueado. O repositório não possui gatilho de eventos; portanto, essa execução faz parte do procedimento explícito de encerramento.
