# Manual — Integração com o banco PostgreSQL "silver" (para ESTE projeto)

> Escrito em 21/07/2026 pelo Claude do projeto Demanda Curva ABC, a pedido do
> Leonardo, para transferir o conhecimento da integração já validada lá.
> **Leia este manual inteiro antes de escrever qualquer consulta.**
> Fonte canônica da integração (decisões, auditorias, regras vivas):
> `..\Demanda Curva abc\Demanda Curva Abc - Pet\Manual_Cloud_Banco_Silver.md`
> — em divergência entre este resumo e o manual canônico, o canônico vence.

## O que é

Banco PostgreSQL da DarosCorp (Azure) alimentado pelo Tiny ERP — o mesmo que
abastece o Power BI. Schema `silver`, 11 objetos documentados. Para ESTE
projeto (BI do canal Distribuição: clientes, churn, mix), o ouro é o que as
planilhas nunca tiveram: **cliente por nota com cidade/UF (99,98% de
cobertura), vendedor, transportadora e frete** — direto da fonte, sem
digitação manual.

Confiabilidade: reconciliado ao centavo com a Base Mãe do projeto Demanda
(7 meses de 2026, produto a produto, auditado adversarialmente em 21/07/2026).
Frescor: recebe notas em tempo quase real (processamento de hora em hora em
implantação pela DarosCorp).

## ⚠️ SEGURANÇA — leia antes de tudo (este projeto é um repo público!)

Este projeto é **versionado em git e publicado** (propetz-bi.streamlit.app).
Regras INEGOCIÁVEIS:

1. **Credenciais NUNCA entram nesta pasta.** Nem em código, nem em .env, nem
   em comentário. As credenciais moram SÓ no projeto Demanda:
   `..\Demanda Curva abc\Demanda Curva Abc - Pet\tools\.db_cloud\credenciais.json`.
2. **Scripts locais** (rodando no PC do Leonardo): use a PONTE
   `ponte_db_silver.py` (já criada aqui, segura para versionar — só importa o
   cliente do projeto vizinho, não contém segredo nenhum).
3. **App publicado (Streamlit Cloud)**: se um dia o app online precisar do
   banco, o caminho é `st.secrets` configurado NO PAINEL do Streamlit Cloud
   (Settings → Secrets), NUNCA em arquivo do repo. Antes de fazer isso,
   discutir com o Leonardo: expõe o banco a uma máquina fora da rede — a
   DarosCorp precisa liberar/avaliar. Até lá, o padrão é: dados extraídos
   localmente → gravados nas planilhas/arquivos que o app já usa.
4. O usuário `consulta` é somente-leitura, mas trate o banco como produção:
   nada de consultas pesadas em loop; sempre filtrar por período.

## Como conectar (script local)

```python
from ponte_db_silver import consultar  # ponte deste projeto (importa o vizinho)

linhas = consultar("""
    SELECT f.cliente_nome, f.cidade, f.uf, sum(f.valor_total) AS faturamento
    FROM silver.faturamento f
    WHERE f.ano = 2026 AND f.tipo_faturamento = 'NF de Venda'
      AND f.modelo_negocio_descricao = 'Distribuição PROPETZ'
    GROUP BY 1, 2, 3 ORDER BY 4 DESC
""")
```

Dicionário de dados completo (tabelas, colunas, grãos, exemplos de SQL):
`..\Demanda Curva abc\Demanda Curva Abc - Pet\dicionario_dados_silver (1).md`.

## Regras de negócio VALIDADAS (não reinventar — já foram auditadas ao centavo)

1. **Só `tipo_faturamento = 'NF de Venda'`** para receita. Devolução, garantia,
   transferência, bonificação têm tipos próprios.
2. **Canal Distribuição** = `modelo_negocio_descricao = 'Distribuição PROPETZ'`
   (o campo `tipo_operacao = 'Distribuição'` inclui também NR/ferragens e
   Manutenção — cuidado).
