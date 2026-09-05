"""Ficha integrada: AppTest, funções reais por AST e dados inteiramente fictícios.

Não executa bootstrap do app, não acessa usuários/secrets reais nem a rede.
fixture_script também fornece uma prévia local para inspeção visual.
"""
import copy
from datetime import date, datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from streamlit.testing.v1 import AppTest
import agenda_comercial as agenda


APP_PATH = Path(__file__).with_name('app.py').resolve()
NOW = datetime.fromisoformat('2026-09-05T10:00:00-03:00')
MONTHS = [f'{name}/{year % 100:02d}' for year in (2024, 2025, 2026)
          for name in ('jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez')
          if year < 2026 or name not in ('set', 'out', 'nov', 'dez')]
CLIENTS = [
    dict(id='001', name='Distribuidor Exemplo', vendor='Carteira A', state='PR', status='Ativo',
         risk='Recuperação', months_since=7, monthly=[1200.] * 25 + [0.] * 7, last_purchase='jan/26'),
    dict(id='002', name='Distribuidor Exemplo', vendor='Carteira A', state='SC', status='Ativo',
         risk='Atenção', months_since=4, monthly=[500.] * 28 + [0.] * 4, last_purchase='abr/26'),
    dict(id='003', name='Cliente Restrito Fictício', vendor='Carteira B', state='SP', status='Ativo',
         risk='Recuperação', months_since=8, monthly=[700.] * 24 + [0.] * 8, last_purchase='dez/25'),
    dict(id='004', name='Cliente Inativado Fictício', vendor='Carteira A', state='PR', status='Ativo',
         risk='Recuperação', months_since=9, monthly=[600.] * 23 + [0.] * 9, last_purchase='nov/25'),
    dict(id='005', name='Cliente Recorrente Fictício', vendor='Carteira A', state='PR', status='Ativo',
         risk='Saudável', months_since=1, monthly=[800.] * 32, last_purchase='ago/26'),
    dict(id='006', name='Cadastro Inativo Fictício', vendor='Carteira A', state='PR', status='Inativo',
         risk='Recuperação', months_since=9, monthly=[400.] * 23 + [0.] * 9, last_purchase='nov/25'),
    dict(id='0010', name='Outro Código Fictício', vendor='Carteira A', state='PR', status='Ativo',
         risk='Saudável', months_since=1, monthly=[300.] * 32, last_purchase='ago/26'),
]
PRODUCTS = [
    dict(cod_cliente='001', sku='SKU-EXEMPLO-A', produto='Lâmina fictícia A', mes='jan/24', quantidade=20.),
    dict(cod_cliente='001', sku='SKU-EXEMPLO-A', produto='Lâmina fictícia A', mes='jan/26', quantidade=6.),
    dict(cod_cliente='002', sku='SKU-EXEMPLO-B', produto='Tesoura fictícia B', mes='abr/26', quantidade=9.),
    dict(cod_cliente='003', sku='SKU-RESTRITO', produto='Produto restrito fictício', mes='ago/26', quantidade=99.),
    dict(cod_cliente='004', sku='SKU-INATIVO', produto='Produto histórico fictício', mes='nov/25', quantidade=3.),
]
EMPTY = {'schema_version': 1, 'clientes': {}}


