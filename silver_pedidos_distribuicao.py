"""Carteira de documentos comerciais do Silver; consulta local e snapshot separado.

Não publica no GitHub, não acessa o Tiny e não escreve na agenda/garantias.
Credenciais continuam exclusivamente na ponte canônica. Valores são nominais
dos documentos, sem conversão para receita líquida ou projeção de metas.
"""
import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import os
from pathlib import Path
import tempfile

from util_comum import norm_cliente

BASE = Path(__file__).resolve().parent
SAIDA = BASE / "silver_pedidos_distribuicao.json"
CANAL = "Distribuição PROPETZ"
SITUACOES = ("aberto", "aprovado", "preparando_envio")
LIMITE_PEDIDOS = 10000


def _codigo(value):
    return str(value or "").strip()


def _money(value):
    try:
        result = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Valor de documento inválido.") from None
    if not result.is_finite() or result < 0:
        raise ValueError("Valor de documento inválido.")
    return float(result)


def _date(value):
    if value is None or value == "":
        return None
    return date.fromisoformat(str(value)[:10]).isoformat()


def _identidade(cliente_nome, depara):
    """Reusa o de-para reconciliado; sem novo fuzzy nem código Tiny presumido."""
    exact = depara.get(str(cliente_nome or ""))
    if isinstance(exact, dict) and _codigo(exact.get("codigo")):
        return _codigo(exact["codigo"])
    normal = norm_cliente(cliente_nome)
    if not normal:
        return ""
    codes = {_codigo(v.get("codigo")) for k, v in depara.items()
             if isinstance(v, dict) and norm_cliente(k) == normal and _codigo(v.get("codigo"))}
    return next(iter(codes)) if len(codes) == 1 else ""


def montar_snapshot(pedidos, itens, notas, marcadores, depara, unidades, *, generated_at,
                    coverage_start, coverage_end):
    """Transformação pura, também usada na validação com evidência capturada."""
    from pedidos_comerciais import validate_snapshot
    item_map, marker_map = defaultdict(list), defaultdict(list)
    for item in itens:
        key = (_codigo(item.get("unidade_negocio_id")), _codigo(item.get("pedido_id")))
        item_map[key].append({"sku": _codigo(item.get("codigo")),
                              "produto": _codigo(item.get("descricao")),
                              "quantidade": float(item["quantidade"]) if item.get("quantidade") is not None else None})
    for marker in marcadores:
        key = (_codigo(marker.get("id_unidade_negocio")), _codigo(marker.get("id_pedido")))
        marker_map[key].append(str(marker.get("descricao") or ""))
    note_id, note_order = defaultdict(list), defaultdict(list)
    for note in notas:
        unit = _codigo(note.get("unidade_negocio_id"))
        note_id[(unit, _codigo(note.get("id")))].append(note)
        if note.get("venda_id"):
            note_order[(unit, _codigo(note["venda_id"]))].append(note)
    rows = []
    for pedido in pedidos:
        unit, ident = _codigo(pedido.get("unidade_negocio_id")), _codigo(pedido.get("id"))
        key = (unit, ident)
        related = {str(n["id"]): n for n in note_order.get(key, [])}
        linked_id = _codigo(pedido.get("nota_fiscal_id"))
        related.update({str(n["id"]): n for n in note_id.get((unit, linked_id), [])})
        alerts = []
        if related:
            # NF pendente ainda não é faturamento confirmado, mas tampouco deve
            # entrar cegamente na soma de documentos sem NF. Vai à conferência.
            pending = all(str(n.get("situacao_descricao") or "").strip().casefold() == "pendente"
                          for n in related.values())
            fiscal = "nf_pendente" if pending else "revisar"
            alerts.append("NF pendente vinculada: confira a emissão no ERP." if pending else
                          "Há documento fiscal vinculado: confira a situação antes de considerar nova venda.")
        elif linked_id not in ("", "0") or pedido.get("data_faturamento") or pedido.get("data_envio"):
            fiscal = "revisar"
            alerts.append("O ERP informa vínculo fiscal ou data de movimentação sem nota correspondente nesta consulta.")
        else:
            fiscal = "sem_nf"
        marker_text = " ".join(marker_map.get(key, [])).casefold()
        if any(s in marker_text for s in ("multiempresa", "transferido")):
            fiscal = "revisar"
            alerts.append("Referência a transferência entre empresas: conferir para evitar duplicação.")
        if any(s in marker_text for s in ("garantia", "garatia", "bonifica", "amostra", "manuten")):
            fiscal = "revisar"
            alerts.append("Marcador sugere operação especial: conferir se representa nova venda.")
        if pedido.get("id_pedido_origem"):
            fiscal = "revisar"
            alerts.append("Documento com origem vinculada: conferir a conversão antes de somar valores.")
        rows.append({
            "chave": f"{unit}:{ident}", "id": ident, "unidade_id": unit,
            "unidade": unidades.get(unit, unit), "numero": _codigo(pedido.get("numero")),
            "cliente_id": _identidade(pedido.get("cliente_nome"), depara),
            "cliente_nome": _codigo(pedido.get("cliente_nome")),
            "vendedor_nome": _codigo(pedido.get("vendedor_nome")),
            "situacao": _codigo(pedido.get("situacao")),
            "data_pedido": _date(pedido.get("data_pedido")),
            "data_prevista": _date(pedido.get("data_prevista")),
            "valor_total": _money(pedido.get("valor_total")),
            "itens": item_map.get(key, []), "fiscal_status": fiscal, "alertas": alerts,
        })
    snapshot = {"schema_version": 1, "generated_at": generated_at,
                "coverage_start": coverage_start, "coverage_end": coverage_end,
                "pedidos": rows}
    return validate_snapshot(snapshot)


