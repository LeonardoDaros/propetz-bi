"""Pedidos comerciais para acompanhamento; recebe somente dados já autorizados.

Não consulta arquivos/rede nem decide acesso. O chamador prepara o recorte e
mantém os callbacks de navegação e de rascunho; nenhum contato é gravado aqui.
"""
from datetime import date, datetime
from hashlib import sha256
from html import escape
import math
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import ui_propetz as ui


STATUS = {
    "aberto": ("Em aberto · negociar", "Entenda o que falta para confirmar o pedido."),
    "aprovado": ("Aprovados · acompanhar", "Confirme o próximo passo e a previsão com a equipe."),
    "preparando_envio": ("Preparando envio", "Confira a previsão antes de orientar o cliente."),
}
FILTERS = {"Todos": None, "Em aberto": "aberto", "Aprovados": "aprovado",
           "Preparando envio": "preparando_envio"}


def _text(value, default="—"):
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return default
    if isinstance(value, float) and not math.isfinite(value):
        return default
    return str(value).strip() or default


def _number(value, digits=0):
    try:
        if isinstance(value, bool):
            return "—"
        number = float(value)
        if not math.isfinite(number):
            return "—"
    except (TypeError, ValueError, OverflowError):
        return "—"
    return f"{number:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _brl(value):
    number = _number(value, 2)
    return "R$ " + number if number != "—" else number


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _date_label(value):
    parsed = _date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else "Não informada"


def _loaded_label(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo("America/Sao_Paulo"))
        return parsed.strftime("%d/%m/%Y às %H:%M")
    except (ValueError, TypeError):
        return "data não informada"


def _row_key(row, index):
    # Número do documento sozinho pode se repetir entre empresas/unidades.
    identity = "|".join(_text(row.get(k), "") for k in ("chave", "unidade_id", "id"))
    return sha256(identity.encode("utf-8")).hexdigest()[:16] + "_" + str(index)


def _suggestion(row):
    given = _text(row.get("acao_sugerida"), "")
    if given:
        return given
    return STATUS.get(row.get("situacao"), ("", "Confira o documento com a equipe."))[1]


