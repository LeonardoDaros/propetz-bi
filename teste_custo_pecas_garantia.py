"""Custos ausentes não bloqueiam a bancada nem viram zero nos indicadores.

Somente registros sintéticos; a página real é executada via AST com I/O simulado.
"""
import copy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

import teste_etapa1_garantias as base
from garantia_analytics import build_frame, product_summary


class _Saved(Exception):
    pass


def save_record(record, *, meta=None, state=None, catalogo=None):
    captures, instances = [], []

    class CostUI(base.FakeUI):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)

        def number_input(self, _label, *_args, value=0, key=None, **_kwargs):
            return self.session_state.get(key, value)

        def checkbox(self, _label, value=False, key=None, **_kwargs):
            return self.session_state.get(key, value)

        def form_submit_button(self, label, **_kwargs):
            return label == "💾 Salvar atualização"

        def rerun(self):
            raise _Saved()

    def update(gid, changes, action, **kwargs):
        captures.append(copy.deepcopy(changes))
        return True

    with patch.object(base, "FakeUI", CostUI), patch.dict(base.NS, {
            "update_garantia": update, "load_catalogo_garantias": lambda: copy.deepcopy(catalogo)}):
        try:
            base.render("garantia_master", [record], meta=meta, state=state)
        except _Saved:
            pass
    if len(captures) != 1:
        raise AssertionError(f"Esperava uma atualização, recebi {len(captures)}: {instances[-1].messages}")
    return captures[0], instances[-1]


def open_case(**changes):
    return base.caso(status="Em bancada", **changes)


def selected_part(**state):
    return {"p0_atv_G-1001": "SKU-EXEMPLO — Produto fictício", **state}


def silver_snapshot(amount=26.40, *, hours_old=0, criterio="maior_custo_medio_sem_saldo"):
    now = datetime.now(timezone.utc)
    return {"schema_version": 1, "fonte": "silver.produto",
            "generated_at": (now - timedelta(hours=hours_old)).isoformat(),
            "produtos": [{"sku": "SKU-EXEMPLO", "nome": "Produto fictício"}],
            "fonte_custo_consolidado": base.garantias_catalogo.FONTE_CUSTO_CONSOLIDADO,
            "custos_consolidados": [{"sku": "SKU-EXEMPLO", "custo": amount,
                                     "criterio": criterio, "unidades": ["Matriz", "Filial", "TradeCorp"],
                                     "atualizado_em": (now - timedelta(days=7)).isoformat()}],
            "custos_consolidados_ambiguos": []}