def consultar_fonte(hoje=None):
    """Uma transação consistente, somente leitura, com limite e prova de contagem."""
    from ponte_db_silver import conectar
    from psycopg2.extras import RealDictCursor
    hoje = hoje or date.today()
    inicio, fim = date(2026, 1, 1), hoje + timedelta(days=1)
    filtro = """p.data_pedido >= %s AND p.data_pedido < %s AND p.situacao=ANY(%s)
        AND EXISTS (SELECT 1 FROM silver.modelo_negocio_vendedor m
          WHERE m.vendedor_id=p.vendedor_id AND m.unidade_negocio_id=p.unidade_negocio_id
          AND m.modelo_negocio_descricao=%s)"""
    args = (inicio, fim, list(SITUACOES), CANAL)
    cx = conectar()
    try:
        cx.set_session(readonly=True, autocommit=False, isolation_level="REPEATABLE READ")
        with cx.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SET LOCAL statement_timeout = 45000")
            cur.execute("SET LOCAL lock_timeout = 3000")
            cur.execute("SHOW transaction_read_only")
            if next(iter(cur.fetchone().values())) != "on":
                raise ValueError("Conexão não está em modo somente leitura.")
            def select(sql, params=()):
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
            prova = select("SELECT count(*) AS n, sum(p.valor_total) AS valor FROM silver.pedido p WHERE " + filtro, args)[0]
            if prova["n"] > LIMITE_PEDIDOS:
                raise ValueError("Carteira excedeu o limite seguro; snapshot anterior preservado.")
            pedidos = select("""SELECT p.id,p.unidade_negocio_id,p.numero,p.data_pedido,p.data_prevista,
                p.data_faturamento,p.data_envio,p.cliente_nome,p.vendedor_nome,p.situacao,p.valor_total,
                p.nota_fiscal_id,p.id_pedido_origem FROM silver.pedido p WHERE """ + filtro + " ORDER BY p.id", args)
            if len(pedidos) != prova["n"] or sum(Decimal(str(p["valor_total"])) for p in pedidos) != Decimal(str(prova["valor"] or 0)):
                raise ValueError("A prova de contagem/valor da fonte não confere.")
            ids = [p["id"] for p in pedidos]
            nids = [p["nota_fiscal_id"] for p in pedidos if p["nota_fiscal_id"]]
            # Consulta limitada aos IDs dos pedidos, inclusive NF sem data ou
            # emitida fora do período. Filtro temporal aqui ocultaria vínculos.
            notas = select("""SELECT id,unidade_negocio_id,venda_id,situacao_descricao
                FROM silver.nota_fiscal WHERE id=ANY(%s) OR venda_id=ANY(%s)""", (nids, ids))
            itens = select("""SELECT unidade_negocio_id,pedido_id,codigo,descricao,quantidade
                FROM silver.pedido_item WHERE pedido_id=ANY(%s) ORDER BY pedido_id,id""", (ids,))
            marcadores = select("""SELECT id_unidade_negocio,id_pedido,descricao
                FROM silver.marcador_pedido WHERE id_pedido=ANY(%s)""", (ids,))
            unidades = {_codigo(r["id"]): r["nome"] for r in select("SELECT id,nome FROM silver.unidade_negocio")}
        return pedidos, itens, notas, marcadores, unidades, inicio.isoformat(), hoje.isoformat()
    finally:
        cx.rollback()
        cx.close()


def salvar_atomico(snapshot, destino, *, aceitar_reducao=False):
    """Falha/encolhimento suspeito preserva a versão anterior e seu timestamp."""
    destino = Path(destino)
    if destino.exists() and not aceitar_reducao:
        from pedidos_comerciais import validate_snapshot
        previous = validate_snapshot(json.loads(destino.read_text(encoding="utf-8")))
        old_count, new_count = len(previous["pedidos"]), len(snapshot["pedidos"])
        if old_count and (not new_count or (old_count >= 10 and new_count < old_count * .3)):
            raise ValueError("Redução superior a 70% ou carteira esvaziada: conferir carga; versão anterior preservada.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=destino.name + ".", suffix=".tmp", dir=destino.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(snapshot, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, destino)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--aceitar-reducao", action="store_true", help="Usar somente após confirmar redução real da carteira.")
    options = parser.parse_args(argv)
    try:
        depara = json.loads((BASE / "depara_clientes_silver.json").read_text(encoding="utf-8"))
        if not isinstance(depara, dict) or not depara:
            raise ValueError("De-para indisponível.")
        pedidos, itens, notas, marcadores, unidades, inicio, fim = consultar_fonte()
        snapshot = montar_snapshot(pedidos, itens, notas, marcadores, depara, unidades,
                                   generated_at=datetime.now(timezone.utc).isoformat(),
                                   coverage_start=inicio, coverage_end=fim)
        salvar_atomico(snapshot, options.saida, aceitar_reducao=options.aceitar_reducao)
        print(f"Carteira coletada: {len(snapshot['pedidos'])} documentos; snapshot local atualizado.")
        return 0
    except Exception as error:
        # Não publicar SQL, credenciais, nomes ou textos livres nos logs.
        print(f"Carteira não atualizada ({type(error).__name__}); versão anterior preservada.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
