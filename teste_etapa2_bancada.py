# -*- coding: utf-8 -*-
"""Lista/detalhe da Bancada com dados sintéticos e sem acesso à produção.

Executar: python teste_etapa2_bancada.py
Inclui interação real com widgets Streamlit via AppTest.
"""
import copy
import unittest
from datetime import date
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from teste_etapa1_garantias import caso, render


def abertos():
    return [caso("G-1001", status="Em bancada", prioridade="Normal", cliente_final="Alfa",
                 data_envio="", concluido_em=""),
            caso("G-1002", status="Aguardando peça", prioridade="Urgente", cliente_final="Beta",
                 data_envio="", concluido_em=""),
            caso("G-1003", status="Aguardando chegada", prioridade="Alta", cliente_final="Gama",
                 data_chegada="", data_envio="", concluido_em="")]


class ListaDetalheTests(unittest.TestCase):
    def test_lista_ordenada_mas_apenas_um_formulario_e_ficha(self):
        ui = render("garantia", abertos())
        tabela = next(t for t in ui.tables if "Cliente final / cliente" in t.columns)
        self.assertEqual(tabela["ID"].tolist(), ["G-1002", "G-1003", "G-1001"])
        self.assertEqual(ui.forms, ["gar_upd_atv_G-1002"])
        self.assertEqual(len(ui.expanders), 1)
        self.assertTrue(ui.expanders[0][1])
        self.assertIn("G-1002", ui.expanders[0][0])

    def test_selecao_por_id_preservada_com_ordenacao_nova(self):
        state = {"gar_atendimento_atv": "G-1001"}
        ui = render("garantia", abertos(), state=state)
        self.assertEqual(ui.forms, ["gar_upd_atv_G-1001"])
        mudados = abertos()
        mudados[2]["prioridade"] = "Urgente"
        ui = render("garantia", mudados, state=ui.session_state)
        self.assertEqual(ui.forms, ["gar_upd_atv_G-1001"])

    def test_id_obsoleto_volta_para_primeiro_valido(self):
        ui = render("garantia", abertos(), state={"gar_atendimento_atv": "G-REMOVIDO"})
        self.assertEqual(ui.session_state["gar_atendimento_atv"], "G-1002")
        self.assertEqual(ui.forms, ["gar_upd_atv_G-1002"])

    def test_busca_cliente_final_limita_lista_e_selecao(self):
        ui = render("garantia", abertos(), state={"gar_busca": "Alfa",
                                                  "gar_atendimento_atv": "G-1002"})
        self.assertEqual(ui.selectors["gar_atendimento_atv"]["options"], ["G-1001"])
        self.assertEqual(ui.forms, ["gar_upd_atv_G-1001"])

    def test_filtro_data_e_fila_preservados(self):
        registros = abertos()
        registros[0]["criado_em"] = "2026-08-20 10:00"
        ui = render("garantia", registros, state={"gar_dtde": date(2026, 8, 15),
                                                   "gar_dtate": date(2026, 8, 25), "gar_subtab": "bc"})
        self.assertEqual(ui.selectors["gar_atendimento_bc"]["options"], ["G-1001"])
        self.assertEqual(ui.forms, ["gar_upd_bc_G-1001"])

    def test_fila_vazia_limpa_selecao_sem_formulario(self):
        ui = render("garantia", abertos(), state={"gar_busca": "Inexistente",
                                                  "gar_atendimento_atv": "G-1002"})
        self.assertNotIn("gar_atendimento_atv", ui.session_state)
        self.assertNotIn("gar_atendimento_atv", ui.selectors)
        self.assertEqual(ui.forms, [])
        self.assertEqual(ui.expanders, [])

    def test_operador_consulta_concluida_sem_formulario(self):
        ui = render("garantia", [caso()], state={"gar_subtab": "co"})
        self.assertEqual(ui.selectors["gar_atendimento_co"]["options"], ["G-1001"])
        self.assertEqual(ui.forms, [])
        self.assertEqual(len(ui.expanders), 1)
        self.assertTrue(any("Garantia finalizada" in m for m in ui.messages))

    def test_master_preserva_correcao_da_concluida(self):
        ui = render("garantia_master", [caso()], state={"gar_subtab": "co"})
        self.assertEqual(ui.forms, ["gar_upd_co_G-1001"])
        self.assertTrue(any("Modo master" in m for m in ui.messages))

    def test_cancelada_nao_entra_no_seletor_do_operador(self):
        ui = render("garantia", [caso("G-CANCELADO", status="Cancelada"), *abertos()],
                    state={"gar_subtab": "td"})
        self.assertEqual(len(ui.selectors["gar_atendimento_td"]["options"]), 3)
        self.assertNotIn("G-CANCELADO", ui.selectors["gar_atendimento_td"]["options"])
        self.assertEqual(ui.forms, ["gar_upd_td_G-1002"])

    def test_registros_nao_sao_alterados_pela_selecao(self):
        registros = abertos()
        original = copy.deepcopy(registros)
        ui = render("garantia", registros, state={"gar_atendimento_atv": "G-1003"})
        self.assertEqual(ui.forms, ["gar_upd_atv_G-1003"])
        self.assertEqual(registros, original)


