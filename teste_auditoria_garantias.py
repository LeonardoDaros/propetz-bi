# -*- coding: utf-8 -*-
"""Contraprovas de garantias: AST/UI simulada, sem arquivos reais ou rede.

Os asserts descrevem o comportamento seguro esperado; falham no código
original de 2026-09-05 e devem passar depois das correções.
"""
import ast
import copy
import inspect
from datetime import date, datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import teste_etapa1_garantias as base


class _Rerun(Exception):
    pass


def mutation_ns(payload, role="garantia"):
    names = {"load_garantias", "add_garantia", "update_garantia", "delete_garantia",
             "can_manage_garantias", "can_edit_garantia_fechada", "_garantia_status",
             "_garantia_versao", "_garantia_autorizar", "_garantia_registros_estado"}
    nodes = [node for node in base.TREE.body if isinstance(node, ast.FunctionDef)
             and node.name in names]
    state = {"value": copy.deepcopy(payload), "writes": 0}

    def mutate(_remote, _local, apply, _default):
        try:
            result = apply(copy.deepcopy(state["value"]))
        except Exception:
            return state["value"], False
        state["value"] = result
        state["writes"] += 1
        return result, True

    ns = dict(base.NS)
    ns.update({"datetime": datetime,
               "st": SimpleNamespace(session_state={"role": role, "user_name": "Pessoa de teste", "authenticated": True},
                                     warning=lambda *_: None),
               "_session_expired": lambda: False,
               "_refresh_session_access": lambda: None,
               "GARANTIAS_FILE": "NAO_USADO.json", "_gh_mutate_json": mutate,
               "_read_state_json": lambda *_: copy.deepcopy(state["value"]),
               "_STATUS_LEGADO": {"Aberta": "Aguardando chegada", "Devolvida ao cliente": "Concluída"}})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(base.APP), "exec"), ns)
    return ns, state


def update_record(ns, record, changes):
    kwargs = {}
    if "expected_version" in inspect.signature(ns["update_garantia"]).parameters:
        kwargs["expected_version"] = ns["_garantia_versao"](record)
    return ns["update_garantia"](record["id"], changes, "Atualização sintética", **kwargs)


def submit_update(record, *, meta=None, state=None, role="garantia_master"):
    captured, instances = [], []

    class SubmitUI(base.FakeUI):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)

        def form_submit_button(self, label, **_):
            return label == "💾 Salvar atualização"

        def rerun(self):
            raise _Rerun()

    def update(gid, changes, action, **kwargs):
        captured.append((gid, copy.deepcopy(changes), action, kwargs))
        return True

    with patch.object(base, "FakeUI", SubmitUI), patch.dict(base.NS, {"update_garantia": update}):
        try:
            base.render(role, [record], meta=meta, state=state)
        except _Rerun:
            pass
    return captured, instances[-1]


