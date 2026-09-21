# Manual do usuário — Codex Spec Harness

## 1. O que é

O Codex Spec Harness é um conjunto pequeno de arquivos e comandos para organizar a documentação de um projeto. Ele ajuda pessoas e IAs a encontrarem a fonte de um requisito, a decisão que o sustenta, o contrato previsto, o teste planejado e a evidência disponível.

Ele não escreve nem aprova regras de negócio por conta própria. Também não substitui revisão humana, segurança, testes reais ou uma decisão de liberar produção. Seu papel é tornar essas distinções visíveis e verificáveis.

O fluxo usado pelo harness é:

```text
fonte → requisito → decisão → contrato → teste → evidência → checkpoint
```

Por exemplo, uma fonte pode dizer que uma aprovação é necessária. Um requisito registra o comportamento esperado. Uma decisão aprovada explica a regra. O contrato define a futura interface. Um teste planejado descreve como verificar o resultado. A evidência indica o que realmente foi comprovado.

## 2. Preciso instalá-lo em cada novo projeto?

Não existe uma instalação global obrigatória e o harness não é um plugin exclusivo do Codex. Para que a documentação de um projeto seja auditável e continue funcionando em outra máquina ou sessão, a recomendação é manter uma cópia versionada do harness dentro daquele projeto, junto dos seus próprios registros.

Há duas formas simples de adoção:

1. Copiar `harness/`, `templates/` e `requirements.txt` para o novo repositório e mantê-los sob controle de versão.
2. Manter o repositório do harness como referência compartilhada e copiar uma versão conhecida para cada projeto quando ele começar. Registre no projeto qual versão foi adotada.

A primeira opção é mais simples para começar. Cada projeto fica independente e conserva seu próprio histórico. Evite colocar fontes, decisões ou dados de diversos projetos no mesmo diretório do harness.

## 3. O que preciso ter instalado?

Você precisa de Python 3 e Git. Depois de copiar ou clonar o harness, instale a única dependência do projeto:

```bash
python -m pip install -r requirements.txt
```

Se o comando `python` não funcionar, experimente `py` no Windows ou `python3` em macOS e Linux.

## 4. Como começar em um projeto novo

O caminho mais seguro é estudar primeiro o [exemplo sintético](../examples/minimal/). Em seguida, copie os arquivos de [templates](../templates/) e crie estes artefatos canônicos no seu projeto:

| Arquivo ou pasta | Para que serve |
|---|---|
| `sources/` e `sources.yaml` | fontes do briefing, legislação, pesquisas ou documentos aprovados, com hash |
| `decisions.md` | decisões com identificador `ADR-xxx` e estado explícito |
| `contracts.yaml` | contratos futuros ou aprovados |
| `tests.yaml` | testes planejados ou executados |
| `evidence/` e `evidence.yaml` | evidências documentais ou executadas |
| `traceability.yaml` | liga cada requisito aos seus elementos de origem |
| `tasks/` | pacotes de contexto pequenos, um para cada tarefa |
| `project-profile.yaml` | nome do projeto, orçamento de contexto e gates |
| `status.md` | situação atual resumida |

Comece com um escopo pequeno. Cadastre uma fonte, um requisito e uma decisão. É melhor expandir uma cadeia válida do que criar dezenas de registros soltos.

## 5. Quais comandos uso no dia a dia?

Execute os comandos a partir da pasta que contém o diretório `harness/`.

```bash
# Verifica estrutura, hashes, referências, conteúdo vazio e padrões de segredo.
python -m harness.spec_harness check --root .

# Mostra o contexto enxuto e validado de uma tarefa.
python -m harness.spec_harness context --root . --task TASK-001

# Atualiza hashes de fontes após análise humana de uma alteração.
python -m harness.spec_harness hash --root .

# Executa os testes do próprio harness.
python -m unittest discover -s tests -p "test_*.py"
```

`check` é o comando principal. Use-o antes de pedir revisão, abrir um pull request ou afirmar que uma etapa documental está pronta.

`context` é o comando para retomada de sessão. Ele valida o pacote selecionado antes de exibi-lo, inclui os hashes das fontes e interrompe a operação se encontrar referência ausente, fonte alterada ou orçamento excedido. Ele não corta texto silenciosamente.

