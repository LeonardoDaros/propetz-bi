"""Contratos de interface e segurança da importação assistida, sem Streamlit/DB."""
from copy import deepcopy
from collections import UserDict
from datetime import datetime, timezone
from hashlib import sha256
import json
import unittest

import orcamentos_garantias as dominio
import orcamentos_garantias_ui as ui


AGORA = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
UNIDADE = "fc97d781-d6d4-433d-94c3-7ceabb1b425a"


def orcamento():
    return {"id": 501, "unidade_negocio_id": UNIDADE, "unidade_negocio_nome": "Filial Foz",
            "tiny_id": 884761201, "numero_proposta": "2936", "data_orcamento": "2026-09-30",
            "contato_nome": "Pet de teste", "contato_tiny_id": 843502342,
            "situacao": "Concluído", "enriquecido": True, "valor_total": 999,
            "introducao": "PRODUTO/EQUIPAMENTO: MÁQUINA VOLARE\nRELATO DO CLIENTE: Não liga",
            "descricao_extra": "Diagnóstico: conferir na bancada", "marcadores": ["GARANTIA"],
            "itens": [{"sku": "VOL-100", "descricao": "Máquina Volare", "quantidade": 1, "tipo": "P"}],
            "pedidos": [{"pedido_id": "5217", "numero_pedido": "5217", "nota_fiscal_id": "5606",
                         "regra_origem": "Filial Foz", "tipo_vinculo": "Orçamento"}]}


def snapshot(budget=None, **campos):
    resultado = {"schema_version": 1, "status": "ok", "atualizado_em": AGORA.isoformat(),
                 "avisos": [], "cobertura": {"orcamentos_total": 1, "orcamentos_enriquecidos": 1},
                 "orcamentos": [budget or orcamento()]}
    resultado.update(campos)
    return resultado


def prefixo(budget=None):
    b = budget or orcamento()
    chave = f"{b['unidade_negocio_id']}:{b['tiny_id']}"
    assinatura = json.dumps(dominio.preparar_orcamento(b)["dados_origem"], ensure_ascii=False,
                            sort_keys=True, separators=(",", ":"))
    return "tiny_gar_" + sha256((chave + assinatura).encode("utf-8")).hexdigest()[:16]


class FakeStreamlit:
    """Os botões podem fingir clique mesmo disabled para provar o guard do app."""
    def __init__(self, inputs=None, checks=False, clicks=None):
        self.inputs = inputs or {}
        self.checks = checks
        self.clicks = set(clicks or [])
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _out(self, metodo, value, **kwargs):
        self.calls.append((metodo, value, kwargs))

    def subheader(self, value): self._out("subheader", value)
    def caption(self, value): self._out("caption", value)
    def text(self, value): self._out("text", value)
    def info(self, value): self._out("info", value)
    def warning(self, value): self._out("warning", value)
    def error(self, value): self._out("error", value)
    def dataframe(self, value, **kwargs): self._out("dataframe", value, **kwargs)
    def expander(self, value, **kwargs): self._out("expander", value, **kwargs); return self
    def container(self, **kwargs): self._out("container", "", **kwargs); return self

    def text_input(self, label, **kwargs):
        self._out("text_input", label, **kwargs)
        return self.inputs.get(kwargs.get("key"), "")

    def selectbox(self, label, options, **kwargs):
        options = list(options)
        self._out("selectbox", label, options=options, **kwargs)
        value = self.inputs.get(kwargs.get("key"), options[0] if options else None)
        formatter = kwargs.get("format_func")
        if callable(formatter) and value in options:
            self._out("format_func", formatter(value))
        return value

    def checkbox(self, label, **kwargs):
        self._out("checkbox", label, **kwargs)
        return self.inputs.get(kwargs.get("key"), self.checks)

    def radio(self, label, options, **kwargs):
        self._out("radio", label, **kwargs)
        return self.inputs.get(kwargs.get("key"), options[0])

    def button(self, label, **kwargs):
        self._out("button", label, **kwargs)
        return label in self.clicks or kwargs.get("key") in self.clicks

    def markdown(self, *args, **kwargs):
        raise AssertionError("Conteúdo de ERP não pode ser renderizado em Markdown/HTML.")


