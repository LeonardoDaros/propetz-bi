"""Contraprovas comerciais independentes: dados fictícios e funções reais por AST.

Não importa app.py, não executa bootstrap, não lê planilhas/estado/credenciais
e não acessa rede. As asserções representam o comportamento seguro esperado.
"""
import ast
from datetime import date, datetime
import html
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

import pandas as pd
import agenda_comercial as agenda
from teste_etapa1_comercial import FakeUI, Figure, MONTHS, client


APP = Path(__file__).with_name('app.py')
FUNCTIONS = {
    'annual_value_estimate', '_year_of_label', '_filter_clients_by_term',
    '_commercial_active_mask', '_commercial_reactivation_candidates',
    '_commercial_period_recurrence', '_commercial_estimate_caption',
    '_sku_stats', '_preco_medio_map', 'page_mix', 'page_churn',
    'page_overview', 'page_clients', 'page_agenda', '_remember_ficha_client',
    '_mv_num', '_mv_int', '_mv_brl', '_mes_vivo_bloco_vendedor',
    '_mes_vivo_tabela_clientes', 'page_mes_vivo',
    '_clients_for_access', '_vendor_options', '_access_configuration_error',
    '_agenda_authorized_clients', 'save_agenda_contact',
}
TREE = ast.parse(APP.read_text(encoding='utf-8-sig'), filename=str(APP))
CODE = compile(ast.Module(body=[n for n in TREE.body
    if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS], type_ignores=[]), str(APP), 'exec')


class AuditUI(FakeUI):
    def container(self, *args, **kwargs):
        return self

    def radio(self, label, options, key=None, **kwargs):
        return self.selectbox(label, options, key=key, **kwargs)


class CommercialAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.ui = AuditUI()
        self.ui.session_state = {'authenticated': True, 'role': 'admin'}
        self.inactive = set()
        self.dossiers = []
        self.inactivations = []
        self.exports = {}
        self.mv = {'total': {}, 'mes_nome': 'Setembro/2026', 'mes': '2026-09',
                   'gerado_em': '2026-09-05 10:00', 'dia': 5, 'dias_no_mes': 30}
        self.ns = {
            'pd': pd, 'st': self.ui, 'math': math, 'datetime': datetime, 'date': date,
            'agenda': agenda, 'esc': lambda x: html.escape(str(x)),
            'px': SimpleNamespace(bar=lambda *a, **k: Figure(), pie=lambda *a, **k: Figure()),
            'go': SimpleNamespace(Figure=Figure, Bar=lambda **k: None, Scatter=lambda **k: None),
            'fmt_brl': lambda value: f'R$ {value:.2f}',
            'fmt_brl_full': lambda value: f'R$ {value:.2f}',
            'risk_badge': str, 'status_badge': str,
            'insight_html': lambda kind, label, text, action: f'{label}: {text} {action}',
            'show_money_table': lambda df, cols, **kw: self.ui.dataframe(df, **kw),
            'has_full_data_access': lambda: True,
            'can_approve_inactivations': lambda: True,
            'load_inactive_clients': lambda: self.inactive.copy(),
            'load_silver_distribuicao': lambda: {},
            'load_silver_mes_vivo': lambda: self.mv,
            'load_abc_valor': lambda: None,
            '_inativacao_form': lambda clients, *a, **k: self.inactivations.extend(clients),
            '_csv_download': lambda df, label, filename, key: self.exports.update({key: df.copy()}),
            '_session_expired': lambda: False,
            '_clients_for_access': lambda df, *a: df.copy(),
            '_vendor_options': lambda df: sorted(df['vendor'].unique().tolist()),
            'load_agenda': lambda: {'schema_version': 1, 'clientes': {}},
            '_agenda_now': lambda: datetime(2026, 9, 5, 10),
            '_render_client_dossier': lambda row, *a, **k: self.dossiers.append(row.to_dict()),
            'ui': SimpleNamespace(page_hero=lambda *a, **k: None, stats_grid=lambda *a, **k: None),
        }
        exec(CODE, self.ns)
        self.access = self.ns['_clients_for_access']

    def mix(self, frame):
        empty = pd.DataFrame()
        products = pd.DataFrame([{'code': 'SKU-FICTICIO', 'name': 'Produto fictício', 'abc': 'C', 'total_qty': 1}])
        self.ns['page_mix'](frame, products, empty, empty, MONTHS, list(range(12)), MONTHS)

    def overview(self, frame):
        self.ns['page_overview'](frame, MONTHS, {}, set(range(12)), list(range(12)), MONTHS)

    def test_mix_does_not_resolve_active_homonym_to_inactive_first_row(self):
        frame = pd.DataFrame([
            client('INATIVO', 'Inativo', 'Recuperação', 99000, name='Nome Fictício Igual'),
            client('ATIVO', 'Ativo', 'Saudável', 150, name='Nome Fictício Igual'),
        ])
        self.mix(frame)
        revenue = next(v[0] for key, v in self.ui.metrics.items() if key.startswith('Receita ('))
        self.assertEqual(revenue, 'R$ 150.00', 'A seleção ofereceu somente o ativo mas resolveu o inativo por nome.')

    def test_churn_inactivation_distinguishes_same_name_by_code(self):
        frame = pd.DataFrame([
            client('001', 'Ativo', 'Recuperação', 900, name='Mesmo Nome Fictício'),
            client('002', 'Ativo', 'Recuperação', 100, name='Mesmo Nome Fictício'),
        ])
        self.ns['page_churn'](frame, MONTHS, list(range(12)), MONTHS)
        self.assertEqual(set(self.ui.options['inactivate_recup']), {'001', '002'},
                         'Nomes iguais não permitem escolher com precisão qual cadastro será inativado.')
        self.ui.values['inactivate_recup'] = ['002']
        self.ns['page_churn'](frame, MONTHS, list(range(12)), MONTHS)
        self.assertEqual([row['cid'] for row in self.inactivations], ['002'])

    def test_overview_risk_count_and_insight_use_only_active_portfolio(self):
        frame = pd.DataFrame([
            client('001', 'Ativo', 'Recuperação', 100),
            client('002', 'Inativo', 'Recuperação', 200),
            client('003', 'Inadimplente', 'Recuperação', 300),
            client('004', 'Permuta', 'Recuperação', 400),
            client('005', 'Ativo', 'Recuperação', 500),
        ])
        self.inactive = {'005'}
        self.overview(frame)
        self.assertEqual(self.ui.metrics['Base Ativa'], ('1', 'Inativos: 2 | Risco: 1'))
        risk = next(text for text in self.ui.texts if text.startswith('RISCO DE CHURN:'))
        self.assertIn('1 clientes', risk)
        self.assertIn('R$ 1200.00', risk)

    def test_overview_valid_filter_combination_with_zero_matches_does_not_crash(self):
        frame = pd.DataFrame([client('001', 'Ativo', 'Saudável', 100),
                              client('002', 'Ativo', 'Saudável', 200)])
        frame.loc[0, ['vendor', 'state']] = ['Carteira A', 'SP']
        frame.loc[1, ['vendor', 'state']] = ['Carteira B', 'SC']
        self.ui.values.update({'ov_vendor': 'Carteira A', 'ov_state': 'SC'})
        self.overview(frame)
        self.assertTrue(any('nenhum' in text.casefold() for text in self.ui.texts),
                        'Filtros sem resultados devem mostrar uma orientação explícita.')

    def test_client_search_cannot_hide_a_duplicate_id_and_open_ambiguous_profile(self):
        frame = pd.DataFrame([
            client('001', 'Ativo', 'Recuperação', 100, name='Alfa Fictício'),
            client('001', 'Ativo', 'Recuperação', 200, name='Beta Fictício'),
        ])
        self.ui.values['client_search'] = 'Alfa'
        self.ns['page_clients'](frame, pd.DataFrame(), MONTHS, {}, list(range(12)), MONTHS)
        self.assertEqual(self.dossiers, [], 'A unicidade deve ser verificada antes da busca visual.')
        self.assertTrue(any('duplicad' in text.casefold() for text in self.ui.texts))

    def test_agenda_duplicate_code_reports_error_before_building_queue(self):
        frame = pd.DataFrame([
            client('001', 'Ativo', 'Recuperação', 100, name='Alfa Fictício'),
            client('001', 'Ativo', 'Recuperação', 200, name='Beta Fictício'),
        ])
        self.ns['page_agenda'](frame, MONTHS, pd.DataFrame())
        self.assertEqual(self.dossiers, [])
        self.assertTrue(any('duplicad' in text.casefold() for text in self.ui.texts))

    def test_duplicate_code_in_another_portfolio_is_not_hidden_by_authorization(self):
        frame = pd.DataFrame([client('001', 'Ativo', 'Saudável', 100),
                              client('001', 'Ativo', 'Saudável', 200),
                              client('003', 'Ativo', 'Saudável', 300)])
        frame['vendor'] = ['Carteira A', 'Carteira B', 'Carteira C']
        with self.assertRaisesRegex(ValueError, 'duplicad|ambígu'):
            self.access(frame, 'vendedor', 'Carteira A')
        self.assertEqual(self.access(frame, 'vendedor', 'Carteira C')['id'].tolist(), ['003'])

    def test_save_rejects_global_duplicate_code_before_any_io(self):
        frame = pd.DataFrame([client('001', 'Ativo', 'Recuperação', 100),
                              client('001', 'Ativo', 'Recuperação', 200)])
        frame['vendor'] = ['Carteira A', 'Carteira B']
        self.ui.session_state.update(role='vendedor', vendor_filter='Carteira A', username='sintetico')
        self.ns['load_data'] = lambda: (frame,)
        self.ns['_refresh_session_access'] = lambda: None
        def no_io(*args, **kwargs):
            self.fail('A guarda de identidade precisa agir antes de consultar persistência.')
        self.ns['_gh_token'] = no_io
        with self.assertRaisesRegex(ValueError, 'duplicad|ambígu'):
            self.ns['save_agenda_contact']('001', expected_version=0,
                event_id='00000000-0000-4000-8000-000000000001', channel='Ligação',
                outcome='Sem resposta', note='Contato inteiramente fictício.',
                next_action='Retornar ficticiamente.', return_date='2026-09-06', closed=False)

    def test_mes_vivo_non_finite_counts_have_safe_fallback(self):
        for poison in (float('inf'), float('-inf'), 'Infinity', '-Infinity'):
            with self.subTest(poison=poison):
                self.assertEqual(self.ns['_mv_int'](poison, 17), 17)

    def test_mes_vivo_malformed_optional_collections_do_not_crash(self):
        for field in ('vendedores', 'por_dia', 'top_clientes'):
            for poison in (1, True, 2.5):
                with self.subTest(field=field, poison=poison):
                    original = dict(self.mv)
                    self.mv[field] = poison
                    try:
                        self.ns['page_mes_vivo']()
                    finally:
                        self.mv = original


if __name__ == '__main__':
    unittest.main(verbosity=2)