class AtomicityAndLoaderTests(unittest.TestCase):
    def test_operador_nao_reabre_registro_que_foi_finalizado_no_remoto(self):
        # Uma alteração feita após a leitura da tela precisa ser revalidada no
        # read-modify-write. A UI local tinha visto Em bancada.
        original = {"garantias": [base.caso(status="Concluída")]}
        ns, state = mutation_ns(original, role="garantia")
        ok = update_record(ns, base.caso(status="Em bancada"), {"status": "Em bancada"})
        self.assertFalse(ok, "Operador não pode reabrir a versão remota finalizada")
        self.assertEqual(state["value"], original)

    def test_atualizacao_concorrente_no_mesmo_caso_recusada_para_master(self):
        seen = base.caso(status="Em bancada")
        current = dict(seen, diagnostico_obs="Outra pessoa registrou este serviço")
        ns, state = mutation_ns({"garantias": [current]}, role="garantia_master")
        self.assertFalse(update_record(ns, seen, {"diagnostico_obs": "Texto antigo"}))
        self.assertEqual(state["value"]["garantias"], [current])

    def test_alteracao_em_outro_caso_nao_bloqueia_nem_se_perde(self):
        seen = base.caso(status="Em bancada")
        other = base.caso("G-2002", diagnostico_obs="Outro caso atualizado")
        ns, state = mutation_ns({"garantias": [seen, other]})
        self.assertTrue(update_record(ns, seen, {"diagnostico_obs": "Serviço adicional"}))
        self.assertEqual(state["value"]["garantias"][1], other)

    def test_add_e_delete_recusam_sessao_sem_permissao(self):
        original = {"garantias": [base.caso()]}
        ns, state = mutation_ns(original, role="vendedor")
        self.assertFalse(ns["add_garantia"](base.caso())[1])
        self.assertFalse(ns["delete_garantia"]("G-1001"))
        self.assertEqual(state["value"], original)

    def test_role_de_operador_nao_substitui_autenticacao(self):
        original = {"garantias": [base.caso(status="Em bancada")]}
        ns, state = mutation_ns(original)
        ns["st"].session_state["authenticated"] = False
        self.assertFalse(ns["add_garantia"](base.caso())[1])
        self.assertFalse(update_record(ns, original["garantias"][0], {"prioridade": "Alta"}))
        self.assertEqual(state["value"], original)

    def test_operador_nao_cancela_caso_ativo(self):
        original = {"garantias": [base.caso(status="Em bancada")]}
        ns, state = mutation_ns(original)
        self.assertFalse(update_record(ns, original["garantias"][0], {"status": "Cancelada"}))
        self.assertEqual(state["value"], original)

    def test_retry_revalida_status_que_mudou_apos_primeira_tentativa(self):
        seen = base.caso(status="Em bancada")
        ns, state = mutation_ns({"garantias": [seen]})
        closed = dict(seen, status="Concluída")
        attempts = []

        def concurrent_mutate(_remote, _local, apply, _default):
            attempts.append(apply(copy.deepcopy(state["value"])))
            # Simula PUT 409: a confirmação de outro usuário venceu.
            state["value"] = {"garantias": [closed]}
            state["value"] = apply(copy.deepcopy(state["value"]))
            return state["value"], True

        ns["_gh_mutate_json"] = concurrent_mutate
        self.assertFalse(update_record(ns, seen, {"status": "Em bancada"}))
        self.assertEqual(len(attempts), 1)
        self.assertEqual(state["value"]["garantias"], [closed])

    def test_formulario_preserva_versao_original_apos_rerun_remoto(self):
        if "_garantia_versao" not in base.NS:
            self.fail("O formulário não tem controle de versão")
        seen = base.caso(status="Em bancada")
        current = dict(seen, diagnostico_obs="Outra pessoa registrou este serviço")
        previous_version = base.NS["_garantia_versao"](seen)
        saved, ui = submit_update(current, state={
            "_gar_snapshot_atv_G-1001": previous_version,
            "st_atv_G-1001": "Em bancada", "do_atv_G-1001": "Texto antigo"})
        self.assertEqual(saved[0][3].get("expected_version"), previous_version)
        self.assertTrue(any("recebeu uma alteração" in m for m in ui.messages))

    def test_revogacao_de_papel_no_retry_impede_gravacao(self):
        seen = base.caso(status="Em bancada")
        ns, state = mutation_ns({"garantias": [seen]})
        calls = []

        def refresh():
            calls.append(1)
            ns["st"].session_state["role"] = "vendedor"
            return None

        def retry(_remote, _local, apply, _default):
            apply(copy.deepcopy(state["value"]))
            ns["_refresh_session_access"] = refresh
            state["value"] = apply(copy.deepcopy(state["value"]))
            return state["value"], True

        ns["_gh_mutate_json"] = retry
        self.assertFalse(update_record(ns, seen, {"prioridade": "Alta"}))
        self.assertTrue(calls)
        self.assertEqual(state["value"]["garantias"], [seen])

    def test_cadastro_removido_recusa_gravacao(self):
        seen = base.caso(status="Em bancada")
        ns, state = mutation_ns({"garantias": [seen]})
        ns["_refresh_session_access"] = lambda: "Seu cadastro não está mais disponível."
        self.assertFalse(update_record(ns, seen, {"prioridade": "Alta"}))
        self.assertEqual(state["value"]["garantias"], [seen])

    def test_atualizacao_nao_reporta_sucesso_se_id_sumiu(self):
        ns, state = mutation_ns({"garantias": []})
        ok = ns["update_garantia"]("G-1001", {"status": "Em bancada"}, "Teste")
        self.assertFalse(ok, "Sem ID no estado remoto, nenhum atendimento foi atualizado")

    def test_loader_tolera_item_nulo_sem_perder_registro_valido(self):
        record = base.caso()
        ns, _ = mutation_ns({"garantias": [None, record]})
        self.assertEqual(ns["load_garantias"](), [record])

    def test_loader_tolera_colecao_nula(self):
        ns, _ = mutation_ns({"garantias": None})
        self.assertEqual(ns["load_garantias"](), [])


