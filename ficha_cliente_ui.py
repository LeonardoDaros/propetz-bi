"""Ficha comercial compartilhada; recebe um cliente já autorizado pelo app.

Não lê arquivos, consulta rede, grava contatos nem amplia a carteira recebida.
Os callbacks pertencem ao chamador, que mantém autorização e persistência.
"""
from datetime import date, datetime
from html import escape
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import agenda_comercial as agenda
from ficha_cliente_dados import PERIODS, build_profile, product_series
import ui_propetz as ui


VIEWS = ("Para a conversa", "Compras", "Contatos")


def _ficha_stats(items):
    """Duas colunas dentro da ficha; mantém os cartões e o escape do tema."""
    st.markdown(
        '<style>'
        '.pp-ficha-stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.8rem;margin-bottom:.6rem}'
        '.pp-ficha-stats .pp-stat{margin:0;min-height:0}'
        '.pp-ficha-stats .pp-stat-value{font-size:1.55rem}'
        '@media(max-width:760px){.pp-ficha-stats{gap:.6rem}'
        '.pp-ficha-stats .pp-stat-value{font-size:1.3rem}}'
        '</style><div class="pp-ficha-stats">'
        + ''.join(ui._stat_card_html(*item) for item in items)
        + '</div>', unsafe_allow_html=True,
    )


def _text(value, default="—"):
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return str(value).strip() or default


def _number(value, digits=0):
    try:
        value = float(value)
        if not math.isfinite(value):
            return "—"
    except (TypeError, ValueError, OverflowError):
        return "—"
    return f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _brl(value):
    formatted = _number(value, 2)
    return "R$ " + formatted if formatted != "—" else "—"


def _month(value):
    try:
        parsed = date.fromisoformat(str(value)[:7] + "-01")
    except (ValueError, TypeError):
        return "—"
    names = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
    return f"{names[parsed.month - 1]}/{parsed.year}"


def _date_label(value):
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return _text(value)


def _remember(key, widget_key):
    st.session_state[key] = st.session_state[widget_key]


def _select(label, options, key, *, radio=False, format_func=None):
    """Valor permanente por ID; o widget temporário pode sair da página.

    Reatribuir antes da criação também preserva opções válidas no Streamlit
    1.41 quando o período altera a lista de produtos.
    """
    options = list(options)
    if not options:
        return None
    current = st.session_state.get(key)
    if current not in options:
        current = options[0]
    st.session_state[key] = current
    widget_key = "_" + key
    st.session_state[widget_key] = current
    kwargs = dict(key=widget_key, on_change=_remember, args=(key, widget_key))
    if format_func is not None:
        kwargs["format_func"] = format_func
    if radio:
        return st.radio(label, options, horizontal=True, label_visibility="collapsed", **kwargs)
    return st.selectbox(label, options, **kwargs)


def _open_history(prefix):
    st.session_state[prefix + "_period"] = "all"
    st.session_state[prefix + "_view"] = "Compras"


def _card(title, body, detail="", kind="success"):
    # Somente classes fixas e texto escapado chegam ao HTML.
    kind = kind if kind in ("success", "warning", "danger") else "success"
    extra = f'<div class="insight-action">{escape(_text(detail))}</div>' if detail else ""
    st.markdown(
        f'<article class="insight-card insight-{kind}">'
        f'<div class="insight-type">{escape(title)}</div>'
        f'<div class="insight-text">{escape(_text(body))}</div>{extra}</article>',
        unsafe_allow_html=True,
    )


def _header(client, active):
    status = _text(client.get("status"), "Não informado")
    risk = _text(client.get("risk"), "Não informado")
    metadata = (f'Código {_text(client.get("id"))} · UF {_text(client.get("state"))}'
                f' · Carteira {_text(client.get("vendor"))}')
    st.markdown(
        '<div class="insight-card">'
        '<div class="insight-type">Ficha do cliente</div>'
        f'<h3 style="padding:0;margin:.2rem 0 .5rem">{escape(_text(client.get("name")))}</h3>'
        f'<div class="insight-text">{escape(metadata)}</div>'
        f'<div class="insight-action">Cadastro: {escape(status)}'
        f' · Risco comercial: {escape(risk)}</div></div>',
        unsafe_allow_html=True,
    )
    if not active:
        st.info("Cliente fora da carteira ativa: consulta disponível. O cadastro deve ser regularizado pelo fluxo administrativo existente antes de novos contatos.")


def _context(client, record, today, active, history_available):
    """Reutiliza a priorização da agenda sem criar uma nova régua de risco."""
    if not active:
        return "Consulta fora da carteira ativa", "O histórico permanece disponível para análise.", ""
    if not history_available:
        return "Histórico de contatos indisponível", "Não é possível confirmar o último combinado nesta consulta.", ""
    if record.get("encerrado") is True:
        return ("Acompanhamento encerrado", "Este acompanhamento não gera sugestão automática na agenda. O histórico foi preservado.", "")
    state = {"schema_version": 1, "clientes": {client["id"]: record} if record else {}}
    scoped_client = {**client, "valor_anual": 0}
    try:
        items = agenda.build_agenda([scoped_client], state, today)
    except (ValueError, TypeError, KeyError):
        return "Combinado não confirmado", "Revise o histórico antes de definir o próximo contato.", ""
    if items:
        item = items[0]
        return item["category"], item["reason"], item["suggested_action"]
    return ("Sem retorno programado", "Não há compromisso pendente registrado nem prioridade automática de risco para este cliente.",
            "Verificar as necessidades atuais e avaliar a reposição dos produtos já comprados.")


