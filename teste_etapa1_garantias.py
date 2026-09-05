# -*- coding: utf-8 -*-
"""Regressão de Garantias sem importar o app ou acessar estado real/remoto.

Extrai funções do AST e executa a página com registros sintéticos e UI simulada.
Rodar: python teste_etapa1_garantias.py
"""
import ast
import copy
import math
import unittest
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from util_comum import parse_label_ym


APP = Path(__file__).with_name("app.py")
TREE = ast.parse(APP.read_text(encoding="utf-8-sig"), filename=str(APP))
FUNCTIONS = {
    "can_edit_garantia_fechada", "_garantias_visiveis", "_garantia_data",
    "_garantia_tempo_info", "_garantia_tempo_rotulo", "_garantia_periodo_vendas",
    "_garantias_no_periodo_vendas", "_garantia_relacao_vendas",
    "_garantia_custo_total", "_rotulo_outro", "_link_rastreio", "page_garantias",
}
CONSTANTS = {
    "STATUS_GARANTIA", "STATUS_ATIVOS", "STATUS_FINALIZADOS", "CANAIS_GARANTIA",
    "EMPRESAS_NF", "DEFEITOS_GARANTIA", "CAUSAS_GARANTIA", "PRIORIDADES_GARANTIA",
    "_PRIO_ICONE", "RESULTADOS_GARANTIA",
}
NODES = [n for n in TREE.body if
         (isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS) or
         (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in CONSTANTS
                                          for t in n.targets))]
NS = {"datetime": datetime, "date": date, "timedelta": timedelta,
      "math": math, "pd": pd, "defaultdict": defaultdict,
      "_parse_label_ym": parse_label_ym}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(APP), "exec"), NS)


META = {"periodo": "out/2025 a set/2026", "gerado_em": "2026-09-01 13:59",
        "custo_unitario": {}, "vendas_12m_todos_canais": {"SKU-EXEMPLO": 200}}


def caso(gid="G-1001", status="Concluída", criado="2026-08-10 10:00", **updates):
    g = {"id": gid, "status": status, "criado_em": criado,
         "cliente": "Distribuidor fictício", "cliente_final": "Cliente fictício",
         "produto_sku": "SKU-EXEMPLO", "produto_nome": "Produto fictício",
         "canal": "Distribuição", "defeito": "Não liga", "diagnostico_causa": "Defeito de fabricação",
         "diagnostico_obs": "Serviço fictício", "resultado": "Consertada", "pecas": [],
         "custo_total": 30.0, "data_chegada": "2026-08-12", "data_envio": "2026-08-15",
         "concluido_em": "2026-08-15 12:00", "nf_entrada": "EXEMPLO", "historico": []}
    g.update(updates)
    return g


class FakeUI:
    """Widgets não submetem formulários; captura só o que seria exibido."""
    def __init__(self, role, state=None):
        self.session_state = {"role": role}
        self.session_state.update(state or {})
        self.messages = []
        self.tables = []
        self.exports = []
        self.metrics = []
        self.forms = []
        self.expanders = []
        self.selectors = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def columns(self, spec):
        return [self] * (spec if isinstance(spec, int) else len(spec))

    def tabs(self, labels):
        return [self] * len(labels)

    def expander(self, label, **kwargs):
        self.messages.append(str(label))
        self.expanders.append((str(label), kwargs.get("expanded", False)))
        return self

    def form(self, key, **_kwargs):
        self.forms.append(key)
        return self

    def selectbox(self, label, options, index=0, key=None, format_func=str, **_):
        options = list(options)
        default = options[index] if index is not None and len(options) else None
        selected = self.session_state.get(key, default) if key else default
        if selected is not None and selected not in options:
            selected = default
        if key:
            self.session_state[key] = selected
        self.selectors[key or label] = {"label": label, "options": options,
                                       "labels": [format_func(o) for o in options]}
        return selected

    def segmented_control(self, _label, options, default=None, key=None, **_):
        selected = self.session_state.get(key, default or options[0])
        return selected if selected in options else default or options[0]

    def text_input(self, _label, value="", key=None, **_):
        return self.session_state.get(key, value) if key else value

    text_area = text_input

    def date_input(self, _label, value=None, key=None, **_):
        return self.session_state.get(key, value) if key else value

    def number_input(self, _label, *_args, value=0, **_kwargs):
        return value

    def button(self, *_args, **_kwargs):
        return False

    checkbox = button
    form_submit_button = button

    def metric(self, label, value, **_):
        self.metrics.append((label, value))

    def dataframe(self, value, **_):
        self.tables.append(value.copy(deep=True))

    def write_message(self, value, **_):
        self.messages.append(str(value))

    header = caption = markdown = info = warning = success = error = write_message

    def divider(self):
        pass

    def rerun(self):
        raise AssertionError("Não deve haver escrita/submissão durante o teste")