class SavedCostTests(unittest.TestCase):
    def test_nova_peca_sem_custo_salva_tecnico_sem_zerar_total(self):
        record = open_case(frete_vinda=12, frete_volta=8, custo_extra=3)
        before = copy.deepcopy(record)
        saved, ui = save_record(record, state=selected_part())
        part = saved["pecas"][0]
        self.assertIsNone(part["custo"])
        self.assertTrue(part["custo_pendente"])
        self.assertEqual(part["custo_origem"], "pendente")
        self.assertIsNone(saved["custo_total"])
        self.assertTrue(saved["custo_pendente"])
        self.assertEqual(saved["frete_vinda"], 12)
        self.assertEqual(saved["frete_volta"], 8)
        self.assertEqual(record, before)
        self.assertTrue(any("atualizada" in m and "pendente / incompleto" in m for m in ui.messages))

    def test_referencia_base_mae_usada_somente_no_primeiro_lancamento(self):
        saved, _ = save_record(open_case(), meta=dict(base.META, custo_unitario={"SKU-EXEMPLO": 7.5}),
                               state=selected_part(**{"q0_atv_G-1001": 2}))
        self.assertEqual(saved["pecas"][0]["custo"], 7.5)
        self.assertEqual(saved["pecas"][0]["custo_origem"], "base_mae")
        self.assertEqual(saved["custo_total"], 15)
        self.assertFalse(saved["custo_pendente"])

    def test_custo_manual_confirmado_multiplica_quantidade(self):
        saved, _ = save_record(open_case(), state=selected_part(**{
            "pc0_atv_G-1001": 14.5, "pcm0_atv_G-1001": True, "q0_atv_G-1001": 2}))
        self.assertEqual(saved["pecas"][0]["custo_origem"], "manual")
        self.assertEqual(saved["custo_total"], 29)
        self.assertFalse(saved["custo_pendente"])

    def test_zero_manual_explicito_e_conhecido(self):
        saved, _ = save_record(open_case(), state=selected_part(**{
            "pc0_atv_G-1001": 0.0, "pcm0_atv_G-1001": True}))
        self.assertEqual(saved["pecas"][0]["custo"], 0)
        self.assertEqual(saved["custo_total"], 0)
        self.assertFalse(saved["custo_pendente"])

    def test_valor_sem_confirmacao_nao_e_herdado_silenciosamente(self):
        service = {"sku": "SERV-MAOOBRA", "nome": "Mão de obra (serviço)", "qtd": 1, "custo": 55.0}
        saved, _ = save_record(open_case(pecas=[service]), state=selected_part())
        self.assertIsNone(saved["pecas"][0]["custo"])
        self.assertIsNone(saved["custo_total"])

    def test_custo_pendente_pode_ser_completado_manual_sem_mudar_demais_valores(self):
        part = {"sku": "SKU-EXEMPLO", "nome": "Produto fictício", "qtd": 2, "custo": None,
                "custo_pendente": True, "custo_origem": "pendente"}
        saved, _ = save_record(open_case(pecas=[part], custo_total=None, custo_pendente=True,
                                        frete_vinda=12, frete_volta=8),
                               state={"pc0_atv_G-1001": 10.0, "pcm0_atv_G-1001": True})
        self.assertEqual(saved["custo_total"], 40)
        self.assertFalse(saved["custo_pendente"])
        self.assertFalse(saved["pecas"][0]["custo_pendente"])

    def test_mudanca_de_prioridade_nao_reprecifica_pendente_com_catalogo_novo(self):
        part = {"sku": "SKU-EXEMPLO", "nome": "Produto fictício", "qtd": 1, "custo": None,
                "custo_pendente": True, "custo_origem": "pendente"}
        saved, _ = save_record(open_case(pecas=[part], custo_total=None),
                               meta=dict(base.META, custo_unitario={"SKU-EXEMPLO": 50}),
                               state={"pr_atv_G-1001": "Alta"})
        self.assertEqual(saved["pecas"], [part])
        self.assertIsNone(saved["custo_total"])

    def test_custo_anterior_inclusive_zero_e_metadados_nao_sao_sobrescritos(self):
        for cost in (0.0, 18.0):
            with self.subTest(cost=cost):
                part = {"sku": "SKU-EXEMPLO", "nome": "Produto fictício", "qtd": 1, "custo": cost,
                        "custo_origem": "manual", "custo_pendente": False, "origem_extra": "preservar"}
                saved, _ = save_record(open_case(pecas=[part]),
                                       meta=dict(base.META, custo_unitario={"SKU-EXEMPLO": 75}),
                                       state={"pc0_atv_G-1001": 99, "pcm0_atv_G-1001": True})
                self.assertEqual(saved["pecas"], [part])
                self.assertEqual(saved["custo_total"], cost)

    def test_servico_sem_valor_continua_zero_e_nao_pendente(self):
        saved, _ = save_record(open_case(), state={"p0_atv_G-1001": "🛠️ SERVIÇO — Afiação"})
        self.assertEqual(saved["pecas"][0]["custo"], 0)
        self.assertFalse(saved["pecas"][0]["custo_pendente"])
        self.assertEqual(saved["custo_total"], 0)

    def test_confirmacao_manual_e_resetada_apos_salvar(self):
        saved, ui = save_record(open_case(), state=selected_part(**{
            "pc0_atv_G-1001": 19, "pcm0_atv_G-1001": True}))
        self.assertTrue(ui.session_state["_gar_reset_custos_atv_G-1001"])
        state = dict(ui.session_state)
        updated = {**open_case(), **saved}
        saved2, ui2 = save_record(updated, state=state)
        self.assertNotIn("pc0_atv_G-1001", ui2.session_state)
        self.assertNotIn("pcm0_atv_G-1001", ui2.session_state)
        self.assertEqual(saved2["custo_total"], 19)


