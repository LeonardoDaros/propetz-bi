"""Coleta local de orçamentos SAC do Silver, sem publicar ou alterar atendimentos.

Itens e preços são comerciais. Não representam peças trocadas nem custos.
Situação do Tiny e referências fiscais não alteram o status técnico do SAC.
Credenciais são acessadas apenas pela ponte existente, fora deste repositório.
"""
import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import tempfile
from uuid import UUID

BASE = Path(__file__).resolve().parent
SAIDA = BASE / "silver_orcamentos_garantias.json"
MARCADORES_OPERACIONAIS = frozenset(("GARANTIA", "SAC", "SAC MANUTENÇÃO", "MANUTENÇÃO"))
FILIAL_FOZ = "fc97d781-d6d4-433d-94c3-7ceabb1b425a"
LIMITE_ORCAMENTOS = 10000
LIMITE_DETALHES = 100000
LIMITE_ARQUIVO = 12 * 1024 * 1024
LIMITE_TEXTO = 50000


class _TextoHTML(HTMLParser):
    """Mantém somente conteúdo textual; elimina blocos executáveis e atributos."""
    proibidos = {"script", "style", "iframe", "object", "embed", "svg", "math", "noscript"}
    quebras = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []
        self.bloqueados = []

    def handle_starttag(self, tag, attrs):
        if tag in self.proibidos:
            self.bloqueados.append(tag)
        if not self.bloqueados and tag in self.quebras:
            self.partes.append("\n")

    def handle_startendtag(self, tag, attrs):
        if not self.bloqueados and tag in self.quebras:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if self.bloqueados:
            if tag == self.bloqueados[-1]:
                self.bloqueados.pop()
        elif tag in self.quebras:
            self.partes.append("\n")

    def handle_data(self, data):
        if not self.bloqueados:
            self.partes.append(data)


def texto_seguro(valor):
    """HTML vira texto e os identificadores pessoais usuais são suprimidos.

    Não é uma classificação automática de relato/diagnóstico. O texto restante
    continua sendo referência da origem, exibida como texto pelo aplicativo.
    """
    if valor is None:
        return ""
    if not isinstance(valor, (str, int, float, Decimal)) or isinstance(valor, bool):
        raise ValueError("Texto de origem inválido.")
    bruto = str(valor)
    if len(bruto) > LIMITE_TEXTO:
        raise ValueError("Texto de origem excedeu limite seguro.")
    parser = _TextoHTML()
    parser.feed(bruto)
    parser.close()
    texto = "".join(parser.partes)
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)
    texto = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[e-mail suprimido]", texto)
    texto = re.sub(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)", "[CNPJ suprimido]", texto)
    texto = re.sub(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)", "[identificador pessoal suprimido]", texto)
    texto = re.sub(r"(?<!\d)(?:\+?55[ .-]*)?\(?[1-9]\d\)?[ .-]*(?:9[ .-]*)?\d{4}[ .-]*-?[ .-]*\d{4}(?!\d)", "[telefone suprimido]", texto)
    texto = re.sub(r"(?<!\d)\d{5}-\d{3}(?!\d)", "[CEP suprimido]", texto)
    linhas = []
    for linha in texto.splitlines():
        linha = re.sub(r"[ \t\u00a0]+", " ", linha).strip()
        # Endereços e contatos por rótulo ficam fora do snapshot publicado.
        if re.search(r"(?i)\b(?:endere[çc]o|logradouro|bairro|complemento do endere[çc]o|cep|cpf|cnpj|e-?mail|telefone|celular|whats(?:app)?)\s*[:=]", linha):
            linha = re.sub(r"(?i)\b(?:endere[çc]o|logradouro|bairro|complemento do endere[çc]o|cep|cpf|cnpj|e-?mail|telefone|celular|whats(?:app)?)\s*[:=].*$", "[dado pessoal suprimido]", linha)
        if re.search(r"(?i)\b(?:rua|r\.|avenida|av\.|rodovia|estrada|travessa|alameda)\s+", linha):
            linha = re.sub(r"(?i)\b(?:rua|r\.|avenida|av\.|rodovia|estrada|travessa|alameda)\s+.*$", "[endereço suprimido]", linha)
        if linha:
            linhas.append(linha)
    return "\n".join(linhas)