SCRIPT = '''
import copy
import pandas as pd
import streamlit as st
from teste_etapa1_garantias import NS, META
st.session_state.setdefault('role', 'garantia')

def atualizar(gid, updates, acao):
    st.session_state.setdefault('_updates', []).append((gid, copy.deepcopy(updates)))
    for registro in st.session_state['_cases']:
        if registro['id'] == gid:
            registro.update(updates)
    return True

def proibido(*args, **kwargs):
    raise AssertionError('Criação/exclusão não fazem parte desta validação')

NS.update({
    'st': st,
    'load_abc_valor': lambda: copy.deepcopy(META),
    'load_garantias': lambda: copy.deepcopy(st.session_state['_cases']),
    'has_full_data_access': lambda: st.session_state.get('role') in ('admin', 'diretor'),
    'fmt_brl': lambda value: f'R$ {value:.2f}',
    'fmt_brl_full': lambda value: f'R$ {value:.2f}',
    'show_money_table': lambda frame, *args, **kwargs: st.dataframe(frame),
    '_csv_download': lambda frame, *args, **kwargs: None,
    'update_garantia': atualizar,
    'add_garantia': proibido,
    'delete_garantia': proibido,
})
products = pd.DataFrame([{'code': 'SKU-EXEMPLO', 'name': 'Produto fictício'}])
clients = pd.DataFrame([{'name': 'Distribuidor fictício'}])
NS['page_garantias'](products, clients)
'''


class StreamlitBancadaTests(unittest.TestCase):
    def ui(self):
        # O app real usa logging DEBUG local; evita imprimir estados de widgets.
        with patch('logging.Logger.isEnabledFor', return_value=False):
            # AppTest 1.41 grava o script temporário no encoding do Windows.
            # Escapes mantêm os literais pt-BR e deixam o código temporário ASCII.
            script = SCRIPT.encode('ascii', 'backslashreplace').decode('ascii')
            at = AppTest.from_string(script, default_timeout=30)
            at.session_state['_cases'] = abertos()
            at.run()
        self.assertEqual(len(at.exception), 0)
        return at

    def run_ui(self, at):
        # AppTest 1.41 representa segmented_control como seleção múltipla,
        # embora a sessão guarde um ID único. Envia o vetor de índices que o
        # navegador usa, sem mudar o seletor real nem a regra do aplicativo.
        for group in at.get('button_group'):
            if isinstance(group.value, str):
                group.set_value([group.value])
        with patch('logging.Logger.isEnabledFor', return_value=False):
            at.run()
        self.assertEqual(len(at.exception), 0)
        return at

    def test_streamlit_preserva_id_ao_reordenar_opcoes(self):
        at = self.ui()
        at.selectbox(key='gar_atendimento_atv').select('G-1001')
        self.run_ui(at)
        self.assertEqual(at.selectbox(key='gar_atendimento_atv').value, 'G-1001')
        novos = abertos()
        novos[0]['prioridade'] = 'Urgente'
        novos[1]['prioridade'] = 'Normal'
        at.session_state['_cases'] = novos
        self.run_ui(at)
        self.assertEqual(at.selectbox(key='gar_atendimento_atv').value, 'G-1001')
        diagnosticos = [a.key for a in at.text_area if a.key.startswith('do_atv_')]
        self.assertEqual(diagnosticos, ['do_atv_G-1001'])

    def test_streamlit_busca_clampa_selecao_e_fila_vazia(self):
        at = self.ui()
        self.assertEqual(at.selectbox(key='gar_atendimento_atv').value, 'G-1002')
        at.text_input(key='gar_busca').input('Alfa')
        self.run_ui(at)
        self.assertEqual(at.selectbox(key='gar_atendimento_atv').value, 'G-1001')
        at.text_input(key='gar_busca').input('Inexistente')
        self.run_ui(at)
        self.assertFalse(any(s.key == 'gar_atendimento_atv' for s in at.selectbox))
        self.assertFalse(any(a.key.startswith('do_atv_') for a in at.text_area))

    def test_streamlit_submit_atual_altera_apenas_id_selecionado(self):
        at = self.ui()
        at.selectbox(key='gar_atendimento_atv').select('G-1001')
        self.run_ui(at)
        at.text_area(key='do_atv_G-1001').input('Atualização sintética do caso selecionado')
        next(b for b in at.button if b.label == '💾 Salvar atualização').click()
        self.run_ui(at)
        self.assertEqual([gid for gid, _ in at.session_state['_updates']], ['G-1001'])
        self.assertEqual(at.session_state['_cases'][0]['diagnostico_obs'],
                         'Atualização sintética do caso selecionado')
        self.assertEqual(at.session_state['_cases'][1]['diagnostico_obs'], 'Serviço fictício')

    def test_streamlit_submit_antigo_nao_muda_outro_caso(self):
        at = self.ui()
        self.assertEqual(at.selectbox(key='gar_atendimento_atv').value, 'G-1002')
        next(b for b in at.button if b.label == '💾 Salvar atualização').click()
        novos = abertos()
        novos[1]['status'] = 'Concluída'  # saiu da fila em outra sessão
        at.session_state['_cases'] = novos
        self.run_ui(at)
        self.assertEqual(at.selectbox(key='gar_atendimento_atv').value, 'G-1003')
        self.assertNotIn('_updates', at.session_state)
        self.assertEqual(at.session_state['_cases'][2]['diagnostico_obs'], 'Serviço fictício')


if __name__ == '__main__':
    unittest.main(verbosity=2)