class TotalAndReportTests(unittest.TestCase):
    def test_total_nao_busca_preco_atual_para_item_sem_custo_salvo(self):
        record = {"pecas": [{"sku": "SKU", "qtd": 1, "custo": None}], "frete_vinda": 30}
        self.assertIsNone(base.NS["_garantia_custo_total"](record, {"SKU": 999}))

    def test_troca_sem_referencia_tem_total_pendente(self):
        saved, _ = save_record(open_case(), state={"re_atv_G-1001": "Trocada por produto novo"})
        self.assertIsNone(saved["custo_produto_trocado"])
        self.assertIsNone(saved["custo_total"])
        self.assertTrue(saved["custo_pendente"])

    def test_troca_pendente_pode_ser_resolvida_com_custo_manual_confirmado(self):
        record = open_case(resultado="Trocada por produto novo", custo_total=None,
                           custo_produto_trocado=None, custo_produto_trocado_pendente=True,
                           custo_pendente=True, frete_vinda=10)
        saved, _ = save_record(record, state={"pct_atv_G-1001": 150, "pctm_atv_G-1001": True})
        self.assertEqual(saved["custo_produto_trocado"], 150)
        self.assertEqual(saved["custo_produto_trocado_origem"], "manual")
        self.assertFalse(saved["custo_produto_trocado_pendente"])
        self.assertFalse(saved["custo_pendente"])
        self.assertEqual(saved["custo_total"], 160)

    def test_custo_manual_nao_sobrescreve_troca_conhecida(self):
        record = open_case(resultado="Trocada por produto novo", custo_total=100,
                           custo_produto_trocado=100, custo_produto_trocado_pendente=False)
        saved, _ = save_record(record, state={"pct_atv_G-1001": 150, "pctm_atv_G-1001": True})
        self.assertEqual(saved["custo_produto_trocado"], 100)
        self.assertEqual(saved["custo_total"], 100)

    def test_dado_invalido_nao_produz_numero_nem_crash(self):
        for value in (None, True, -1, "abc", float("inf"), float("nan")):
            with self.subTest(value=value):
                self.assertIsNone(base.NS["_garantia_custo_total"]({"pecas": [{"qtd": 1, "custo": value}]}, {}))

    def test_caso_pendente_conta_no_volume_mas_nao_no_custo(self):
        frame = build_frame([base.caso(custo_total=None, custo_pendente=True), base.caso("G-2", custo_total=20)])
        summary = product_summary(frame).iloc[0]
        self.assertEqual(summary["casos"], 2)
        self.assertEqual(summary["custos_informados"], 1)
        self.assertEqual(summary["custo_registrado"], 20)

    def test_bancada_finalizada_e_exports_sinalizam_none(self):
        record = base.caso(custo_total=None, custo_pendente=True,
                           pecas=[{"sku": "SKU", "nome": "Peça fictícia", "qtd": 1, "custo": None,
                                   "custo_pendente": True}])
        ui = base.render("garantia", [record], state={"gar_subtab": "co"})
        self.assertTrue(any("**Custo do caso:** Pendente / incompleto" in m for m in ui.messages))
        self.assertTrue(any("não entram na soma" in m for m in ui.messages))
        for export in ui.exports:
            if "Custo pendente" in export:
                self.assertTrue(bool(export.iloc[0]["Custo pendente"]))
        self.assertTrue(all(frame["Custo total"].isna().all() for frame in ui.exports if "Custo total" in frame))

    def test_pecas_mesmo_sku_com_custo_parcial_mostram_quantidade_e_pendencias(self):
        records = [base.caso(custo_total=None, custo_pendente=True, pecas=[
            {"sku": "SKU", "nome": "Peça fictícia", "qtd": 2, "custo": None, "custo_pendente": True}]),
            base.caso("G-2", custo_total=10, pecas=[
                {"sku": "SKU", "nome": "Peça fictícia", "qtd": 1, "custo": 10}])]
        ui = base.render("garantia", records, state={"gp_visao": "Operação e custos"})
        parts = next(t for t in ui.tables if "Lançamentos sem custo" in t)
        self.assertEqual(parts.iloc[0]["Quantidade"], 3)
        self.assertEqual(parts.iloc[0]["Lançamentos sem custo"], 1)
        self.assertEqual(parts.iloc[0]["Custo lançado"], "R$ 10,00")
        self.assertTrue(any("parcela conhecida" in m for m in ui.messages))

    def test_peca_legada_sem_custo_nao_invalida_total_historico_salvo(self):
        record = base.caso(custo_total=45, pecas=[
            {"sku": "SKU", "nome": "Peça fictícia", "qtd": 1, "custo": None}])
        frame = build_frame([record])
        self.assertEqual(frame.iloc[0]["custo_registrado"], 45)
        ui = base.render("garantia", [record])
        self.assertTrue(any("Totais já registrados no histórico são preservados" in m for m in ui.messages))
        self.assertFalse(any("Esses casos não entram" in m for m in ui.messages))


