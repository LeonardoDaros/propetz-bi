"""Interface de pedidos com dados fictícios; sem app, rede ou estado real."""
from copy import deepcopy
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


def order(number="100", **changes):
    row = dict(chave="unidade-a:" + number, id=number, unidade_id="unidade-a",
               unidade="Unidade de Teste", numero=number, cliente_id="001",
               cliente_nome="Cliente Exemplo", vendedor_nome="Carteira Fictícia",
               situacao="aberto", data_pedido="2026-09-18", data_prevista="2026-09-23",
               valor_total=1234.50, fiscal_status="sem_nf", alertas=[],
               itens=[dict(sku="SKU-FICTICIO", produto="Produto de teste", quantidade=2)],
               acao_sugerida="Confirmar a decisão sobre o documento " + number)
    row.update(changes)
    return row


def snapshot(rows=None, **changes):
    rows = [order()] if rows is None else rows
    view = dict(pedidos=rows, pendencias=[], generated_at="2026-09-18T22:00:00-03:00",
                coverage_start="2026-01-01", coverage_end="2026-09-18", stale=False,
                resumo={key: dict(quantidade=sum(row['situacao'] == key for row in rows),
                                  valor=sum(row['valor_total'] for row in rows if row['situacao'] == key))
                        for key in ('aberto', 'aprovado', 'preparando_envio')})
    view.update(changes)
    return view


def fixture(view, *, compact=False):
    root = str(Path(__file__).resolve().parent)
    return f'''
import sys
sys.path.insert(0, {root!a})
import streamlit as st
import pedidos_comerciais_ui as ui

def opened(cid):
    st.session_state['opened'] = cid

def suggested(action):
    st.session_state['suggested'] = action

ui.render_pedidos({view!a}, key_prefix='test', on_open_client=opened,
                  on_suggest=suggested, compact={compact!r})
'''


class PedidosInterfaceTests(unittest.TestCase):
    def render(self, view, **kwargs):
        app = AppTest.from_string(fixture(view, **kwargs), default_timeout=15).run()
        self.assertEqual(list(app.exception), [])
        return app

    def test_absence_does_not_become_zero_or_offer_actions(self):
        for invalid in (None, {}, {'pedidos': None}):
            app = self.render(invalid)
            self.assertIn('indisponível', app.info[0].value)
            self.assertFalse(app.button)
            self.assertFalse(any('R$ 0,00' in value.value for value in app.markdown))

    def test_real_zero_stage_and_pending_not_in_summary(self):
        pending = order('999', valor_total=9000, fiscal_status='nf_pendente',
                        motivos=['Nota vinculada; aguarda conferência fiscal.'])
        app = self.render(snapshot(pendencias=[pending]))
        summary = next(item.value for item in app.markdown if 'pp-pedidos-stats' in item.value)
        self.assertIn('R$ 1.234,50', summary)
        self.assertIn('R$ 0,00', summary)
        self.assertNotIn('R$ 9.000,00', summary)
        self.assertTrue(any('Em conferência' in item.value for item in app.caption))
        self.assertFalse(any(button.label == 'Usar como próxima ação' for button in app.button))

    def test_filter_search_and_pagination_leave_no_stale_selection(self):
        rows = [order(str(n)) for n in range(100, 107)] + [order('500', situacao='preparando_envio')]
        app = self.render(snapshot(rows))
        self.assertEqual(len([button for button in app.button if button.label == 'Abrir cliente →']), 5)
        app.selectbox(key='test_page').set_value(2).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(len([button for button in app.button if button.label == 'Abrir cliente →']), 3)
        app.radio(key='test_status').set_value('Preparando envio').run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any('Documento 500' in item.value for item in app.text))
        self.assertFalse(any('Documento 100' in item.value for item in app.text))
        app.text_input(key='test_search').set_value('inexistente').run()
        self.assertEqual(list(app.exception), [])
        self.assertIn('Nenhum pedido', app.info[0].value)
        self.assertFalse(app.button)

    def test_open_callback_uses_code_even_for_same_names(self):
        app = self.render(snapshot([order('100'), order('101', cliente_id='002')]))
        buttons = [button for button in app.button if button.label == 'Abrir cliente →']
        buttons[1].click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.session_state['opened'], '002')

    def test_compact_suggestion_requires_click_and_only_updates_callback(self):
        app = self.render(snapshot(), compact=True)
        self.assertNotIn('suggested', app.session_state)
        self.assertFalse(any(button.label == 'Abrir cliente →' for button in app.button))
        app.button[0].click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.session_state['suggested'], 'Confirmar a decisão sobre o documento 100')
        self.assertNotIn('opened', app.session_state)

    def test_stale_currency_and_external_html_safe(self):
        hostile = '<img src=x onerror=alert(1)>'
        row = order(cliente_nome=hostile, unidade=hostile, numero='**42**',
                    itens=[dict(sku=hostile, produto=hostile, quantidade=1)])
        app = self.render(snapshot([row], stale=True))
        self.assertIn('mais de 24 horas', app.warning[0].value)
        self.assertIn('18/09/2026 às 22:00', app.warning[0].value)
        headers = '\n'.join(item.value for item in app.markdown)
        self.assertIn('&lt;img', headers)
        self.assertNotIn(hostile, headers)
        self.assertTrue(any(hostile in item.value for item in app.text))
        self.assertTrue(any('Não compõem o faturamento' in item.value for item in app.caption))

    def test_same_document_number_in_two_units_and_input_unchanged(self):
        source = snapshot([order(), order(unidade_id='unidade-b', chave='unidade-b:100')])
        before = deepcopy(source)
        app = self.render(source)
        self.assertEqual(len(app.button), 2)
        self.assertEqual(source, before)


if __name__ == '__main__':
    unittest.main()
