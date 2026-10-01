"""Importação assistida de orçamentos Tiny, sem I/O nem alteração clínica.

O orçamento descreve uma referência comercial. Item comercial não prova peça
trocada, preço não prova custo e Concluído no Tiny não conclui o atendimento.
As decisões de vínculo devem ser chamadas dentro da mutação atômica do app.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import math
import re
import unicodedata
from uuid import UUID

FONTE = "tiny_orcamento"
MAX_IDADE = timedelta(hours=24)
MARCADORES_OPERACIONAIS = {"GARANTIA", "SAC", "SAC MANUTENCAO", "MANUTENCAO"}
FINALIZADOS = {"CONCLUIDA", "CANCELADA", "FINALIZADA", "DEVOLVIDA AO CLIENTE"}


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).upper().split())


class _TextoHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []
        self.oculto = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "iframe", "object"}:
            self.oculto += 1
        if not self.oculto and tag in {"p", "br", "div", "li", "tr"}:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "iframe", "object"} and self.oculto:
            self.oculto -= 1
        if not self.oculto and tag in {"p", "div", "li", "tr"}:
            self.partes.append("\n")

    def handle_data(self, text):
        if not self.oculto:
            self.partes.append(text)


def texto_sem_html(value, limite=20000):
    """Texto de fonte externa para exibir com widgets de texto, nunca HTML."""
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    parser = _TextoHTML()
    parser.feed(unescape(str(value)[:limite * 3]))
    text = unescape("".join(parser.partes)).replace("\xa0", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())[:limite]


def _tiny_id(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,24}", str(value or "")):
        raise ValueError("O orçamento está sem identificador Tiny válido.")
    if int(value) <= 0:
        raise ValueError("O identificador Tiny deve ser positivo.")
    return str(int(value))


def chave_orcamento(orcamento):
    if not isinstance(orcamento, dict):
        raise ValueError("Orçamento inválido.")
    try:
        unidade = str(UUID(str(orcamento.get("unidade_negocio_id", ""))))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("O orçamento está sem unidade de negócio válida.") from None
    return f"{unidade}:{_tiny_id(orcamento.get('tiny_id'))}"


def _instante(value):
    if isinstance(value, datetime):
        stamp = value
    elif isinstance(value, str):
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Data de atualização da fonte inválida.") from None
    else:
        raise ValueError("Data de atualização da fonte ausente.")
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Data de atualização da fonte sem fuso horário.")
    return stamp.astimezone(timezone.utc)


def _agora(agora=None):
    return _instante(agora) if agora is not None else datetime.now(timezone.utc)


def _fonte_atual(stamp, agora=None):
    age = _agora(agora) - _instante(stamp)
    if age < -timedelta(minutes=5):
        raise ValueError("A data da fonte está no futuro. Aguarde uma coleta válida.")
    if age > MAX_IDADE:
        raise ValueError("A fonte está há mais de 24 horas sem atualização. Atualize antes de importar.")


def _lista(orcamento, key):
    value = orcamento.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"A lista {key} do orçamento está inválida.")
    return value


def _marcadores(orcamento):
    return [texto_sem_html(m.get("descricao", m.get("nome", "")) if isinstance(m, dict) else m, 250)
            for m in _lista(orcamento, "marcadores")]


def _operacional(orcamento):
    return bool({_norm(m) for m in _marcadores(orcamento)} & MARCADORES_OPERACIONAIS)


def validar_snapshot(snapshot, agora=None):
    """Falha fechada em identidade duplicada; carga parcial continua legível."""
    result = {"valido": False, "disponivel": False, "atualizado": False,
              "pode_importar": False, "erros": [], "avisos": [], "orcamentos": []}
    try:
        if not isinstance(snapshot, dict) or type(snapshot.get("schema_version")) is not int or snapshot.get("schema_version") != 1:
            raise ValueError("A fonte de orçamentos ainda não está disponível em formato válido.")
        if snapshot.get("status") not in {"ok", "parcial"}:
            raise ValueError("A última coleta de orçamentos não foi concluída.")
        stamp = _instante(snapshot.get("atualizado_em"))
        budgets = snapshot.get("orcamentos")
        if not isinstance(budgets, list) or len(budgets) > 20000:
            raise ValueError("Lista de orçamentos inválida.")
        keys = set()
        for budget in budgets:
            key = chave_orcamento(budget)
            if key in keys:
                raise ValueError("A fonte contém o mesmo orçamento mais de uma vez.")
            keys.add(key)
            for collection in ("itens", "pedidos"):
                if any(not isinstance(item, dict) for item in _lista(budget, collection)):
                    raise ValueError(f"A lista {collection} contém um registro inválido.")
            _marcadores(budget)
        result.update(valido=True, disponivel=True, atualizado_em=stamp.isoformat(),
                      orcamentos=[deepcopy(b) for b in budgets if _operacional(b)])
        result["avisos"] = [texto_sem_html(v, 500) for v in snapshot.get("avisos", [])
                            if isinstance(v, str)] if isinstance(snapshot.get("avisos", []), list) else []
        if snapshot["status"] == "parcial":
            result["avisos"].append("Coleta parcial: confira a cobertura antes de procurar um orçamento ausente.")
        try:
            _fonte_atual(stamp, agora)
            result.update(atualizado=True, pode_importar=True)
        except ValueError as error:
            result["avisos"].append(str(error))
    except (ValueError, TypeError, OverflowError) as error:
        result["erros"].append(str(error))
    return result


def _numero(value):
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        result = float(number)
        return result if number.is_finite() and math.isfinite(result) and number >= 0 else None
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return None


def _campo_texto(text, nomes):
    """Extrai só rótulo explícito; texto sem rótulo permanece para conferência."""
    normalized = {_norm(n) for n in nomes}
    for line in text.splitlines():
        if ":" in line:
            label, content = line.split(":", 1)
            if _norm(label) in normalized and content.strip():
                return content.strip()
    return ""


def _familias(text):
    text = _norm(text)
    patterns = {"VOLARE": r"\bVOLARE\b", "AURA": r"\bAURA\b", "PRO7": r"\bPRO\s*7\b",
                "PRO6": r"\bPRO\s*6\b", "PROX MINI": r"\bPRO\s*X\s*MINI\b",
                "PROX": r"\bPRO\s*X\b(?!\s*MINI)", "PLUMA EVOLUTION": r"\bPLUMA\s*EVOLUTION\b",
                "PLUMA": r"\bPLUMA\b(?!\s*EVOLUTION)", "MO3": r"\bMO\s*3\b", "MO4": r"\bMO\s*4\b"}
    return {name for name, pattern in patterns.items() if re.search(pattern, text)}


def _tensoes(text):
    return set(re.findall(r"\b(110|127|220)\s*(?:V(?:OLTS?)?)?\b", _norm(text)))


def _classe_produto(text):
    text = _norm(text)
    # Uma fonte "da máquina Pluma" e uma lâmina "da Pro7" continuam acessórios.
    # A menção ao modelo não comprova que a linha representa a máquina inteira.
    for name in ("FONTE", "BATERIA", "PLACA", "CARREGADOR", "CABO", "LAMINA", "ADAPTADOR",
                 "SECADOR", "SOPRADOR", "MAQUINA", "TESOURA", "RASQUEADEIRA", "ESCOVA"):
        if re.search(rf"\b{name}\b", text):
            return name
    return ""


def _catalogo_map(catalogo):
    if not catalogo:
        return {}
    if isinstance(catalogo, dict) and "produtos" in catalogo:
        catalogo = catalogo["produtos"]
    if isinstance(catalogo, dict):
        return {str(k): texto_sem_html(v.get("nome", v.get("produto", "")) if isinstance(v, dict) else v, 400)
                for k, v in catalogo.items()}
    if isinstance(catalogo, list):
        return {str(v.get("sku", "")): texto_sem_html(v.get("nome", v.get("produto", "")), 400)
                for v in catalogo if isinstance(v, dict) and v.get("sku")}
    return {}


def _dados_origem(orcamento):
    key = chave_orcamento(orcamento)
    unidade, tiny = key.split(":", 1)
    data = {"unidade_negocio_id": unidade, "tiny_id": tiny,
            "numero_proposta": texto_sem_html(orcamento.get("numero_proposta"), 80),
            "situacao": texto_sem_html(orcamento.get("situacao"), 120),
            "data_orcamento": texto_sem_html(orcamento.get("data_orcamento"), 30),
            "data_proximo_contato": texto_sem_html(orcamento.get("data_proximo_contato"), 30),
            "contato_tiny_id": texto_sem_html(orcamento.get("contato_tiny_id"), 80),
            "contato_nome": texto_sem_html(orcamento.get("contato_nome"), 300),
            "introducao": texto_sem_html(orcamento.get("introducao")),
            "descricao_extra": texto_sem_html(orcamento.get("descricao_extra")),
            "marcadores": sorted(set(_marcadores(orcamento))),
            "valor_total_comercial": _numero(orcamento.get("valor_total")),
            "itens": [], "pedidos": []}
    for item in _lista(orcamento, "itens"):
        if not isinstance(item, dict):
            raise ValueError("Item comercial inválido.")
        data["itens"].append({"sku": texto_sem_html(item.get("sku"), 120),
                              "descricao": texto_sem_html(item.get("descricao", item.get("nome")), 600),
                              "quantidade": _numero(item.get("quantidade")),
                              "tipo": texto_sem_html(item.get("tipo"), 30),
                              "valor_unitario_comercial": _numero(item.get("valor_unitario")),
                              "valor_total_comercial": _numero(item.get("valor_total"))})
    # A posição da API nunca é persistida como identidade. Ordenar evita mudança
    # artificial de fingerprint ao Tiny retornar as mesmas linhas reordenadas.
    data["itens"].sort(key=lambda i: json.dumps(i, sort_keys=True, ensure_ascii=False))
    for pedido in _lista(orcamento, "pedidos"):
        if not isinstance(pedido, dict):
            raise ValueError("Referência de pedido inválida.")
        data["pedidos"].append({k: texto_sem_html(pedido.get(k), 250) for k in
                               ("pedido_id", "numero_pedido", "situacao_pedido", "nota_fiscal_id",
                                "tipo_vinculo", "regra_origem", "data_pedido")})
    data["pedidos"].sort(key=lambda i: json.dumps(i, sort_keys=True, ensure_ascii=False))
    return data


def preparar_orcamento(orcamento, catalogo=None):
    dados = _dados_origem(orcamento)
    intro, extra = dados["introducao"], dados["descricao_extra"]
    equipment = _campo_texto(intro, {"PRODUTO/EQUIPAMENTO", "EQUIPAMENTO", "PRODUTO"})
    report = _campo_texto(intro, {"RELATO CITADO PELO CLIENTE", "RELATO DO CLIENTE", "RELATO"})
    if not report:
        report = _campo_texto(extra, {"RELATO DO CLIENTE", "RELATO CITADO PELO CLIENTE", "RELATO"})
    text_family = _familias(equipment)
    marker_family = _familias(" ".join(dados["marcadores"]))
    item_family = _familias(" ".join(i["descricao"] for i in dados["itens"]))
    text_voltage = _tensoes(equipment)
    marker_voltage = _tensoes(" ".join(dados["marcadores"]))
    item_voltage = _tensoes(" ".join(i["descricao"] for i in dados["itens"]))
    text_class = _classe_produto(equipment)
    item_classes = {_classe_produto(i["descricao"]) for i in dados["itens"]} - {""}
    conflicts = []
    if text_family and item_family and text_family.isdisjoint(item_family):
        conflicts.append("O equipamento no texto difere dos itens comerciais. Confirme o equipamento atendido.")
    if marker_family and item_family and marker_family.isdisjoint(item_family):
        conflicts.append("Os marcadores de equipamento diferem dos itens comerciais.")
    if text_family and marker_family and text_family.isdisjoint(marker_family):
        conflicts.append("O texto e os marcadores indicam equipamentos diferentes.")
    if text_voltage and item_voltage and text_voltage.isdisjoint(item_voltage):
        conflicts.append("A tensão do equipamento no texto difere dos itens comerciais.")
    if marker_voltage and item_voltage and marker_voltage.isdisjoint(item_voltage):
        conflicts.append("A tensão nos marcadores difere dos itens comerciais.")
    if text_class and item_classes and text_class not in item_classes:
        conflicts.append("O tipo de equipamento no texto difere dos itens comerciais.")
    alerts = ["Os itens são referências comerciais: confirme as peças usadas na bancada.",
              "O contato do orçamento é uma referência; confirme quem é o cliente final e o distribuidor."]
    if _norm(dados["situacao"]) == "CONCLUIDO":
        alerts.append("Concluído no Tiny é a situação do orçamento. Confira o andamento técnico no BI.")
    if any(i["quantidade"] is None or i["quantidade"] <= 0 for i in dados["itens"]):
        alerts.append("Há item com quantidade ausente ou inválida. Confirme a quantidade atendida.")
    if not _operacional(orcamento):
        alerts.append("Orçamento sem marcador operacional de garantia, SAC ou manutenção.")
    if orcamento.get("enriquecido") is not True:
        alerts.append("O detalhe deste orçamento ainda não foi confirmado na coleta.")
    if dados["data_proximo_contato"] and dados["data_orcamento"] and dados["data_proximo_contato"] < dados["data_orcamento"]:
        alerts.append("A data de próximo contato precede o orçamento. Ela precisa de conferência.")
    catalog = _catalogo_map(catalogo)
    candidate = None
    if equipment and not conflicts and text_family and text_class:
        matching = [i for i in dados["itens"] if _familias(i["descricao"]) == text_family
                    and _classe_produto(i["descricao"]) == text_class and i["sku"] in catalog
                    and (not text_voltage or _tensoes(i["descricao"]) == text_voltage)
                    and _familias(catalog[i["sku"]]) == text_family]
        if len(matching) == 1:
            candidate = matching[0]
    multiple = len(dados["itens"]) > 1 or any((i["quantidade"] or 0) > 1 for i in dados["itens"])
    suggestion = {"texto": equipment, "sku": candidate["sku"] if candidate else "",
                  "nome": catalog[candidate["sku"]] if candidate else "", "confirmacao_obrigatoria": True}
    return {"chave_orcamento": chave_orcamento(orcamento),
            "rotulo": f"Orçamento {dados['numero_proposta'] or dados['tiny_id']} · {dados['contato_nome'] or 'Contato não informado'}",
            "referencia": f"Tiny · orçamento {dados['numero_proposta'] or dados['tiny_id']} · {dados['situacao'] or 'Sem situação'}",
            "texto_original": "\n\n".join(t for t in (intro, extra) if t),
            "introducao_texto": intro, "descricao_extra_texto": extra,
            "relato_sugerido": report, "sugestao_equipamento": suggestion,
            "campos_iniciais": {"relato": report, "produto": suggestion["nome"], "sku": suggestion["sku"]},
            "alertas": alerts, "conflitos": conflicts, "exige_unidade_atendida": True,
            "exige_confirmacao_multiplo": multiple, "equipamentos_comerciais": dados["itens"],
            "dados_origem": dados}


def chave_unidade_atendida(*, serie="", slot_manual="", confirmada=False):
    if confirmada is not True:
        raise ValueError("Confirme a identificação da unidade atendida.")
    if bool(str(serie).strip()) == bool(str(slot_manual).strip()):
        raise ValueError("Informe a série ou um identificador manual estável para esta unidade.")
    value = str(serie or slot_manual).strip()
    if len(value) > 80 or not re.fullmatch(r"[\w ./-]+", value, re.UNICODE):
        raise ValueError("Identificação da unidade inválida. Use letras, números, espaço, ponto, barra ou hífen.")
    value = _norm(value)
    return f"{'serie' if serie else 'manual'}:{value}"


def _validar_chave_unidade(value):
    if not isinstance(value, str) or ":" not in value:
        raise ValueError("Identificação estável da unidade atendida ausente.")
    kind, raw = value.split(":", 1)
    if kind not in {"serie", "manual"}:
        raise ValueError("Identificação da unidade deve usar série ou código manual.")
    return chave_unidade_atendida(serie=raw if kind == "serie" else "",
                                 slot_manual=raw if kind == "manual" else "", confirmada=True)


def preparar_contexto_importacao(orcamento, *, unidade_atendida, confirmado, atualizado_em,
                                confirmou_multiplo=False, confirmou_conflitos=False, agora=None):
    if confirmado is not True:
        raise ValueError("Confirme os dados do orçamento antes de continuar.")
    _fonte_atual(atualizado_em, agora)
    if not _operacional(orcamento) or orcamento.get("enriquecido") is not True:
        raise ValueError("O orçamento precisa estar identificado para SAC e com detalhe coletado.")
    view = preparar_orcamento(orcamento)
    dados = view["dados_origem"]
    if not dados["contato_nome"] or not (dados["introducao"] or dados["descricao_extra"]):
        raise ValueError("O orçamento está sem contato ou texto do atendimento. Aguarde uma coleta completa.")
    if not dados["itens"] or any(not i["sku"] or not i["descricao"] for i in dados["itens"]):
        raise ValueError("O orçamento precisa ter itens com SKU e descrição para importar.")
    try:
        issued = date.fromisoformat(dados["data_orcamento"])
    except ValueError:
        raise ValueError("A data do orçamento está inválida. Confira a origem antes de importar.") from None
    if issued.year < 2026 or issued > _agora(agora).date():
        raise ValueError("A importação usa orçamentos de 2026 em diante, até a data atual.")
    if any(i["quantidade"] is None or i["quantidade"] <= 0 for i in view["equipamentos_comerciais"]):
        raise ValueError("O orçamento tem quantidade comercial inválida. Corrija o cadastro na origem antes de importar.")
    if view["conflitos"] and confirmou_conflitos is not True:
        raise ValueError("Confirme a divergência entre o equipamento, os marcadores e os itens comerciais.")
    if view["exige_confirmacao_multiplo"] and confirmou_multiplo is not True:
        raise ValueError("Este orçamento tem mais de um item ou unidade. Confirme qual unidade será atendida.")
    attended = _validar_chave_unidade(unidade_atendida)
    fingerprint = sha256(json.dumps(dados, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")).encode("utf-8")).hexdigest()
    origin = {"schema_version": 1, "fonte": FONTE, "unidade_negocio_id": dados["unidade_negocio_id"],
              "tiny_id": dados["tiny_id"], "unidade_atendida": attended,
              "chave_externa": f"{chave_orcamento(orcamento)}:{attended}",
              "numero_proposta": dados["numero_proposta"], "fingerprint": fingerprint,
              "atualizado_em": _instante(atualizado_em).isoformat(), "dados": dados}
    return {"schema_version": 1, "confirmado": True, "confirmou_multiplo": confirmou_multiplo is True,
            "confirmou_conflitos": confirmou_conflitos is True,
            "origem_tiny": origin}


construir_proposta = preparar_contexto_importacao


def validar_confirmacao(contexto, agora=None):
    if (not isinstance(contexto, dict) or type(contexto.get("schema_version")) is not int
            or contexto.get("schema_version") != 1 or contexto.get("confirmado") is not True):
        raise ValueError("Confirmação da importação ausente. Abra novamente o orçamento.")
    origin = contexto.get("origem_tiny")
    if not isinstance(origin, dict) or origin.get("fonte") != FONTE:
        raise ValueError("Referência de origem inválida.")
    key = chave_orcamento(origin)
    attended = _validar_chave_unidade(origin.get("unidade_atendida"))
    if origin.get("chave_externa") != f"{key}:{attended}":
        raise ValueError("A identidade de origem mudou. Abra novamente o orçamento.")
    _fonte_atual(origin.get("atualizado_em"), agora)
    dados = origin.get("dados")
    if not isinstance(dados, dict) or chave_orcamento(dados) != key:
        raise ValueError("Os dados da origem não correspondem ao orçamento confirmado.")
    fingerprint = sha256(json.dumps(dados, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8")).hexdigest()
    if origin.get("fingerprint") != fingerprint:
        raise ValueError("Os dados da origem mudaram desde a confirmação.")
    return deepcopy(contexto)


def validar_contexto_no_snapshot(contexto, snapshot, agora=None):
    """Revalida também a publicação atual, não só a proposta aberta na tela."""
    contexto = validar_confirmacao(contexto, agora)
    validated = validar_snapshot(snapshot, agora)
    if not validated["valido"] or not validated["pode_importar"]:
        detail = validated["erros"] or validated["avisos"]
        raise ValueError(detail[0] if detail else "A fonte atual não permite importar orçamentos.")
    origin = contexto["origem_tiny"]
    key = chave_orcamento(origin)
    matches = [b for b in validated["orcamentos"] if chave_orcamento(b) == key]
    if len(matches) != 1:
        raise ValueError("O orçamento não está mais disponível nesta publicação. Recarregue a fila.")
    fresh = preparar_contexto_importacao(matches[0], unidade_atendida=origin["unidade_atendida"],
                                        confirmado=True, atualizado_em=validated["atualizado_em"],
                                        confirmou_multiplo=contexto.get("confirmou_multiplo") is True,
                                        confirmou_conflitos=contexto.get("confirmou_conflitos") is True, agora=agora)
    if fresh["origem_tiny"]["fingerprint"] != origin["fingerprint"]:
        raise ValueError("O orçamento mudou na origem. Recarregue e confira antes de salvar.")
    return fresh


def _origem_registro(registro):
    origin = registro.get("origem_tiny")
    if origin is None:
        return None
    if not isinstance(origin, dict) or origin.get("fonte") != FONTE:
        raise ValueError("Um atendimento contém uma referência Tiny inválida. Confira o vínculo existente.")
    key = chave_orcamento(origin)
    attended = _validar_chave_unidade(origin.get("unidade_atendida"))
    if origin.get("chave_externa") != f"{key}:{attended}":
        raise ValueError("Um atendimento contém identidade Tiny inconsistente. Confira antes de importar.")
    return origin


def status_ligacao(registros, orcamento, unidade_atendida=None):
    if not isinstance(registros, list) or any(not isinstance(g, dict) for g in registros):
        raise ValueError("Lista de atendimentos inválida.")
    key = chave_orcamento(orcamento)
    attended = _validar_chave_unidade(unidade_atendida) if unidade_atendida else None
    links = []
    seen = set()
    seen_ids = set()
    ambiguous = False
    for record in registros:
        if not isinstance(record.get("id"), str) or not record["id"] or record["id"] in seen_ids:
            raise ValueError("Os atendimentos precisam ter protocolos únicos antes da importação.")
        seen_ids.add(record["id"])
        origin = _origem_registro(record)
        if origin and chave_orcamento(origin) == key:
            if attended and origin["unidade_atendida"] != attended:
                continue
            external = origin["chave_externa"]
            ambiguous = ambiguous or external in seen
            seen.add(external)
            links.append({"id": record.get("id", ""), "status": record.get("status", ""),
                          "unidade_atendida": origin["unidade_atendida"]})
    return {"estado": "ambiguo" if ambiguous else "vinculado" if links else "livre",
            "vinculos": links, "total": len(links)}


def decidir_importacao(registros, contexto, *, acao="criar", target_id=None,
                       expected_version=None, version_fn=None, allow_closed=False, agora=None):
    """Recalcular em cada retry atômico, nunca com lista carregada pela tela.

    Retorna somente a decisão e a referência externa. O app mantém autorização,
    versão, histórico e todos os campos clínicos e financeiros sob seu controle.
    """
    context = validar_confirmacao(contexto, agora)
    if acao not in {"criar", "vincular", "atualizar"}:
        raise ValueError("Ação de importação inválida.")
    origin = context["origem_tiny"]
    status = status_ligacao(registros, origin, origin["unidade_atendida"])
    if status["estado"] == "ambiguo":
        raise ValueError("Esta unidade já está ligada a mais de um protocolo. Resolva o vínculo antes de importar.")
    exact = status["vinculos"]
    if acao == "criar":
        if exact:
            return {"acao": "ja_vinculado", "id": exact[0]["id"], "origem_tiny": deepcopy(origin)}
        other = status_ligacao(registros, origin)
        if other["estado"] == "ambiguo":
            raise ValueError("O orçamento possui vínculos duplicados. Confira os atendimentos existentes.")
        if other["total"] and context.get("confirmou_multiplo") is not True:
            raise ValueError("Este orçamento já tem atendimento. Confirme uma unidade adicional antes de criar outro protocolo.")
        return {"acao": "criar", "id": None, "origem_tiny": deepcopy(origin)}
    matches = [record for record in registros if record.get("id") == target_id]
    if not target_id or len(matches) != 1:
        raise ValueError("O protocolo escolhido não está disponível com um ID único.")
    current = matches[0]
    if not expected_version or not callable(version_fn) or version_fn(current) != expected_version:
        raise ValueError("O atendimento mudou desde que você abriu a ficha. Recarregue antes de vincular.")
    if _norm(current.get("status")) in FINALIZADOS and allow_closed is not True:
        raise ValueError("Este atendimento está fechado. Seu perfil precisa permitir correções pós-fechamento.")
    if exact and exact[0]["id"] != target_id:
        raise ValueError("Esta unidade já pertence a outro protocolo. Nenhum atendimento foi alterado.")
    existing = _origem_registro(current)
    if existing and existing["chave_externa"] != origin["chave_externa"]:
        raise ValueError("O protocolo já está ligado a outro orçamento ou unidade atendida.")
    if acao == "atualizar" and not existing:
        raise ValueError("O protocolo ainda não possui este vínculo. Confirme a ligação antes de atualizar.")
    unchanged = existing and existing.get("fingerprint") == origin.get("fingerprint")
    return {"acao": "ja_vinculado" if unchanged else "atualizar" if existing else "vincular",
            "id": target_id, "origem_tiny": deepcopy(origin)}
