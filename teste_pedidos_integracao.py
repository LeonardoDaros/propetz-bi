"""Pedidos + Agenda + ficha reais por AST, com estado e clientes fictícios."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from teste_ficha_cliente_interface import EMPTY, NOW, fixture_script


def pedido(number, cid, vendor='Carteira A', **changes):
    row = dict(chave='teste:' + number, id=number, unidade_id='teste', unidade='Unidade Fictícia',
               numero=number, cliente_id=cid, cliente_nome='Nome de origem fictício',
               vendedor_nome=vendor, situacao='aberto', data_pedido='2026-09-01',
               data_prevista='2026-09-08', valor_total=100.0, fiscal_status='sem_nf', alertas=[],
               itens=[dict(sku='SKU-DO-DOC-' + number, produto='Produto fictício ' + number, quantidade=1)])
    row.update(changes)
    return row


SNAPSHOT = dict(schema_version=1, generated_at=NOW.isoformat(), coverage_start='2026-01-01',
                coverage_end='2026-09-05', pedidos=[
                    pedido('D-100', '001'),
                    pedido('D-110', '0010', situacao='preparando_envio'),
                    pedido('D-111', '0010', fiscal_status='nf_pendente'),
                    pedido('D-900', '003', 'Carteira B', valor_total=99999),
                    pedido('D-901', '003', 'Carteira B', fiscal_status='nf_pendente'),
                    pedido('D-999', '', cliente_nome='Sem vínculo fictício'),
                    pedido('D-101', '001', fiscal_status='faturado'),
                ])


def script(folder, *, preview=False):
    source = fixture_script(folder, preview=preview)
    injected = f'''
def pedidos_ficticios():
    if control.get('orders_unavailable'):
        raise ValueError('Pedidos indisponíveis nesta simulação.')
    return ns['pedidos_comerciais'].validate_snapshot(control.get('orders', {SNAPSHOT!a}),
        now=datetime.fromisoformat({NOW.isoformat()!r}))
ns['load_silver_pedidos_distribuicao'] = pedidos_ficticios
'''
    marker = "ns['load_silver_pedidos_distribuicao'] = pedidos_indisponiveis"
    if source.count(marker) != 1:
        raise AssertionError('A fixture mudou: revisar a injeção de pedidos antes de testar.')
    source = source.replace(marker, injected)
    source = source.replace("st.session_state.setdefault('role', 'vendedor')",
                            "st.session_state.setdefault('role', control.get('role', 'vendedor'))")
    return source


class PedidosIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='propetz-pedidos-integracao-')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.state_file = self.folder / 'agenda.json'
        self.state_file.write_text(json.dumps(EMPTY), encoding='utf-8')
        self.script_file = self.folder / 'ui.py'
        self.script_file.write_text(script(self.folder), encoding='utf-8')
        self.http = patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP proibido neste teste'))
        self.http_mock = self.http.start()
        self.addCleanup(self.http.stop)

    def start(self, **controls):
        self.control(**controls)
        self.app = AppTest.from_file(str(self.script_file), default_timeout=30).run()
        self.clean()
        return self.app

    def clean(self):
        self.assertEqual(list(self.app.exception), [])
        self.http_mock.assert_not_called()

    def control(self, **values):
        path = self.folder / 'control.json'
        old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        path.write_text(json.dumps({**old, **values}), encoding='utf-8')

    def texts(self):
        return '\n'.join(item.value for item in self.app.text)

    def state(self):
        return json.loads(self.state_file.read_text(encoding='utf-8'))

    def test_agenda_restricts_wallet_and_navigates_code_with_leading_zeroes(self):
        app = self.start()
        self.assertIn('Documento D-100', self.texts())
        self.assertIn('Documento D-110', self.texts())
        self.assertIn('Documento D-111', self.texts())
        for hidden in ('D-900', 'D-901', 'D-999', 'D-101'):
            self.assertNotIn('Documento ' + hidden, self.texts())
        buttons = [button for button in app.button if (button.key or '').startswith('agenda_pedidos_')
                   and '_pending_' not in button.key and button.key.endswith('_open')]
        self.assertEqual(len(buttons), 2)
        buttons[1].click().run()
        self.clean()
        self.assertEqual(app.selectbox(key='agenda_client').value, '0010')
        self.assertEqual(app.session_state['_ficha_selected_client'], '0010')
        self.assertTrue(any('4 dia(s) desde o pedido' in item.value for item in app.caption))
        self.assertEqual(self.state(), EMPTY)

    def test_manager_client_dossier_does_not_include_global_pending_documents(self):
        app = self.start(role='admin', saved_role='admin')
        # A Agenda do gestor pode mostrar pendências gerais.
        self.assertIn('Documento D-999', self.texts())
        app.radio(key='fixture_route').set_value('Clientes').run()
        app.selectbox(key='client_select').select('0010').run()
        self.clean()
        self.assertIn('Documento D-110', self.texts())
        self.assertIn('Documento D-111', self.texts())
        for hidden in ('D-100', 'D-101', 'D-900', 'D-901', 'D-999'):
            self.assertNotIn('Documento ' + hidden, self.texts())
        self.assertEqual(self.state(), EMPTY)

    def test_suggestion_fills_only_action_and_keeps_unsaved_contact(self):
        app = self.start()
        app.selectbox(key='agenda_client').select('0010').run()
        app.text_area(key='agenda_contact_0010_note').input('Rascunho fictício importante').run()
        before = deepcopy(app.session_state['_agenda_drafts']['0010'])
        buttons = [button for button in app.button if (button.key or '').startswith('ficha_pedidos_0010_')
                   and button.key.endswith('_suggest')]
        self.assertEqual(len(buttons), 1)
        buttons[0].click().run()
        self.clean()
        self.assertEqual(app.text_input(key='agenda_contact_0010_action').value,
                         'Confirmar a previsão de envio com a operação. Documento D-110 (Unidade Fictícia).')
        after = app.session_state['_agenda_drafts']['0010']
        self.assertEqual(after['note'], before['note'])
        self.assertEqual(after['event'], before['event'])
        self.assertEqual(after['version'], before['version'])
        self.assertEqual(self.state(), EMPTY)

    def test_unavailable_orders_preserve_purchases_and_contact_registration(self):
        app = self.start(orders_unavailable=True)
        self.assertTrue(any('pedidos está indisponível' in item.value for item in app.info))
        app.selectbox(key='agenda_client').select('001').run()
        app.radio(key='_ficha_001_view').set_value('Compras').run()
        self.clean()
        self.assertEqual(app.selectbox(key='_ficha_001_sku').value, 'SKU-EXEMPLO-A')
        app.selectbox(key='agenda_contact_001_channel').select('Ligação').run()
        app.selectbox(key='agenda_contact_001_outcome').select('Retorno combinado').run()
        app.text_area(key='agenda_contact_001_note').input('Conversa fictícia completa').run()
        app.text_input(key='agenda_contact_001_action').input('Retornar para confirmar condições').run()
        app.button(key='agenda_contact_001_save').click().run()
        self.clean()
        self.assertEqual(len(self.state()['clientes']['001']['historico']), 1)
        self.assertIn('Contato salvo', '\n'.join(item.value for item in app.success))

    def test_empty_client_orders_do_not_add_extra_filters(self):
        app = self.start()
        app.selectbox(key='agenda_client').select('005').run()
        self.clean()
        self.assertTrue(any('Nenhum pedido para acompanhar deste cliente' in item.value for item in app.info))
        self.assertFalse(any((item.key or '').startswith('ficha_pedidos_005') for item in app.radio))
        self.assertFalse(any((item.key or '').startswith('ficha_pedidos_005') for item in app.text_input))


if __name__ == '__main__':
    unittest.main()
