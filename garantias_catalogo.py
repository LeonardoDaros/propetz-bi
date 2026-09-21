"""Catálogo de garantia independente de vendas; validação sem I/O ou credenciais."""
from datetime import datetime, timedelta, timezone
import math


LIMITE_PRODUTOS = 10000
FONTE_CUSTO_CONSOLIDADO = "silver.produto"
UNIDADES_CUSTO = ("Matriz", "Filial", "TradeCorp")
CRITERIOS_CUSTO = ("media_ponderada_saldo_fisico", "maior_custo_medio_sem_saldo")


def _texto(value, limite):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > limite or any(ord(c) < 32 for c in value):
        return None
    return value


def _data_aware(value, current):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        if parsed > current + timedelta(minutes=5):
            return None
        return parsed
    except (TypeError, ValueError, OverflowError):
        return None


def validate_snapshot(raw, now=None):
    """Retorna uma cópia mínima válida, ou None; nunca fabrica catálogo vazio."""
    if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int:
        return None
    if raw["schema_version"] != 1 or raw.get("fonte") != "silver.produto":
        return None
    try:
        generated = datetime.fromisoformat(raw["generated_at"])
        current = now or datetime.now(timezone.utc)
        if generated.tzinfo is None or generated.utcoffset() is None:
            return None
        if current.tzinfo is None or current.utcoffset() is None:
            return None
        if generated > current + timedelta(minutes=5):
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    produtos = raw.get("produtos")
    if not isinstance(produtos, list) or not 0 < len(produtos) <= LIMITE_PRODUTOS:
        return None
    result, seen = [], set()
    for product in produtos:
        if not isinstance(product, dict):
            return None
        sku, nome = _texto(product.get("sku"), 128), _texto(product.get("nome"), 1000)
        if not sku or not nome or " — " in sku or sku in seen:
            return None
        seen.add(sku)
        # O catálogo permanece separado das referências de custo por unidade.
        result.append({"sku": sku, "nome": nome})
    result.sort(key=lambda p: (p["nome"].casefold(), p["sku"]))
    valid = {"schema_version": 1, "generated_at": generated.isoformat(),
             "fonte": "silver.produto", "produtos": result}
    if any(key in raw for key in ("custos_consolidados", "fonte_custo_consolidado", "custos_consolidados_ambiguos")):
        if raw.get("fonte_custo_consolidado") != FONTE_CUSTO_CONSOLIDADO:
            return None
        costs = raw.get("custos_consolidados")
        ambiguous = raw.get("custos_consolidados_ambiguos", [])
        if (not isinstance(costs, list) or not isinstance(ambiguous, list) or
                len(costs) + len(ambiguous) > LIMITE_PRODUTOS):
            return None
        cost_keys, clean_costs, clean_ambiguous = set(), [], []
        for row in costs + ambiguous:
            if not isinstance(row, dict):
                return None
            sku = _texto(row.get("sku"), 128)
            if sku not in seen or sku in cost_keys:
                return None
            cost_keys.add(sku)
        for row in costs:
            amount = row.get("custo")
            updated = _data_aware(row.get("atualizado_em"), current)
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or updated is None:
                return None
            try:
                amount = float(amount)
                if not math.isfinite(amount) or amount <= 0:
                    return None
            except (ValueError, OverflowError):
                return None
            if row.get("criterio") not in CRITERIOS_CUSTO or row.get("unidades") != list(UNIDADES_CUSTO):
                return None
            clean_costs.append({"sku": row["sku"].strip(),
                                "custo": float(amount), "atualizado_em": updated.isoformat(),
                                "criterio": row["criterio"], "unidades": list(UNIDADES_CUSTO)})
        for row in ambiguous:
            reason = _texto(row.get("motivo"), 200)
            if not reason:
                return None
            clean_ambiguous.append({"sku": row["sku"].strip(),
                                    "motivo": reason})
        valid.update({"fonte_custo_consolidado": FONTE_CUSTO_CONSOLIDADO,
                      "custos_consolidados": sorted(clean_costs, key=lambda p: p["sku"]),
                      "custos_consolidados_ambiguos": sorted(clean_ambiguous, key=lambda p: p["sku"])})
    return valid


def custo_referencia_consolidado(snapshot, sku, now=None):
    """Referência consolidada Matriz + Filial + TradeCorp, sem custo da Foz.

    Atualização é o timestamp técnico do cadastro, não um fechamento mensal.
    Coleta com mais de 24 horas exige conferência, sem autopreencher.
    """
    current = now or datetime.now(timezone.utc)
    valid = validate_snapshot(snapshot, now=current)
    if valid is None or not isinstance(sku, str):
        return None
    if current - datetime.fromisoformat(valid["generated_at"]) > timedelta(hours=24):
        return None
    for row in valid.get("custos_consolidados", []):
        if row["sku"] == sku.strip():
            return dict(row, fonte=valid["fonte_custo_consolidado"])
    return None


def catalogo_opcoes(snapshot, legados):
    """União por SKU exato: catálogo válido prevalece, legado não desaparece."""
    by_sku = {}
    if isinstance(legados, (list, tuple)):
        for product in legados:
            if not isinstance(product, dict):
                continue
            sku, nome = _texto(product.get("code"), 128), _texto(product.get("name"), 1000)
            if sku and nome and " — " not in sku:
                by_sku.setdefault(sku, nome)
    valid = validate_snapshot(snapshot)
    if valid is not None:
        by_sku.update((p["sku"], p["nome"]) for p in valid["produtos"])
    return [f"{sku} — {nome}" for sku, nome in
            sorted(by_sku.items(), key=lambda item: (item[1].casefold(), item[0]))]