class ImportacaoUITest(unittest.TestCase):
    def render(self, st=None, budget=None, registros=None, role="garantia", **callbacks):
        st = st or FakeStreamlit()
        result = ui.render_importacao_tiny(st, snapshot(budget), registros or [], role,
            catalogo={"VOL-100": "Máquina Volare"}, agora=AGORA, **callbacks)
        return st, result

    def test_vendedor_nao_inspeciona_snapshot_nem_renderiza_lista(self):
        st = FakeStreamlit()
        result = ui.render_importacao_tiny(st, object(), object(), "vendedor")
        self.assertEqual(result["status"], "sem_permissao")
        self.assertEqual(st.calls, [])

    def test_usuario_mapping_com_role_reconhecido(self):
        self.assertTrue(ui.pode_importar(UserDict({"role": "garantia"})))
        self.assertFalse(ui.pode_importar(UserDict({"role": "vendedor"})))

    def test_sem_carga_mantem_manual_e_informa_indisponibilidade(self):
        st = FakeStreamlit()
        result = ui.render_importacao_tiny(st, None, [], "garantia")
        self.assertEqual(result["status"], "indisponivel")
        self.assertTrue(any("entrada manual" in str(c[1]) for c in st.calls))

    def test_html_erp_vai_so_para_texto_tabela_e_controles_nativos(self):
        budget = orcamento()
        ataque = '<img src=x onerror="alert(1)"><script>alert(2)</script>'
        budget.update(contato_nome=ataque, introducao=ataque, descricao_extra="[Clique](javascript:alert(3))")
        budget["itens"][0]["descricao"] = ataque
        budget["marcadores"].append(ataque)
        st, result = self.render(budget=budget)
        self.assertEqual(result["status"], "conferindo")
        self.assertFalse(any(c[2].get("unsafe_allow_html") for c in st.calls))
        self.assertFalse(any(c[0] == "text" and ataque == c[1] for c in st.calls))
        self.assertNotIn("alert(2)", repr(st.calls))

    def test_prefill_carrega_so_relato_equipamento_e_origem(self):
        recebido = []
        st = FakeStreamlit(inputs={prefixo() + "_serie": "SER-100"}, checks=True,
                           clicks={"Conferir na Nova Garantia"})
        _, result = self.render(st=st, abrir_nova=recebido.append)
        self.assertEqual(result["status"], "abrir_nova")
        self.assertEqual(recebido[0]["campos_iniciais"],
                         {"relato": "Não liga", "produto": "Máquina Volare", "sku": "VOL-100"})
        self.assertEqual(recebido[0]["tiny_context"]["origem_tiny"]["unidade_atendida"], "serie:SER-100")
        self.assertFalse({"cliente", "cliente_final", "canal", "pecas", "custo_total"}
                         & recebido[0]["campos_iniciais"].keys())

    def test_botao_falso_nao_continua_sem_confirmacao_ou_unidade(self):
        recebido = []
        st = FakeStreamlit(clicks={"Conferir na Nova Garantia"})
        _, result = self.render(st=st, abrir_nova=recebido.append)
        self.assertEqual(result["status"], "conferindo")
        self.assertEqual(recebido, [])

    def test_sem_enriquecimento_bloqueia_mesmo_com_confirmacao(self):
        budget = orcamento(); budget["enriquecido"] = False
        recebido = []
        st = FakeStreamlit(inputs={prefixo() + "_serie": "SER-100"}, checks=True,
                           clicks={"Conferir na Nova Garantia"})
        self.render(st=st, budget=budget, abrir_nova=recebido.append)
        self.assertEqual(recebido, [])

    def test_conflito_volare_aura_exige_checkbox_especifico(self):
        budget = orcamento(); budget["numero_proposta"] = "3162"
        budget["itens"][0].update(sku="AURA-100", descricao="Secador Aura")
        recebido = []
        st = FakeStreamlit(inputs={prefixo(budget) + "_serie": "SER-100", prefixo(budget) + "_conflito": False},
                           checks=True, clicks={"Conferir na Nova Garantia"})
        self.render(st=st, budget=budget, abrir_nova=recebido.append)
        self.assertEqual(recebido, [])
        st.inputs[prefixo(budget) + "_conflito"] = True
        self.render(st=st, budget=budget, abrir_nova=recebido.append)
        self.assertEqual(recebido[0]["campos_iniciais"]["sku"], "")
        self.assertTrue(recebido[0]["tiny_context"]["confirmou_conflitos"])

    def test_pedido_nf_1n_nao_descarta_referencias(self):
        budget = orcamento()
        budget["pedidos"].append({"pedido_id": "5218", "numero_pedido": "5218", "nota_fiscal_id": "5607"})
        st, _ = self.render(budget=budget)
        tabelas = [c[1] for c in st.calls if c[0] == "dataframe"]
        fiscal = [t for t in tabelas if t and "ID da NF no Silver" in t[0]][0]
        self.assertEqual([x["ID da NF no Silver"] for x in fiscal], ["5606", "5607"])

    def test_cancelada_bloqueia_copia_sem_vazar_id_status_privado(self):
        st, result = self.render(ligacao_origem=lambda _: {
            "estado": "vinculado", "vinculos": [{"id": "", "status": "restrito", "unidade_atendida": ""}], "total": 1})
        self.assertEqual(result["status"], "vinculo_restrito")
        self.assertFalse(any(c[0] == "text_input" and "série" in c[1] for c in st.calls))

    def test_cancelada_bruta_nao_revela_protocolo_a_garantia(self):
        st, result = self.render(ligacao_origem=lambda _: {
            "estado": "vinculado", "vinculos": [{"id": "G-SEGREDO", "status": "Cancelada", "unidade_atendida": "manual:SECRETO"}], "total": 1})
        self.assertEqual(result["status"], "vinculo_restrito")
        self.assertNotIn("G-SEGREDO", repr(st.calls))
        self.assertNotIn("manual:SECRETO", repr(st.calls))
        self.assertNotIn("Pet de teste", repr(st.calls))
        self.assertNotIn("RELATO DO CLIENTE", repr(st.calls))
        self.assertFalse(any(c[0] == "selectbox" for c in st.calls))

    def test_falha_dedup_bloqueia_antes_de_busca_e_nomes(self):
        st, result = self.render(ligacao_origem=lambda _: None)
        self.assertEqual(result["status"], "ligacao_indisponivel")
        self.assertNotIn("Pet de teste", repr(st.calls))

    def test_confirmacoes_resetam_quando_texto_origem_muda(self):
        primeiro = orcamento()
        segundo = orcamento(); segundo["descricao_extra"] = "Novo diagnóstico no Tiny"
        self.assertNotEqual(prefixo(primeiro), prefixo(segundo))
        novo = []
        st = FakeStreamlit(inputs={prefixo(primeiro) + "_serie": "SER-100", prefixo(primeiro) + "_conferiu": True},
                           clicks={"Conferir na Nova Garantia"})
        self.render(st=st, budget=segundo, abrir_nova=novo.append)
        self.assertEqual(novo, [])

    def test_equipmento_existente_abre_protocolo_em_vez_de_criar(self):
        contexto = dominio.preparar_contexto_importacao(orcamento(), unidade_atendida="serie:SER-100",
            confirmado=True, atualizado_em=AGORA.isoformat(), agora=AGORA)
        registros = [{"id": "G-100", "status": "Em bancada", "origem_tiny": contexto["origem_tiny"]}]
        aberto = []; novo = []
        st = FakeStreamlit(clicks={"Abrir protocolo G-100"})
        _, result = self.render(st=st, registros=registros, abrir_existente=aberto.append, abrir_nova=novo.append)
        self.assertEqual(result["status"], "abrir_existente")
        self.assertEqual(aberto, ["G-100"]); self.assertEqual(novo, [])

    def test_outra_unidade_do_mesmo_orcamento_exige_confirmacao_multiplo(self):
        contexto = dominio.preparar_contexto_importacao(orcamento(), unidade_atendida="serie:SER-100",
            confirmado=True, atualizado_em=AGORA.isoformat(), agora=AGORA)
        registros = [{"id": "G-100", "status": "Em bancada", "origem_tiny": contexto["origem_tiny"]}]
        novo = []
        st = FakeStreamlit(inputs={prefixo() + "_serie": "SER-101", prefixo() + "_multiplo": False}, checks=True,
                           clicks={"Conferir na Nova Garantia"})
        _, result = self.render(st=st, registros=registros, abrir_nova=novo.append)
        self.assertEqual(result["status"], "ja_vinculado"); self.assertEqual(novo, [])
        st.inputs[prefixo() + "_multiplo"] = True
        self.render(st=st, registros=registros, abrir_nova=novo.append)
        self.assertTrue(novo[0]["tiny_context"]["confirmou_multiplo"])

    def test_vincular_inclui_versao_sem_copiar_campos_clinicos(self):
        recebido = []
        registro = {"id": "G-100", "status": "Em bancada", "cliente": "Cliente confirmado",
                    "produto_nome": "Volare", "diagnostico_causa": "Motor", "custo_total": 350, "_version": "sha-versao"}
        antes = deepcopy(registro)
        st = FakeStreamlit(inputs={prefixo() + "_serie": "SER-100", prefixo() + "_acao": "Vincular a um protocolo já existente"},
                           checks=True, clicks={"Confirmar vínculo com o Tiny"})
        self.render(st=st, registros=[registro], vincular_existente=lambda *args: recebido.append(args))
        self.assertEqual(recebido[0][0], "G-100"); self.assertEqual(recebido[0][2], "sha-versao")
        self.assertEqual(registro, antes)

    def test_fechadas_vinculo_apenas_master_admin(self):
        registros = [{"id": "ABERTA", "status": "Em bancada"}, {"id": "FECHADA", "status": "Concluída"},
                     {"id": "CANCELADA", "status": "Cancelada"}]
        for papel in ("garantia", "diretor"):
            self.assertEqual([x["id"] for x in ui.registros_para_vincular(registros, papel)], ["ABERTA"])
        for papel in ("garantia_master", "admin"):
            self.assertEqual(len(ui.registros_para_vincular(registros, papel)), 3)

    def test_busca_so_local_por_numero_sku_texto(self):
        self.assertEqual(len(ui.filtrar_orcamentos([orcamento()], "2936 VOL-100")), 1)
        self.assertEqual(ui.filtrar_orcamentos([orcamento()], "ausente"), [])

    def test_carga_parcial_nao_afirma_ausencia_de_orcamento(self):
        st = FakeStreamlit(inputs={"tiny_gar_busca": "999999"})
        result = ui.render_importacao_tiny(st, snapshot(status="parcial"), [], "garantia", agora=AGORA)
        self.assertEqual(result["status"], "sem_resultados")
        self.assertIn("não prova", repr(st.calls))


