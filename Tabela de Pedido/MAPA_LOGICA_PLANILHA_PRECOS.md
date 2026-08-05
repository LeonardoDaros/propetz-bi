---
dono: Leonardo Daros
status: rascunho
atualizado: 2026-08-03
validade: —
exportavel: NAO
---

# Mapa lógico — planilha de preços e campanhas

## Propósito

Explicar como Leonardo utiliza `Novos valores distribuicao (1).xlsx` sem
reescrever suas fórmulas nem transformar dados auxiliares em fontes oficiais.

## Autoridade e fronteira

Leonardo define os preços e as campanhas mensais da Distribuição e do Varejo.
A planilha oficial está em:

`Dcorp\ATUALIZAR MES A MES\Tabela de Preço\Novos valores distribuicao (1).xlsx`

A aba mensal aprovada é a fonte comercial. Uma aba `ABERTO <mês>` é ambiente de
trabalho e não se torna vigente sem aprovação de Leonardo.

Estoque, custos, demanda, curva ABC e demais indicadores são copiados de outras
planilhas para apoiar o raciocínio. Eles continuam pertencendo às respectivas
fontes, que serão apresentadas por Leonardo em outro momento. Nesta planilha,
são fotografias auxiliares, não fontes da verdade.

## O que a planilha faz

Ela reúne, numa mesma aba mensal:

1. memória de decisões e campanhas;
2. identificação do produto;
3. fotografias auxiliares de estoque, custo e demanda;
4. formação de preço da Distribuição;
5. formação de preço do Varejo;
6. promoções dos dois canais;
7. comparativos, markups e margens de apoio;
8. histórico mensal dos canais;
9. simulações de faturamento e quantidade.

Essa combinação explica sua utilidade e também sua complexidade. Separar os
blocos sem compreender as dependências pode apagar raciocínio histórico.

## Mapa da aba mensal atual

### Linhas 2–24 — memória de decisão

Contêm hipóteses, campanhas, ações abertas, análises e decisões do mês. É uma
memória de trabalho de Leonardo, não um workflow formal com prazo e responsável.

### Linha 27 — cabeçalho do cadastro e da formação de preço

| Colunas | Função observada | Autoridade |
|---|---|---|
| C–H | NCM, fábrica, categoria, SKU, descrição e observação | fotografia cadastral; fonte externa a mapear |
| I–M | estoque, curva ABC, média, Custo TRADE e Custo Filial | apoio copiado de análises específicas |
| N–P | referência FOB, FOB vigente e FOB com IPI | preço em O é decisão comercial; IPI precisa de fonte validada |
| Q–R | simulação de FOB e markup de exportação | cenário auxiliar; não alimenta a tabela atual |
| S–AC | aumentos, markups, CMV, margem e promoção FOB | cálculos e decisão de campanha da Distribuição |
| AD–AK | comparativos, preço e promoção do site | preço e campanha do Varejo |
| AM–BJ | histórico mensal da Distribuição | apoio copiado ou calculado |
| BK–CH | histórico mensal do Varejo | apoio copiado ou calculado |
| CJ–FC | médias, projeções de receita, quantidade e crescimento | apoio analítico; não define preço sozinho |

## Campos comerciais consumidos pela Tabela de Pedido

O extrator de agosto lê da aba mensal:

- `F`: SKU;
- `I`: estoque auxiliar usado no filtro;
- `L`: Custo TRADE usado em controle interno;
- `O`: preço FOB de tabela;
- `P`: FOB com IPI, quando calculado;
- `Y`: promoção FOB;
- `AG`: preço do site Propetz.

Estrutura, barras, múltiplos e mínimos ainda vêm da antiga planilha FOB. O
resultado passa por `_modelo_tabela.json` e gera os arquivos FOB e CIF para o
cliente. Modelo e arquivos gerados são derivados, nunca fontes oficiais.

## Fluxo mensal reconstruído

Este fluxo foi inferido da planilha e deve ser refinado com o uso real:

1. criar ou copiar a aba de trabalho do próximo mês;
2. trazer fotografias atualizadas das análises auxiliares;
3. revisar resultados, estoque, custos, demanda e campanhas anteriores;
4. registrar hipóteses e ações no bloco superior;
5. Leonardo definir preços-base e campanhas dos dois canais;
6. revisar fórmulas, exceções e itens sem dados;
7. Leonardo aprovar a aba como vigente;
8. gerar e conferir as tabelas FOB/CIF;
9. preservar a aba mensal como histórico.

## Fotografia técnica de 03/08/2026

- 46 abas no arquivo;
- 228 SKUs com preço FOB na aba `Ago-26`;
- 88 promoções FOB reais nessa aba;
- 140 SKUs chegaram às tabelas FOB/CIF após os filtros atuais;
- zero erro calculado nas tabelas FOB/CIF entregáveis;
- 614 erros armazenados na aba de análise de agosto:
  - 436 em simulações ocultas de exportação sem premissa preenchida;
  - 54 derivados de referências quebradas num único SKU de peça;
  - 22 produtos sem cálculo de IPI nessa aba, nenhum presente nas saídas atuais;
  - demais erros em comparativos com referência vazia ou zero.

Os erros não provam preço publicado incorreto. Eles mostram que partes
analíticas copiadas entre meses precisam de controle antes de serem reutilizadas.

## Regras de preservação

1. não editar a planilha para “limpar” aparência sem projeto e rollback;
2. não tratar dado auxiliar copiado como atual sem consultar sua fonte;
3. nenhuma IA altera preço ou campanha sem decisão de Leonardo;
4. aba aberta ou futura é rascunho;
5. fórmulas, premissas e erros devem ser avaliados por bloco, não em massa;
6. toda automação nova começa em modo sombra e compara com a rotina atual;
7. fontes auxiliares serão mapeadas gradualmente, sem interromper a operação.

## Próxima evolução segura

Criar um auditor somente leitura que valide a aba escolhida antes da publicação:
fonte, fórmulas comerciais, IPI, promoções, preços ausentes, fallbacks e paridade
FOB/CIF. Ele deve informar; nunca corrigir ou publicar automaticamente.

Nenhuma planilha ou automação foi alterada para criar este mapa.
