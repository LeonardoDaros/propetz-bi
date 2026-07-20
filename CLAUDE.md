# CLAUDE.md — Propetz BI (Distribuição)

> Última consolidação: 2026-06-10

## O que é este projeto

Dashboard BI do canal **Propetz Distribuição (PD)** em Streamlit, publicado em **https://propetz-bi.streamlit.app** (repo GitHub privado `propetz-bi`, deploy via Streamlit Cloud). Usuários: Leonardo (admin) + vendedores (Cristiane, Emanuel, Yasmin). Dados: 516 clientes, ~297 produtos, set/2021 a fev/2026.

## Arquivos principais

- `app.py` (~2.400 linhas) — aplicação completa em arquivo único. Seções: config/CSS → users (YAML) → rate limit → access log → clientes inativos → auto-login → login → `load_data()`/`process_excel()` → helpers de formatação → páginas.
- `users.yaml` — usuários e senhas (hash). Credenciais de referência em `COMO-USAR.md`. NÃO commitar/expor.
- `Relatorio Distribuidores Mensal.xlsx` — planilha-fonte lida por `load_data()`. Atualizada pelo Leonardo via página Admin do app (upload).
- `Qtd_Comprada_Por_Cliente_RECONSTRUIDA.xlsx` — base SKU×cliente reconstruída (blocos: Produto, SKU, Quantidade, Vendedor, Cliente, Código).
- `inactive_clients.json`, `access_log.json`, `login_attempts.json` — estado persistido do app.
- `inactive_requests.json` — fluxo de inativação com aprovação: vendedor E diretora SUGEREM (Minhas Ações/Churn, e a diretora também direto na tabela do Painel do Gestor); só o admin aprova/rejeita/reativa/inativa direto. Permissões: `has_full_data_access()` (admin+diretor, vê tudo) ≠ `can_approve_inactivations()` (só admin). Não colar esses dois conceitos de novo nem reabrir a brecha de inativar direto. Toda inativação carrega MOTIVO obrigatório (`MOTIVOS_INATIVACAO`, selectbox `index=None`) + observação livre, via `_inativacao_form()` (form por cliente); vira banco de dados no Painel do Gestor ("Histórico de inativações e motivos", com resumo por motivo + CSV). Seleção inline de tabela é clampada a índices válidos (anti-crash em rerun).

## Persistência no Streamlit Cloud (não regredir!)

O disco do Streamlit Cloud é efêmero — era a causa do app "cair" todo dia (planilha enviada via Admin sumia a cada restart do container). Arquitetura desde 2026-06-10:

- **Planilha** commitada no repo — o `.gitignore` NÃO pode voltar a ter `*.xlsx`. Upload pela página Admin também commita no branch `main` via API do GitHub.
- **Estado** sincronizado com o branch `state` do repo. **O GitHub é a FONTE DA VERDADE** das inativações: `load_inactive_clients()`/`load_inactive_requests()` leem o remoto via `_read_state_json` (memo `_STATE_RAW_CACHE` por rerun, limpo no `main()`); fallback local. Mutações são ATÔMICAS via `_gh_mutate_json` (read-modify-write sob `_GH_WRITE_LOCK` + SHA do GitHub + retry em 409): use `inactivate_clients`/`reactivate_clients`/`add_inactivation_request`/`decide_inactivation_request` — NUNCA voltar ao padrão `load→modifica→save_inactive_clients` (não-atômico: causou perda de dados em 2026-06-17, boot incompleto + overwrite cego, e race entre abas). O `access_log.json` (frequência de uso: quem/quando/páginas, NÃO duração) também é blindado: lê do GitHub e grava por APPEND ATÔMICO (`_append_access_log_entry` → `_gh_mutate_json`) em thread (não trava navegação). Painéis que leem o log toleram log vazio/malformado (checam colunas action/date). `users.yaml` ainda usa `_push_state_file` assíncrono (mudança rara, via Admin). `_sync_state_from_github()` (boot) só prima o fallback local.
- Requer `GITHUB_TOKEN` (escopo repo) nos secrets do Streamlit Cloud — instruções no `COMO-USAR.md`. Sem token, degrada graciosamente para só-local (sem persistência entre restarts).
- **Arquivos de estado >1MB** (auditoria 2026-07-20): a API contents do GitHub devolve 200 com `content:""`/`encoding:"none"` (e sha VÁLIDO) para arquivos de 1–100MB — sem tratamento isso lia o estado como vazio e a próxima gravação sobrescrevia tudo. `_gh_get_file` refaz o GET com `Accept: application/vnd.github.raw+json` nesse caso (`so_sha=True` pula o corpo, p/ PUT); `_gh_mutate_json` ABORTA (ok=False, sem PUT) se o remoto existe mas está ilegível — nunca aplicar mudanças sobre default segurando sha válido. Corpo remoto gravado COMPACTO (`separators=(",",":")`); histórico de garantia com teto de 300 eventos. Não regredir nenhuma dessas 4 defesas.
- `_gh_token()` limpa aspas/espaços do valor (erro de colagem comum); escritas de estado são serializadas por `_GH_WRITE_LOCK` (evita corrida read-SHA/PUT); `_gh_put_file` relê o sha e tenta 1x mais em 409/422 (PUTs concorrentes no mesmo branch). Página Admin tem botão "Testar conexão com o GitHub" (`_gh_diagnose()`) que reporta passo a passo onde a persistência quebra (token ausente/inválido/sem acesso ao repo/falha de escrita). Banner vermelho no topo alerta admin/diretor quando não há token.
- `deploy.bat` / `setup.bat` — fluxo de deploy em 1 clique (commit + push → Streamlit Cloud atualiza em ~1 min).
- **Para o Claude: NUNCA usar `git worktree` neste repo** (o OneDrive trava `.git/worktrees/*` e o deploy do Leonardo passa a perguntar "Deletion of directory failed. Should I try again?" — aconteceu 2x, jul/2026). Para escrever no branch `state` sem token: `git clone --depth 1 --branch state <remote> %TEMP%\pasta` → editar → push de lá → apagar a pasta. Se o prompt aparecer no deploy: responder `n` e remover `.git\worktrees\<nome>` com `cmd /c rmdir /s /q`.
- `AUDIT_REPORT.txt` — auditoria completa de 2026-03-27 (status: PASS).

## Páginas do app

Navegação por papel: admin/diretor abrem no `page_manager` (Painel do Gestor: mês vs histórico, YTD, desempenho/cobertura por vendedor, top recuperações, adoção do BI); vendedores abrem no `page_actions` (contatos prioritários + ofertas com R$ potencial/mês, export CSV). Demais: `page_overview` (insights no topo), `page_clients`, `page_mix` (redesenhada 2026-06-10: oportunidades "não compra"/"compra pouco" priorizadas por R$ potencial = qtd típica mediana × preço médio real, materialidade mín. R$ 100/mês; raio-x do cliente em valor), `page_churn`, `page_products` (curva por faturamento + análise de gap global admin), `page_admin`. Estimativas em R$ usam `_preco_medio_map()` (faturamento÷qtd 12m do abc_valor.json) e `_sku_stats()` (mediana/compradores por SKU).

Impacto financeiro de churn/risco usa `annual_value_estimate()` (ticket médio dos últimos 12 meses × 12) — não reintroduzir cálculos com anos fixos ('2024'/'2023').