`hash` não é uma aprovação. Quando uma fonte muda, primeiro analise quais requisitos e evidências foram afetados. Só então atualize o manifesto de fontes. A evidência ainda precisa ser revisada ou substituída conscientemente.

## 6. Como interpretar os estados

| Elemento | Estados aceitos | Significado |
|---|---|---|
| Decisão | `proposed`, `approved`, `superseded`, `rejected` | Somente uma decisão `approved` sustenta um requisito. |
| Contrato | `future`, `approved` | `future` descreve intenção; não autoriza implementação. |
| Teste | `planned`, `executed` | Um teste planejado não prova execução. |
| Evidência | `documentary`, `executed` | Evidência documental registra contexto; evidência executada prova uma atividade específica. |
| Requisito | `specified`, `implementation_ready`, `implemented`, `released` | `implemented` e `released` exigem contrato aprovado, teste executado e evidência executada. |

Esses estados evitam uma conclusão falsa, como chamar um contrato futuro de API pronta ou chamar um teste planejado de teste realizado.

## 7. Como integrar com o Codex ou outra IA

O harness funciona com Codex, Claude Code, OpenCode, Cursor, DeepSeek Harness ou qualquer IA que possa ler arquivos e executar comandos Python. Ele não depende de MCP, token, extensão de editor ou conversa anterior.

Para o Codex, mantenha as regras em `AGENTS.md` do projeto. Uma instrução inicial simples pode ser:

```text
Leia AGENTS.md e o pacote TASK-001. Execute:
python -m harness.spec_harness context --root . --task TASK-001
Use somente os artefatos versionados como fonte de verdade.
Antes de encerrar, execute:
python -m harness.spec_harness check --root .
Informe arquivos alterados, validações e pendências.
```

Passe o resultado de `context` para a IA ou peça que ela execute o comando. O pacote traz apenas o contexto da tarefa, em vez de carregar todos os documentos do projeto. A IA pode redigir e propor mudanças; aprovação de negócio e liberação continuam sendo responsabilidade humana.

Se você já usa outro harness, integre este como a camada de rastreabilidade documental. Escolha um único arquivo canônico para cada tipo de informação. Não copie a mesma decisão para dois registros, nem crie um segundo status para o mesmo requisito.

## 8. Posso usar sem Codex?

Sim. O nome do projeto indica o primeiro caso de uso, mas o componente é uma CLI Python e arquivos versionados. Você pode usá-lo sem nenhuma IA, com outra ferramenta de IA ou dentro de um processo humano de revisão documental.

Também pode colocá-lo ao lado de GSD, um sistema de ADRs ou um processo interno. O harness não substitui esses processos; ele registra referências e impede que metadados sejam confundidos com evidência.

## 9. Erros comuns

**`source_changed`** — a fonte foi alterada desde o hash registrado. Compare a mudança, avalie o impacto nos requisitos e evidências, depois use `hash` se a alteração for aceita.

**`evidence_source_changed`** — uma evidência documental referencia uma fonte cujo hash mudou. Atualizar somente `sources.yaml` não resolve isso; revise a evidência.

**`orphan_decision`, `orphan_contract`, `orphan_test` ou `orphan_evidence`** — o requisito aponta para um identificador que não existe no catálogo correspondente. Corrija a referência ou crie o registro canônico.

**`unproven_completion`** — um requisito foi marcado como implementado ou liberado sem a cadeia de evidências necessária. Corrija o estado ou registre contrato aprovado, teste executado e evidência executada verificáveis.

**`packet_over_budget`** — o pacote de tarefa excede `context.max_words`. Reduza o escopo, substitua texto repetido por referências ou divida a tarefa. Não aumente o limite apenas para acomodar histórico desnecessário.

## 10. Limites importantes

O harness não protege sozinho dados pessoais, credenciais ou informações confidenciais. Não armazene segredos em fontes, exemplos, evidências ou logs. A verificação de padrões de segredo é preventiva e conservadora; ela não substitui uma revisão de segurança.

Ele também não executa testes de produto, não aprova regras de negócio e não libera produção. Use os checkpoints para mostrar o que foi verificado e o que permanece pendente, sempre com uma pessoa responsável pelas decisões relevantes.