class ConsolidatedSilverCostTests(unittest.TestCase):
    def test_peca_nova_prioriza_silver_consolidado_com_proveniencia(self):
        for criterio in base.garantias_catalogo.CRITERIOS_CUSTO:
            with self.subTest(criterio=criterio):
                snapshot = silver_snapshot(26.40, criterio=criterio)
                saved, ui = save_record(open_case(), catalogo=snapshot,
                                       meta=dict(base.META, custo_unitario={"SKU-EXEMPLO": 999}),
                                       state=selected_part(**{"pc0_atv_G-1001": 888, "pcm0_atv_G-1001": True}))
                part = saved["pecas"][0]
                self.assertEqual(part["custo"], 26.40)
                self.assertEqual(part["custo_origem"], "silver_consolidado")
                self.assertEqual(part["custo_fonte"], snapshot["fonte_custo_consolidado"])
                self.assertEqual(part["custo_criterio"], criterio)
                self.assertEqual(part["custo_unidades"], ["Matriz", "Filial", "TradeCorp"])
                self.assertEqual(part["custo_coletado_em"], snapshot["generated_at"])
                self.assertTrue(any("Ao salvar" in m and "consolidado" in m for m in ui.messages))

    def test_silver_atual_nao_reprecifica_custo_historico_inclusive_zero(self):
        for cost in (0.0, 18.0):
            with self.subTest(cost=cost):
                part = {"sku": "SKU-EXEMPLO", "nome": "Produto fictício", "qtd": 1, "custo": cost,
                        "custo_origem": "manual", "custo_pendente": False}
                saved, _ = save_record(open_case(pecas=[part]), catalogo=silver_snapshot(50))
                self.assertEqual(saved["pecas"], [part])
                self.assertEqual(saved["custo_total"], cost)

    def test_silver_antigo_usa_base_mae_identificada(self):
        saved, ui = save_record(open_case(), catalogo=silver_snapshot(50, hours_old=25),
                               meta=dict(base.META, custo_unitario={"SKU-EXEMPLO": 12}), state=selected_part())
        part = saved["pecas"][0]
        self.assertEqual(part["custo"], 12)
        self.assertEqual(part["custo_origem"], "base_mae")
        self.assertEqual(part["custo_fonte"], "Base Mãe / abc_valor.json")
        self.assertTrue(any("Base Mãe" in m and "alternativa" in m for m in ui.messages))

    def test_peca_pendente_mostra_referencia_silver_sem_preencher_historico(self):
        part = {"sku": "SKU-EXEMPLO", "nome": "Produto fictício", "qtd": 1, "custo": None,
                "custo_origem": "pendente", "custo_pendente": True}
        saved, ui = save_record(open_case(pecas=[part], custo_total=None), catalogo=silver_snapshot(50))
        self.assertEqual(saved["pecas"], [part])
        self.assertIsNone(saved["custo_total"])
        self.assertTrue(any("Referência atual" in m and "50.00" in m and "manualmente" in m for m in ui.messages))

    def test_troca_nova_usa_silver_e_congela_referencia(self):
        record = open_case()
        saved, _ = save_record(record, catalogo=silver_snapshot(26.40),
                               meta=dict(base.META, custo_unitario={"SKU-EXEMPLO": 999}),
                               state={"re_atv_G-1001": "Trocada por produto novo"})
        self.assertEqual(saved["custo_produto_trocado"], 26.40)
        self.assertEqual(saved["custo_produto_trocado_origem"], "silver_consolidado")
        self.assertFalse(saved["custo_produto_trocado_estimado"])
        self.assertEqual(saved["custo_produto_trocado_referencia"]["custo_unidades"], ["Matriz", "Filial", "TradeCorp"])
        after, _ = save_record({**record, **saved}, catalogo=silver_snapshot(100))
        self.assertEqual(after["custo_produto_trocado"], 26.40)
        self.assertEqual(after["custo_produto_trocado_referencia"], saved["custo_produto_trocado_referencia"])

    def test_troca_pendente_nao_e_preenchida_por_referencia_nova(self):
        record = open_case(resultado="Trocada por produto novo", custo_total=None,
                           custo_produto_trocado=None, custo_produto_trocado_pendente=True,
                           custo_pendente=True)
        saved, ui = save_record(record, catalogo=silver_snapshot(50))
        self.assertIsNone(saved["custo_produto_trocado"])
        self.assertIsNone(saved["custo_total"])
        self.assertTrue(any("Referência atual do produto novo" in m and "não muda automaticamente" in m for m in ui.messages))

    def test_exportacao_preserva_origem_do_custo_consolidado(self):
        saved, _ = save_record(open_case(), catalogo=silver_snapshot(), state=selected_part())
        ui = base.render("garantia", [{**base.caso(), **saved}])
        history = next(e for e in ui.exports if "Origem custo peças" in e)
        self.assertIn("silver_consolidado", history.iloc[0]["Origem custo peças"])
        self.assertIn(base.garantias_catalogo.FONTE_CUSTO_CONSOLIDADO, history.iloc[0]["Referência custo peças"])


if __name__ == "__main__":
    unittest.main()
