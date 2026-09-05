"""Regressões de autorização e login real na UI Streamlit, com dados sintéticos.

Executar: python teste_etapa1_acessos.py
Não usa contas, planilhas, logs ou serviços de produção.
"""
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml
from streamlit.testing.v1 import AppTest
import app


CLIENTS = [
    dict(id='001', name='Cliente Alfa', vendor='Carteira A', status='Ativo', risk='Saudável'),
    dict(id='002', name='Cliente Beta', vendor='Carteira B', status='Ativo', risk='Atenção'),
]


class AccessRules(unittest.TestCase):
    def test_seller_scope_is_exact_and_does_not_mutate_source(self):
        source = pd.DataFrame(CLIENTS)
        result = app._clients_for_access(source, 'vendedor', ' Carteira A ')
        self.assertEqual(result['id'].tolist(), ['001'])
        result.loc[result.index[0], 'name'] = 'Mudou'
        self.assertEqual(source.loc[0, 'name'], 'Cliente Alfa')

    def test_invalid_access_fails_closed(self):
        for role, wallet in [('vendedor', None), ('vendedor', ''), ('vendedor', ' '),
                             ('vendedor', 'Carteira'), ('desconhecido', 'Carteira A'),
                             (None, None)]:
            with self.subTest(role=role, wallet=wallet), self.assertRaises(ValueError):
                app._clients_for_access(pd.DataFrame(CLIENTS), role, wallet)

    def test_known_privileged_roles_keep_expected_client_lookup(self):
        for role in ('admin', 'diretor', 'garantia', 'garantia_master'):
            with self.subTest(role=role):
                self.assertEqual(len(app._clients_for_access(pd.DataFrame(CLIENTS), role, 'Carteira A')), 2)

    def test_registration_rejects_duplicate_missing_wallet_and_short_password(self):
        users = {'users': {'teste': {}}}
        for username, password, role, wallet in [
            (' TESTE ', 'SenhaFicticia123!', 'admin', None),
            ('novo', 'SenhaFicticia123!', 'vendedor', None),
            ('novo', 'SenhaFicticia123!', 'vendedor', 'Não existe'),
            ('novo', 'curta', 'vendedor', 'Carteira A'),
        ]:
            with self.subTest(username=username, role=role, wallet=wallet):
                self.assertIsNotNone(app._new_user_error(users, username, 'Pessoa', password,
                                                        role, wallet, ['Carteira A']))
        self.assertIsNone(app._new_user_error(users, 'novo', 'Pessoa', 'SenhaFicticia123!',
                                              'vendedor', 'Carteira A', ['Carteira A']))