class OrigemUITest(unittest.TestCase):
    def registro(self):
        contexto = dominio.preparar_contexto_importacao(orcamento(), unidade_atendida="serie:SER-100",
            confirmado=True, atualizado_em=AGORA.isoformat(), agora=AGORA)
        return {"id": "G-100", "status": "Em bancada", "origem_tiny": contexto["origem_tiny"], "_version": "v1"}

    def test_origem_cancelada_garantia_nao_renderiza_nada(self):
        registro = self.registro(); registro["status"] = "Cancelada"
        st = FakeStreamlit()
        self.assertEqual(ui.render_origem_tiny(st, registro, snapshot(), "garantia")["status"], "sem_permissao")
        self.assertEqual(st.calls, [])

    def test_origem_igual_apenas_mostra_conferencia(self):
        st = FakeStreamlit(checks=True)
        result = ui.render_origem_tiny(st, self.registro(), snapshot(), "garantia", agora=AGORA)
        self.assertEqual(result["status"], "origem_atual")

    def test_origem_alterada_requer_confirmacao_e_versao(self):
        budget = orcamento(); budget["descricao_extra"] = "Diagnóstico na origem atualizado"
        recebido = []
        st = FakeStreamlit(checks=True, clicks={"Atualizar referência do Tiny"})
        result = ui.render_origem_tiny(st, self.registro(), snapshot(budget), "garantia", agora=AGORA,
            atualizar_origem=lambda *args: recebido.append(args))
        self.assertEqual(result["status"], "atualizar_origem")
        self.assertEqual(recebido[0][0], "G-100"); self.assertEqual(recebido[0][2], "v1")
        self.assertNotIn("diagnostico_causa", recebido[0][1])

    def test_origem_fechada_comum_somente_leitura(self):
        budget = orcamento(); budget["descricao_extra"] = "Alterou origem"
        registro = self.registro(); registro["status"] = "Concluída"
        recebido = []
        st = FakeStreamlit(checks=True, clicks={"Atualizar referência do Tiny"})
        result = ui.render_origem_tiny(st, registro, snapshot(budget), "garantia", agora=AGORA,
            atualizar_origem=lambda *args: recebido.append(args))
        self.assertEqual(result["status"], "origem_alterada_somente_leitura"); self.assertEqual(recebido, [])

    def test_origem_ausente_na_carga_nao_sugere_cancelar_ou_apagar(self):
        st = FakeStreamlit(checks=True)
        result = ui.render_origem_tiny(st, self.registro(), snapshot(orcamentos=[]), "garantia", agora=AGORA)
        self.assertEqual(result["status"], "origem_sem_detalhe_atual")
        self.assertIn("não cancela", repr(st.calls))

    def test_origem_recolhida_nao_despeja_texto_na_bancada(self):
        st = FakeStreamlit()
        result = ui.render_origem_tiny(st, self.registro(), snapshot(), "garantia", agora=AGORA)
        self.assertEqual(result["status"], "origem_recolhida")
        self.assertFalse(any(c[0] in {"text", "dataframe"} for c in st.calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
