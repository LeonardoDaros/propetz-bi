"""Coleta somente o cadastro de produtos para garantia, sem publicar no GitHub.

Sem filtro de venda, estoque ou criação: peças novas devem ser selecionáveis.
Custos consolidados seguem a regra dos demais painéis: Matriz/Filial/TradeCorp,
saldo físico e valor de estoque; estoque e custos por unidade não são publicados.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import tempfile

from garantias_catalogo import FONTE_CUSTO_CONSOLIDADO, LIMITE_PRODUTOS, UNIDADES_CUSTO, validate_snapshot


SAIDA = Path(__file__).resolve().parent / "silver_catalogo_garantias.json"
FILTRO = """p.situacao = %s
    AND NULLIF(btrim(p.codigo), '') IS NOT NULL
    AND NULLIF(btrim(p.nome), '') IS NOT NULL
    AND (p.marca ILIKE %s OR p.nome ILIKE %s)
    AND EXISTS (SELECT 1 FROM silver.unidade_negocio u
                WHERE u.id=p.id_unidade_negocio
                  AND lower(btrim(u.nome)) <> lower(%s))"""
PARAMETROS = ("A", "%propetz%", "%propetz%", "Gerencial")


def _nome_ordem(nome):
    # Prefere texto legível e identificável, mantendo o nome real do cadastro.
    # O desempate textual torna o resultado independente da ordem das unidades.
    return ("\ufffd" in nome, "propetz" not in nome.casefold(),
            -len(nome.split()), -len(nome), nome.casefold(), nome)


def _decimal(value, *, empty_zero=False):
    if value is None and empty_zero:
        return Decimal(0)
    if isinstance(value, bool):
        raise ValueError("Valor numérico inválido.")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Valor numérico inválido.")
    return result


def _consolidar_custos(linhas, skus):
    if not isinstance(linhas, list) or len(linhas) > LIMITE_PRODUTOS:
        raise ValueError("Consulta de custos inválida ou acima do limite.")
    groups, invalid = defaultdict(lambda: defaultdict(list)), set()
    for row in linhas:
        if not isinstance(row, dict):
            raise ValueError("Linha de custo inválida.")
        sku = str(row.get("codigo") or "").strip()
        if sku not in skus:
            continue
        if row.get("unidade") not in UNIDADES_CUSTO:
            continue
        try:
            saldo = _decimal(row.get("saldo_estoque"), empty_zero=True)
            preco = _decimal(row.get("preco_custo"), empty_zero=saldo == 0)
            medio = _decimal(row.get("preco_custo_medio"), empty_zero=True)
            if preco < 0 or medio < 0 or (saldo != 0 and preco <= 0):
                raise ValueError("Custo indisponível para o saldo informado.")
            stamp = row.get("xdata_atualizacao")
            stamp = stamp if isinstance(stamp, datetime) else datetime.fromisoformat(stamp)
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("Timestamp técnico inválido.")
            groups[sku][row["unidade"]].append((saldo, preco, medio, stamp))
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            invalid.add(sku)
    custos, ambiguos = [], []
    for sku in sorted(set(groups) | invalid):
        if sku in invalid:
            ambiguos.append({"sku": sku, "motivo": "Referência de custo inválida no cadastro."})
            continue
        saldo, valor, custo_max, stamps = Decimal(0), Decimal(0), Decimal(0), []
        conflito = False
        for rows in groups[sku].values():
            signatures = {(r[0], r[1], r[2]) for r in rows}
            if len(signatures) != 1:
                conflito = True
                break
            qty, preco, medio = next(iter(signatures))
            saldo += qty
            valor += qty * preco
            custo_max = max(custo_max, medio)
            stamps.extend(row[3] for row in rows)
        if conflito:
            ambiguos.append({"sku": sku, "motivo": "Cadastros divergentes do mesmo SKU na mesma unidade."})
            continue
        amount = valor / saldo if saldo > 0 else custo_max
        amount = round(float(amount), 2)  # Mesmo arredondamento do extrator canônico.
        if amount <= 0:
            continue  # Ausência de referência nunca vira custo gratuito.
        custos.append({"sku": sku, "custo": amount, "atualizado_em": min(stamps).isoformat(),
                       "criterio": "media_ponderada_saldo_fisico" if saldo > 0 else "maior_custo_medio_sem_saldo",
                       "unidades": list(UNIDADES_CUSTO)})
    return custos, ambiguos


def montar_snapshot(linhas, *, linhas_custo=None, generated_at=None):
    """Agrupa somente SKU exato; nomes iguais e variantes não são fundidos."""
    if not isinstance(linhas, list) or not 0 < len(linhas) <= LIMITE_PRODUTOS:
        raise ValueError("Catálogo vazio ou acima do limite seguro.")
    nomes = defaultdict(set)
    for row in linhas:
        if not isinstance(row, dict):
            raise ValueError("Linha de produto inválida.")
        codigo, nome = row.get("codigo"), row.get("nome")
        if not isinstance(codigo, str) or not isinstance(nome, str):
            raise ValueError("Produto sem identificação válida.")
        codigo, nome = codigo.strip(), nome.strip()
        if not codigo or not nome:
            raise ValueError("Produto sem identificação válida.")
        nomes[codigo].add(nome)
    custos, ambiguos = _consolidar_custos([] if linhas_custo is None else linhas_custo, set(nomes))
    raw = {"schema_version": 1, "fonte": "silver.produto",
           "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
           "produtos": [{"sku": sku, "nome": min(options, key=_nome_ordem)}
                        for sku, options in nomes.items()],
           "fonte_custo_consolidado": FONTE_CUSTO_CONSOLIDADO,
           "custos_consolidados": custos, "custos_consolidados_ambiguos": ambiguos}
    snapshot = validate_snapshot(raw)
    if snapshot is None:
        raise ValueError("Catálogo inválido; versão anterior preservada.")
    return snapshot


def consultar_fonte():
    """Cadastro ativo, limitado, em uma transação consistente somente leitura."""
    from ponte_db_silver import conectar
    from psycopg2.extras import RealDictCursor

    cx = conectar()
    try:
        cx.set_session(readonly=True, autocommit=False, isolation_level="REPEATABLE READ")
        with cx.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SET LOCAL statement_timeout = 45000")
            cur.execute("SET LOCAL lock_timeout = 3000")
            cur.execute("SHOW transaction_read_only")
            if next(iter(cur.fetchone().values())) != "on":
                raise ValueError("Conexão não está em modo somente leitura.")
            cur.execute("SELECT count(*) AS n, count(DISTINCT btrim(p.codigo)) AS skus "
                        "FROM silver.produto p WHERE " + FILTRO, PARAMETROS)
            prova = cur.fetchone()
            if not prova or not 0 < prova["n"] <= LIMITE_PRODUTOS:
                raise ValueError("Catálogo vazio ou acima do limite seguro.")
            cur.execute("SELECT p.codigo,p.nome FROM silver.produto p WHERE " + FILTRO +
                        " ORDER BY p.codigo,p.nome LIMIT %s", PARAMETROS + (LIMITE_PRODUTOS + 1,))
            linhas = [dict(row) for row in cur.fetchall()]
            if (len(linhas) != prova["n"] or
                    len({row["codigo"].strip() for row in linhas}) != prova["skus"]):
                raise ValueError("A contagem independente do catálogo não confere.")
            cur.execute("SELECT id,nome FROM silver.unidade_negocio")
            unidades = {}
            for unit in cur.fetchall():
                ident, nome = str(unit["id"]), unit["nome"]
                if ident in unidades and unidades[ident] != nome:
                    raise ValueError("Unidade de negócio com identificação ambígua.")
                unidades[ident] = nome
            unidades_custo = [ident for ident, nome in unidades.items() if nome in UNIDADES_CUSTO]
            if {unidades[ident] for ident in unidades_custo} != set(UNIDADES_CUSTO):
                raise ValueError("Unidades do custo consolidado incompletas.")
            # Não repetir o filtro de marca/nome: o cadastro da outra unidade
            # pode usar descrição diferente para o MESMO SKU elegível.
            filtro_custo = "p.situacao=%s AND btrim(p.codigo)=ANY(%s) AND p.id_unidade_negocio::text=ANY(%s)"
            args_custo = ("A", sorted({row["codigo"].strip() for row in linhas}), unidades_custo)
            cur.execute("SELECT count(*) AS n FROM silver.produto p WHERE " + filtro_custo, args_custo)
            prova_custo = cur.fetchone()
            if not prova_custo or not 0 <= prova_custo["n"] <= LIMITE_PRODUTOS:
                raise ValueError("Consulta de custos acima do limite seguro.")
            cur.execute("SELECT p.id,p.codigo,p.id_unidade_negocio,p.preco_custo,p.preco_custo_medio,"
                        "p.saldo_estoque,p.xdata_atualizacao FROM silver.produto p WHERE " + filtro_custo +
                        " ORDER BY p.codigo,p.id_unidade_negocio,p.id LIMIT %s",
                        args_custo + (LIMITE_PRODUTOS + 1,))
            linhas_custo = [dict(row) for row in cur.fetchall()]
            if len(linhas_custo) != prova_custo["n"]:
                raise ValueError("A contagem independente dos custos não confere.")
            for row in linhas_custo:
                row["unidade"] = unidades.get(str(row.get("id_unidade_negocio")))
                if not row["unidade"]:
                    raise ValueError("Unidade de negócio sem identificação.")
        return linhas, linhas_custo
    finally:
        try:
            cx.rollback()
        finally:
            cx.close()


def salvar_atomico(snapshot, destino, *, aceitar_reducao=False):
    """Falhas e quedas superiores a 30% preservam o arquivo e seu timestamp."""
    valid = validate_snapshot(snapshot)
    if valid is None:
        raise ValueError("Catálogo inválido; versão anterior preservada.")
    destino = Path(destino)
    if destino.exists():
        previous = validate_snapshot(json.loads(destino.read_text(encoding="utf-8")))
        if previous is None:
            raise ValueError("Catálogo anterior inválido: revisar antes de substituir.")
        if not aceitar_reducao and len(valid["produtos"]) * 10 < len(previous["produtos"]) * 7:
            raise ValueError("Redução superior a 30%: conferir carga antes de substituir.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=destino.name + ".", suffix=".tmp", dir=destino.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(valid, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, destino)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--aceitar-reducao", action="store_true",
                        help="Usar apenas após confirmar uma redução real superior a 30%.")
    args = parser.parse_args(argv)
    try:
        linhas, linhas_custo = consultar_fonte()
        snapshot = montar_snapshot(linhas, linhas_custo=linhas_custo)
        salvar_atomico(snapshot, args.saida, aceitar_reducao=args.aceitar_reducao)
        print(f"Catálogo coletado: {len(snapshot['produtos'])} SKUs; snapshot local atualizado.")
        return 0
    except Exception as error:
        # Nunca despejar SQL, configuração de conexão ou textos da fonte no log.
        print(f"Catálogo não atualizado ({type(error).__name__}); versão anterior preservada.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