class StreamlitAccess(unittest.TestCase):
    def tearDown(self):
        # Os scripts AppTest importam o mesmo módulo; não vazar stubs a outras suítes.
        import importlib
        importlib.reload(app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='propetz-acesso-')
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.users_path = folder / 'users.yaml'
        self.users_path.write_text(yaml.safe_dump({'users': {'teste': {
            'name': 'Pessoa de Teste', 'role': 'vendedor', 'vendor_filter': 'Carteira A',
            'password': app.hash_password('SenhaFicticia123!'),
        }}}), encoding='utf-8')
        self.script = f'''
import pandas as pd
import streamlit as st
import app
app.USERS_FILE = {str(self.users_path)!r}
app.LOGIN_ATTEMPTS_FILE = {str(folder / 'tentativas.json')!r}
app._gh_token = lambda: None
app._sync_state_from_github = lambda: None
app._push_state_file = lambda *a, **kw: None
app.log_access = lambda *a, **kw: None
app.log_page_view = lambda *a, **kw: None
app.load_inactive_clients = lambda: {{}}
app._load_access_log = lambda: []
clients = pd.DataFrame({CLIENTS!r})
def data():
    st.session_state['_test_loaded'] = True
    return clients, pd.DataFrame(), pd.DataFrame(), ['jan/26'], {{'2026': [0]}}, pd.DataFrame()
app.load_data = data
def client_page(df, *args):
    st.dataframe(df[['id', 'name']], hide_index=True)
app.page_actions = client_page
app.page_agenda = client_page
app.page_manager = client_page
app.page_clients = client_page
app.page_overview = client_page
app.page_mix = client_page
app.page_churn = client_page
app.page_garantias = lambda products, df: client_page(df)
app.main()
'''

    def app_test(self, source):
        # Streamlit 1.41 from_string usa o encoding do Windows ao gravar.
        script_path = Path(self.temp.name) / f'ui_{len(list(Path(self.temp.name).glob("ui_*.py")))}.py'
        script_path.write_text(source, encoding='utf-8')
        return AppTest.from_file(str(script_path), default_timeout=30)

    def ui(self, role=None, wallet=None):
        at = self.app_test(self.script)
        if role is not None:
            users = yaml.safe_load(self.users_path.read_text(encoding='utf-8'))
            users['users']['teste'].update(role=role, vendor_filter=wallet)
            self.users_path.write_text(yaml.safe_dump(users), encoding='utf-8')
            for key, value in dict(authenticated=True, role=role, vendor_filter=wallet,
                                   username='teste', user_name='Pessoa de Teste').items():
                at.session_state[key] = value
        at.run()
        self.assertEqual(len(at.exception), 0)
        return at

    def test_wallet_change_and_removed_account_take_effect_on_next_interaction(self):
        at = self.ui('vendedor', 'Carteira A')
        self.assertEqual(at.dataframe[0].value['id'].tolist(), ['001'])
        users = yaml.safe_load(self.users_path.read_text(encoding='utf-8'))
        users['users']['teste']['vendor_filter'] = 'Carteira B'
        self.users_path.write_text(yaml.safe_dump(users), encoding='utf-8')
        at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.dataframe[0].value['id'].tolist(), ['002'])
        self.users_path.write_text('users: {}', encoding='utf-8')
        at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.dataframe), 0)
        self.assertTrue(any('cadastro' in error.value for error in at.error))

    def test_unreadable_registry_denies_instead_of_reusing_old_scope(self):
        at = self.ui('vendedor', 'Carteira A')
        self.users_path.write_text('users: [', encoding='utf-8')
        at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.dataframe), 0)
        self.assertTrue(any('validar' in error.value for error in at.error))

    def test_admin_demotion_removes_admin_page_on_next_interaction(self):
        at = self.ui('admin')
        at.radio[0].set_value('⚙️ Admin').run()
        users = yaml.safe_load(self.users_path.read_text(encoding='utf-8'))
        users['users']['teste'].update(role='vendedor', vendor_filter='Carteira B')
        self.users_path.write_text(yaml.safe_dump(users), encoding='utf-8')
        at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertNotIn('⚙️ Admin', at.radio[0].options)
        self.assertEqual(at.dataframe[0].value['id'].tolist(), ['002'])
        self.assertFalse(any(item.value == 'Gerenciar Usuários' for item in at.subheader))

    def test_admin_form_rejects_duplicate_without_overwriting_and_repairs_wallet(self):
        at = self.ui('admin')
        at.radio[0].set_value('⚙️ Admin').run()
        self.assertEqual(len(at.exception), 0)
        before = self.users_path.read_text(encoding='utf-8')
        next(item for item in at.text_input if item.label == 'Usuário (login)').input(' TESTE ')
        next(item for item in at.text_input if item.label == 'Nome completo').input('Duplicado')
        next(item for item in at.text_input if item.label == 'Senha').input('SenhaFicticia123!')
        next(button for button in at.button if button.label == 'Adicionar Usuário').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any('já existe' in error.value for error in at.error))
        self.assertEqual(self.users_path.read_text(encoding='utf-8'), before)

        users = yaml.safe_load(before)
        users['users']['vendedor_teste'] = dict(users['users']['teste'], role='vendedor', vendor_filter=None)
        self.users_path.write_text(yaml.safe_dump(users), encoding='utf-8')
        at.run()
        next(item for item in at.selectbox if item.label == 'Nova carteira').select('Carteira B')
        next(button for button in at.button if button.label == 'Salvar Carteira').click().run()
        self.assertEqual(len(at.exception), 0)
        saved = yaml.safe_load(self.users_path.read_text(encoding='utf-8'))
        self.assertEqual(saved['users']['vendedor_teste']['vendor_filter'], 'Carteira B')

    def test_without_session_never_loads_data(self):
        at = self.ui()
        self.assertEqual(len(at.text_input), 2)
        self.assertEqual(len(at.dataframe), 0)
        self.assertNotIn('_test_loaded', at.session_state)

    def test_real_login_rejects_wrong_password_and_limits_visible_wallet(self):
        at = self.ui()
        at.text_input(key='login_user').input('teste')
        at.text_input(key='login_pass').input('ErradaDeTeste!')
        at.button[0].click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any('incorretos' in e.value for e in at.error))
        self.assertEqual(len(at.dataframe), 0)
        at.text_input(key='login_user').input(' TESTE ')
        at.text_input(key='login_pass').input('SenhaFicticia123!')
        at.button[0].click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.dataframe[0].value['id'].tolist(), ['001'])
        self.assertFalse(any('Admin' in option or 'Garantias' in option for option in at.radio[0].options))

    def test_logout_clears_an_authenticated_session(self):
        at = self.ui('vendedor', 'Carteira A')
        next(button for button in at.button if button.label == '🚪 Sair').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.dataframe), 0)
        self.assertEqual(len(at.text_input), 2)

    def test_misconfigured_sessions_are_blocked_and_can_logout(self):
        for role, wallet in [('vendedor', None), ('vendedor', 'Ausente'), ('estranho', None)]:
            with self.subTest(role=role, wallet=wallet):
                at = self.ui(role, wallet)
                self.assertEqual(len(at.dataframe), 0)
                self.assertEqual(len(at.radio), 0)
                self.assertEqual(len(at.error), 1)
                if wallet != 'Ausente':
                    self.assertNotIn('_test_loaded', at.session_state)
                at.button(key='access_denied_logout').click().run()
                self.assertEqual(len(at.text_input), 2)

    def test_admin_and_director_see_all_but_only_admin_has_admin_menu(self):
        for role in ('admin', 'diretor'):
            with self.subTest(role=role):
                at = self.ui(role, 'Carteira A')
                self.assertEqual(at.dataframe[0].value['id'].tolist(), ['001', '002'])
                self.assertEqual('⚙️ Admin' in at.radio[0].options, role == 'admin')

    def test_warranty_navigation_stays_restricted(self):
        for role in ('garantia', 'garantia_master'):
            with self.subTest(role=role):
                at = self.ui(role)
                self.assertEqual(at.radio[0].options, ['🔧 Garantias'])

    def test_admin_function_rejects_direct_call_without_authorization(self):
        for role, authenticated in [('vendedor', True), ('diretor', True), ('admin', False)]:
            with self.subTest(role=role, authenticated=authenticated):
                at = self.app_test(f'''
import app
import streamlit as st
st.session_state['role'] = {role!r}
st.session_state['authenticated'] = {authenticated!r}
def forbidden():
    raise AssertionError('Não pode ler usuários sem autorização')
app.load_users = forbidden
app.page_admin(['Carteira A'])
''').run()
                self.assertEqual(len(at.exception), 0)
                self.assertEqual(len(at.error), 1)
                # Import compartilhado: restaura a leitura real para outros testes.
                import importlib
                importlib.reload(app)


if __name__ == '__main__':
    unittest.main(verbosity=2)