def render(role, registros, meta=None, produtos=None, state=None):
    ui = FakeUI(role, state)
    NS.update({"st": ui,
               "load_abc_valor": lambda: copy.deepcopy(META if meta is None else meta),
               "load_garantias": lambda: copy.deepcopy(registros),
               "has_full_data_access": lambda: role in ("admin", "diretor"),
               "fmt_brl": lambda value: f"R$ {value:.2f}",
               "fmt_brl_full": lambda value: f"R$ {value:.2f}",
               "show_money_table": lambda frame, *_args, **_kwargs: ui.tables.append(frame.copy(deep=True)),
               "_csv_download": lambda frame, *_args, **_kwargs: ui.exports.append(frame.copy(deep=True))})
    if produtos is None:
        produtos = pd.DataFrame([{"code": "SKU-EXEMPLO", "name": "Produto fictício"}])
    clientes = pd.DataFrame([{"name": "Distribuidor fictício"}])
    NS["page_garantias"](produtos, clientes)
    return ui


class VisibilidadeTests(unittest.TestCase):
    def test_pagina_e_csv_nao_revelam_canceladas_para_garantia(self):
        registros = [caso(), caso("G-SEGREDO-CANCELADO", "Cancelada", cliente="NOME-CANCELADO")]
        for role in ("garantia",):
            with self.subTest(role=role):
                ui = render(role, registros)
                self.assertEqual(ui.exports[0]["ID"].tolist(), ["G-1001"])
                self.assertNotIn("G-SEGREDO-CANCELADO", " ".join(ui.messages))
                self.assertNotIn("NOME-CANCELADO", " ".join(ui.messages))
                self.assertIn(("📋 Total histórico", 1), ui.metrics)
                relacao = next(t for t in ui.tables if "Casos / unidades" in t.columns)
                self.assertEqual(relacao["Casos"].tolist(), [1])

    def test_admin_master_diretor_exportam_canceladas_mas_relacao_as_exclui(self):
        for role in ("admin", "garantia_master", "diretor"):
            with self.subTest(role=role):
                ui = render(role, [caso(), caso("G-1002", "Cancelada")])
                self.assertEqual(ui.exports[0]["ID"].tolist(), ["G-1001", "G-1002"])
                self.assertIn(("📋 Total histórico", 2), ui.metrics)
                relacao = next(t for t in ui.tables if "Casos / unidades" in t.columns)
                self.assertEqual(relacao["Casos"].tolist(), [1])
                self.assertEqual(relacao["Custo"].tolist(), [30.0])

    def test_somente_canceladas_parece_vazio_para_operador(self):
        ui = render("garantia", [caso(status="Cancelada")])
        self.assertEqual(ui.exports, [])
        self.assertEqual(ui.metrics, [])

    def test_papel_desconhecido_sem_visibilidade(self):
        for role in (None, "vendedor", "desconhecido"):
            self.assertEqual(NS["_garantias_visiveis"]([caso()], role), [])

    def test_recorte_nao_muta_registros(self):
        registros = [caso(), caso(status="Cancelada")]
        original = copy.deepcopy(registros)
        NS["_garantias_visiveis"](registros, "garantia")
        self.assertEqual(registros, original)


