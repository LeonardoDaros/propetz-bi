"""Contratos de dados e isolamento da carteira de pedidos (stdlib, sem I/O)."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import unittest

from pedidos_comerciais import MOTIVOS, scope_snapshot, validate_snapshot


NOW = datetime(2026, 9, 18, 18, tzinfo=timezone.utc)
TODAY = date(2026, 9, 18)
VENDOR = "Emanuel Propetz Distribuição"
OTHER = "Yasmin Propetz Distribuição"


def order(key="u1:1", **changes):
    unit, oid = key.split(":")
    result = {"chave": key, "id": oid, "unidade_id": unit, "unidade": "Unidade exemplo",
              "numero": oid, "cliente_id": "C1", "cliente_nome": "Nome ERP descartado",
              "vendedor_nome": VENDOR, "situacao": "aberto", "data_pedido": "2026-09-10",
              "data_prevista": "2026-09-20", "valor_total": 100.1, "fiscal_status": "sem_nf",
              "alertas": [], "itens": [{"sku": "SKU-100", "produto": "Produto exemplo", "quantidade": 2}]}
    result.update(changes)
    return result


def snapshot(*rows):
    return {"schema_version": 1, "generated_at": NOW.isoformat(), "coverage_start": "2026-01-01",
            "coverage_end": "2026-09-18", "pedidos": list(rows)}


def clients():
    return [{"id": "C1", "name": "Cliente exemplo", "vendor": VENDOR, "status": "Ativo"},
            {"id": "C2", "name": "Outro cliente", "vendor": OTHER, "status": "Ativo"}]


def scoped(raw, role="vendedor", vendor=VENDOR, carteira=None, now=NOW):
    return scope_snapshot(raw, clients() if carteira is None else carteira, role, vendor, TODAY, now=now)


class SnapshotTests(unittest.TestCase):
    def test_missing_is_error_but_explicit_empty_is_valid(self):
        for raw in (None, {}, [], {"schema_version": True}, snapshot(None)):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_snapshot(raw, now=NOW)
        self.assertEqual(validate_snapshot(snapshot(), now=NOW)["pedidos"], [])

    def test_required_fields(self):
        base = snapshot(order())
        for field in base:
            bad = deepcopy(base)
            del bad[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_snapshot(bad, now=NOW)
        for field in base["pedidos"][0]:
            bad = deepcopy(base)
            del bad["pedidos"][0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_snapshot(bad, now=NOW)

    def test_duplicate_keys_never_sum_even_identical(self):
        for value in (100.1, 900):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_snapshot(snapshot(order(), order(valor_total=value)), now=NOW)
        self.assertEqual(len(validate_snapshot(snapshot(order(), order("u2:1")), now=NOW)["pedidos"]), 2)

    def test_key_cannot_disagree_with_composite_identity(self):
        with self.assertRaises(ValueError):
            validate_snapshot(snapshot(order(id="2")), now=NOW)

    def test_finite_nonnegative_json_numbers_required(self):
        for value in (True, "10", None, -1, float("nan"), float("inf"), -float("inf"), 10 ** 400):
            for field in ("valor_total", "quantidade"):
                row = order()
                (row if field == "valor_total" else row["itens"][0])[field] = value
                with self.subTest(value=str(value)[:20], field=field), self.assertRaises(ValueError):
                    validate_snapshot(snapshot(row), now=NOW)
        with self.assertRaises(ValueError):
            validate_snapshot(snapshot(order(valor_total=1e308), order("u1:2", valor_total=1e308)), now=NOW)

    def test_strict_dates_and_coverage(self):
        for value in (None, "18/09/2026", "2026-02-30", "2026-9-10", "2025-12-31", "2026-09-19"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_snapshot(snapshot(order(data_pedido=value)), now=NOW)
        for value in ("2026-02-30", "20260920"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_snapshot(snapshot(order(data_prevista=value)), now=NOW)
        self.assertEqual(validate_snapshot(snapshot(order(data_prevista="")), now=NOW)["pedidos"][0]["data_prevista"], "")
        self.assertEqual(validate_snapshot(snapshot(order(data_prevista=None)), now=NOW)["pedidos"][0]["data_prevista"], "")
        for field, value in (("coverage_start", "2026-09-19"), ("coverage_end", "2026-09-19")):
            bad = snapshot()
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_snapshot(bad, now=NOW)

    def test_generation_timezone_future_tolerance(self):
        for value in (None, "2026-09-18", "2026-09-18T18:00:00", (NOW + timedelta(minutes=6)).isoformat()):
            raw = snapshot()
            raw["generated_at"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_snapshot(raw, now=NOW)
        for value in ("2026-09-18T15:00:00-03:00", "2026-09-18T18:00:00Z", (NOW + timedelta(minutes=5)).isoformat()):
            raw = snapshot()
            raw["generated_at"] = value
            validate_snapshot(raw, now=NOW)

    def test_unknown_fiscal_fails_closed(self):
        with self.assertRaises(ValueError):
            validate_snapshot(snapshot(order(fiscal_status="novo_status")), now=NOW)

    def test_extras_and_linked_erp_name_not_propagated(self):
        raw = snapshot(order(credencial="segredo fictício"))
        raw["token"] = "segredo fictício"
        raw["pedidos"][0]["itens"][0]["custo"] = 17
        clean = validate_snapshot(raw, now=NOW)
        self.assertNotIn("token", clean)
        self.assertNotIn("credencial", clean["pedidos"][0])
        self.assertNotIn("custo", clean["pedidos"][0]["itens"][0])
        self.assertEqual(clean["pedidos"][0]["cliente_nome"], "")
        self.assertEqual(raw["pedidos"][0]["cliente_nome"], "Nome ERP descartado")

    def test_nested_bad_types_fail_closed(self):
        for changes in ({"itens": {}}, {"itens": [None]}, {"alertas": "texto"}, {"alertas": [42]}, {"cliente_id": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_snapshot(snapshot(order(**changes)), now=NOW)


class ScopeTests(unittest.TestCase):
    def test_role_and_vendor_required(self):
        for role in ("garantia", "garantia_master", "", None, "ADMIN", [], {}):
            with self.subTest(role=role), self.assertRaises(ValueError):
                scoped(snapshot(order()), role=role)
        for vendor in (None, "", "   ", 1, []):
            with self.subTest(vendor=vendor), self.assertRaises(ValueError):
                scoped(snapshot(order()), vendor=vendor)

    def test_only_exact_authorized_client_and_vendor(self):
        raw = snapshot(order(), order("u1:2", cliente_id="C2", vendedor_nome=OTHER),
                       order("u1:3", cliente_id="C3"), order("u1:4", cliente_id="C1", vendedor_nome=OTHER))
        view = scoped(raw)
        self.assertEqual([row["chave"] for row in view["pedidos"]], ["u1:1"])
        self.assertEqual(view["pendencias"], [])
        self.assertEqual(view["pedidos"][0]["cliente_nome"], "Cliente exemplo")
        self.assertEqual(view["resumo"]["aberto"], {"quantidade": 1, "valor": 100.1})

    def test_no_name_or_first_name_match_and_no_id_coercion(self):
        for changes in ({"cliente_id": "", "cliente_nome": "Cliente exemplo"},
                        {"cliente_id": "c1"}, {"cliente_id": "C01"}, {"vendedor_nome": "Emanuel Outro Sobrenome"}):
            with self.subTest(changes=changes):
                view = scoped(snapshot(order(**changes)))
                self.assertEqual(view["pedidos"], [])
                self.assertEqual(view["pendencias"], [])

    def test_existing_vendor_merge_is_respected(self):
        view = scoped(snapshot(order(vendedor_nome="Ellen Propetz Distribuição")))
        self.assertEqual(len(view["pedidos"]), 1)

    def test_missing_inactive_and_divergent_clients_hidden(self):
        for carteira in ([], [dict(clients()[0], status="Inativo")], [dict(clients()[0], vendor=OTHER)], [dict(clients()[0], vendor="")]):
            with self.subTest(carteira=carteira):
                view = scoped(snapshot(order()), carteira=carteira)
                self.assertEqual(view["pedidos"], [])
                self.assertEqual(view["pendencias"], [])
        with self.assertRaises(ValueError):
            scoped(snapshot(order()), carteira=[clients()[0], clients()[0]])

    def test_manager_sees_unlinked_and_divergent_only_as_pending(self):
        raw = snapshot(order(cliente_id="", cliente_nome="Cliente sem código"),
                       order("u1:2", cliente_id="C2"), order("u1:3", cliente_id="C3"))
        for role in ("admin", "diretor"):
            view = scoped(raw, role=role, vendor=None)
            self.assertEqual(view["pedidos"], [])
            self.assertEqual(len(view["pendencias"]), 3)
            self.assertEqual(view["pendencias"][0]["cliente_nome"], "Cliente sem código")
            self.assertEqual(view["resumo"]["aberto"]["quantidade"], 0)
            self.assertEqual(view["pendencias"][1]["motivos"], [MOTIVOS["vendedor_divergente"]])

    def test_fiscal_never_counted_as_pipeline(self):
        raw = snapshot(order(), order("u1:2", fiscal_status="nf_pendente"),
                       order("u1:3", fiscal_status="faturado"), order("u1:4", fiscal_status="revisar"))
        for role, count in (("vendedor", 1), ("admin", 3), ("diretor", 3)):
            view = scoped(raw, role=role)
            self.assertEqual(view["resumo"]["aberto"], {"quantidade": 1, "valor": 100.1})
            self.assertEqual(len(view["pendencias"]), count)
        self.assertEqual(scoped(raw)["pendencias"][0]["motivos"], [MOTIVOS["nf_pendente"]])

    def test_fiscal_pending_from_other_or_unlinked_never_leaks(self):
        raw = snapshot(order(cliente_id="", cliente_nome="Cliente sem código", fiscal_status="nf_pendente"),
                       order("u1:2", cliente_id="C2", fiscal_status="nf_pendente"),
                       order("u1:3", vendedor_nome=OTHER, fiscal_status="nf_pendente"))
        view = scoped(raw)
        self.assertEqual(view["pedidos"], [])
        self.assertEqual(view["pendencias"], [])

    def test_manager_filter_restricts_pending_too(self):
        raw = snapshot(order(), order("u1:2", cliente_id="", vendedor_nome=OTHER))
        view = scoped(raw, role="admin")
        self.assertEqual(len(view["pedidos"]), 1)
        self.assertEqual(view["pendencias"], [])

    def test_unrecognized_order_status_not_assumed_open(self):
        raw = snapshot(order(situacao="orcamento"))
        self.assertEqual(scoped(raw)["pedidos"], [])
        manager = scoped(raw, role="admin", vendor=None)
        self.assertEqual(manager["pendencias"][0]["motivos"], [MOTIVOS["situacao"]])

    def test_summary_separate_stages_items_do_not_multiply_headers(self):
        many_items = [dict(order()["itens"][0]) for _ in range(3)]
        raw = snapshot(order(valor_total=0.1, itens=many_items), order("u1:2", valor_total=0.2),
                       order("u1:3", situacao="aprovado", valor_total=20),
                       order("u1:4", situacao="preparando_envio", valor_total=30))
        view = scoped(raw)
        self.assertEqual(view["resumo"], {"aberto": {"quantidade": 2, "valor": 0.3},
                         "aprovado": {"quantidade": 1, "valor": 20.0}, "preparando_envio": {"quantidade": 1, "valor": 30.0}})
        self.assertEqual(view["pedidos"][0]["idade_dias"], 8)
        opened = next(row for row in view['pedidos'] if row['chave'] == 'u1:1')
        self.assertIn("interesse", opened["acao_sugerida"])
        self.assertIn("Documento 1 (Unidade exemplo)", opened["acao_sugerida"])

    def test_overdue_erp_forecast_then_age_prioritize_without_changing_status(self):
        raw = snapshot(order('u1:1', data_pedido='2026-01-02', data_prevista='2026-09-25'),
                       order('u1:2', data_pedido='2026-09-17', data_prevista='2026-09-17'),
                       order('u1:3', data_pedido='2026-09-15', data_prevista='2026-09-17'))
        view = scoped(raw)
        self.assertEqual([row['id'] for row in view['pedidos']], ['3','2','1'])
        self.assertTrue(all(row['situacao']=='aberto' for row in view['pedidos']))

    def test_stale_and_metadata_survive_empty_scoped_view(self):
        for hours, stale in ((24, False), (24.01, True)):
            view = scoped(snapshot(order()), carteira=[], now=NOW + timedelta(hours=hours))
            self.assertEqual(view["stale"], stale)
            self.assertEqual(view["coverage_start"], "2026-01-01")
            self.assertEqual(view["coverage_end"], "2026-09-18")
            self.assertEqual(view["stale_hours"], hours)

    def test_scope_revalidates_and_does_not_mutate_inputs(self):
        raw, carteira = snapshot(order()), clients()
        before, before_clients = deepcopy(raw), deepcopy(carteira)
        view = scoped(raw, carteira=carteira)
        view["pedidos"][0]["itens"][0]["sku"] = "MUTADO"
        self.assertEqual(raw, before)
        self.assertEqual(carteira, before_clients)
        raw["pedidos"].append(deepcopy(raw["pedidos"][0]))
        with self.assertRaises(ValueError):
            scoped(raw)

    def test_large_finite_values_do_not_raise_during_summary(self):
        view = scoped(snapshot(order(valor_total=1e308)))
        self.assertEqual(view["resumo"]["aberto"]["valor"], 1e308)


if __name__ == "__main__":
    unittest.main(verbosity=2)
