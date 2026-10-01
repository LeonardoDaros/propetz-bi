"""Testes do domínio Tiny/SAC: execução isolada, sem app, banco ou credenciais."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import unittest

import orcamentos_garantias as dominio

NOW = datetime(2026, 10, 1, 17, 0, tzinfo=timezone.utc)
UNIT = "fc97d781-d6d4-433d-94c3-7ceabb1b425a"


def budget(**changes):
    value = {"unidade_negocio_id": UNIT, "tiny_id": 885059268, "numero_proposta": "3162",
             "situacao": "Pendente", "data_orcamento": "2026-09-28", "data_proximo_contato": "2026-09-28",
             "contato_tiny_id": 843530030, "contato_nome": "Contato de teste",
             "introducao": "PRODUTO/EQUIPAMENTO: MAQUINA VOLARE\nRELATO CITADO PELO CLIENTE: NÃO LIGA",
             "descricao_extra": "<p>RELATO DO CLIENTE: PROBLEMA DE BATERIA<br>AÇÃO EXECUTADA: REVERSA ENVIADA</p>",
             "valor_total": 1390, "enriquecido": True,
             "marcadores": ["GARANTIA", "MAQUINA VOLARE"],
             "itens": [{"sku": "VOLARE-220", "descricao": "MAQUINA VOLARE", "quantidade": 1,
                         "valor_unitario": 1390, "valor_total": 1390, "item": 1}],
             "pedidos": [{"pedido_id": 123, "numero_pedido": "456", "tipo_vinculo": "REGRA_NEGOCIO",
                          "regra_origem": "OS_ESTRITA", "nota_fiscal_id": 789}]}
    value.update(changes)
    return value


def snapshot(budgets=None, **changes):
    value = {"schema_version": 1, "atualizado_em": NOW.isoformat(), "status": "ok",
             "orcamentos": budgets if budgets is not None else [budget()], "avisos": []}
    value.update(changes)
    return value


def proposal(source=None, **changes):
    args = {"unidade_atendida": "serie:TESTE-01", "confirmado": True, "atualizado_em": NOW.isoformat(), "agora": NOW}
    args.update(changes)
    return dominio.preparar_contexto_importacao(source or budget(), **args)


def version(record):
    return sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def record(gid="G-0001", origin=True, status="Em bancada"):
    value = {"id": gid, "status": status, "cliente": "Distribuidor de teste", "cliente_final": "Cliente final confirmado",
             "sku": "VOLARE-220", "produto": "Volare", "causa": "Desgaste natural", "relato": "Confirmado pela equipe",
             "pecas": [{"sku": "BATERIA-01", "qtd": 1, "custo": 17.5}], "custo_total": 27.5,
             "frete_volta": 10, "historico": [{"acao": "Atendimento conferido"}], "criado_por": "operador1",
             "criado_em": "2026-09-28 10:00", "versao": "manter"}
    if origin:
        value["origem_tiny"] = proposal()["origem_tiny"]
    return value


class FonteTests(unittest.TestCase):
    def test_html_scripts_and_encoded_scripts_removed(self):
        text = dominio.texto_sem_html('<p>Relato &amp; diagnóstico<br>segunda linha</p><script>segredo()</script>'
                                     '<style>body{display:none}</style>&lt;script&gt;oculto()&lt;/script&gt;')
        self.assertEqual(text, "Relato & diagnóstico\nsegunda linha")

    def test_plain_text_keeps_line_labels(self):
        self.assertEqual(dominio.texto_sem_html("  PRODUTO: VOLARE\n  RELATO: NÃO LIGA\x00"),
                         "PRODUTO: VOLARE\nRELATO: NÃO LIGA")

    def test_fresh_partial_source_is_visible_and_usable(self):
        view = dominio.validar_snapshot(snapshot(status="parcial"), NOW)
        self.assertTrue(view["valido"] and view["pode_importar"])
        self.assertTrue(any("parcial" in a for a in view["avisos"]))

    def test_stale_source_remains_visible_but_blocks_import(self):
        view = dominio.validar_snapshot(snapshot(atualizado_em=(NOW - timedelta(hours=25)).isoformat()), NOW)
        self.assertTrue(view["disponivel"])
        self.assertFalse(view["pode_importar"])
        self.assertRaises(ValueError, proposal, atualizado_em=(NOW - timedelta(hours=25)).isoformat())

    def test_future_timestamp_blocks_import(self):
        view = dominio.validar_snapshot(snapshot(atualizado_em=(NOW + timedelta(minutes=6)).isoformat()), NOW)
        self.assertFalse(view["pode_importar"])

    def test_naive_timestamp_rejected(self):
        self.assertFalse(dominio.validar_snapshot(snapshot(atualizado_em="2026-10-01T17:00:00"), NOW)["valido"])

    def test_duplicate_source_identity_rejected_even_tiny_int_vs_string(self):
        sources = [budget(), budget(tiny_id="885059268", numero_proposta="9999")]
        self.assertFalse(dominio.validar_snapshot(snapshot(sources), NOW)["valido"])

    def test_invalid_keys_rejected(self):
        for changes in ({"tiny_id": True}, {"tiny_id": 0}, {"tiny_id": 1.5}, {"unidade_negocio_id": "foz"}):
            with self.subTest(changes=changes):
                self.assertFalse(dominio.validar_snapshot(snapshot([budget(**changes)]), NOW)["valido"])

    def test_invalid_payloads_fail_without_io(self):
        for value in (None, [], snapshot(schema_version=True), snapshot(status="erro"),
                      snapshot([budget(itens=[None])]), snapshot([budget(pedidos={})])):
            with self.subTest(value=value):
                self.assertFalse(dominio.validar_snapshot(value, NOW)["valido"])

    def test_only_operational_markers_selected(self):
        view = dominio.validar_snapshot(snapshot([budget(marcadores=["MAQUINA VOLARE"])]), NOW)
        self.assertEqual(view["orcamentos"], [])
        self.assertRaises(ValueError, proposal, budget(marcadores=["MAQUINA VOLARE"]))

    def test_unenriched_budget_visible_but_not_importable(self):
        source = budget(enriquecido=False)
        self.assertEqual(len(dominio.validar_snapshot(snapshot([source]), NOW)["orcamentos"]), 1)
        self.assertRaises(ValueError, proposal, source)

    def test_snapshot_result_is_copy(self):
        source = snapshot()
        view = dominio.validar_snapshot(source, NOW)
        view["orcamentos"][0]["itens"][0]["sku"] = "MODIFICADO"
        self.assertEqual(source["orcamentos"][0]["itens"][0]["sku"], "VOLARE-220")


class SugestoesTests(unittest.TestCase):
    def test_contact_is_never_assumed_customer_and_prices_never_cost(self):
        view = dominio.preparar_orcamento(budget(), {"VOLARE-220": "Volare"})
        self.assertEqual(view["campos_iniciais"], {"relato": "NÃO LIGA", "produto": "Volare", "sku": "VOLARE-220"})
        self.assertNotIn("cliente", view["campos_iniciais"])
        self.assertNotIn("cliente_final", view["campos_iniciais"])
        self.assertNotIn("pecas", view["campos_iniciais"])
        self.assertNotIn("custo", view["dados_origem"]["itens"][0])

    def test_3162_volare_vs_aura_requires_explicit_conflict_confirmation(self):
        source = budget(itens=[{"sku": "AURA-220", "descricao": "SECADOR AURA 220V", "quantidade": 1}])
        view = dominio.preparar_orcamento(source, {"AURA-220": "Aura"})
        self.assertGreaterEqual(len(view["conflitos"]), 2)
        self.assertEqual(view["sugestao_equipamento"]["sku"], "")
        self.assertRaises(ValueError, proposal, source)
        confirmed = proposal(source, confirmou_conflitos=True)
        self.assertTrue(confirmed["confirmou_conflitos"])

    def test_2936_parts_only_in_text_not_imported_as_parts(self):
        source = budget(introducao="PRODUTO/EQUIPAMENTO: MÁQUINA PRO7\nRELATO CITADO PELO CLIENTE: DESLIGANDO COM 30%",
                        descricao_extra="<p>REALIZAMOS A TROCA DO KIT PLACA+ BATERIA</p>",
                        marcadores=["GARANTIA", "MAQUINA PRO7"],
                        itens=[{"sku": "PRO7", "descricao": "MÁQUINA PRO7", "quantidade": 1, "valor_unitario": 739.2}])
        view = dominio.preparar_orcamento(source)
        self.assertIn("PLACA+ BATERIA", view["texto_original"])
        self.assertNotIn("pecas", view["campos_iniciais"])
        self.assertNotIn("diagnostico", view["campos_iniciais"])

    def test_tiny_completed_does_not_become_technical_status(self):
        view = dominio.preparar_orcamento(budget(situacao="Concluído"))
        self.assertNotIn("status", view["campos_iniciais"])
        self.assertTrue(any("andamento técnico" in a for a in view["alertas"]))

    def test_unlabelled_equipment_text_not_auto_classified(self):
        view = dominio.preparar_orcamento(budget(introducao="Meu secador Aura deu problema", marcadores=["GARANTIA"]))
        self.assertEqual(view["sugestao_equipamento"]["texto"], "")
        self.assertEqual(view["campos_iniciais"]["sku"], "")

    def test_no_labelled_report_uses_original_text_only(self):
        view = dominio.preparar_orcamento(budget(introducao="sem padrão", descricao_extra="bateria trocada"))
        self.assertEqual(view["relato_sugerido"], "")
        self.assertIn("bateria trocada", view["texto_original"])

    def test_multiple_orders_preserved_as_business_rule_references(self):
        source = budget(pedidos=[{"pedido_id": 1, "tipo_vinculo": "REGRA_NEGOCIO", "regra_origem": "OS_ESTRITA"},
                                {"pedido_id": 2, "tipo_vinculo": "REGRA_NEGOCIO", "regra_origem": "OS_VARIANTE"}])
        refs = dominio.preparar_orcamento(source)["dados_origem"]["pedidos"]
        self.assertEqual(len(refs), 2)
        self.assertTrue(all(r["tipo_vinculo"] == "REGRA_NEGOCIO" for r in refs))

    def test_aura_voltage_difference_requires_confirmation(self):
        source = budget(introducao="PRODUTO/EQUIPAMENTO: SECADOR AURA 127V\nRELATO: NÃO LIGA",
                        marcadores=["GARANTIA", "SECADOR AURA 127V"],
                        itens=[{"sku": "AURA-220", "descricao": "SECADOR AURA 220V", "quantidade": 1}])
        view = dominio.preparar_orcamento(source, {"AURA-220": "SECADOR AURA 220V"})
        self.assertTrue(any("tensão" in c for c in view["conflitos"]))
        self.assertEqual(view["campos_iniciais"]["sku"], "")
        self.assertRaises(ValueError, proposal, source)

    def test_accessory_for_machine_is_not_suggested_as_the_machine(self):
        source = budget(introducao="PRODUTO/EQUIPAMENTO: MÁQUINA PRO7\nRELATO: NÃO LIGA",
                        marcadores=["GARANTIA", "MAQUINA PRO7"],
                        itens=[{"sku": "LAMINA-PRO7", "descricao": "LÂMINA DA MÁQUINA PRO7", "quantidade": 1}])
        view = dominio.preparar_orcamento(source, {"LAMINA-PRO7": "LÂMINA PRO7"})
        self.assertTrue(any("tipo de equipamento" in c for c in view["conflitos"]))
        self.assertEqual(view["campos_iniciais"]["sku"], "")

    def test_catalog_name_must_agree_with_source_family_before_suggestion(self):
        view = dominio.preparar_orcamento(budget(), {"VOLARE-220": "SECADOR AURA"})
        self.assertEqual(view["campos_iniciais"]["sku"], "")


class PropostaTests(unittest.TestCase):
    def test_unit_requires_one_confirmed_series_or_manual_identity(self):
        for args in ({}, {"serie": "ABC"}, {"serie": "ABC", "slot_manual": "DEF", "confirmada": True},
                     {"slot_manual": "<img>", "confirmada": True}):
            with self.subTest(args=args):
                self.assertRaises(ValueError, dominio.chave_unidade_atendida, **args)
        self.assertEqual(dominio.chave_unidade_atendida(slot_manual="Bancada-01", confirmada=True), "manual:BANCADA-01")

    def test_multiple_units_same_sku_require_confirmation(self):
        source = budget(itens=[{"sku": "VOLARE-220", "descricao": "MAQUINA VOLARE", "quantidade": 2}])
        self.assertRaises(ValueError, proposal, source)
        self.assertTrue(proposal(source, confirmou_multiplo=True)["confirmou_multiplo"])

    def test_invalid_commercial_quantity_cannot_be_overridden(self):
        for qty in (None, 0, -1, True, "NaN", "Infinity", "1e99999"):
            with self.subTest(qty=qty):
                source = budget(itens=[{"sku": "VOLARE-220", "descricao": "VOLARE", "quantidade": qty}])
                self.assertRaises(ValueError, proposal, source, confirmou_multiplo=True, confirmou_conflitos=True)

    def test_source_items_position_ignored_and_reordering_idempotent(self):
        source = budget(itens=[{"sku": "A", "descricao": "MAQUINA VOLARE", "quantidade": 1, "item": 1},
                                {"sku": "B", "descricao": "MAQUINA VOLARE", "quantidade": 1, "item": 2}])
        first = proposal(source, confirmou_multiplo=True)
        changed = deepcopy(source)
        changed["itens"].reverse()
        changed["itens"][0]["item"], changed["itens"][1]["item"] = 1, 2
        second = proposal(changed, confirmou_multiplo=True)
        self.assertEqual(first["origem_tiny"]["fingerprint"], second["origem_tiny"]["fingerprint"])
        self.assertEqual(first["origem_tiny"]["chave_externa"], second["origem_tiny"]["chave_externa"])
        self.assertNotIn("item", first["origem_tiny"]["dados"]["itens"][0])
        fresh = dominio.validar_contexto_no_snapshot(first, snapshot([changed]), NOW)
        self.assertEqual(fresh["origem_tiny"]["fingerprint"], first["origem_tiny"]["fingerprint"])

    def test_source_real_change_requires_new_confirmation(self):
        context = proposal()
        changed = budget(introducao="PRODUTO/EQUIPAMENTO: MAQUINA VOLARE\nRELATO: NOVO RELATO")
        self.assertRaises(ValueError, dominio.validar_contexto_no_snapshot, context, snapshot([changed]), NOW)

    def test_absence_is_not_automatic_cancel_or_delete(self):
        context = proposal()
        self.assertRaises(ValueError, dominio.validar_contexto_no_snapshot, context, snapshot([]), NOW)
        saved = record()
        before = deepcopy(saved)
        self.assertEqual(saved, before)

    def test_tampered_origin_is_rejected(self):
        context = proposal()
        context["origem_tiny"]["dados"]["contato_nome"] = "Outra pessoa"
        self.assertRaises(ValueError, dominio.validar_confirmacao, context, NOW)

    def test_external_key_must_match_unit_and_tiny(self):
        context = proposal()
        context["origem_tiny"]["unidade_atendida"] = "serie:OUTRA"
        self.assertRaises(ValueError, dominio.validar_confirmacao, context, NOW)

    def test_source_timestamp_renewed_only_when_current_contents_equal(self):
        context = proposal(atualizado_em=(NOW - timedelta(hours=2)).isoformat())
        fresh = dominio.validar_contexto_no_snapshot(context, snapshot(), NOW)
        self.assertEqual(fresh["origem_tiny"]["atualizado_em"], NOW.isoformat())

    def test_enriched_flag_cannot_override_missing_source_details(self):
        for changes in ({"contato_nome": ""}, {"introducao": "", "descricao_extra": ""}, {"itens": []},
                        {"itens": [{"sku": "", "descricao": "Volare", "quantidade": 1}]},
                        {"itens": [{"sku": "VOLARE", "descricao": "", "quantidade": 1}]}):
            with self.subTest(changes=changes):
                self.assertRaises(ValueError, proposal, budget(enriquecido=True, **changes))

    def test_invalid_historical_or_future_budget_date_cannot_import(self):
        for value in ("2025-09-01", "2026-13-01", "2026-10-02", "", None):
            with self.subTest(value=value):
                self.assertRaises(ValueError, proposal, budget(data_orcamento=value))


class DeduplicacaoTests(unittest.TestCase):
    def test_reimport_returns_same_protocol_even_closed_or_cancelled(self):
        for status in ("Em bancada", "Concluída", "Cancelada", "Devolvida ao cliente"):
            with self.subTest(status=status):
                saved = record(status=status)
                before = deepcopy(saved)
                decision = dominio.decidir_importacao([saved], proposal(), agora=NOW)
                self.assertEqual((decision["acao"], decision["id"]), ("ja_vinculado", "G-0001"))
                self.assertEqual(saved, before)

    def test_two_proposals_race_is_rechecked_against_current_list(self):
        context_a, context_b = proposal(), proposal()
        first = dominio.decidir_importacao([], context_a, agora=NOW)
        self.assertEqual(first["acao"], "criar")
        current = record()
        current["origem_tiny"] = first["origem_tiny"]
        retry = dominio.decidir_importacao([current], context_b, agora=NOW)
        self.assertEqual(retry["acao"], "ja_vinculado")
        self.assertEqual(retry["id"], current["id"])

    def test_duplicate_external_identity_blocks(self):
        records = [record("G-0001"), record("G-0002", status="Cancelada")]
        self.assertEqual(dominio.status_ligacao(records, budget())["estado"], "ambiguo")
        self.assertRaises(ValueError, dominio.decidir_importacao, records, proposal(), agora=NOW)

    def test_duplicate_protocol_ids_block(self):
        records = [record("G-0001"), record("G-0001", origin=False)]
        self.assertRaises(ValueError, dominio.decidir_importacao, records, proposal(), agora=NOW)

    def test_new_slot_not_copy_of_existing_budget_without_explicit_confirmation(self):
        context = proposal(unidade_atendida="manual:SEGUNDA-UNIDADE")
        self.assertRaises(ValueError, dominio.decidir_importacao, [record()], context, agora=NOW)
        context = proposal(unidade_atendida="manual:SEGUNDA-UNIDADE", confirmou_multiplo=True)
        self.assertEqual(dominio.decidir_importacao([record()], context, agora=NOW)["acao"], "criar")

    def test_historical_number_nf_or_client_never_auto_link(self):
        saved = record(origin=False)
        saved.update(numero_proposta="3162", nf="789", contato_nome="Contato de teste")
        decision = dominio.decidir_importacao([saved], proposal(), agora=NOW)
        self.assertEqual(decision["acao"], "criar")
        self.assertIsNone(decision["id"])

    def test_link_existing_requires_version_and_preserves_clinical_data(self):
        saved = record(origin=False)
        before = deepcopy(saved)
        decision = dominio.decidir_importacao([saved], proposal(), acao="vincular", target_id=saved["id"],
                                             expected_version=version(saved), version_fn=version, agora=NOW)
        self.assertEqual(decision["acao"], "vincular")
        self.assertEqual(saved, before)
        self.assertEqual(set(decision), {"acao", "id", "origem_tiny"})
        merged = {**saved, "origem_tiny": decision["origem_tiny"]}
        for field in ("status", "cliente_final", "causa", "pecas", "custo_total", "historico", "criado_por", "versao"):
            self.assertEqual(merged[field], before[field])

    def test_stale_existing_record_version_blocks(self):
        saved = record(origin=False)
        self.assertRaises(ValueError, dominio.decidir_importacao, [saved], proposal(), acao="vincular",
                          target_id=saved["id"], expected_version="old", version_fn=version, agora=NOW)

    def test_closed_link_requires_authorized_correction(self):
        for status in ("Concluída", "Cancelada", "Devolvida ao cliente"):
            saved = record(origin=False, status=status)
            kwargs = {"acao": "vincular", "target_id": saved["id"], "expected_version": version(saved),
                      "version_fn": version, "agora": NOW}
            self.assertRaises(ValueError, dominio.decidir_importacao, [saved], proposal(), **kwargs)
            self.assertEqual(dominio.decidir_importacao([saved], proposal(), allow_closed=True, **kwargs)["acao"], "vincular")

    def test_identity_already_owned_by_another_protocol_cannot_be_reassigned(self):
        old, chosen = record(), record("G-0002", origin=False)
        self.assertRaises(ValueError, dominio.decidir_importacao, [old, chosen], proposal(), acao="vincular",
                          target_id=chosen["id"], expected_version=version(chosen), version_fn=version, agora=NOW)

    def test_existing_protocol_origin_cannot_be_replaced_by_different_budget(self):
        saved = record()
        context = proposal(budget(tiny_id=99999))
        self.assertRaises(ValueError, dominio.decidir_importacao, [saved], context, acao="vincular",
                          target_id=saved["id"], expected_version=version(saved), version_fn=version, agora=NOW)

    def test_reference_update_has_no_clinical_fields_and_preserves_saved_record(self):
        saved = record()
        before = deepcopy(saved)
        context = proposal(budget(descricao_extra="<p>Nova anotação no Tiny</p>"))
        decision = dominio.decidir_importacao([saved], context, acao="atualizar", target_id=saved["id"],
                                             expected_version=version(saved), version_fn=version, agora=NOW)
        self.assertEqual(decision["acao"], "atualizar")
        self.assertEqual(saved, before)
        self.assertNotIn("cliente_final", decision["origem_tiny"])
        self.assertNotIn("pecas", decision["origem_tiny"])

    def test_update_without_existing_link_requires_explicit_link_first(self):
        saved = record(origin=False)
        self.assertRaises(ValueError, dominio.decidir_importacao, [saved], proposal(), acao="atualizar",
                          target_id=saved["id"], expected_version=version(saved), version_fn=version, agora=NOW)

    def test_malformed_saved_external_identity_blocks_new_import(self):
        saved = record()
        saved["origem_tiny"]["chave_externa"] = "invalid"
        self.assertRaises(ValueError, dominio.decidir_importacao, [saved], proposal(), agora=NOW)


if __name__ == "__main__":
    unittest.main(verbosity=2)