class TempoTests(unittest.TestCase):
    def rotulo(self, g, hoje=date(2026, 9, 4)):
        return NS["_garantia_tempo_rotulo"](g, hoje)

    def test_aguardando_chegada_conta_abertura(self):
        g = caso(status="Aguardando chegada", criado="2026-09-01 10:00",
                 data_chegada="", data_envio="", concluido_em="")
        self.assertEqual(self.rotulo(g), "3d desde a abertura")

    def test_permanencia_comeca_na_chegada(self):
        g = caso(status="Em bancada", data_chegada="2026-09-02", data_envio="", concluido_em="")
        self.assertEqual(self.rotulo(g), "2d na empresa")

    def test_concluida_nao_envelhece(self):
        g = caso()
        esperado = "3d na empresa (chegada→envio)"
        self.assertEqual(self.rotulo(g), esperado)
        self.assertEqual(self.rotulo(g, date(2027, 9, 4)), esperado)

    def test_confirmada_sem_envio_congela_na_confirmacao(self):
        g = caso(status="Confirmado — aguardando R$ frete", data_envio="")
        esperado = "3d da chegada à confirmação"
        self.assertEqual(self.rotulo(g), esperado)
        self.assertEqual(self.rotulo(g, date(2027, 9, 4)), esperado)

    def test_legado_sem_chegada_explica_base(self):
        g = caso(data_chegada="", data_envio="")
        self.assertEqual(self.rotulo(g), "5d da abertura à confirmação")

    def test_encerrada_sem_data_final_nao_usa_hoje(self):
        for status in ("Concluída", "Cancelada", "Confirmado — aguardando R$ frete"):
            with self.subTest(status=status):
                g = caso(status=status, data_envio="", concluido_em="")
                self.assertEqual(self.rotulo(g), "duração encerrada — data final não informada")
                self.assertEqual(self.rotulo(g), self.rotulo(g, date(2027, 9, 4)))

    def test_datas_invertidas_ou_futuras_nao_geram_prazo_negativo(self):
        for g in (caso(data_envio="2026-08-11"), caso(data_envio="2027-08-15")):
            self.assertIn("confira as datas", self.rotulo(g))

    def test_datas_invalidas_nao_quebram_pagina(self):
        g = caso(status="Em bancada", criado=None, data_chegada="errada", data_envio="", concluido_em="")
        self.assertIn("data inicial não informada", self.rotulo(g))

    def test_reaberta_nao_congela_no_envio_do_ciclo_anterior(self):
        g = caso(status="Em bancada")
        self.assertEqual(self.rotulo(g), "23d desde a chegada registrada (caso ativo)")
        depois = NS["_garantia_tempo_info"](g, date(2026, 9, 5))
        self.assertEqual(depois["dias"], 24)
        self.assertEqual(depois["base"], "chegada_hoje")
        ui = render("garantia", [g])
        self.assertIn(("🔴 Em aberto", 1), ui.metrics)
        self.assertEqual(next(value for label, value in ui.metrics if label.startswith("⏱")), "—")

    def test_kpi_exclui_conclusao_anterior_a_abertura(self):
        g = caso(data_chegada="", data_envio="", concluido_em="2026-08-05 12:00")
        self.assertIn("confira as datas", self.rotulo(g))
        ui = render("garantia", [g])
        self.assertEqual(next(value for label, value in ui.metrics if label.startswith("⏱")), "—")
        self.assertTrue(any("Prazo calculado com 0 de 1" in m for m in ui.messages))

    def test_kpi_exclui_datas_futuras(self):
        futuro = (date.today() + timedelta(days=30)).isoformat()
        g = caso(data_envio=futuro)
        ui = render("garantia", [g])
        self.assertEqual(next(value for label, value in ui.metrics if label.startswith("⏱")), "—")
        self.assertTrue(any("Prazo calculado com 0 de 1" in m for m in ui.messages))

    def test_kpi_nao_mistura_bases_e_informa_cobertura(self):
        ui = render("garantia", [caso(), caso("G-1002", data_chegada="", data_envio=""),
                                 caso("G-1003", data_chegada="", data_envio="",
                                      concluido_em="2026-08-05 12:00")])
        self.assertIn(("⏱️ Tempo na empresa (chegada→envio)", "3 dias"), ui.metrics)
        self.assertTrue(any("Prazo calculado com 1 de 3" in m for m in ui.messages))

    def test_kpi_fallback_usa_mesma_base_do_card(self):
        g = caso(data_envio="")
        ui = render("garantia", [g])
        self.assertEqual(self.rotulo(g), "3d da chegada à confirmação")
        self.assertIn(("⏱️ Tempo médio (chegada→confirmação)", "3 dias"), ui.metrics)
        self.assertTrue(any("Prazo calculado com 1 de 1" in m for m in ui.messages))


