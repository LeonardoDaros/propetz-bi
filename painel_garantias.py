"""Leitura gerencial das garantias. Não grava nem altera atendimentos."""
from datetime import date, timedelta
from html import escape
import math
import textwrap

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import garantia_analytics as ga
import ui_propetz as ui


TEAL = "#00877F"
INK = "#2C2A29"
AMBER = "#A65B14"
ROSE = "#B02C3C"
BLUE = "#305D9E"
PALETTE = [TEAL, BLUE, AMBER, ROSE, "#71857D", "#9477AD", "#547889"]


def _brl(value):
    if pd.isna(value) or not math.isfinite(value):
        return "—"
    return "R$ " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _chart(fig, height=320):
    fig.update_layout(
        height=height, margin=dict(l=0, r=30, t=15, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12, color=INK),
        separators=",.", showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#E6ECE9", zeroline=False, title=None)
    fig.update_yaxes(showgrid=False, zeroline=False, title=None)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _bars(labels, values, color=TEAL, money=False):
    labels, values = list(labels), list(values)
    wrapped = ["<br>".join(escape(line) for line in textwrap.wrap(str(label), 35)) for label in labels]
    fig = go.Figure(go.Bar(
        y=list(range(len(labels))), x=values, orientation="h", marker_color=color,
        text=[_brl(v) if money else str(int(v)) for v in values], textposition="outside",
        cliponaxis=False, customdata=[[escape(str(label))] for label in labels],
        hovertemplate="%{customdata[0]}<br>%{text}<extra></extra>",
    ))
    fig.update_yaxes(tickvals=list(range(len(labels))), ticktext=wrapped, autorange="reversed")
    if not money:
        fig.update_xaxes(dtick=1 if not values or max(values) < 10 else None, tickformat="d")
    else:
        fig.update_xaxes(tickprefix="R$ ")
    _chart(fig, max(230, len(labels) * 53))


def _count_chart(frame, field, color=TEAL, limit=7):
    counts = frame[field].value_counts()
    if counts.empty:
        st.caption("Sem registros neste recorte.")
        return
    # A cauda continua representada; não some do total do gráfico.
    if len(counts) > limit:
        counts = pd.concat([counts.iloc[:limit], pd.Series({"Demais categorias": int(counts.iloc[limit:].sum())})])
    _bars(counts.index, counts.values, color)


def _note(kind, title, evidence, action):
    st.markdown(
        f'<article class="insight-card insight-{escape(kind)}">'
        f'<div class="insight-type">{escape(title)}</div>'
        f'<div class="insight-text">{escape(evidence)}</div>'
        f'<div class="insight-action">{escape(action)}</div></article>',
        unsafe_allow_html=True,
    )


def _safe_select(label, options, key, **kwargs):
    if st.session_state.get(key) not in options:
        st.session_state.pop(key, None)
    elif key in st.session_state:
        # Streamlit 1.41 recria o widget quando as opções mudam. Reafirma o
        # valor válido para preservar a escolha ao alterar o recorte.
        st.session_state[key] = st.session_state[key]
    return st.selectbox(label, options, key=key, **kwargs)


def _filters(frame):
    today = date.today()
    a, b = st.columns([1, 1])
    with a:
        period = _safe_select("Período de registro", ["Todo o histórico", "Últimos 90 dias", "Este ano", "Personalizado"], "gp_periodo")
    with b:
        channel = _safe_select("Canal de origem", ["Todos os canais"] + sorted(frame["canal"].unique()), "gp_canal")
    start = end = None
    if period == "Últimos 90 dias":
        start, end = today - timedelta(days=89), today
    elif period == "Este ano":
        start, end = date(today.year, 1, 1), today
    elif period == "Personalizado":
        value = st.date_input("De / até", value=(today - timedelta(days=89), today), max_value=today,
                              format="DD/MM/YYYY", key="gp_datas")
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            st.info("Selecione a data inicial e a final para atualizar a análise.")
            return None, None, None
        start, end = value
        if start > end:
            st.warning("A data inicial precisa vir antes da data final.")
            return None, None, None
    selected = ga.filter_frame(frame, inicio=start, fim=end,
                               canais=None if channel == "Todos os canais" else [channel])
    period_text = f"{start:%d/%m/%Y} a {end:%d/%m/%Y}" if start else "Todo o histórico"
    st.caption(f"{period_text} · {channel} · {len(selected)} casos não cancelados. "
               "O período seleciona a data de registro; status e custos refletem a situação atual desses casos.")
    channel_frame = frame if channel == "Todos os canais" else frame[frame["canal"] == channel]
    missing = int(channel_frame["criado"].isna().sum())
    if missing:
        st.caption(f"{missing} registros sem data válida: " +
                   ("incluídos no histórico, fora da evolução mensal." if start is None else "fora do período selecionado."))
    return selected, start, end


def _priorities(frame, summary):
    st.subheader("Onde agir primeiro")
    a, b, c = st.columns(3)
    top = summary.iloc[0]
    with a:
        _note("warning", "Concentração por produto",
              f"{top['produto']} · {int(top['casos'])} casos ({top['participacao']:.0%} do recorte).",
              "Abra Produtos e causas para conferir o padrão dos relatos e os diagnósticos.")
    missing = int((frame["causa"] == "Sem diagnóstico").sum())
    with b:
        diagnosed = frame[frame["causa"] != "Sem diagnóstico"]
        if diagnosed.empty or missing >= len(diagnosed):
            _note("warning", "Completar a investigação",
                  f"{missing} de {len(frame)} casos ainda sem causa registrada.",
                  "Confirme a chegada dos produtos e complete o diagnóstico dos que já passaram pela bancada.")
        else:
            cause = diagnosed["causa"].value_counts()
            _note("success", "Causa mais diagnosticada",
                  f"{cause.index[0]}: {int(cause.iloc[0])} de {len(diagnosed)} casos com diagnóstico.",
                  "Revise os registros desse grupo antes de definir a ação corretiva.")
    with c:
        parts = int((frame["status"] == "Aguardando peça").sum())
        waiting = int((frame["status"] == "Aguardando chegada").sum())
        freight = int(frame["pendente_frete"].sum())
        if parts:
            _note("danger", "Destravar o atendimento", f"{parts} casos aguardando peça.",
                  "Confira as peças e os protocolos em Operação e custos para planejar a reposição.")
        elif waiting:
            _note("warning", "Conferir as entradas", f"{waiting} casos marcados como aguardando chegada.",
                  "Valide o recebimento e atualize o status. Esse volume não comprova atraso da bancada.")
        elif freight:
            _note("warning", "Fechar os custos", f"{freight} serviços confirmados ainda aguardam o valor do frete.",
                  "Complete o frete na Bancada para finalizar o custo dos atendimentos.")
        else:
            _note("success", "Próxima decisão", "Compare volume, diagnóstico e custo por SKU.",
                  "Use os casos detalhados para orientar treinamento, reposição ou conversa com o fornecedor.")


def _product_table(summary):
    view = summary.rename(columns={"sku": "SKU", "produto": "Produto", "casos": "Casos",
        "abertos": "Em aberto", "sem_diagnostico": "Sem diagnóstico",
        "custo_registrado": "Custo informado", "custos_informados": "Com custo",
        "participacao": "Participação"}).copy()
    view["Participação"] = view["Participação"].map(lambda value: f"{value:.1%}")
    view["Custo informado"] = view["Custo informado"].map(_brl)
    st.dataframe(view[["SKU", "Produto", "Casos", "Participação", "Em aberto", "Sem diagnóstico", "Custo informado", "Com custo"]],
                 use_container_width=True, hide_index=True)
    st.caption("Custos informados acumulados dos casos, inclusive em andamento. — = nenhum valor informado. "
               "Com custo inclui valores zero; não comprova que todas as despesas foram lançadas.")


def _overview(frame, summary, start, end):
    _priorities(frame, summary)
    left, right = st.columns([1, 1])
    with left:
        st.subheader("Produtos que concentram os casos")
        metric = _safe_select("Ordenar produtos por", ["Quantidade de casos", "Custo informado"], "gp_ranking")
        cost = metric == "Custo informado"
        ranked = summary.sort_values("custo_registrado" if cost else "casos", ascending=False, kind="stable")
        if cost:
            ranked = ranked[ranked["custo_registrado"].notna()]
        top = ranked.head(8)
        if top.empty:
            st.info("Ainda não há custos informados para ordenar os produtos.")
        else:
            _bars(top["produto"] + " · " + top["sku"], top["custo_registrado" if cost else "casos"], money=cost)
            st.caption(f"{len(top)} de {len(summary)} produtos. Ranking por volume ou custo; não mede a taxa de defeito.")
    with right:
        st.subheader("Evolução dos registros")
        valid = frame["criado"].dropna()
        if valid.empty:
            st.info("Informe datas válidas para acompanhar a evolução.")
        else:
            monthly = ga.monthly_summary(frame, start or min(valid), end or date.today())
            fig = go.Figure(go.Bar(x=monthly["mes"], y=monthly["casos"], marker_color=TEAL,
                text=monthly["casos"], textposition="outside", cliponaxis=False,
                hovertemplate="%{x|%m/%Y}<br>%{y} casos registrados<extra></extra>"))
            fig.update_xaxes(tickformat="%m/%y", dtick="M1" if len(monthly) <= 12 else "M3")
            fig.update_yaxes(rangemode="tozero", tickformat="d")
            _chart(fig, max(330, min(8, len(summary)) * 53 + 68))
            st.caption("Contagem pela data de registro, com meses sem casos representados por zero. "
                       "Os meses inicial e final podem ser parciais; registros não equivalem à data em que o defeito ocorreu.")
    st.subheader("Comparar todos os produtos")
    _product_table(summary)


def _product_detail(frame, summary):
    st.subheader("Investigar um produto")
    labels = {r.sku: f"{r.produto} · {r.sku} · {int(r.casos)} casos" for r in summary.itertuples()}
    sku = _safe_select("Produto para análise", list(labels), "gp_produto", format_func=labels.get)
    current = frame[frame["sku"] == sku]
    diagnosed = current[current["causa"] != "Sem diagnóstico"]
    factory = int(current["causa"].map(lambda value: value.casefold() == "defeito de fabricação").sum())
    ui.stats_grid([
        ("Casos deste produto", len(current), f"{len(current) / len(frame):.0%} do recorte", "teal"),
        ("Com diagnóstico", f"{len(diagnosed)} / {len(current)}", "Causa registrada pela bancada", "blue"),
        ("Fabricação diagnosticada", factory, f"De {len(diagnosed)} casos com diagnóstico", "amber"),
        ("Custo informado", _brl(current["custo_registrado"].sum(min_count=1)), "Inclui casos em andamento", "rose"),
    ])
    st.caption("Fabricação considera apenas a classificação registrada pela bancada. "
               "Casos do mesmo SKU não comprovam reincidência no mesmo equipamento.")
    a, b = st.columns(2)
    with a:
        st.subheader("O que o cliente relata")
        _count_chart(current, "defeito", BLUE)
    with b:
        st.subheader("O que a bancada identifica")
        _count_chart(current, "causa", TEAL)
    st.subheader("Do relato ao diagnóstico")
    cross = pd.crosstab(current["defeito"], current["causa"])
    cross = cross.reindex(index=cross.sum(axis=1).sort_values(ascending=False).index)
    cross.index.name = "Defeito relatado"
    st.dataframe(cross, use_container_width=True)
    st.caption("Cada célula conta os casos com aquele relato e aquela causa. "
               "Sem diagnóstico permanece visível para não transformar falta de informação em conclusão.")
    st.subheader("Casos que sustentam a análise")
    _case_table(current)
    return current


def _case_table(frame):
    view = frame[["id", "sku", "produto", "status", "defeito", "causa", "criado", "custo_registrado"]].copy()
    view["criado"] = view["criado"].map(lambda v: v.strftime("%d/%m/%Y") if pd.notna(v) else "—")
    view["custo_registrado"] = view["custo_registrado"].map(_brl)
    st.dataframe(view.rename(columns={"id": "Protocolo", "sku": "SKU", "produto": "Produto", "status": "Status",
        "defeito": "Defeito relatado", "causa": "Causa diagnosticada", "criado": "Registro", "custo_registrado": "Custo informado"}),
        use_container_width=True, hide_index=True)
    st.caption("Para atualizar um atendimento, localize o protocolo na aba Bancada / Fila.")


def _operations(frame, records):
    a, b = st.columns(2)
    with a:
        st.subheader("Onde os atendimentos estão")
        _count_chart(frame, "status", BLUE)
    with b:
        st.subheader("Como os serviços terminaram")
        closed = frame[frame["encerrado"]]
        _count_chart(closed, "resultado", TEAL)
        st.caption("Inclui serviço confirmado aguardando valor de frete; o custo desse grupo ainda pode mudar.")
    st.subheader("Pendências para conferir na bancada")
    pending = frame[frame["ativo_tecnico"] | frame["pendente_frete"]].copy()
    if pending.empty:
        st.success("Nenhuma pendência neste recorte.")
    else:
        pending = pending.sort_values("dias_empresa", ascending=False, na_position="last", kind="stable")
        view = pending[["id", "produto", "status", "prioridade", "dias_empresa"]].rename(columns={
            "id": "Protocolo", "produto": "Produto", "status": "Status", "prioridade": "Prioridade",
            "dias_empresa": "Dias desde a chegada"})
        st.dataframe(view, hide_index=True, use_container_width=True)
        st.caption("Dias desde a chegada registrada, somente em atendimento técnico e com data válida. "
                   "Não é tempo na etapa atual. Em reaberturas, pode incluir o ciclo anterior. "
                   "Aguardando chegada pede conferência do recebimento; sem data, não se presume permanência na empresa.")
    st.subheader("Custo informado por resultado")
    closed = frame[frame["encerrado"]]
    costs = closed.groupby("resultado")["custo_registrado"].sum(min_count=1).dropna().sort_values(ascending=False)
    if costs.empty:
        st.info("Sem custos informados em serviços encerrados neste recorte.")
    else:
        _bars(costs.index, costs.values, ROSE, money=True)
    st.caption("Soma do custo total salvo em cada caso. Não recalcula peças ou trocas com preços atuais. "
               "Não representa despesa realizada no mês; faltam datas de cada lançamento para essa leitura.")
    st.subheader("Peças e serviços lançados")
    items = []
    for record in records:
        parts = record.get("pecas")
        for part in parts if isinstance(parts, list) else []:
            if not isinstance(part, dict):
                continue
            try:
                qty = float(part.get("qtd", 1))
                cost = float(part.get("custo"))
            except (TypeError, ValueError, OverflowError):
                cost = float("nan")
                try:
                    qty = float(part.get("qtd", 1))
                except (TypeError, ValueError, OverflowError):
                    continue
            if not math.isfinite(qty) or qty <= 0:
                continue
            items.append({"Peça / serviço": str(part.get("sku") or "Sem SKU") + " · " + str(part.get("nome") or "Sem nome"),
                          "Quantidade": qty, "Custo lançado": qty * cost if math.isfinite(cost) and cost >= 0 else float("nan")})
    if items:
        parts = pd.DataFrame(items).groupby("Peça / serviço", as_index=False).agg(
            Quantidade=("Quantidade", "sum"), **{"Custo lançado": ("Custo lançado", lambda s: s.sum(min_count=1))})
        parts = parts.sort_values("Quantidade", ascending=False, kind="stable")
        parts["Custo lançado"] = parts["Custo lançado"].map(_brl)
        st.dataframe(parts, use_container_width=True, hide_index=True)
        st.caption("Itens registrados nos casos deste recorte, inclusive em andamento. "
                   "Não é saldo de estoque nem lista de peças faltantes. Valores ausentes não usam preços atuais.")
    else:
        st.caption("Nenhuma peça ou serviço lançado nos casos selecionados.")


def _duration(records, tempo_info):
    closed_names = {"concluída": "Concluída", "devolvida ao cliente": "Concluída",
                    "confirmado — aguardando r$ frete": "Confirmado — aguardando R$ frete"}
    closed = [dict(g, status=closed_names[str(g.get("status", "")).strip().casefold()]) for g in records
              if str(g.get("status", "")).strip().casefold() in closed_names]
    tempos = [tempo_info(g) for g in closed]
    labels = {
        "chegada_envio": "⏱️ Tempo na empresa (chegada→envio)",
        "chegada_confirmacao": "⏱️ Tempo médio (chegada→confirmação)",
        "abertura_envio": "⏱️ Tempo médio (abertura→envio)",
        "abertura_confirmacao": "⏱️ Tempo médio (abertura→confirmação)",
    }
    base = next((b for b in labels if any(t["base"] == b and t["dias"] is not None for t in tempos)), None)
    valid = [t["dias"] for t in tempos if t["base"] == base and t["dias"] is not None]
    a, b = st.columns([1, 2])
    with a:
        st.metric(labels.get(base, "⏱️ Tempo médio (datas válidas)"), f"{sum(valid)/len(valid):.0f} dias" if valid else "—")
    with b:
        st.caption(f"Prazo calculado com {len(valid)} de {len(closed)} casos encerrados operacionalmente. "
                   "A média usa apenas casos com a mesma base de datas; datas ausentes, inconsistentes ou futuras não entram. "
                   "Casos ainda em atendimento não entram nessa média.")


def _sales_reference(records, products_df, meta, periodo_vendas, casos_periodo, relacao_vendas):
    with st.expander("Referência de vendas · todos os canais"):
        st.markdown("**Casos registrados × unidades vendidas**")
        st.caption("Esta comparação usa a janela própria da base de vendas e todos os canais. "
                   "Os filtros de período e canal acima não se aplicam a esta referência.")
        period = periodo_vendas(meta)
        if not period:
            st.info("Relação indisponível: a referência de vendas não informa um período e uma data de publicação válidos.")
            return
        start, end = period
        last = end - timedelta(minutes=1)
        st.caption(f"Vendas: {meta['periodo']} · Referência publicada em {meta['gerado_em']}. "
                   f"Casos registrados de {start:%d/%m/%Y} até {last:%d/%m/%Y %H:%M}, sem canceladas.")
        st.caption("O mês final pode ser parcial. A publicação não comprova a cobertura integral das vendas "
                   "ou dos registros de assistência. Esta relação não representa a taxa real de defeito dos produtos vendidos.")
        ref = ga.product_summary(ga.build_frame(casos_periodo(records, period), products_df))
        if ref.empty:
            st.info("Nenhum caso não cancelado com data de registro válida nessa referência.")
            return
        sales = meta.get("vendas_12m_todos_canais") or {}
        sales = {str(k).strip().upper(): v for k, v in sales.items()} if isinstance(sales, dict) else {}
        view = ref[["sku", "produto", "casos", "custo_registrado"]].rename(columns={
            "sku": "SKU", "produto": "Produto", "casos": "Casos", "custo_registrado": "Custo"})
        view["Unidades vendidas"] = view["SKU"].map(sales)
        view["Casos / unidades"] = view.apply(lambda r: relacao_vendas(r["Casos"], r["Unidades vendidas"]), axis=1)
        view["Casos / unidades"] = view["Casos / unidades"].map(lambda v: f"{v:.1%}" if pd.notna(v) else "—")
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.caption("— indica ausência de quantidade vendida válida. Custo soma somente os valores salvos nos casos.")


def render_painel(garantias, products_df, meta, *, role, tempo_info, periodo_vendas, casos_periodo, relacao_vendas, csv_download):
    if role not in ("admin", "diretor", "garantia", "garantia_master"):
        return
    with st.container(key="gp_painel"):
        # O download nativo da tabela ignora o serializador CSV da aplicação.
        # Neste painel, os botões explícitos abaixo são a saída para Excel.
        # A regra fica restrita ao painel e mantém busca e tela cheia das tabelas.
        st.markdown('<style>.st-key-gp_painel button[aria-label="Download as CSV"] '
                    '{display:none !important;}</style>', unsafe_allow_html=True)
        _render_content(garantias, products_df, meta, role=role, tempo_info=tempo_info,
                        periodo_vendas=periodo_vendas, casos_periodo=casos_periodo,
                        relacao_vendas=relacao_vendas, csv_download=csv_download)


def _render_content(garantias, products_df, meta, *, role, tempo_info, periodo_vendas, casos_periodo, relacao_vendas, csv_download):
    if role not in ("admin", "diretor", "garantia", "garantia_master"):
        return
    records = [g for g in garantias if isinstance(g, dict) and
               (role != "garantia" or str(g.get("status", "")).strip().casefold() != "cancelada")]
    ui.page_hero("Assistência · Inteligência de qualidade", "Entenda o problema. Direcione a ação.",
                 "Produtos, diagnósticos e pendências em uma leitura para decidir o próximo passo.",
                 "Painel de garantias · visão gerencial")
    if not records:
        st.info("Nenhuma garantia registrada ainda. Os indicadores nascem conforme o time registra.")
        return
    frame = ga.build_frame(records, products_df)
    if frame.empty:
        st.info("Nenhuma garantia não cancelada disponível para análise.")
        _export_historico(records, csv_download)
        return
    selected, start, end = _filters(frame)
    if selected is None:
        return
    if selected.empty:
        st.info("Nenhum caso para os filtros escolhidos. Amplie o período ou altere o canal.")
    else:
        diagnosed = int((selected["causa"] != "Sem diagnóstico").sum())
        closed = selected[selected["encerrado"]]
        ui.stats_grid([
            ("Casos no recorte", len(selected), f"{selected.loc[selected['sku'] != ga.MISSING_SKU, 'sku'].nunique()} SKUs identificados", "teal"),
            ("Com diagnóstico", f"{diagnosed / len(selected):.0%}", f"{diagnosed} de {len(selected)} com causa registrada", "blue"),
            ("Pendências técnicas", int(selected["ativo_tecnico"].sum()), "Inclui casos aguardando chegada", "amber"),
            ("Custo dos serviços encerrados", _brl(closed["custo_registrado"].sum(min_count=1)),
             f"Valor informado em {int(closed['custo_registrado'].notna().sum())} de {len(closed)} casos", "rose"),
        ])
        st.caption(f"{int(selected['pendente_frete'].sum())} serviços confirmados aguardam valor de frete. "
                   "Os custos desse grupo ainda são provisórios. Zero salvo não comprova custo final gratuito. "
                   "Canceladas ficam fora dos indicadores.")
        view = st.radio("Explorar a análise", ["Visão geral", "Produtos e causas", "Operação e custos"],
                        key="gp_visao", horizontal=True)
        summary = ga.product_summary(selected)
        # O motor mantém os índices de entrada mesmo após excluir canceladas e aplicar filtros.
        selected_records = [records[i] for i in selected.index]
        export_frame = selected
        if view == "Produtos e causas":
            export_frame = _product_detail(selected, summary)
        elif view == "Operação e custos":
            _operations(selected, selected_records)
        else:
            _overview(selected, summary, start, end)
        st.divider()
        _duration([records[i] for i in export_frame.index], tempo_info)
    _sales_reference(records, products_df, meta, periodo_vendas, casos_periodo, relacao_vendas)
    _export_historico(records, csv_download)
    if not selected.empty:
        export_label = "Baixar análise filtrada (CSV)"
        if view == "Produtos e causas":
            export_label = "Baixar casos deste produto (CSV)"
        export = export_frame.rename(columns={"id": "ID", "sku": "SKU", "produto": "Produto",
            "canal": "Canal", "status": "Status", "defeito": "Defeito relatado", "causa": "Causa diagnosticada",
            "resultado": "Resultado", "criado": "Data de registro", "custo_registrado": "Custo informado",
            "encerrado": "Serviço encerrado", "pendente_frete": "Frete pendente", "ativo_tecnico": "Pendência técnica",
            "dias_empresa": "Dias desde chegada", "dias_resolucao": "Dias chegada até envio", "data_envio": "Data de envio", "prioridade": "Prioridade"})
        csv_download(export, export_label, "garantias_analise.csv", "gp_export")


def _other(value, extra):
    if value == "Outro" and str(extra or "").strip():
        return f"Outro ({str(extra).strip()})"
    return str(value or "")


def _export_historico(garantias, csv_download):
    with st.expander("Exportação do histórico autorizado"):
        st.caption("Arquivo de auditoria com todo o histórico permitido ao seu perfil, sem os filtros da análise. Canceladas aparecem somente para os perfis autorizados.")
        flat = []
        for g in garantias:
            parts = g.get("pecas")
            parts = [p for p in parts if isinstance(p, dict)] if isinstance(parts, list) else []
            flat.append({"ID": g.get("id", ""), "Status": g.get("status"),
                         "Prioridade": g.get("prioridade", "Normal"),
                         "Canal": _other(g.get("canal"), g.get("canal_outro")),
                         "Cliente": g.get("cliente"), "SKU": g.get("produto_sku"),
                         "Produto": g.get("produto_nome"),
                         "Empresa NF": g.get("empresa_nf", ""),
                         "Data compra": g.get("data_compra", ""),
                         "Cliente final": g.get("cliente_final", ""),
                         "NF cliente final": g.get("cliente_final_nf", ""),
                         "Chave NF cliente final": g.get("cliente_final_nf_chave", ""),
                         "NF entrada": g.get("nf_entrada"), "NF saída": g.get("nf_saida"),
                         "Rastreio entrada": g.get("rastreio_entrada", ""),
                         "Rastreio saída": g.get("rastreio_saida", ""),
                         "Defeito": _other(g.get("defeito"), g.get("defeito_outro")),
                         "Relato": g.get("defeito_obs"),
                         "Causa": g.get("diagnostico_causa"), "Serviço": g.get("diagnostico_obs"),
                         "Data chegada": g.get("data_chegada", ""), "Data envio": g.get("data_envio", ""),
                         "Peças": "; ".join(f"{p.get('qtd',1)}x {p.get('nome','')}" for p in parts),
                         "Frete vinda": g.get("frete_vinda", 0), "Frete volta": g.get("frete_volta", 0),
                         "Sem frete (justif.)": g.get("frete_obs", ""),
                         "Custo total": g.get("custo_total"), "Resultado": g.get("resultado"),
                         "Entrada": g.get("criado_em"), "Concluída": g.get("concluido_em", ""),
                         "Registrado por": g.get("criado_por")})
        csv_download(pd.DataFrame(flat), "⬇️ Baixar garantias deste perfil (Excel/CSV)",
                      "garantias.csv", "dl_gar")