def _id(valor, *, opcional=False):
    if opcional and valor in (None, "", 0, "0"):
        return ""
    if isinstance(valor, bool):
        raise ValueError("Identificador de origem inválido.")
    ident = str(valor).strip()
    if not re.fullmatch(r"[1-9]\d{0,19}", ident):
        raise ValueError("Identificador de origem inválido.")
    return ident


def _unidade(valor):
    try:
        return str(UUID(str(valor)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Unidade de origem inválida.") from None


def _data(valor, *, opcional=False):
    if opcional and valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        valor = valor.date()
    try:
        return date.fromisoformat(str(valor)).isoformat()
    except (ValueError, TypeError):
        raise ValueError("Data de origem inválida.") from None


def _numero(valor, *, positivo=False, opcional=False):
    if opcional and valor in (None, ""):
        return None
    if isinstance(valor, bool):
        raise ValueError("Valor de origem inválido.")
    try:
        num = Decimal(str(valor))
        if not num.is_finite() or num < 0 or (positivo and num <= 0) or num > Decimal("1000000000000"):
            raise ValueError
        resultado = float(num)
        if not math.isfinite(resultado):
            raise ValueError
        return resultado
    except (ValueError, TypeError, InvalidOperation, OverflowError):
        raise ValueError("Valor de origem inválido.") from None


def _json_canonico(valor):
    return json.dumps(valor, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _fingerprint(orcamento):
    conteudo = {k: v for k, v in orcamento.items() if k not in ("fingerprint", "id")}
    return hashlib.sha256(_json_canonico(conteudo).encode("utf-8")).hexdigest()


def _colecao(linhas, limite):
    if not isinstance(linhas, (list, tuple)) or len(linhas) > limite or any(not isinstance(l, dict) for l in linhas):
        raise ValueError("Coleção de origem inválida ou fora do limite seguro.")
    return linhas


def montar_snapshot(orcamentos, itens, marcadores, pedidos, *, generated_at=None,
                    atualizado_em=None, coverage_start="2026-01-01", coverage_end=None,
                    unidades=None):
    """Normalização pura; linhas de origem são substituíveis, sem identidade por posição."""
    _colecao(orcamentos, LIMITE_ORCAMENTOS)
    for linhas in (itens, marcadores, pedidos):
        _colecao(linhas, LIMITE_DETALHES)
    horario = atualizado_em or generated_at
    try:
        instante = datetime.fromisoformat(str(horario).replace("Z", "+00:00"))
        if instante.tzinfo is None:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("Horário de coleta completa inválido.") from None
    inicio = _data(coverage_start)
    fim = _data(coverage_end or instante.date())
    if inicio < "2026-01-01" or inicio > fim:
        raise ValueError("Recorte de origem inválido.")
    headers, lake_keys = {}, {}
    for linha in orcamentos:
        unidade, tiny = _unidade(linha.get("unidade_negocio_id")), _id(linha.get("tiny_id"))
        chave = f"{unidade}:{tiny}"
        lake = _id(linha.get("id"))
        data = _data(linha.get("data_orcamento"))
        if not inicio <= data <= fim or chave in headers or (unidade, lake) in lake_keys:
            raise ValueError("Cabeçalhos duplicados ou fora do recorte; versão anterior preservada.")
        headers[chave] = (linha, unidade, tiny, lake, data)
        lake_keys[(unidade, lake)] = chave

    def pai(linha):
        unidade = _unidade(linha.get("unidade_negocio_id"))
        tiny = _id(linha.get("orcamento_tiny_id"))
        chave = f"{unidade}:{tiny}"
        lake = _id(linha.get("orcamento_id"))
        if chave not in headers or lake_keys.get((unidade, lake)) != chave:
            raise ValueError("Detalhe não pertence ao cabeçalho da mesma unidade.")
        if texto_seguro(linha.get("numero_proposta")) != texto_seguro(headers[chave][0].get("numero_proposta")):
            raise ValueError("Número de proposta divergente no detalhe.")
        return chave

    item_map, marker_map, order_map = defaultdict(list), defaultdict(set), defaultdict(list)
    problemas = defaultdict(set)
    for linha in marcadores:
        chave = pai(linha)
        descricao = texto_seguro(linha.get("descricao")).strip()
        if descricao:
            marker_map[chave].add(descricao)
    for linha in itens:
        chave = pai(linha)
        produto_id = _id(linha.get("produto_tiny_id"), opcional=True)
        item = {"produto_tiny_id": produto_id, "sku": texto_seguro(linha.get("sku")),
                "descricao": texto_seguro(linha.get("descricao")), "tipo": texto_seguro(linha.get("tipo")),
                "unidade": texto_seguro(linha.get("unidade"))}
        item["nome"] = item["descricao"]
        for campo in ("quantidade", "valor_unitario", "desconto", "valor_total"):
            try:
                item[campo] = _numero(linha.get(campo), positivo=(campo == "quantidade"), opcional=(campo != "quantidade"))
            except ValueError:
                item[campo] = None
                problemas[chave].add(f"ITEM_{campo.upper()}_INVALIDO")
        if not item["sku"] or not item["descricao"]:
            problemas[chave].add("ITEM_SEM_IDENTIFICACAO")
        # id e item/posição não entram no conteúdo nem no fingerprint.
        item_map[chave].append(item)
    for linha in pedidos:
        chave = pai(linha)
        unidade = headers[chave][1]
        if unidade != FILIAL_FOZ or linha.get("tipo_vinculo") != "REGRA_NEGOCIO" or linha.get("regra_origem") not in ("OS_ESTRITA", "OS_VARIANTE"):
            raise ValueError("Vínculo operacional fora do contrato validado.")
        pedido = {"pedido_id": _id(linha.get("pedido_id")), "numero_pedido": texto_seguro(linha.get("numero_pedido")),
                  "data_pedido": _data(linha.get("data_pedido"), opcional=True),
                  "situacao_pedido": texto_seguro(linha.get("situacao_pedido")),
                  "nota_fiscal_id": _id(linha.get("nota_fiscal_id"), opcional=True),
                  "tipo_vinculo": "REGRA_NEGOCIO", "regra_origem": linha["regra_origem"]}
        if any(p["pedido_id"] == pedido["pedido_id"] for p in order_map[chave]):
            raise ValueError("Referência de pedido duplicada na mesma unidade/orçamento.")
        order_map[chave].append(pedido)

    rows = []
    enriquecidos = com_itens = 0
    for chave, (linha, unidade, tiny, lake, data) in headers.items():
        contato = texto_seguro(linha.get("contato_nome"))
        introducao = texto_seguro(linha.get("introducao"))
        descricao_extra = texto_seguro(linha.get("descricao_extra"))
        marks = sorted(marker_map[chave])
        detalhes = bool(contato and (introducao or descricao_extra) and marks)
        enriquecidos += int(detalhes)
        com_itens += int(bool(item_map[chave]))
        # Classificação somente por marcador completo: marca e palavra solta não contam.
        if not MARCADORES_OPERACIONAIS.intersection(marks):
            continue
        pendencias = problemas[chave]
        if not contato:
            pendencias.add("CONTATO_AUSENTE")
        if not (introducao or descricao_extra):
            pendencias.add("TEXTOS_AUSENTES")
        if not item_map[chave]:
            pendencias.add("ITENS_AUSENTES")
        proximo = None
        try:
            proximo = _data(linha.get("data_proximo_contato"), opcional=True)
            if proximo and proximo < data:
                pendencias.add("PROXIMO_CONTATO_ANTERIOR_AO_ORCAMENTO")
                proximo = None
        except ValueError:
            pendencias.add("PROXIMO_CONTATO_INVALIDO")
        valor_total = None
        try:
            valor_total = _numero(linha.get("valor_total"), opcional=True)
        except ValueError:
            pendencias.add("VALOR_COMERCIAL_INVALIDO")
        ident_contato = _id(linha.get("contato_tiny_id"), opcional=True)
        bloqueios = {"CONTATO_AUSENTE", "TEXTOS_AUSENTES", "ITENS_AUSENTES", "ITEM_QUANTIDADE_INVALIDO", "ITEM_SEM_IDENTIFICACAO"}
        row = {"chave_origem": chave, "id": lake, "unidade_negocio_id": unidade,
               "unidade_negocio_nome": texto_seguro((unidades or {}).get(unidade, unidade)),
               "tiny_id": tiny, "numero_proposta": texto_seguro(linha.get("numero_proposta")),
               "situacao": texto_seguro(linha.get("situacao")), "data_orcamento": data,
               "data_proximo_contato": proximo, "contato_tiny_id": ident_contato, "contato_nome": contato,
               "nome_modelo": texto_seguro(linha.get("nome_modelo")), "valor_total": valor_total,
               "introducao": introducao, "descricao_extra": descricao_extra,
               "itens": sorted(item_map[chave], key=_json_canonico), "marcadores": marks,
               "pedidos": sorted(order_map[chave], key=_json_canonico),
               "enriquecido": detalhes and not bool(bloqueios.intersection(pendencias)),
               "pendencias_origem": sorted(pendencias)}
        if not row["numero_proposta"]:
            raise ValueError("Orçamento operacional sem número legível.")
        row["fingerprint"] = _fingerprint(row)
        rows.append(row)
    total = len(headers)
    status = "parcial" if enriquecidos < total or any(not r["enriquecido"] for r in rows) else "ok"
    snapshot = {"schema_version": 1, "atualizado_em": instante.astimezone(timezone.utc).isoformat(),
                "status": status, "coverage_start": inicio, "coverage_end": fim,
                "cobertura": {"orcamentos_total": total, "orcamentos_enriquecidos": enriquecidos,
                              "orcamentos_com_itens": com_itens, "orcamentos_operacionais": len(rows),
                              "percentual_enriquecido": round(100 * enriquecidos / total, 2) if total else 0},
                "origem": {"sistema": "Tiny via Silver", "identidade": "unidade_negocio_id + tiny_id",
                           "frescor_tiny_comprovado": False, "timestamp_origem_disponivel": False,
                           "itens": "linhas_comerciais", "pedidos": "regra_operacional_filial_foz",
                           "status_tecnico_automatico": False},
                "avisos": ["Horário indica coleta completa do Silver; não comprova atualização do Tiny.",
                           "Itens e valores são comerciais; equipamento, peças trocadas e custos exigem conferência.",
                           "Vínculo com pedidos é regra operacional da FilialFoz; papel das NFs exige conferência."],
                "orcamentos": sorted(rows, key=lambda r: r["chave_origem"])}
    if status == "parcial":
        snapshot["avisos"].append("Enriquecimento parcial: ausência na fonte não cancela nem exclui protocolos do BI.")
    return validar_snapshot(snapshot)


def validar_snapshot(snapshot):
    """Guardas de publicação; arquivo corrompido nunca é tratado como estado vazio."""
    if not isinstance(snapshot, dict) or type(snapshot.get("schema_version")) is not int or snapshot.get("schema_version") != 1 or snapshot.get("status") not in ("ok", "parcial"):
        raise ValueError("Snapshot de orçamentos inválido.")
    try:
        instante = datetime.fromisoformat(str(snapshot["atualizado_em"]).replace("Z", "+00:00"))
        if instante.tzinfo is None:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise ValueError("Snapshot sem horário de coleta completa.") from None
    rows = _colecao(snapshot.get("orcamentos"), LIMITE_ORCAMENTOS)
    cobertura = snapshot.get("cobertura")
    if not isinstance(cobertura, dict):
        raise ValueError("Snapshot sem cobertura verificável.")
    for campo in ("orcamentos_total", "orcamentos_enriquecidos", "orcamentos_com_itens", "orcamentos_operacionais"):
        valor = cobertura.get(campo)
        if not isinstance(valor, int) or isinstance(valor, bool) or not 0 <= valor <= LIMITE_ORCAMENTOS:
            raise ValueError("Cobertura inválida.")
    if cobertura["orcamentos_operacionais"] != len(rows) or any(cobertura[c] > cobertura["orcamentos_total"] for c in ("orcamentos_enriquecidos", "orcamentos_com_itens", "orcamentos_operacionais")):
        raise ValueError("Cobertura não confere com o snapshot.")
    chaves = set()
    for row in rows:
        chave = f"{_unidade(row.get('unidade_negocio_id'))}:{_id(row.get('tiny_id'))}"
        if row.get("chave_origem") != chave or chave in chaves or row.get("fingerprint") != _fingerprint(row):
            raise ValueError("Snapshot com identidade duplicada ou fingerprint inválido.")
        chaves.add(chave)
        if (not isinstance(row.get("marcadores"), list)
                or any(not isinstance(m, str) for m in row["marcadores"])
                or not MARCADORES_OPERACIONAIS.intersection(row["marcadores"])):
            raise ValueError("Snapshot contém candidato sem marcador operacional exato.")
    # allow_nan=False também percorre nested values e impede JSON não-portável.
    if len(_json_canonico(snapshot).encode("utf-8")) > LIMITE_ARQUIVO:
        raise ValueError("Snapshot excedeu limite seguro.")
    return snapshot


def consultar_fonte(hoje=None):
    """Uma transação REPEATABLE READ somente leitura; consultas limitadas por período."""
    from ponte_db_silver import conectar
    from psycopg2.extras import RealDictCursor
    hoje = hoje or datetime.now(timezone(timedelta(hours=-3))).date()
    inicio, fim_exclusivo = date(2026, 1, 1), hoje + timedelta(days=1)
    filtro = "o.data_orcamento >= %s AND o.data_orcamento < %s"
    params = (inicio, fim_exclusivo)
    fontes = (
        ("orcamento", "SELECT o.id,o.unidade_negocio_id,o.tiny_id,o.numero_proposta,o.situacao,o.data_orcamento,o.data_proximo_contato,o.contato_tiny_id,o.contato_nome,o.nome_modelo,o.valor_total,o.introducao,o.descricao_extra FROM silver.orcamento o WHERE " + filtro, LIMITE_ORCAMENTOS),
        ("orcamento_item", "SELECT d.orcamento_id,d.unidade_negocio_id,d.orcamento_tiny_id,d.numero_proposta,d.produto_tiny_id,d.sku,d.descricao,d.tipo,d.unidade,d.quantidade,d.valor_unitario,d.desconto,d.valor_total FROM silver.orcamento_item d WHERE EXISTS (SELECT 1 FROM silver.orcamento o WHERE o.id=d.orcamento_id AND o.unidade_negocio_id=d.unidade_negocio_id AND o.tiny_id=d.orcamento_tiny_id AND " + filtro + ")", LIMITE_DETALHES),
        ("orcamento_marcador", "SELECT d.orcamento_id,d.unidade_negocio_id,d.orcamento_tiny_id,d.numero_proposta,d.descricao FROM silver.orcamento_marcador d WHERE EXISTS (SELECT 1 FROM silver.orcamento o WHERE o.id=d.orcamento_id AND o.unidade_negocio_id=d.unidade_negocio_id AND o.tiny_id=d.orcamento_tiny_id AND " + filtro + ")", LIMITE_DETALHES),
        ("orcamento_pedido", "SELECT d.orcamento_id,d.unidade_negocio_id,d.orcamento_tiny_id,d.numero_proposta,d.pedido_id,d.numero_pedido,d.data_pedido,d.situacao_pedido,d.nota_fiscal_id,d.tipo_vinculo,d.regra_origem FROM silver.orcamento_pedido d WHERE EXISTS (SELECT 1 FROM silver.orcamento o WHERE o.id=d.orcamento_id AND o.unidade_negocio_id=d.unidade_negocio_id AND o.tiny_id=d.orcamento_tiny_id AND " + filtro + ")", LIMITE_DETALHES))
    cx = conectar()
    try:
        cx.set_session(readonly=True, autocommit=False, isolation_level="REPEATABLE READ")
        with cx.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SET LOCAL statement_timeout = 45000")
            cur.execute("SET LOCAL lock_timeout = 3000")
            cur.execute("SHOW transaction_read_only")
            if next(iter(cur.fetchone().values())) != "on":
                raise ValueError("Conexão não confirmou modo somente leitura.")
            conjuntos = []
            for nome, sql, limite in fontes:
                cur.execute("SELECT count(*) AS n FROM (" + sql + ") AS fonte_limitada", params)
                quantidade = int(cur.fetchone()["n"])
                if quantidade > limite:
                    raise ValueError("Fonte excedeu o limite seguro.")
                cur.execute(sql + " LIMIT %s", params + (limite + 1,))
                linhas = [dict(r) for r in cur.fetchall()]
                if len(linhas) != quantidade:
                    raise ValueError("Contagem independente da fonte não confere.")
                conjuntos.append(linhas)
            cur.execute("SELECT id,nome FROM silver.unidade_negocio LIMIT 101")
            unidades = {str(r["id"]): r["nome"] for r in cur.fetchall()}
            if len(unidades) > 100:
                raise ValueError("Cadastro de unidades excedeu limite seguro.")
        return (*conjuntos, unidades, inicio.isoformat(), hoje.isoformat())
    finally:
        try:
            cx.rollback()
        finally:
            cx.close()


def salvar_atomico(snapshot, destino, *, aceitar_reducao=False):
    """Somente snapshot completo validado substitui arquivo, timestamp e conteúdo anteriores."""
    validar_snapshot(snapshot)
    destino = Path(destino)
    if destino.exists():
        if destino.stat().st_size > LIMITE_ARQUIVO:
            raise ValueError("Arquivo anterior fora do limite seguro; requer revisão.")
        anterior = validar_snapshot(json.loads(destino.read_text(encoding="utf-8")))
        if not aceitar_reducao:
            for campo in ("orcamentos_total", "orcamentos_enriquecidos", "orcamentos_com_itens", "orcamentos_operacionais"):
                antes, depois = anterior["cobertura"][campo], snapshot["cobertura"][campo]
                if antes and (not depois or (antes >= 10 and depois < antes * .7)):
                    raise ValueError("Redução suspeita da cobertura; snapshot anterior preservado.")
            antes = {r["chave_origem"] for r in anterior["orcamentos"]}
            depois = {r["chave_origem"] for r in snapshot["orcamentos"]}
            if len(antes) >= 10 and len(antes - depois) > len(antes) * .3:
                raise ValueError("Desaparecimento suspeito de referências; snapshot anterior preservado.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, nome = tempfile.mkstemp(prefix=destino.name + ".", suffix=".tmp", dir=destino.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            json.dump(snapshot, arquivo, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(nome, destino)
    finally:
        if os.path.exists(nome):
            os.unlink(nome)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, default=SAIDA, help="Arquivo local; pode apontar para pasta privada de validação.")
    parser.add_argument("--aceitar-reducao", action="store_true", help="Usar apenas após confirmar a redução real da fonte.")
    options = parser.parse_args(argv)
    try:
        orcamentos, itens, marcadores, pedidos, unidades, inicio, fim = consultar_fonte()
        snapshot = montar_snapshot(orcamentos, itens, marcadores, pedidos, unidades=unidades,
                                   generated_at=datetime.now(timezone.utc).isoformat(),
                                   coverage_start=inicio, coverage_end=fim)
        salvar_atomico(snapshot, options.saida, aceitar_reducao=options.aceitar_reducao)
        print(f"Orçamentos SAC coletados: {len(snapshot['orcamentos'])}; cobertura {snapshot['cobertura']['orcamentos_enriquecidos']}/{snapshot['cobertura']['orcamentos_total']}; snapshot local atualizado.")
        return 0
    except Exception as erro:
        # Não expor SQL, contato, texto técnico, configuração de rede ou credenciais.
        print(f"Orçamentos SAC não atualizados ({type(erro).__name__}); versão anterior preservada.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