class ReferenciaTests(unittest.TestCase):
    def test_janela_da_fonte_com_mes_final_parcial(self):
        self.assertEqual(NS["_garantia_periodo_vendas"](META),
                         (datetime(2025, 10, 1), datetime(2026, 9, 1, 14, 0)))

    def test_fim_do_periodo_encerrado_prevalece_sobre_publicacao(self):
        meta = {"periodo": "jan/2025 a dez/2025", "gerado_em": "2026-09-01 13:59"}
        self.assertEqual(NS["_garantia_periodo_vendas"](meta),
                         (datetime(2025, 1, 1), datetime(2026, 1, 1)))

    def test_limites_do_periodo_e_publicacao_e_canceladas(self):
        registros = [caso("ANTES", criado="2025-09-30 23:59"),
                     caso("INICIO", criado="2025-10-01 00:00"),
                     caso("PUBLICACAO", criado="2026-09-01 13:59"),
                     caso("DEPOIS", criado="2026-09-01 14:00"),
                     caso("INVALIDA", criado="texto"),
                     caso("CANCELADA", status="Cancelada")]
        periodo = NS["_garantia_periodo_vendas"](META)
        self.assertEqual([g["id"] for g in NS["_garantias_no_periodo_vendas"](registros, periodo)],
                         ["INICIO", "PUBLICACAO"])

    def test_meta_ausente_ou_invalida_nao_inventa_comparacao(self):
        for meta in ({}, None, {"periodo": "não informado"},
                     {"periodo": "out/2026 a set/2025", "gerado_em": "2026-09-01 13:59"},
                     {"periodo": "out/2025 a set/2026", "gerado_em": "errada"},
                     {"periodo": "out/2025 a set/2026", "gerado_em": "2025-09-01 13:59"}):
            with self.subTest(meta=meta):
                self.assertIsNone(NS["_garantia_periodo_vendas"](meta))

    def test_ui_sem_meta_preserva_exportacao_sem_taxa_inventada(self):
        ui = render("garantia", [caso()], meta={})
        self.assertEqual(ui.exports[0]["ID"].tolist(), ["G-1001"])
        self.assertFalse(any("Casos / unidades" in t.columns for t in ui.tables))
        self.assertTrue(any("Relação indisponível" in m for m in ui.messages))

    def test_relacao_sem_denominador_valido_indisponivel(self):
        for quantidade in (0, -1, None, "texto", float("nan"), float("inf")):
            self.assertIsNone(NS["_garantia_relacao_vendas"](2, quantidade))
        self.assertEqual(NS["_garantia_relacao_vendas"](2, 200), 0.01)

    def test_pagina_calcula_so_casos_da_janela_sem_alterar_custos(self):
        registros = [caso(), caso("G-1002", criado="2025-09-01 10:00", custo_total=999.0),
                     caso("G-1003", criado="2026-09-02 10:00", custo_total=999.0)]
        original = copy.deepcopy(registros)
        ui = render("garantia", registros)
        relacao = next(t for t in ui.tables if "Casos / unidades" in t.columns)
        self.assertEqual(relacao["Casos"].tolist(), [1])
        self.assertEqual(relacao["Casos / unidades"].tolist(), ["0.5%"])
        self.assertEqual(relacao["Custo"].tolist(), [30.0])
        self.assertEqual(len(ui.exports[0]), 3)
        self.assertEqual(registros, original)
        self.assertTrue(any("não representa a taxa real de defeito" in m for m in ui.messages))

    def test_sku_com_nomes_variantes_e_espacos_e_agregado_uma_vez(self):
        registros = [caso(produto_nome="Nome antigo"),
                     caso("G-1002", produto_sku=" SKU-EXEMPLO ", produto_nome="Nome atualizado")]
        ui = render("garantia", registros)
        relacao = next(t for t in ui.tables if "Casos / unidades" in t.columns)
        self.assertEqual(len(relacao), 1)
        self.assertEqual(relacao["SKU"].tolist(), ["SKU-EXEMPLO"])
        self.assertEqual(relacao["Produto"].tolist(), ["Produto fictício"])
        self.assertEqual(relacao["Casos"].tolist(), [2])
        self.assertEqual(relacao["Custo"].tolist(), [60.0])
        self.assertEqual(relacao["Unidades vendidas"].tolist(), [200])
        self.assertEqual(relacao["Casos / unidades"].tolist(), ["1.0%"])

    def test_sku_fora_catalogo_usa_primeiro_nome_valido(self):
        produtos = pd.DataFrame(columns=["code", "name"])
        registros = [caso(produto_nome=""), caso("G-1002", produto_nome="Nome histórico"),
                     caso("G-1003", produto_nome="Outra descrição")]
        ui = render("garantia", registros, produtos=produtos)
        relacao = next(t for t in ui.tables if "Casos / unidades" in t.columns)
        self.assertEqual(relacao["Produto"].tolist(), ["Nome histórico"])
        self.assertEqual(relacao["Casos"].tolist(), [3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
