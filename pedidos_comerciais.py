# -*- coding: utf-8 -*-
"""Validação e recorte da carteira de pedidos, sem I/O ou Streamlit.

O coletor confirma canal, situação fiscal e vínculo por código BI. Nomes não
são usados aqui para vincular clientes. O chamador fornece somente clientes
ativos autorizados e o vendedor da sessão autenticada, nunca um filtro livre
do navegador. Valores são nominais do ERP, separados do faturamento e metas.
"""
from datetime import date, datetime, timedelta, timezone
import math
import re

from util_comum import normalize_vendor


SITUACOES = ("aberto", "aprovado", "preparando_envio")
ACOES = {
    "aberto": "Confirmar interesse e combinar o próximo retorno.",
    "aprovado": "Conferir as pendências do pedido aprovado.",
    "preparando_envio": "Confirmar a previsão de envio com a operação.",
}
MOTIVOS = {
    "sem_vinculo": "Cliente sem vínculo confirmado com o BI.",
    "fora_carteira": "Cliente fora da carteira ativa autorizada.",
    "vendedor_divergente": "Vendedor do pedido diverge da carteira do cliente.",
    "situacao": "Situação do pedido fora das etapas acompanhadas.",
    "nf_pendente": "Nota fiscal pendente; confirmar a situação no ERP.",
    "faturado": "Pedido já identificado como faturado.",
    "revisar": "Documento fiscal exige conferência.",
}
_FISCAIS = {"sem_nf", "nf_pendente", "faturado", "revisar"}
_FUTURO_TOLERADO = timedelta(minutes=5)
_FRESCOR_MAXIMO = timedelta(hours=24)


def _texto(value, field, *, vazio=False):
    if not isinstance(value, str) or (not vazio and not value.strip()):
        raise ValueError(f"Campo de texto inválido: {field}.")
    return value.strip()


def _data(value, field, *, vazio=False):
    if vazio and (value is None or value == ""):
        return ""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"Data inválida: {field}.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError(f"Data inválida: {field}.") from None


def _instante(value, field):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"Data e hora inválidas: {field}.") from None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"Data e hora com fuso obrigatórias: {field}.")
    return value


def _agora(now):
    return datetime.now(timezone.utc) if now is None else _instante(now, "now")


def _numero(value, field):
    # bool é subclasse de int, mas não é valor monetário nem quantidade.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Número inválido: {field}.")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"Número inválido: {field}.") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"Número negativo ou não finito: {field}.")
    return number


def _item(raw):
    if not isinstance(raw, dict):
        raise ValueError("Item de pedido inválido.")
    return {
        "sku": _texto(raw.get("sku"), "sku", vazio=True),
        "produto": _texto(raw.get("produto"), "produto", vazio=True),
        "quantidade": _numero(raw.get("quantidade"), "quantidade"),
    }


def _pedido(raw, inicio, fim):
    if not isinstance(raw, dict):
        raise ValueError("Pedido inválido.")
    row = {
        field: _texto(raw.get(field), field, vazio=field in {"cliente_id", "cliente_nome", "vendedor_nome"})
        for field in ("chave", "id", "unidade_id", "unidade", "numero", "cliente_id", "cliente_nome", "vendedor_nome", "situacao")
    }
    if row["chave"] != f'{row["unidade_id"]}:{row["id"]}':
        raise ValueError("Chave do pedido não corresponde à unidade e ao ID.")
    row["data_pedido"] = _data(raw.get("data_pedido"), "data_pedido")
    if "data_prevista" not in raw:
        raise ValueError("Campo de previsão ausente.")
    row["data_prevista"] = _data(raw["data_prevista"], "data_prevista", vazio=True)
    if not inicio <= row["data_pedido"] <= fim:
        raise ValueError("Data do pedido fora da cobertura declarada.")
    row["valor_total"] = _numero(raw.get("valor_total"), "valor_total")
    row["fiscal_status"] = _texto(raw.get("fiscal_status"), "fiscal_status")
    if row["fiscal_status"] not in _FISCAIS:
        raise ValueError("Situação fiscal inválida.")
    if not isinstance(raw.get("itens"), list) or not isinstance(raw.get("alertas"), list):
        raise ValueError("Itens e alertas devem ser listas.")
    row["itens"] = [_item(item) for item in raw["itens"]]
    row["alertas"] = [_texto(alert, "alerta") for alert in raw["alertas"]]
    # O nome autorizado do cadastro do BI será usado depois do recorte.
    if row["cliente_id"]:
        row["cliente_nome"] = ""
    return row


def validate_snapshot(raw, now=None):
    """Retorna cópia canônica ou ValueError; ausência nunca significa zero.

    ``raw`` é um objeto JSON já decodificado. Datas de pedido/cobertura usam
    YYYY-MM-DD; previsão ausente é ''/null, normalizada para ''. ``generated_at`` exige fuso. Campos
    extras são descartados em todos os níveis. Qualquer chave unidade:ID
    duplicada invalida o arquivo inteiro, inclusive cópias idênticas.
    """
    if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise ValueError("Arquivo de pedidos ausente ou versão inválida.")
    if not isinstance(raw.get("generated_at"), str):
        raise ValueError("Data de geração inválida.")
    generated = _instante(raw["generated_at"], "generated_at")
    if generated > _agora(now) + _FUTURO_TOLERADO:
        raise ValueError("Arquivo de pedidos tem geração no futuro.")
    inicio = _data(raw.get("coverage_start"), "coverage_start")
    fim = _data(raw.get("coverage_end"), "coverage_end")
    if inicio > fim or fim > generated.date().isoformat():
        raise ValueError("Cobertura temporal inválida.")
    if not isinstance(raw.get("pedidos"), list):
        raise ValueError("Lista de pedidos ausente ou inválida.")
    rows, keys = [], set()
    for raw_row in raw["pedidos"]:
        row = _pedido(raw_row, inicio, fim)
        if row["chave"] in keys:
            raise ValueError("Há pedidos duplicados na mesma unidade.")
        keys.add(row["chave"])
        rows.append(row)
    try:
        total = math.fsum(row["valor_total"] for row in rows)
    except OverflowError:
        raise ValueError("Soma dos valores fora do limite numérico.") from None
    if not math.isfinite(total):
        raise ValueError("Soma dos valores fora do limite numérico.")
    return {"schema_version": 1, "generated_at": generated.isoformat(),
            "coverage_start": inicio, "coverage_end": fim, "pedidos": rows}