def _conversation(profile, record, today, active, history_available, on_suggest, prefix):
    client, metrics, history = profile["client"], profile["metrics"], profile["history"]
    last_purchase = _text(client.get("last_purchase"), "Não informada")
    if last_purchase.casefold() in ("nunca", "nan", "nat"):
        last_purchase = "Sem registro"
    _ficha_stats([
        ("Última compra informada", last_purchase, "Recência recebida da base", "teal"),
        ("Realizado · últimos 12 meses", _brl(metrics["revenue"]),
         f'{_month(profile["period"]["start"])} a {_month(profile["period"]["end"])}', "blue"),
        ("Valor histórico observado", _brl(history["revenue"]), "Série mensal disponível", "neutral"),
        ("Primeira compra observada", _month(history["first_purchase_month"]), "Dentro da série disponível", "neutral"),
    ])
    st.caption("A recência pode incluir a atualização do Silver. Sua origem individual não está identificada nesta ficha; ela não acrescenta valores à série mensal.")
    title, reason, action = _context(client, record, today, active, history_available)
    _card(title, reason, kind="warning" if title in ("Atrasados", "Recuperação", "Atenção") else "success")

    observed = metrics["months_with_purchase"]
    evidence = (f'{_number(observed)} mês(es) com compra identificados nos '
                f'{profile["period"]["count"]} meses selecionados da base.')
    if history["has_older_purchases"] and observed == 0:
        evidence = "Há compras no histórico anterior ao recorte recente. Consulte esse período para preparar a retomada."
        _card("Histórico anterior disponível", evidence)
        st.button("Ver histórico anterior aos 12 meses", key=prefix + "_older",
                  on_click=_open_history, args=(prefix,), use_container_width=True)
    if action:
        _card("Pauta para preparar a conversa", action, evidence)
        if on_suggest is not None:
            st.button("Usar pauta na próxima ação", key=prefix + "_suggest",
                      on_click=on_suggest, args=(action,), disabled=not active,
                      use_container_width=True)
            st.caption("Preenche somente a próxima ação. O resumo da conversa continua sendo escrito após o contato.")

    st.subheader("Último combinado")
    if not history_available:
        st.warning("Histórico indisponível. Isso não confirma ausência de contatos anteriores.")
        return
    events = record.get("historico", [])
    if not isinstance(events, list) or not events:
        st.caption("Nenhum contato registrado neste histórico do BI. Não há uma causa de afastamento informada.")
        return
    last = events[-1]
    if not isinstance(last, dict):
        st.warning("Não foi possível exibir o último registro. Consulte a aba Contatos.")
        return
    st.text(f'{_date_label(last.get("em"))} · {_text(last.get("canal"))} · {_text(last.get("resultado"))}')
    if last.get("observacao"):
        with st.expander("Resumo registrado", expanded=False):
            st.text(_text(last["observacao"]))
    if record.get("encerrado"):
        st.caption("Acompanhamento encerrado no último registro.")
    elif record.get("proxima_acao"):
        _card("Próxima ação combinada", record["proxima_acao"], f'Retorno: {_date_label(record.get("retorno_em"))}')


def _chart(points, field, *, key, money):
    x = [point["month"] + "-01" for point in points]
    values = [point[field] for point in points]
    labels = [_month(point["month"]) for point in points]
    fig = go.Figure(go.Bar(
        x=x, y=values, marker_color=ui.COLORS["brand"],
        customdata=[[_month(p["month"]), _brl(p[field]) if money else _number(p[field], 2)] for p in points],
        hovertemplate="%{customdata[0]}<br>%{customdata[1]}" + ("" if money else " un.") + "<extra></extra>",
    ))
    # Uma linha SKU ausente permanece None; não é desenhada como compra zero.
    fig.update_layout(
        height=300, margin=dict(l=5, r=10, t=12, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12, color=ui.COLORS["ink"]),
        separators=",.", showlegend=False,
    )
    every = max(1, math.ceil(len(points) / 8))
    fig.update_xaxes(type="date", tickvals=x[::every], ticktext=labels[::every], showgrid=False)
    fig.update_yaxes(title_text="Realizado (R$)" if money else "Quantidade (un.)", gridcolor="#E6ECE9", zeroline=False)
    st.plotly_chart(fig, key=key, use_container_width=True,
                    config={"displaylogo": False, "displayModeBar": False})


