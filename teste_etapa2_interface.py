"""Agenda integrada no Streamlit: somente contas, clientes e arquivos fictícios."""
import json
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path

from streamlit.testing.v1 import AppTest
import agenda_comercial as agenda


CLIENTS = [
    dict(id='001', name='Pet Aurora', vendor='Carteira A', state='PR', status='Ativo',
         risk='Recuperação', months_since=7, monthly=[1200.] * 12, last_purchase='jan/26'),
    dict(id='002', name='Pet Horizonte', vendor='Carteira A', state='SC', status='Ativo',
         risk='Atenção', months_since=4, monthly=[500.] * 12, last_purchase='abr/26'),
    dict(id='003', name='Cliente de Outra Carteira', vendor='Carteira B', state='SP', status='Ativo',
         risk='Recuperação', months_since=8, monthly=[700.] * 12, last_purchase='dez/25'),
    dict(id='004', name='Cliente Inativado', vendor='Carteira A', state='PR', status='Ativo',
         risk='Recuperação', months_since=9, monthly=[600.] * 12, last_purchase='nov/25'),
    dict(id='005', name='Pet Lua', vendor='Carteira A', state='PR', status='Ativo',
         risk='Saudável', months_since=1, monthly=[800.] * 12, last_purchase='ago/26'),
]


def fixture_script(folder, preview=False):
    """Também serve à inspeção visual local, sem autenticar em produção."""
    return f'''
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
import streamlit as st
import importlib, sys
if 'ui_propetz' in sys.modules:
    importlib.reload(sys.modules['ui_propetz'])
if 'app' in sys.modules:
    app = importlib.reload(sys.modules['app'])
else:
    import app
app.AGENDA_FILE = {str(Path(folder) / 'agenda.json')!r}
app._gh_token = lambda: None
app._agenda_now = lambda: datetime.fromisoformat('2026-09-04T10:00:00-03:00')
app.load_inactive_clients = lambda: {{'004'}}
app.load_users = lambda: {{'users':{{'pessoa_teste':{{'name':'Pessoa de Teste', 'role':'vendedor','vendor_filter':'Carteira A'}}}}}}
clients = pd.DataFrame({CLIENTS!r})
exclude_path = Path({str(Path(folder) / 'exclude.json')!r})
if exclude_path.exists():
    clients = clients[~clients['id'].isin(json.loads(exclude_path.read_text(encoding='utf-8')))]
app.load_data = lambda: (clients, pd.DataFrame(), pd.DataFrame(), ['set/26'], {{}}, pd.DataFrame())
app._STATE_RAW_CACHE.clear()
st.session_state.setdefault('authenticated', True)
st.session_state.setdefault('username', 'pessoa_teste')
st.session_state.setdefault('user_name', 'Pessoa de Teste')
st.session_state.setdefault('role', 'vendedor')
st.session_state.setdefault('vendor_filter', 'Carteira A')
if {preview!r}:
    st.caption('PRÉVIA LOCAL · DADOS FICTÍCIOS')
    app._sync_state_from_github = lambda: None
    app.log_page_view = lambda *args: None
    app.log_access = lambda *args: None
    if st.query_params.get('preview') == 'login':
        st.session_state.clear()
        app.login_page()
    else:
        app.main()
else:
    app.page_agenda(clients, ['set/26'])
'''


class AgendaInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='propetz-agenda-ui-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.state_file = self.folder / 'agenda.json'
        self.state_file.write_text(json.dumps({'schema_version': 1, 'clientes': {}}), encoding='utf-8')
        script_path = self.folder / 'ui.py'
        script_path.write_text(fixture_script(self.folder), encoding='utf-8')
        self.at = AppTest.from_file(str(script_path), default_timeout=30).run()
        self.assertEqual(len(self.at.exception), 0)

    def state(self):
        return json.loads(self.state_file.read_text(encoding='utf-8'))

    def submit(self, close=False):
        self.at.selectbox(key='agenda_contact_001_outcome').select('Proposta enviada')
        self.at.text_area(key='agenda_contact_001_note').input('Solicitou proposta de lâminas.')
        self.at.text_input(key='agenda_contact_001_action').input('Retornar sobre a proposta')
        self.at.checkbox(key='agenda_contact_001_closed').set_value(close)
        next(b for b in self.at.button if b.label == 'Salvar contato').click().run()
        self.assertEqual(len(self.at.exception), 0)

    def test_initial_queue_is_scoped_and_contains_one_contact_form(self):
        options = self.at.selectbox(key='agenda_client').options
        self.assertEqual(len(options), 3)
        self.assertTrue(any('Aurora' in option for option in options))
        self.assertFalse(any('Outra' in option or 'Inativado' in option for option in options))
        self.assertEqual(sum(b.label == 'Salvar contato' for b in self.at.button), 1)

    def test_contact_persists_followup_and_history_and_leaves_today_queue(self):
        self.submit()
        record = self.state()['clientes']['001']
        self.assertEqual(record['version'], 1)
        self.assertEqual(record['retorno_em'], '2026-09-05')
        self.assertEqual(record['historico'][0]['user'], 'pessoa_teste')
        self.assertTrue(any('salvo apenas' in msg.value for msg in self.at.success))
        self.assertFalse(any('agenda_open_001' == button.key for button in self.at.button))
        self.assertTrue(any('01' in str(exp.label) or '1' in str(exp.label) for exp in self.at.expander))

    def test_validation_error_keeps_the_typed_note(self):
        self.at.text_area(key='agenda_contact_001_note').input('Texto ainda não salvo')
        next(b for b in self.at.button if b.label == 'Salvar contato').click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(self.state()['clientes'], {})
        self.assertEqual(self.at.text_area(key='agenda_contact_001_note').value, 'Texto ainda não salvo')
        self.assertTrue(self.at.error)

    def test_closing_does_not_inactivate_the_client(self):
        self.submit(close=True)
        self.assertTrue(self.state()['clientes']['001']['encerrado'])
        self.assertIsNone(self.state()['clientes']['001']['retorno_em'])
        self.assertEqual(len(self.at.selectbox(key='agenda_client').options), 3)
        self.assertTrue(any('encerrado' in message.value for message in self.at.info))

    def test_external_contact_requires_review_before_saving(self):
        new_state = agenda.register_contact(self.state(), client_id='001', actor='outro_usuario',
            channel='Ligação', outcome='Retorno combinado', note='Registro de outra sessão',
            next_action='Ligar', return_date='2026-09-06', closed=False, expected_version=0,
            event_id=str(uuid.uuid4()), now=datetime.fromisoformat('2026-09-04T09:00:00-03:00'))
        self.state_file.write_text(json.dumps(new_state), encoding='utf-8')
        self.at.run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertTrue(next(b for b in self.at.button if b.label == 'Salvar contato').disabled)
        self.assertTrue(any('mais recente' in message.value for message in self.at.warning))

    def test_lost_response_detects_own_event_and_prevents_duplicate(self):
        pending_id = self.at.session_state['agenda_contact_001_event']
        saved = agenda.register_contact(self.state(), client_id='001', actor='pessoa_teste',
            channel='WhatsApp', outcome='Contato realizado', note='Contato já confirmado',
            next_action='Retornar', return_date='2026-09-05', closed=False, expected_version=0,
            event_id=pending_id, now=datetime.fromisoformat('2026-09-04T10:00:00-03:00'))
        self.state_file.write_text(json.dumps(saved), encoding='utf-8')
        self.at.run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertTrue(any('já está confirmado' in message.value for message in self.at.success))
        self.assertTrue(next(b for b in self.at.button if b.label == 'Salvar contato').disabled)
        self.assertFalse(any('Revisei:' in b.label for b in self.at.button))
        self.assertEqual(len(self.state()['clientes']['001']['historico']), 1)

    def test_programmed_filter_keeps_its_item_without_duplicate_risk(self):
        self.submit()
        # Nova sessão de UI, preservando somente o arquivo salvo.
        self.at = AppTest.from_file(str(self.folder / 'ui.py'), default_timeout=30).run()
        self.at.radio(key='agenda_queue').set_value('Programados').run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual([b.key for b in self.at.button if str(b.key).startswith('agenda_open_')], ['agenda_open_001'])

    def test_selection_survives_removing_another_client(self):
        self.at.selectbox(key='agenda_client').select('005').run()
        (self.folder / 'exclude.json').write_text('["002"]', encoding='utf-8')
        self.at.run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(self.at.selectbox(key='agenda_client').value, '005')

    def test_saving_preserves_draft_of_client_with_similar_code(self):
        self.at.session_state['agenda_contact_0010_event'] = 'rascunho-outro-cliente'
        self.submit()
        self.assertEqual(self.at.session_state['agenda_contact_0010_event'], 'rascunho-outro-cliente')


if __name__ == '__main__':
    unittest.main(verbosity=2)
