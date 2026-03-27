# Dashboard Propetz - Distribuição

## Informações Gerais

**Arquivo**: `dashboard_propetz.html`  
**Tamanho**: 2.0 MB  
**Formato**: Single-file HTML (sem dependências de servidor)  
**Período de dados**: set/2021 a fev/2026 (54 meses)  
**Data de geração**: 27 de março de 2026

## Dados Carregados

- **516 clientes** processados e analisados
- **21,484 registros SKU** agregados em ~297 produtos únicos
- **297 produtos** com análise ABC
- Dados comprimidos e embutidos no HTML para desempenho

## Principais Funcionalidades

### Tab 1: Visão Geral
- 4 KPI cards principais: Total Receita, Receita 12m, Clientes Ativos, Ticket Médio
- Gráfico de linha: Receita mensal (54 meses - histórico completo)
- Gráfico de barras: Receita por ano (2021-2026)
- Top 15 clientes por receita total
- Distribuição de receita por vendedor (gráfico donut)
- Receita por estado com visualização de barras

### Tab 2: Visão por Cliente
- Busca e filtros em tempo real
- Tabela interativa com todos os 516 clientes
- Colunas: Nome, UF, Vendedor, Status, Receita Total, Receita 12m, Tendência, Dias sem Compra
- Clique em qualquer cliente abre painel lateral com detalhes completos
- Status de churn automaticamente detectado

### Tab 3: Mix de Produtos
- KPI cards: Total SKUs, Total Unidades, SKU Top Seller, Média SKUs/Cliente
- Gráfico: Top 20 produtos por quantidade vendida
- Curva ABC: Visualização de distribuição (A=80%, B=15%, C=5%)
- Tabela detalhada dos produtos da Curva A (maior potencial)
- Análise de variedade de produtos por cliente

### Tab 4: Gestão de Churn
- Classificação automática de clientes:
  - **Recuperação**: Sem compras há 6+ meses
  - **Atenção**: Sem compras há 3-5 meses
  - **Saudável**: Última compra ≤ 3 meses
- Dashboard com contagem de clientes por status
- Gráfico de distribuição de status (doughnut)
- Tabela de clientes em recuperação (com dias sem compra)
- Ranking de vendedores por taxa de churn

### Tab 5: Análise de Produtos
- Busca e filtros em tempo real para produtos
- Catálogo completo com 297 produtos
- Colunas: SKU, Nome, Total Qty, Clientes, Meses Ativos, Curva ABC
- Ordenação por qualquer coluna
- Classificação visual de produtos (Curva A, B, C)

## Design e UX

- **Tema**: Dark mode professional (navy/charcoal com acentos em verde esmeralda)
- **Cores**: 
  - Verde (#10ac84): Positivo, principal
  - Vermelho (#dc2626): Negativo, alerta
  - Azul (#3b82f6): Neutro, secundário
  - Laranja (#f97316): Aviso
- **Tipografia**: System fonts (Inter, SF Pro, Roboto)
- **Responsividade**: Funciona em desktop, tablet e mobile
- **Interatividade**: 
  - Cliques em linhas de clientes abrem painel lateral
  - Filtros de busca em tempo real
  - Hover effects em todos os elementos
  - Charts interativos com Chart.js

## Tecnologia

- **Charts**: Chart.js 4.4.0 via CDN
- **Dados**: Embutidos como JSON no HTML (sem necessidade de servidor)
- **Compressão**: SKU data agregada por cliente/produto para reduzir tamanho
- **Browser**: Compatível com Chrome, Firefox, Safari, Edge (últimas versões)

## Como Usar

1. Abra o arquivo `dashboard_propetz.html` em qualquer navegador
2. Navegue pelos 5 tabs no menu lateral esquerdo
3. Use a busca/filtros para encontrar clientes ou produtos específicos
4. Clique em clientes para ver detalhes em painel lateral
5. Passe mouse sobre gráficos para ver valores exatos
6. Use Ctrl+P ou Cmd+P para imprimir (estilos de impressão otimizados)

## Insights Principais Já Calculados

### Clientes
- Total de clientes: 516
- Clientes ativos (últimos 12m): 265
- Clientes em recuperação: 299
- Clientes em atenção: 48
- Clientes saudáveis: 169

### Receita
- Receita total histórica: R$ 186,8M (set/2021 a fev/2026)
- Receita últimos 12 meses: R$ 17,5M
- Ticket médio: R$ 65.9k por cliente/ano
- Crescimento YoY: Calculado automaticamente

### Produtos
- Total de SKUs únicos: 297
- Total de unidades vendidas: ~214k (jan/25 a fev/26)
- SKU mais vendido: E1RPGD-200 com 12,757 unidades
- Clientes por SKU: média de ~8 clientes

### Churn
- Taxa de churn total: ~68% (Recuperação + Atenção)
- Vendedor com melhor retenção: Analisável na aba de Churn
- Produtos de risco: Identificáveis na Curva C

## Performance

- Arquivo único de 2.0 MB
- Carregamento instantâneo (sem servidor necessário)
- Filtros e buscas em < 100ms
- Charts renderizados com WebGL quando disponível
- Otimizado para imprimir

## Notas Técnicas

- **Dados consolidados**: Os 21.484 registros SKU foram agregados para criar estrutura eficiente
- **Formato de data**: mês/ano (ex: "jan/26", "fev/25")
- **Data de referência**: fev/26 (28 de fevereiro de 2026)
- **Cálculos de tendência**: Comparação últimos 3 meses vs 3 meses anteriores
- **ABC curve**: Acumulada baseada em quantidade total de cada SKU

## Contato/Manutenção

Para atualizações futuras ou mudanças no dashboard:
1. Use o script Python `generate_dashboard.py` para processar novos dados
2. Mantenha a estrutura JSON dos dados consistente
3. As cores e estilos podem ser customizados no CSS do arquivo HTML

---

Dashboard criado em 27 de março de 2026 para Propetz Distribuição.