def _purchases(profile, prefix):
    period, metrics, coverage = profile["period"], profile["metrics"], profile["coverage"]
    st.caption(f'Janela desta ficha: {_month(period["start"])} a {_month(period["end"])} · '
               'independente do filtro de período da página. Os meses são os da base carregada.')
    _ficha_stats([
        ("Realizado no período", _brl(metrics["revenue"]), "Série mensal", "teal"),
        ("Meses com compra", _number(metrics["months_with_purchase"]),
         f'{metrics["months_valid"]} de {metrics["months_selected"]} meses com valor válido', "blue"),
        ("Média por mês com compra", _brl(metrics["average_purchase_month"]), "Não representa valor por pedido", "neutral"),
        ("Frequência mensal", (_number(metrics["frequency_pct"], 1) + "%") if metrics["frequency_pct"] is not None else "—",
         "Meses com compra / meses do recorte", "neutral"),
    ])
    if profile["monthly_series"]:
        _chart(profile["monthly_series"], "revenue", key=prefix + "_revenue_chart", money=True)
    else:
        st.info("Nenhum mês disponível para este recorte.")

    st.subheader("Produtos no mesmo período")
    st.caption("Quantidades registradas por SKU. A fonte de produtos não comprova cobertura integral de todos os meses; ausência de linha significa sem registro, não compra zero.")
    products = profile["products"]
    if not coverage["sku_available"]:
        st.info("Base de produtos indisponível nesta consulta. O histórico mensal continua acessível.")
        return
    if not products:
        st.info("Nenhum produto registrado para este cliente no período selecionado. Isso não comprova ausência de compra.")
        if profile["history"]["has_older_purchases"] and period["key"] != "all":
            st.button("Consultar todo o histórico", key=prefix + "_products_older",
                      on_click=_open_history, args=(prefix,), use_container_width=True)
        return
    rows = [{"SKU": p["sku"], "Produto": p["product"], "Quantidade (un.)": p["quantity"],
             "Meses com compra": p["months_with_purchase"],
             "Último mês registrado": _month(p["last_purchase_month"])} for p in products]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"Quantidade (un.)": st.column_config.NumberColumn(format="%.2f")})
    names = {p["sku"]: p["product"] for p in products}
    selected_sku = _select("Explorar um produto", names, prefix + "_sku",
                           format_func=lambda sku: f'{sku} · {names[sku]}')
    series = product_series(profile, selected_sku)
    if series:
        _chart(series, "quantity", key=prefix + "_sku_chart", money=False)
    st.caption("A evolução usa quantidades. Não há receita atribuída ao produto a partir de preços de referência.")


def render_ficha_cliente(client, df_sku, months, record, today, *, active=True,
                         on_suggest=None, history_available=True, render_history=None):
    """Renderiza a ficha; o app fornece o cliente escopado e mantém o formulário.

    on_suggest(action): callback de botão; deve alterar apenas o rascunho da
    próxima ação do cliente atual. render_history(record, cid): renderização
    do histórico e exportação segura já existentes no app. Retorna o perfil
    exibido para facilitar testes sem efeitos persistentes.
    """
    try:
        client = dict(client)
        raw_id = client.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise ValueError("Código de cliente ausente.")
        cid = raw_id.strip()
        client["id"] = cid
        client_frame = pd.DataFrame([client])
        overview = build_profile(client_frame, cid, months, df_sku, period="12m")
    except (ValueError, TypeError, KeyError):
        st.warning("Não foi possível identificar este cliente na base autorizada. Selecione novamente o código.")
        return None
    if isinstance(today, datetime):
        today = today.date()
    if not isinstance(record, dict):
        history_available = False
        record = {}
    prefix = "ficha_" + cid
    _header(overview["client"], active)
    view = _select("Área da ficha", VIEWS, prefix + "_view", radio=True)
    if view == "Para a conversa":
        _conversation(overview, record, today, active, history_available, on_suggest, prefix)
        profile = overview
    elif view == "Compras":
        selected_period = _select("Período das compras", PERIODS, prefix + "_period", format_func=PERIODS.get)
        profile = overview if selected_period == "12m" else build_profile(client_frame, cid, months, df_sku, period=selected_period)
        _purchases(profile, prefix)
    else:
        profile = overview
        if not history_available:
            st.warning("Histórico de contatos indisponível nesta consulta. Tente novamente antes de registrar um novo contato.")
        elif render_history is not None:
            render_history(record, cid)
        else:
            st.caption("O histórico de contatos é apresentado pelo módulo da agenda.")
    warnings = profile.get("warnings", [])
    if profile["metrics"]["months_valid"] < profile["metrics"]["months_selected"]:
        st.warning("Há valores mensais ausentes ou inválidos ainda identificáveis neste recorte. Indicadores incompletos aparecem como ‘—’ e as lacunas não viram zero no gráfico.")
    elif profile["coverage"].get("monthly_invalid_count", 0):
        st.caption("Há lacunas identificáveis em meses anteriores. O total histórico está indisponível; os indicadores do recorte atual usam seus meses válidos.")
    if warnings:
        with st.expander("Referência e limites dos dados", expanded=False):
            for warning in dict.fromkeys(warnings):
                st.text(warning)
    return profile
