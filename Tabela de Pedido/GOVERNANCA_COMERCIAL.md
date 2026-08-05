---
dono: Leonardo Daros
status: rascunho
atualizado: 2026-08-03
validade: —
exportavel: NAO
---

# Governança comercial — Tabela de Pedido Propetz

## Finalidade

Definir a autoridade, os controles mínimos e as pendências da Tabela de Pedido
da Distribuição. Este documento não contém tabela de preços e não autoriza
alteração de preço, promoção, estoque, margem, planilha ou automação.

## Decisão de autoridade — 03/08/2026

- Leonardo Daros define os preços e as campanhas mensais da Distribuição e do
  Varejo;
- a fonte oficial é `Dcorp\ATUALIZAR MES A MES\Tabela de Preço\Novos valores
  distribuicao (1).xlsx`, sempre na aba mensal aprovada por Leonardo;
- estoque, custos, demanda e demais indicadores copiados para essa planilha são
  fotografias auxiliares de análises separadas; suas fontes donas serão mapeadas
  gradualmente e não foram solicitadas nesta etapa.

O funcionamento da planilha está descrito em
[MAPA_LOGICA_PLANILHA_PRECOS.md](./MAPA_LOGICA_PLANILHA_PRECOS.md).

## Regra de autoridade

Um fato tem um dono. Planilha gerada, script, arquivo de IA e documento de
Marketing não se tornam fonte de preço apenas por reproduzi-lo.

| Assunto | Fonte dona atual | Papel |
|---|---|---|
| estrutura, ordem, múltiplos, barras e mínimos | `Tabela de Pedido\TABELA FOB <MÊS> <ANO> xlsx.xlsx` | fonte operacional interna da estrutura |
| preço e campanha da Distribuição e do Varejo | Leonardo Daros + planilha Dcorp, aba mensal aprovada | fonte oficial comercial |
| estoque, custos, demanda e demais indicadores auxiliares | planilhas de análise específicas — a mapear quando Leonardo as disponibilizar | fotografias copiadas; não são fatos oficiais nesta planilha |
| NCM e IPI usados nos cálculos | fonte fiscal/produto ainda a mapear | valores derivados ou copiados; validar antes de publicar |
| modelo intermediário | `_modelo_tabela.json` | derivado; nunca fonte oficial |
| pedido FOB e CIF enviado ao cliente | `Pedido Propetz Distribuição ...xlsx` | saída derivada com vigência |
| demanda e venda por SKU | Base Mãe e banco silver | evidência para decisão; não define preço |
| arquitetura de marca e linha | Marketing | define significado; não define condição comercial |
| margem financeira oficial | Financeiro — fonte ainda a confirmar | deve incluir cobertura e conceito aprovados |

Código implementa decisões; não é dono delas. `CLAUDE.md` permanece como
registro operacional legado até conversão aprovada, mas não deve receber uma
segunda cópia desta governança.

## Fotografia auditada em 03/08/2026

Escopo: arquivos de agosto existentes em `Tabela de Pedido`, auditados somente
em leitura. Esta fotografia vence em 31/08/2026.

- 140 linhas de produto disponíveis para pedido em 30 categorias;
- 148 SKUs no modelo intermediário, sem duplicidade de código;
- os preços e preços de site dos 140 SKUs compartilhados conferem com as duas
  cópias examinadas da planilha comercial;
- as cópias não são idênticas: dois SKUs aparecem apenas na cópia da Dcorp;
- 88 dos 140 produtos disponíveis estão em promoção (`62,9%`);
- 12 categorias têm todos os seus produtos em promoção;
- mediana do desconto promocional: `13,7%`; 32 promoções superam `20%`;
- nove SKUs mantêm preço antigo porque não foram encontrados no mestre mensal;
- cinco produtos disponíveis não possuem preço de site no mestre e usam
  referência anterior na aba de revenda;
- nenhum campo estruturado separa linha visual, tier comercial, função do SKU
  ou estado do ciclo de vida;
- cinco preços abaixo do Custo TRADE são queima deliberada já decidida por
  Leonardo em 22/07/2026; a auditoria não reabre essa decisão.

Não foi encontrada evidência de defasagem geral dos preços publicados. Dados
auxiliares não foram validados contra suas planilhas donas e não devem ser
tratados como atuais apenas por estarem nesta aba. O risco principal é de
governança: fallback, promoção permanente, dimensão comercial implícita e duas
cópias físicas de um arquivo confidencial.

## Comportamentos implementados a preservar até revisão

Conforme registro operacional de 22/07/2026:

- estoque zerado no mestre NÃO retira produto da tabela (decisão Leonardo,
  03/08/2026): produto em linha com reposição a caminho segue vendável; os
  zerados saem listados a cada geração e a retirada exige decisão humana
  registrada no set `RETIRADOS` do extrator, com data e motivo;
- CIF aplica `+3,5%` sobre tabela e promoção FOB;
- pagamento à vista aplica `-5%` ao total;
- revenda sugerida usa preço do site `-5%` e o piso exibido usa site `-15%`;
- promoção é aplicada desde o primeiro item, sem gatilho de pedido mínimo;
- as cinco queimas abaixo do Custo TRADE são intencionais.

Esses comportamentos não devem ser alterados silenciosamente. Mudança exige
decisão datada, responsável, vigência e teste das duas saídas FOB/CIF.

## Gate mínimo antes de publicar uma tabela

1. registrar mês, caminho, aba, data e hash da planilha comercial utilizada;
2. listar SKUs que usam preço antigo, fallback ou troca automática de variante;
3. listar produtos sem preço do site e declarar a fonte alternativa;
4. dar a cada promoção motivo, início, fim e responsável;
5. manter queima abaixo da referência de custo com motivo e critério de saída;
6. confirmar origem e data dos dados auxiliares usados na decisão;
7. confirmar IPI, fator CIF, condição à vista e texto exibido ao cliente;
8. comparar uma amostra independente da aba aprovada com FOB e CIF gerados;
9. testar quantidades, totais, promoções e fórmulas no Excel real;
10. impedir que custo, cliente ou credencial saiam no arquivo distribuído;
11. preservar os arquivos do mês anterior antes de substituir uma saída.

Falha em qualquer item bloqueia publicação até correção ou exceção aprovada.

## Campos exigidos para tornar o portfólio replicável

A estrutura comercial futura deverá distinguir, sem depender do nome do produto:

- SKU e categoria;
- linha visual e tier comercial;
- função no portfólio;
- estado do ciclo de vida;
- canal e vigência;
- preço-base, promoção e motivo;
- preço público de referência;
- fonte de custo e cobertura da margem;
- responsável e decisão que autorizou a condição.

Esta exigência é de contrato. Nenhuma coluna será adicionada às planilhas sem
projeto próprio, backup, teste paralelo, rollback e aprovação de Leonardo.

## Decisões pendentes

1. identificar e arquivar futuramente a cópia local que não é fonte canônica;
2. nomear o responsável operacional pela publicação mensal e seu substituto;
3. mapear, no ritmo definido por Leonardo, as fontes dos dados auxiliares;
4. decidir quando uma promoção recorrente vira novo preço-base;
5. definir arquitetura vigente entre linha visual e tier comercial;
6. registrar função, substituição e saída dos SKUs sobrepostos;
7. aprovar com Financeiro o conceito de margem por canal;
8. decidir se “Seu Lucro” deve ser renomeado para “spread bruto potencial” ou
   receber custos suficientes para sustentar o termo atual.

## Limite desta etapa

Esta criação registra o controle, não o executa. Nenhum preço, planilha, script,
arquivo gerado ou regra operacional foi modificado em 03/08/2026.