def _metrics(summary):
    cards = []
    for status, (title, _) in STATUS.items():
        entry = summary.get(status, {}) if isinstance(summary, dict) else {}
        entry = entry if isinstance(entry, dict) else {}
        cards.append(ui._stat_card_html(title, _brl(entry.get("valor")),
                                        _number(entry.get("quantidade")) + " documento(s)", "teal"))
    st.markdown(
        '<style>.pp-pedidos-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.8rem}'
        '@media(max-width:760px){.pp-pedidos-stats{grid-template-columns:1fr}}</style>'
        '<div class="pp-pedidos-stats">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


def _render_row(row, *, key, on_open_client, on_suggest, compact, pending=False):
    title = STATUS.get(row.get("situacao"), ("Conferir documento", ""))[0]
    name = _text(row.get("cliente_nome"), "Cliente sem vínculo confirmado")
    number, unit = _text(row.get("numero")), _text(row.get("unidade"))
    client_id = _text(row.get("cliente_id"), "")
    with st.container(border=True):
        st.markdown(
            f'<div class="agenda-kicker">{escape(title)}</div>'
            f'<div class="agenda-client">{escape(name)}</div>', unsafe_allow_html=True,
        )
        # External text uses plain text, never Markdown links or raw HTML.
        st.text(f"Documento {number} · {unit}" + (f" · Cliente {client_id}" if client_id else ""))
        created = _date(row.get("data_pedido"))
        age = row.get("idade_dias")
        if type(age) is not int or age < 0:
            age = (datetime.now(ZoneInfo("America/Sao_Paulo")).date() - created).days if created else None
        age_label = f" · {age} dia(s) desde o pedido" if age is not None and age >= 0 else ""
        st.caption(f"Pedido: {_date_label(row.get('data_pedido'))}{age_label}")
        st.caption(f"Previsão no ERP: {_date_label(row.get('data_prevista'))} · confirmar antes de prometer")
        st.text(f"Valor do documento: {_brl(row.get('valor_total'))}")
        if pending:
            reasons = row.get("motivos") or row.get("alertas") or []
            if isinstance(reasons, str):
                reasons = [reasons]
            if isinstance(reasons, list):
                for reason in reasons:
                    st.text(_text(reason))
            st.caption("Em conferência; este valor não está nos totais acima.")
        else:
            st.text("Próxima ação: " + _suggestion(row))
        alerts = row.get("alertas") if not pending else []
        if isinstance(alerts, list):
            for alert in alerts:
                st.text(_text(alert))
        if callable(on_open_client) and client_id and not compact:
            if st.button("Abrir cliente →", key=key + "_open", use_container_width=True):
                on_open_client(client_id)
        if callable(on_suggest) and client_id and compact and not pending:
            if st.button("Usar como próxima ação", key=key + "_suggest", use_container_width=True):
                on_suggest(_suggestion(row))
                st.caption("Sugestão enviada ao campo Próxima ação. Confira o formulário antes de salvar.")
        items = row.get("itens")
        with st.popover("Ver produtos do documento"):
            if not isinstance(items, list) or not items:
                st.caption("Produtos indisponíveis nesta carga.")
            else:
                rows = [{"SKU": _text(item.get("sku")), "Produto": _text(item.get("produto")),
                         "Quantidade": _number(item.get("quantidade"), 2)}
                        for item in items if isinstance(item, dict)]
                if rows:
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                else:
                    st.caption("Produtos indisponíveis nesta carga.")


def _page(rows, *, key_prefix, on_open_client, on_suggest, compact, pending=False):
    pages = max(1, math.ceil(len(rows) / 5))
    current = st.selectbox("Página dos documentos", range(1, pages + 1),
                           format_func=lambda n: f"{n} de {pages}", key=key_prefix + "_page") if pages > 1 else 1
    st.caption(f"{len(rows)} documento(s) · até 5 por página")
    for index, row in enumerate(rows[(current - 1) * 5:current * 5], start=(current - 1) * 5):
        _render_row(row, key=key_prefix + "_" + _row_key(row, index),
                    on_open_client=on_open_client, on_suggest=on_suggest, compact=compact, pending=pending)


def render_pedidos(view, *, key_prefix, on_open_client=None, on_suggest=None, compact=False):
    """Exibe um recorte autorizado; callbacks não são chamados sem clique.

    on_open_client(cliente_id): navega para a ficha. on_suggest(acao): preenche
    o rascunho da ficha atual (compact=True), sem salvar nem registrar contato.
    ``pendencias`` também deve vir autorizado; este módulo não decide papéis.
    """
    label = "Pedidos deste cliente" if compact else "Pedidos para acompanhar"
    with st.expander(label, expanded=True):
        if not isinstance(view, dict) or not isinstance(view.get("pedidos"), list):
            st.info("A consulta de pedidos está indisponível. Tente novamente mais tarde.")
            return
        loaded = _loaded_label(view.get("generated_at"))
        if view.get("stale"):
            st.warning(f"A carga de pedidos tem mais de 24 horas. Última carga: {loaded}. Confirme a situação no ERP antes de agir.")
        else:
            st.caption(f"Última carga: {loaded}")
        if view.get("coverage_start"):
            st.caption(f"Cobertura: pedidos desde {_date_label(view['coverage_start'])}.")
        st.caption("Valores dos documentos no ERP; podem incluir frete e tributos. "
                   "Não compõem o faturamento realizado nem o atingimento da meta.")
        if not compact:
            st.caption("A lista prioriza previsões vencidas no ERP e pedidos mais antigos. "
                       "Os totais consideram somente documentos sem nota fiscal vinculada localizada nesta consulta.")
        if not compact:
            _metrics(view.get("resumo"))
        rows = [row for row in view["pedidos"] if isinstance(row, dict)]
        if not compact or len(rows) > 5:
            selected = st.radio("Situação dos pedidos", FILTERS, horizontal=True,
                                 key=key_prefix + "_status")
            search = st.text_input("Buscar pedido ou cliente", key=key_prefix + "_search",
                                   placeholder="Nome, código ou número do documento")
            status = FILTERS[selected]
            term = search.strip().casefold()
            rows = [row for row in rows if (status is None or row.get("situacao") == status)
                    and (not term or term in " ".join(_text(row.get(k), "") for k in
                         ("cliente_nome", "cliente_id", "numero")).casefold())]
        if not rows:
            st.info("Nenhum pedido para acompanhar deste cliente nesta carga." if compact
                    else "Nenhum pedido neste filtro da carga disponível.")
        else:
            _page(rows, key_prefix=key_prefix, on_open_client=on_open_client,
                  on_suggest=on_suggest, compact=compact)
    pending = view.get("pendencias")
    if isinstance(pending, list):
        pending = [row for row in pending if isinstance(row, dict)]
        if pending:
            with st.expander(f"Documentos em conferência · {len(pending)}"):
                st.caption("Estes documentos precisam de conferência antes de contar como pedidos a acompanhar.")
                _page(pending, key_prefix=key_prefix + "_pending", on_open_client=on_open_client,
                      on_suggest=None, compact=compact, pending=True)