def fixture_script(folder, preview=False):
    """Recebe pasta exclusiva da fixture; seu agenda.json nunca é o estado real."""
    folder = Path(folder).resolve()
    return f'''
import ast, copy, json, sys, threading, types
from pathlib import Path
from datetime import datetime
import pandas as pd
import streamlit as st

app_path = Path({str(APP_PATH)!r})
sys.path.insert(0, str(app_path.parent))
tree = ast.parse(app_path.read_text(encoding='utf-8-sig'))
nodes = [copy.deepcopy(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
for node in nodes:
    if isinstance(node, ast.FunctionDef):
        node.decorator_list = []
ns = {{'__file__': str(app_path), '__name__': 'isolated_app_functions'}}
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<app-functions-only>', 'exec'), ns)

folder = Path({str(folder)!r})
folder.mkdir(parents=True, exist_ok=True)
state_file = folder / 'agenda.json'
if not state_file.exists():
    state_file.write_text(json.dumps({EMPTY!r}), encoding='utf-8')
control_file = folder / 'control.json'
control = json.loads(control_file.read_text(encoding='utf-8')) if control_file.exists() else {{}}
clients = pd.DataFrame({CLIENTS!r})
clients = clients[~clients['id'].isin(control.get('exclude', []))].copy()
products = pd.DataFrame({PRODUCTS!r})
months = {MONTHS!r}
def denied(*args, **kwargs):
    raise AssertionError('Esta fixture não permite acesso à rede.')
ns['requests'] = types.SimpleNamespace(get=denied, put=denied, post=denied,
                                     RequestException=RuntimeError)
ns['AGENDA_FILE'] = str(state_file)
ns['_STATE_RAW_CACHE'] = {{}}
ns['_GH_WRITE_LOCK'] = threading.RLock()
ns['_SESSION_INATIVIDADE'] = 10800
ns['_SESSION_MAX'] = 43200
ns['_gh_token'] = lambda: None
ns['_agenda_now'] = lambda: datetime.fromisoformat({NOW.isoformat()!r})
ns['load_inactive_clients'] = lambda: set(control.get('inactive', ['004']))
ns['load_data'] = lambda: (clients, pd.DataFrame(), pd.DataFrame(), months, {{}}, products)
ns['load_users'] = lambda: {{'users': {{'pessoa_ficticia': {{'name': 'Pessoa Fictícia',
    'role': control.get('saved_role', 'vendedor'), 'vendor_filter': control.get('saved_vendor', 'Carteira A')}}}}}}
actual_load_agenda = ns['load_agenda']
def load_agenda():
    if control.get('history_error'):
        raise ValueError('Histórico fictício temporariamente indisponível.')
    return actual_load_agenda()
ns['load_agenda'] = load_agenda
if control.get('write_error'):
    def unavailable_write(state):
        raise OSError('Falha simulada ao persistir o registro local.')
    ns['_agenda_write_local'] = unavailable_write

st.set_page_config(page_title='Prévia fictícia · Ficha Propetz', layout='wide')
if {preview!r}:
    ns['ui'].apply_theme()
    st.caption('PRÉVIA LOCAL · CLIENTES E VALORES FICTÍCIOS · SEM CONEXÃO COM PRODUÇÃO')
st.session_state.setdefault('authenticated', True)
st.session_state.setdefault('username', 'pessoa_ficticia')
st.session_state.setdefault('user_name', 'Pessoa Fictícia')
st.session_state.setdefault('role', 'vendedor')
st.session_state.setdefault('vendor_filter', 'Carteira A')
route = st.radio('Página de teste', ['Hoje', 'Clientes', 'Outra página'], horizontal=True, key='fixture_route')
if route == 'Hoje':
    ns['page_agenda'](clients, months, products)
elif route == 'Clientes':
    ns['page_clients'](clients, products, months, {{}}, list(range(len(months))), months)
else:
    st.info('Página fictícia sem widgets da ficha; comprova a preservação do rascunho ao navegar.')
'''


class FichaInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='propetz-ficha-ui-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.state_file = self.folder / 'agenda.json'
        self.state_file.write_text(json.dumps(EMPTY), encoding='utf-8')
        script = self.folder / 'ui.py'
        script.write_text(fixture_script(self.folder), encoding='utf-8')
        # Defesa independente: qualquer HTTP acidental faz o teste falhar.
        self.http = patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP proibido na fixture'))
        self.http_mock = self.http.start()
        self.addCleanup(self.http.stop)
        self.at = AppTest.from_file(str(script), default_timeout=30).run()
        self.clean()

    def clean(self):
        self.assertEqual(len(self.at.exception), 0, [item.message for item in self.at.exception])
        self.http_mock.assert_not_called()

    def state(self):
        return json.loads(self.state_file.read_text(encoding='utf-8'))

    def control(self, **values):
        path = self.folder / 'control.json'
        current = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        path.write_text(json.dumps({**current, **values}), encoding='utf-8')

    def route(self, page):
        self.at.radio(key='fixture_route').set_value(page).run()
        self.clean()

    def client(self, cid):
        key = 'agenda_client' if self.at.radio(key='fixture_route').value == 'Hoje' else 'client_select'
        self.at.selectbox(key=key).select(cid).run()
        self.clean()

    def draft(self, cid='001'):
        return copy.deepcopy(self.at.session_state['_agenda_drafts'][cid])

    def fill(self, cid='001', note='Conversa fictícia ainda não salva'):
        prefix = f'agenda_contact_{cid}'
        self.at.selectbox(key=prefix + '_channel').select('Ligação').run()
        self.at.selectbox(key=prefix + '_outcome').select('Retorno combinado').run()
        self.at.text_area(key=prefix + '_note').input(note).run()
        self.at.text_input(key=prefix + '_action').input('Retornar sobre a proposta fictícia').run()
        self.at.date_input(key=prefix + '_date').set_value(date(2026, 9, 8)).run()
        self.at.checkbox(key=prefix + '_closed').set_value(True).run()
        self.clean()

    def external_contact(self, *, eid=None, expected=0):
        state = agenda.register_contact(self.state(), client_id='001', actor='outra_pessoa_ficticia',
            channel='WhatsApp', outcome='Retorno combinado', note='Histórico sintético de outra sessão',
            next_action='Confirmar condições', return_date='2026-09-07', closed=False,
            expected_version=expected, event_id=eid or str(uuid.uuid4()), now=NOW)
        self.state_file.write_text(json.dumps(state), encoding='utf-8')

    def test_duplicate_names_remain_distinct_and_scoped_in_both_routes(self):
        choices = self.at.selectbox(key='agenda_client').options
        self.assertEqual(sum('Distribuidor Exemplo' in value for value in choices), 2)
        self.assertFalse(any('Restrito' in value or 'Inativo' in value or 'Inativado' in value for value in choices))
        for cid, sku in [('001', 'SKU-EXEMPLO-A'), ('002', 'SKU-EXEMPLO-B')]:
            self.client(cid)
            self.at.radio(key=f'_ficha_{cid}_view').set_value('Compras').run()
            self.clean()
            self.assertEqual(self.at.selectbox(key=f'_ficha_{cid}_sku').value, sku)
        self.route('Clientes')
        choices = self.at.selectbox(key='client_select').options
        self.assertEqual(sum('Distribuidor Exemplo' in value for value in choices), 2)
        self.assertFalse(any('Restrito' in value for value in choices))
        self.assertTrue(any('004' in value for value in choices))
        self.client('002')
        self.assertEqual(self.at.selectbox(key='_ficha_002_sku').value, 'SKU-EXEMPLO-B')

    def test_drafts_are_separate_by_id_and_survive_widget_cleanup(self):
        self.client('001')
        self.fill()
        first = self.draft()
        self.client('002')
        self.assertEqual(self.at.text_area(key='agenda_contact_002_note').value, '')
        self.fill('002', 'Rascunho independente do segundo código')
        second = self.draft('002')
        self.route('Outra página')
        self.assertNotIn('agenda_contact_001_note', self.at.session_state)
        self.assertNotIn('agenda_contact_002_note', self.at.session_state)
        self.assertEqual(self.draft(), first)
        self.assertEqual(self.draft('002'), second)
        self.route('Clientes')
        self.client('001')
        self.assertEqual(self.draft(), first)
        self.assertEqual(self.at.text_area(key='agenda_contact_001_note').value, first['note'])
        self.assertEqual(self.at.date_input(key='agenda_contact_001_date').value, first['date'])
        self.assertEqual(self.at.checkbox(key='agenda_contact_001_closed').value, first['closed'])
        self.route('Hoje')
        self.client('002')
        self.assertEqual(self.draft('002'), second)

    def test_period_product_and_internal_view_preserve_the_contact_draft(self):
        self.client('001')
        self.fill()
        draft = self.draft()
        self.at.radio(key='_ficha_001_view').set_value('Compras').run()
        self.at.selectbox(key='_ficha_001_period').select('24m').run()
        self.at.radio(key='_ficha_001_view').set_value('Contatos').run()
        self.clean()
        self.assertTrue(any('Histórico de contatos' in item.label for item in self.at.expander))
        self.route('Outra página')
        self.route('Clientes')
        self.client('001')
        self.assertEqual(self.at.radio(key='_ficha_001_view').value, 'Contatos')
        self.at.radio(key='_ficha_001_view').set_value('Compras').run()
        self.assertEqual(self.at.selectbox(key='_ficha_001_period').value, '24m')
        self.assertEqual(self.draft(), draft)
        self.assertEqual(self.state(), EMPTY)

    def test_selected_client_follows_navigation_between_today_and_clients(self):
        self.client('002')
        self.at.text_area(key='agenda_contact_002_note').input('Manter esta ficha ao navegar').run()
        original = self.draft('002')
        self.route('Clientes')
        self.assertEqual(self.at.selectbox(key='client_select').value, '002')
        self.assertEqual(self.at.text_area(key='agenda_contact_002_note').value, original['note'])
        self.client('001')
        self.route('Hoje')
        self.assertEqual(self.at.selectbox(key='agenda_client').value, '001')
        self.assertEqual(self.draft('002'), original)

    def test_suggestion_changes_only_next_action_and_does_not_save(self):
        self.client('001')
        self.fill()
        before = self.draft()
        self.at.button(key='ficha_001_suggest').click().run()
        self.clean()
        after = self.draft()
        self.assertNotEqual(after['action'], before['action'])
        self.assertTrue(after['action'])
        self.assertLessEqual(len(after['action']), 300)
        self.assertEqual({k: v for k, v in after.items() if k != 'action'},
                         {k: v for k, v in before.items() if k != 'action'})
        self.assertEqual(self.state(), EMPTY)

    def test_history_unavailable_keeps_purchases_and_preserves_draft_without_save(self):
        self.client('001')
        self.fill()
        before = self.draft()
        self.control(history_error=True)
        self.route('Clientes')
        self.client('001')
        self.assertFalse(any(button.key == 'agenda_contact_001_save' for button in self.at.button))
        self.assertTrue(any('indisponível' in message.value for message in self.at.warning))
        self.at.radio(key='_ficha_001_view').set_value('Compras').run()
        self.clean()
        self.assertEqual(self.at.selectbox(key='_ficha_001_sku').value, 'SKU-EXEMPLO-A')
        self.assertEqual(self.draft(), before)
        self.assertEqual(self.state(), EMPTY)
        self.control(history_error=False)
        self.at.run()
        self.clean()
        self.assertEqual(self.at.text_area(key='agenda_contact_001_note').value, before['note'])
        self.assertEqual(self.draft(), before)

    def test_today_history_failure_keeps_purchases_without_false_empty_history(self):
        self.control(history_error=True)
        self.at.run()
        self.clean()
        self.assertTrue(any('indisponível' in item.value for item in self.at.warning))
        self.assertFalse(any(button.label == 'Salvar contato' for button in self.at.button))
        self.assertFalse(any('Nenhum contato registrado' in item.value for item in self.at.caption))
        self.client('001')
        self.at.radio(key='_ficha_001_view').set_value('Compras').run()
        self.clean()
        self.assertEqual(self.at.selectbox(key='_ficha_001_sku').value, 'SKU-EXEMPLO-A')
        self.assertEqual(self.state(), EMPTY)

    def test_manual_and_source_inactive_clients_are_read_only(self):
        self.route('Clientes')
        for cid in ('004', '006'):
            with self.subTest(cid=cid):
                self.client(cid)
                self.assertFalse(any(button.label == 'Salvar contato' for button in self.at.button))
                self.assertTrue(any('fora da carteira ativa' in item.value for item in self.at.info))
                self.at.radio(key=f'_ficha_{cid}_view').set_value('Compras').run()
                self.clean()
                self.assertTrue(any('Produtos no mesmo período' in item.value for item in self.at.subheader))
        self.assertEqual(self.state(), EMPTY)

    def test_inactivation_after_drafting_blocks_write_and_restores_draft_on_reactivation(self):
        self.client('001')
        self.fill()
        before = self.draft()
        self.control(inactive=['001', '004'])
        self.route('Clientes')
        self.client('001')
        self.assertFalse(any(button.label == 'Salvar contato' for button in self.at.button))
        self.assertEqual(self.draft(), before)
        self.control(inactive=['004'])
        self.at.run()
        self.clean()
        self.assertEqual(self.draft(), before)
        self.assertFalse(self.at.button(key='agenda_contact_001_save').disabled)

    def test_version_conflict_survives_navigation_and_requires_explicit_review(self):
        self.client('001')
        self.fill()
        original = self.draft()
        self.route('Outra página')
        self.external_contact()
        self.route('Clientes')
        self.client('001')
        self.assertEqual(self.draft(), original)
        self.assertTrue(self.at.button(key='agenda_contact_001_save').disabled)
        self.at.radio(key='_ficha_001_view').set_value('Contatos').run()
        self.assertTrue(any('Histórico sintético' in item.value for item in self.at.text))
        self.at.button(key='agenda_contact_001_refresh').click().run()
        self.clean()
        reviewed = self.draft()
        self.assertEqual(reviewed['version'], 1)
        self.assertNotEqual(reviewed['event'], original['event'])
        for field in ('channel', 'outcome', 'note', 'action', 'date', 'closed'):
            self.assertEqual(reviewed[field], original[field])
        self.at.button(key='agenda_contact_001_save').click().run()
        self.clean()
        self.assertEqual(self.state()['clientes']['001']['version'], 2)
        self.assertEqual(len(self.state()['clientes']['001']['historico']), 2)

    def test_own_event_after_lost_response_cannot_duplicate_or_clear_similar_id(self):
        self.client('0010')
        self.fill('0010', 'Preservar outro código semelhante')
        other = self.draft('0010')
        self.client('001')
        self.fill()
        before = self.draft()
        self.route('Outra página')
        self.external_contact(eid=before['event'])
        self.route('Clientes')
        self.client('001')
        self.assertTrue(self.at.button(key='agenda_contact_001_save').disabled)
        self.assertTrue(any('já está confirmado' in item.value for item in self.at.success))
        self.assertFalse(any(button.key == 'agenda_contact_001_refresh' for button in self.at.button))
        self.at.button(key='agenda_contact_001_restart').click().run()
        self.clean()
        self.assertEqual(self.at.text_area(key='agenda_contact_001_note').value, '')
        self.assertNotEqual(self.draft()['event'], before['event'])
        self.assertEqual(self.draft()['version'], 1)
        self.assertEqual(self.draft('0010'), other)
        self.assertEqual(len(self.state()['clientes']['001']['historico']), 1)

    def test_failed_local_save_keeps_payload_and_event_then_retry_saves_once(self):
        self.client('001')
        self.fill()
        before = self.draft()
        self.control(write_error=True)
        self.at.button(key='agenda_contact_001_save').click().run()
        self.clean()
        self.assertTrue(self.at.error)
        self.assertFalse(any('salvo' in item.value.casefold() for item in self.at.success))
        self.assertEqual(self.draft(), before)
        self.assertEqual(self.state(), EMPTY)
        self.control(write_error=False)
        self.at.button(key='agenda_contact_001_save').click().run()
        self.clean()
        record = self.state()['clientes']['001']
        self.assertEqual(record['version'], 1)
        self.assertEqual(record['historico'][0]['id'], before['event'])
        self.assertEqual(self.at.text_area(key='agenda_contact_001_note').value, '')

    def test_changed_wallet_or_warranty_role_is_revalidated_before_save(self):
        self.client('001')
        self.fill()
        before = self.draft()
        self.control(saved_vendor='Carteira B')
        self.at.button(key='agenda_contact_001_save').click().run()
        self.clean()
        self.assertTrue(any('carteira ativa' in item.value for item in self.at.error))
        self.assertEqual(self.state(), EMPTY)
        self.assertEqual(self.draft(), before)
        # Simula a tela antiga ainda aberta quando o perfil muda na fonte.
        self.at.session_state['vendor_filter'] = 'Carteira A'
        self.control(saved_vendor='Carteira A', saved_role='garantia')
        self.at.run()
        self.at.button(key='agenda_contact_001_save').click().run()
        self.clean()
        self.assertTrue(any('perfil' in item.value for item in self.at.error))
        self.assertEqual(self.state(), EMPTY)


if __name__ == '__main__':
    unittest.main(verbosity=2)
