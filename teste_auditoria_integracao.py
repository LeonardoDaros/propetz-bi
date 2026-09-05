"""Navegação real por perfil, com fontes/arquivos fictícios e HTTP proibido."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from teste_ficha_cliente_interface import CLIENTS, MONTHS, PRODUCTS


def integrated_script(folder):
    return f'''
import importlib, json, sys
from pathlib import Path
import pandas as pd
import streamlit as st
app = importlib.reload(sys.modules['app']) if 'app' in sys.modules else importlib.import_module('app')
folder = Path({str(folder)!r})
control = json.loads((folder / 'control.json').read_text(encoding='utf-8'))
clients = pd.DataFrame({CLIENTS!r})
clients['credit_limit'] = 0
clients['total_geral'] = clients['monthly'].map(sum)
for field in ['yearly_totals','months_bought','avg_month']:
    clients[field] = [{{}} for _ in range(len(clients))]
products = pd.DataFrame([dict(code='SKU-EXEMPLO-A',name='Lâmina fictícia A',category='Lâminas',abc='A',total_qty=26,valor_12m=2600,qty_12m=26),
                         dict(code='SKU-EXEMPLO-B',name='Tesoura fictícia B',category='Tesouras',abc='B',total_qty=9,valor_12m=1800,qty_12m=9)])
sku = pd.DataFrame({PRODUCTS!r})
cp = sku.groupby(['cod_cliente','sku','produto'],as_index=False)['quantidade'].sum().rename(columns={{'cod_cliente':'client_id','sku':'product_code','produto':'product_name','quantidade':'total_qty'}})
cp['client_name'] = cp['client_id'].map(clients.set_index('id')['name'])
if control.get('no_catalog'):
    products = pd.DataFrame()
if control.get('empty_clients'):
    clients = clients.iloc[:0].copy()
if control.get('duplicate_clients'):
    clients = pd.concat([clients, clients.iloc[[0]]], ignore_index=True)
months = [] if control.get('no_months') else {MONTHS!r}
app._gh_token = lambda: None
app._sync_state_from_github = lambda: None
app.log_access = lambda *a, **kw: None
app.log_page_view = lambda *a, **kw: None
app.load_inactive_clients = lambda: {{'004'}}
app.load_inactive_requests = lambda: []
app.load_garantias = lambda: []
app._load_access_log = lambda: []
app.load_silver_distribuicao = lambda: {{}}
app.load_silver_mes_vivo = lambda: {{}}
app.load_abc_valor = lambda: None
app.load_users = lambda: {{'users':{{'pessoa_auditoria':{{'name':'Pessoa Fictícia','role':control['role'],'vendor_filter':'Carteira A','password':'synthetic-not-for-login'}}}}}}
app.load_data = lambda: (clients, products, cp, months, {{}}, sku)
app.AGENDA_FILE = str(folder / 'agenda.json')
st.session_state.setdefault('authenticated', True)
st.session_state.setdefault('username','pessoa_auditoria')
st.session_state.setdefault('user_name','Pessoa Fictícia')
st.session_state.setdefault('role',control['role'])
st.session_state.setdefault('vendor_filter','Carteira A')
app.main()
'''


class IntegratedRoutesAudit(unittest.TestCase):
    def tearDown(self):
        # As páginas usam um módulo compartilhado: não deixar fontes fictícias
        # instaladas para a próxima suíte no mesmo processo.
        import importlib
        import sys
        if 'app' in sys.modules:
            importlib.reload(sys.modules['app'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='propetz-integracao-audit-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder / 'agenda.json').write_text('{"schema_version":1,"clientes":{}}', encoding='utf-8')
        (self.folder / 'app_test.py').write_text(integrated_script(self.folder), encoding='utf-8')
        self.http = patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP proibido na auditoria local'))
        self.http_mock = self.http.start()
        self.addCleanup(self.http.stop)

    def start(self, role='admin', **options):
        (self.folder / 'control.json').write_text(json.dumps({'role':role, **options}), encoding='utf-8')
        return AppTest.from_file(str(self.folder / 'app_test.py'), default_timeout=30).run()

    def navigation(self, at):
        return next(r for r in at.radio if r.label == 'Navegação')

    def clean(self, at, context):
        self.assertFalse(at.exception, f'{context}: {[e.message for e in at.exception]}')
        self.http_mock.assert_not_called()

    def run_ui(self, at):
        # AppTest 1.41 serializa o segmented_control single como multiselect.
        for group in at.get('button_group'):
            if isinstance(group.value, str):
                group.set_value([group.value])
        return at.run()

    def test_every_authorized_route_renders_for_each_role(self):
        for role in ('admin','diretor','vendedor','garantia','garantia_master'):
            at = self.start(role)
            self.clean(at, role)
            pages = list(self.navigation(at).options)
            if role.startswith('garantia'):
                self.assertEqual(pages, ['🔧 Garantias'])
            if role == 'vendedor':
                self.assertFalse(any('Gestor' in p or 'Admin' in p or 'Garantias' in p for p in pages))
            for page in pages:
                with self.subTest(role=role, page=page):
                    self.navigation(at).set_value(page)
                    self.run_ui(at)
                    self.clean(at, (role, page))

    def test_optional_catalog_absence_keeps_products_page_available(self):
        at = self.start(no_catalog=True)
        self.navigation(at).set_value('📦 Produtos')
        self.run_ui(at)
        self.clean(at, 'catálogo ausente')
        self.assertTrue(at.info or at.warning)

    def test_catalog_search_treats_user_input_as_literal_text(self):
        at = self.start()
        self.clean(at, 'início da busca')
        self.navigation(at).set_value('📦 Produtos')
        self.run_ui(at)
        at.text_input(key='prod_search').input('[')
        self.run_ui(at)
        self.clean(at, 'busca literal')

    def test_missing_months_has_recovery_message_instead_of_exception(self):
        at = self.start(no_months=True)
        self.clean(at, 'meses ausentes')
        self.assertTrue(at.warning or at.error)

    def test_empty_clients_has_recovery_message_instead_of_exception(self):
        at = self.start(empty_clients=True)
        self.clean(at, 'clientes ausentes')
        self.assertTrue(at.warning or at.error)

    def test_mix_without_catalog_does_not_invent_zero_opportunities(self):
        at = self.start(no_catalog=True)
        self.navigation(at).set_value('🧩 Mix de Produtos')
        self.run_ui(at)
        self.clean(at, 'mix sem catálogo')
        self.assertTrue(any('Catálogo' in item.value for item in at.info))

    def test_admin_can_recover_duplicate_ids_without_showing_ambiguous_data(self):
        at = self.start(duplicate_clients=True)
        self.clean(at, 'admin com IDs duplicados')
        self.assertTrue(any('duplicados' in item.value for item in at.error))
        self.assertEqual(len(at.get('file_uploader')), 1)
        self.assertFalse(at.dataframe)

    def test_seller_cannot_upload_to_bypass_duplicate_id_block(self):
        at = self.start('vendedor', duplicate_clients=True)
        self.clean(at, 'vendedor com IDs duplicados')
        self.assertTrue(any('duplicados' in item.value for item in at.error))
        self.assertFalse(at.get('file_uploader'))
        self.assertFalse(at.dataframe)


if __name__ == '__main__':
    unittest.main(verbosity=2)