**Módulo Garantias** (2026-07-20): `page_garantias` (Nova/Bancada/Painel) registra o que a NF não conta — defeito relatado, causa diagnosticada, peças trocadas (custo auto da Base Mãe) e serviços (Afiação/Mão de obra com R$ manual), resultado, NFs, datas de chegada/envio, fretes vinda/volta. Ciclo: Aguardando chegada → Em bancada → Aguardando peça → Confirmado—aguardando R$ frete (exige causa+resultado) → Concluída (exige também fretes ou justificativa). `_STATUS_LEGADO` migra nomes antigos ao carregar. Bancada tem sub-abas por status (keys de widget prefixadas por sub-aba — a mesma garantia renderiza em várias abas; não remover o prefixo `tk`). Rótulos das sub-abas são FIXOS (contagem via caption dentro da aba): rótulo dinâmico faz o st.tabs voltar pra 1ª aba a cada save. Sub-aba Canceladas (e Cancelada em "Todas") só aparece p/ master/admin/diretor. Canal Distribuição exige no registro o CLIENTE FINAL + NF da venda distribuidor→cliente (sem nota não aceitamos garantia) + chave de acesso opcional (44 dígitos, completável na Bancada); ao escolher o distribuidor no selectbox, o campo Cliente autopreenche (on_change), e no submit o TEXTO visível prevalece sobre a seleção. Anexos por garantia (`anexar_documento_garantia`, máx 8MB, binário em `anexos/<gid>/` no branch state, caminho com microssegundos; uploader com nonce `axv_` na key p/ esvaziar após sucesso + flash `gar_flash_bancada`). Persistência atômica em `garantias.json` (branch state). Papéis: `garantia` (Marcos, Pedro — operam o dia a dia; garantia FINALIZADA vira somente-leitura e "Cancelada" não aparece pra eles) e `garantia_master` (Jackson — reabre/corrige/cancela finalizadas via `can_edit_garantia_fechada()`, junto com admin; correção pós-fechamento marca o histórico). Ambos veem SÓ essa página; admin/diretor também acessam. Registro NUNCA é excluído (Cancelada = exclusão lógica com rastro). Categorias padronizadas em `DEFEITOS_GARANTIA`/`CAUSAS_GARANTIA`/`RESULTADOS_GARANTIA` (editar lá se a bancada pedir novas). Referências cruzadas vêm do `abc_valor.json` (chaves `vendas_12m_todos_canais` p/ taxa de garantia por SKU e `custo_unitario` = cmv mais recente da Base Mãe) — geradas pelo `atualizar_abc_valor.py` no deploy. Registro não se apaga: status Cancelada.

## Lógica de negócio (não alterar sem confirmar)

- **Churn:** Recuperação = 6+ meses sem compra | Atenção = 3-5 meses | Saudável = ≤3 meses.
- **Curva ABC:** A = 80% da receita, B = 15%, C = 5%. Desde 2026-06-10 calculada pelo APP (`apply_abc_by_value`) por **faturamento** do canal Distribuição (últimos 12m), via `abc_valor.json` — gerado da Base Mãe pelo `atualizar_abc_valor.py` (o `deploy.bat` roda automaticamente). A coluna "Curva ABC QTD." da planilha NÃO é mais usada (regra dela era share individual por quantidade — errada; classificava a PRO X Preta, 3º produto em faturamento, como B). Produtos sem venda no período = C.
- **`normalize_vendor()`** — unificação de carteiras de vendedores (mapeamento no topo da função `load_data`). Ao mudar vendedor de carteira, atualizar aqui.
- **`has_full_data_access()`** — vendedores veem dados restritos; admin vê tudo. Preservar essa separação em qualquer página nova.

## Regras de trabalho

1. **Nunca quebrar autenticação** — login, rate limit e access log são requisitos. Testar login após qualquer mudança estrutural.
2. **Dados sensíveis** — receita por cliente/vendedor. Repo é privado; nunca colocar dados ou senhas em código.
3. **Deploy** — alterações só entram no ar após Leonardo rodar `deploy.bat`. Avisar quando uma mudança exigir deploy.
4. **Interface em pt-BR**, valores em R$ (`fmt_brl`), identidade visual Propetz (teal/azul).
5. **Mudança em `process_excel()`** exige validar contra a planilha real — estrutura de blocos da planilha SKU é frágil. Pegadinha conhecida (jul/26): o Excel converte cabeçalho de mês digitado ("MAR/26") em datetime; o parser aceita os DOIS formatos (str com "/" e datetime) — manter assim, senão blocos novos são pulados em silêncio.

## Contexto de negócio

ProPetz (Grupo Daros) vende equipamentos profissionais de grooming PET. Este dashboard cobre o canal Distribuição (B2B para pet shops/distribuidores) — distinto do dashboard de demanda/estoque (pasta `Demanda Curva abc`, canais PD/PV/VE/NR). Objetivo central: dar visibilidade de churn e mix por cliente para o time comercial agir.