def _carteira(clients):
    if not isinstance(clients, list):
        raise ValueError("Carteira autorizada inválida.")
    result, seen = {}, set()
    for raw in clients:
        if not isinstance(raw, dict):
            raise ValueError("Cadastro de cliente inválido.")
        cid = _texto(raw.get("id"), "cliente.id")
        if cid in seen:
            raise ValueError("Código de cliente duplicado na carteira.")
        seen.add(cid)
        status = _texto(raw.get("status"), "cliente.status")
        name = _texto(raw.get("name"), "cliente.name")
        vendor = normalize_vendor(_texto(raw.get("vendor"), "cliente.vendor", vazio=True))
        if status == "Ativo":
            result[cid] = {"id": cid, "name": name, "vendor": vendor}
    return result


def _motivos(row, client):
    reasons = []
    if not row["cliente_id"]:
        reasons.append(MOTIVOS["sem_vinculo"])
    elif client is None:
        reasons.append(MOTIVOS["fora_carteira"])
    elif not client["vendor"] or client["vendor"] != normalize_vendor(row["vendedor_nome"]):
        reasons.append(MOTIVOS["vendedor_divergente"])
    if row["situacao"] not in SITUACOES:
        reasons.append(MOTIVOS["situacao"])
    if row["fiscal_status"] != "sem_nf":
        reasons.append(MOTIVOS[row["fiscal_status"]])
    return reasons


def scope_snapshot(snapshot, clients, role, vendor_filter, today, now=None):
    """Recorta pedidos por IDs autorizados e vendedor exato normalizado.

    ``role`` aceita admin/diretor/vendedor. Para vendedor, ``vendor_filter``
    é obrigatório e vem da sessão. Gestores podem usar None/'' para todos.
    Divergências de cliente/vendedor nunca aparecem para vendedores. Eles
    podem ver somente a conferência fiscal de uma NF pendente de seu cliente,
    sempre fora das métricas. Outros impedimentos ficam só para gestores.
    ``pendencias`` conserva o formato dos pedidos e acrescenta ``motivos``.
    """
    if not isinstance(role, str) or role not in {"admin", "diretor", "vendedor"}:
        raise ValueError("Papel sem acesso à carteira de pedidos.")
    if vendor_filter is not None and not isinstance(vendor_filter, str):
        raise ValueError("Filtro de vendedor inválido.")
    vendor = normalize_vendor(vendor_filter or "")
    if role == "vendedor" and not vendor:
        raise ValueError("Vendedor autenticado obrigatório para este acesso.")
    if isinstance(today, str):
        today = date.fromisoformat(_data(today, "today"))
    if type(today) is not date:
        raise ValueError("Data de referência inválida.")
    current = _agora(now)
    clean = validate_snapshot(snapshot, now=current)
    carteira = _carteira(clients)
    pedidos, pendencias = [], []
    for row in clean["pedidos"]:
        source_vendor = normalize_vendor(row["vendedor_nome"])
        if vendor and source_vendor != vendor:
            continue
        client = carteira.get(row["cliente_id"])
        reasons = _motivos(row, client)
        if role == "vendedor":
            # Não confiar só no vendedor que o próprio pedido declara.
            if client is None or not client["vendor"] or client["vendor"] != vendor:
                continue
            if reasons and reasons != [MOTIVOS["nf_pendente"]]:
                continue
        if client is not None:
            row["cliente_nome"] = client["name"]
        row["idade_dias"] = max(0, (today - date.fromisoformat(row["data_pedido"])).days)
        row["acao_sugerida"] = (ACOES.get(row["situacao"], "Conferir a situação do pedido no ERP.")
                                + f" Documento {row['numero']} ({row['unidade']}).")
        if reasons:
            row["motivos"] = reasons
            pendencias.append(row)
        else:
            pedidos.append(row)
    # Priorizar datas previstas vencidas e documentos antigos sem alterar
    # os retornos prometidos da agenda nem chamar previsão do ERP de prazo.
    pedidos.sort(key=lambda row: (
        0 if row['data_prevista'] and row['data_prevista'] < today.isoformat() else 1,
        -row['idade_dias'], -row['valor_total'], row['chave']))
    # Valores de pedidos independentes; não somar com faturamento/meta.
    resumo = {}
    for situacao in SITUACOES:
        selected = [row for row in pedidos if row["situacao"] == situacao]
        total = math.fsum(row["valor_total"] for row in selected)
        resumo[situacao] = {"quantidade": len(selected), "valor": round(total, 2)}
    generated = _instante(clean["generated_at"], "generated_at")
    age = max(timedelta(0), current - generated)
    return {"pedidos": pedidos, "pendencias": pendencias, "resumo": resumo,
            "generated_at": clean["generated_at"], "coverage_start": clean["coverage_start"],
            "coverage_end": clean["coverage_end"], "stale": age > _FRESCOR_MAXIMO,
            "stale_hours": round(age.total_seconds() / 3600, 2)}