3. **`valor_total` é a receita analítica** e JÁ embute a "venda gerencial"
   (valor complementar positivo — nota + parte por fora = valor do pedido,
   regra oficial do Leonardo 21/07). Não use `valor_nota` para receita.
4. **Modelos excluídos das análises**: Manutenção, Garantia, Feira.
5. **Cabeçalho vs itens**: `silver.faturamento` (1 linha por documento) ×
   `silver.faturamento_item` (join por `faturamento_id`). NUNCA somar
   cabeçalho depois de join com itens sem controlar duplicidade.
6. **Quantidade** = `faturamento_item.quantidade`.
7. **Notas canceladas não existem no banco** (o pipeline já as exclui) — não
   precisa filtrar situação.
8. **Notas sem `modelo_negocio`** (vendedor não atribuído no Tiny) ficam fora
   de qualquer filtro por modelo — o time do #4-power-bi corrige; volume
   irrisório.
9. **Histórico**: dados confiáveis **de 2026 em diante**. 2025 para trás, o
   banco NÃO bate com as bases manuais do grupo (decisão do Leonardo:
   histórico congelado nas planilhas). Para churn/recompra multi-ano, dá para
   usar o banco como visão própria — mas NUNCA misturar banco e planilha na
   mesma métrica sem reconciliar antes.

## Armadilhas conhecidas (auditadas — vão te morder se ignorar)

- `silver.produto.saldo_estoque` é saldo TOTAL (o dicionário diz "disponível",
  está errado): disponível = `saldo_estoque - saldo_estoque_reservado`, e SÓ
  linhas `situacao = 'A'` (E/I carregam saldo fantasma). Unidade "Gerencial"
  (uuid d09c5db8…) é visão CONSOLIDADA — nunca somar com as demais.
- Tabelas `classificacao_abc_*`: linhas duplicadas em massa — NÃO usar como
  fonte (a correção foi pedida à DarosCorp).
- `valor_frete_efetivo`: morto desde 2024; use `valor_frete`.
- Pedidos (`tipo_documento = 'P'`): alimentação parou em 2026 — não usar.
- Metas 2026 NÃO estão no banco (`meta_faturamento*` só 2023/2025);
  `meta_vendedor` 2026 existe mas diverge do plano oficial — não usar.
- Consultas podem levar ~1 min em janelas de carga do servidor (cache
  frio/ETL) — a ponte já usa timeout de 5 min; nunca rode sem filtro de data.

## Processo de trabalho (padrão do grupo, exigido pelo Leonardo)

1. **Análise crítica sempre** — questionar, não concordar passivamente.
2. **Validar antes de confiar**: toda métrica nova tirada do banco deve ser
   conferida contra uma referência conhecida (planilha do canal, BI, ou o
   dashboard do projeto Demanda) antes de entrar no app. Trabalho grande =
   auditores adversariais (workflow) antes de virar produção.
3. **Backup antes de editar** qualquer base/dashboard (`*.backup_AAAAMMDD_HHMMSS`).
4. **Documentar**: descobertas NOVAS sobre o banco vão primeiro no manual
   canônico do projeto Demanda (`Manual_Cloud_Banco_Silver.md`); o que for
   específico deste projeto, documente aqui e no CLAUDE.md local.
5. **pt-BR e R$** em tudo voltado ao usuário; Leonardo é leigo em código —
   explicar mudanças em linguagem simples.

## Ideias de uso imediato neste projeto (conversadas com o Leonardo)

- **Churn/recompra direto da fonte**: última compra por cliente, intervalo
  médio entre pedidos, clientes ativos/inativos por mês — hoje isso vem de
  planilha manual (`Qtd_Comprada_Por_Cliente_RECONSTRUIDA.xlsx`).
- **Mapa de demanda por cidade/UF** do canal Distribuição.
- **Custo de frete por transportadora/rota** (`valor_frete`, transportador).
- **Mix por cliente**: itens por nota via `faturamento_item` (o que cada
  distribuidor compra e deixou de comprar).