class PersistedCostsTests(unittest.TestCase):
    def test_atualizacao_de_prioridade_preserva_custo_de_peca_lancada(self):
        record = base.caso(status="Em bancada", custo_total=10.0,
                           pecas=[{"sku": "SKU-EXEMPLO", "nome": "Produto fictício", "qtd": 1, "custo": 10.0}])
        meta = dict(base.META, custo_unitario={"SKU-EXEMPLO": 50.0})
        saved, _ = submit_update(record, meta=meta, state={"pr_atv_G-1001": "Alta"})
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0][1]["pecas"][0]["custo"], 10.0)
        self.assertEqual(saved[0][1]["custo_total"], 10.0)

    def test_atualizacao_preserva_peca_fora_do_catalogo_atual(self):
        old = {"sku": "SKU-DESCONTINUADO", "nome": "Peça antiga", "qtd": 2, "custo": 10.0}
        record = base.caso(status="Em bancada", custo_total=20.0, pecas=[old])
        saved, _ = submit_update(record, state={"pr_atv_G-1001": "Alta"})
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0][1]["pecas"], [old])
        self.assertEqual(saved[0][1]["custo_total"], 20.0)

    def test_custo_zero_explicito_nao_usa_preco_atual(self):
        record = {"pecas": [{"sku": "SKU-EXEMPLO", "qtd": 1, "custo": 0.0}]}
        self.assertEqual(base.NS["_garantia_custo_total"](record, {"SKU-EXEMPLO": 50.0}), 0.0)

    def test_troca_legada_recupera_custo_do_total_e_preserva_ao_somar_frete(self):
        record = base.caso(status="Em bancada", resultado="Trocada por produto novo", custo_total=130.0,
                           frete_vinda=10.0, frete_volta=20.0)
        meta = dict(base.META, custo_unitario={"SKU-EXEMPLO": 250.0})
        saved, _ = submit_update(record, meta=meta)
        self.assertEqual(saved[0][1].get("custo_produto_trocado"), 100.0)
        self.assertEqual(saved[0][1]["custo_total"], 130.0)
        self.assertFalse(saved[0][1].get("custo_produto_trocado_estimado"))
        updated = {**record, **saved[0][1], "frete_volta": 40.0}
        self.assertEqual(base.NS["_garantia_custo_total"](updated, {"SKU-EXEMPLO": 999.0}), 150.0)

    def test_troca_nova_nao_herda_total_do_conserto_anterior(self):
        record = base.caso(status="Em bancada", resultado="Consertada", custo_total=30.0,
                           frete_vinda=10.0, frete_volta=20.0)
        saved, _ = submit_update(record, meta=dict(base.META, custo_unitario={"SKU-EXEMPLO": 250.0}),
                                 state={"re_atv_G-1001": "Trocada por produto novo"})
        self.assertEqual(saved[0][1].get("custo_produto_trocado"), 250.0)
        self.assertEqual(saved[0][1]["custo_total"], 280.0)

    def test_troca_legada_sem_total_informa_estimativa_e_congela_referencia(self):
        record = base.caso(status="Em bancada", resultado="Trocada por produto novo", custo_total=None)
        meta = dict(base.META, custo_unitario={"SKU-EXEMPLO": 250.0})
        saved, ui = submit_update(record, meta=meta)
        self.assertEqual(saved[0][1].get("custo_produto_trocado"), 250.0)
        self.assertTrue(saved[0][1].get("custo_produto_trocado_estimado"))
        self.assertTrue(any("estimado pela referência atual" in m for m in ui.messages))
        updated = {**record, **saved[0][1]}
        self.assertEqual(base.NS["_garantia_custo_total"](updated, {"SKU-EXEMPLO": 999.0}), 250.0)

    def test_troca_nova_preserva_zero_informado_no_catalogo(self):
        record = base.caso(status="Em bancada", resultado="Consertada", custo_total=0.0)
        saved, _ = submit_update(record, meta=dict(base.META, custo_unitario={"SKU-EXEMPLO": 0.0}),
                                 state={"re_atv_G-1001": "Trocada por produto novo"})
        self.assertEqual(saved[0][1].get("custo_produto_trocado"), 0.0)
        self.assertIs(saved[0][1].get("custo_produto_trocado_estimado"), False)

    def test_estimativa_aparece_no_painel_e_nas_duas_exportacoes(self):
        record = base.caso(custo_produto_trocado=100.0, custo_produto_trocado_estimado=True)
        ui = base.render("garantia", [record])
        self.assertTrue(any("custo estimado do produto trocado" in m for m in ui.messages))
        self.assertTrue(bool(ui.exports[0].iloc[0]["Custo troca estimado"]))
        self.assertTrue(bool(ui.exports[1].iloc[0]["Custo troca estimado"]))


class DateAndDenominatorTests(unittest.TestCase):
    def test_formulario_recusa_envio_anterior_a_chegada(self):
        saved, ui = submit_update(base.caso(status="Em bancada"), state={
            "dc_atv_G-1001": date(2026, 8, 20), "de_atv_G-1001": date(2026, 8, 19)})
        self.assertEqual(saved, [], "Datas fisicamente invertidas não podem ser gravadas")
        self.assertTrue(ui.messages)

    def test_denominador_booleano_nao_e_unidade_vendida(self):
        self.assertIsNone(base.NS["_garantia_relacao_vendas"](1, True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
