# -*- coding: utf-8 -*-
"""Regressões comerciais com dados sintéticos, sem rede ou estado real.

Carrega pelo AST somente as funções sob teste. Não importa app.py, não abre
planilhas, não consulta credenciais e não executa inicialização do Streamlit.
"""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd


SOURCE = Path(__file__).with_name('app.py')
FUNCTIONS = {
    'annual_value_estimate', '_year_of_label', '_filter_clients_by_term',
    '_commercial_active_mask', '_commercial_reactivation_candidates',
    '_commercial_period_recurrence', '_commercial_estimate_caption',
    'page_manager', 'page_actions', 'page_clients', 'page_churn', 'page_mix',
}
tree = ast.parse(SOURCE.read_text(encoding='utf-8-sig'), filename=str(SOURCE))
isolated = ast.Module(
    body=[node for node in tree.body
          if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS],
    type_ignores=[],
)
CODE = compile(ast.fix_missing_locations(isolated), str(SOURCE), 'exec')


class Figure:
    def __getattr__(self, name):
        return lambda *args, **kwargs: self


class FakeUI:
    def __init__(self):
        self.metrics = {}
        self.tables = []
        self.texts = []
        self.options = {}
        self.values = {}
        self.pressed = set()
        self.session_state = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def columns(self, count, **kwargs):
        return [self] * (count if isinstance(count, int) else len(count))

    def tabs(self, labels):
        self.tab_labels = labels
        return [self] * len(labels)

    def expander(self, *args, **kwargs):
        return self

    def metric(self, label, value, delta=None, **kwargs):
        self.metrics[label] = (value, delta)

    def dataframe(self, df, **kwargs):
        self.tables.append(df.copy())
        return SimpleNamespace(selection=SimpleNamespace(rows=[]))

    def selectbox(self, label, options, key=None, **kwargs):
        options = list(options)
        self.options[key or label] = options
        return self.values.get(key, options[0] if options else None)

    def multiselect(self, label, options, key=None, **kwargs):
        self.options[key or label] = list(options)
        return self.values.get(key, [])

    def text_input(self, label, key=None, **kwargs):
        return self.values.get(key, '')

    def button(self, label, key=None, **kwargs):
        return key in self.pressed

    def __getattr__(self, name):
        def record(*args, **kwargs):
            if args and isinstance(args[0], str):
                self.texts.append(args[0])
        return record


MONTHS = ['jan/26', 'fev/26', 'mar/26', 'abr/26', 'mai/26', 'jun/26',
          'jul/26', 'ago/26', 'set/26', 'out/26', 'nov/26', 'dez/26']


def client(cid, status, risk, amount, name=None):
    return {
        'id': str(cid), 'name': name or f'Cliente sintético {cid}',
        'status': status, 'risk': risk, 'state': 'SC', 'vendor': 'Carteira teste',
        'monthly': [0] * 11 + [amount], 'months_since': 6,
        'last_purchase': 'jan/26', 'credit_limit': 0,
        'yearly_totals': {}, 'avg_month': {},
    }


def fixture():
    return pd.DataFrame([
        client(1, 'Ativo', 'Atenção', 100),
        client(2, 'Ativo', 'Recuperação', 200),
        client(3, 'Ativo', 'Saudável', 300),
        client(4, 'Inativo', 'Recuperação', 10000),
        client(5, 'Ativo', 'Recuperação', 20000, name='Nome repetido'),
        client(6, 'Inadimplente', 'Atenção', 30000),
        client(7, 'Inativo', 'Recuperação', 40000, name='Nome repetido'),
        client(8, 'Permuta', 'Saudável', 50000),
    ])


class CommercialRegression(unittest.TestCase):
    def setUp(self):
        self.ui = FakeUI()
        self.inactive = {'5', '7'}
        self.admin = True
        self.reactivations = []
        self.exports = {}
        self.ns = {
            'pd': pd, 'st': self.ui,
            'px': SimpleNamespace(bar=lambda *a, **k: Figure()),
            'go': SimpleNamespace(Figure=Figure, Bar=lambda **k: None,
                                  Scatter=lambda **k: None),
            'fmt_brl': lambda value: f'R$ {value:.2f}',
            'fmt_brl_full': lambda value: f'R$ {value:.2f}',
            'risk_badge': str, 'status_badge': str,
            'insight_html': lambda kind, label, text, action: f'{label}: {text}',
            'show_money_table': lambda df, money_cols, **kw: self.ui.dataframe(df, **kw),
            'has_full_data_access': lambda: True,
            'can_approve_inactivations': lambda: self.admin,
            'load_inactive_clients': lambda: self.inactive.copy(),
            'pending_inactivation_requests': lambda: [],
            'load_inactive_requests': lambda: [],
            'load_silver_distribuicao': lambda: {},
            'load_abc_valor': lambda: None,
            '_load_access_log': lambda: [],
            '_inativacao_form': lambda *a, **k: None,
            '_csv_download': lambda df, label, filename, key: self.exports.update({key: df.copy()}),
            'reactivate_clients': lambda ids: self.reactivations.append(ids) or True,
        }
        exec(CODE, self.ns)
        self.df = fixture()

    def render(self, page, df=None):
        df = self.df if df is None else df
        empty = pd.DataFrame()
        if page == 'actions':
            self.ns['page_actions'](df, empty, empty, empty, MONTHS)
        elif page == 'manager':
            self.ns['page_manager'](df, MONTHS, empty, empty)
        elif page == 'churn':
            self.ns['page_churn'](df, MONTHS, list(range(12)), MONTHS)

    def table_with(self, column):
        return next(table for table in self.ui.tables if column in table.columns)

    def test_population_and_official_risks_are_preserved(self):
        before = self.df.copy(deep=True)
        mask = self.ns['_commercial_active_mask'](self.df, {' 5 ', 7})
        self.assertEqual(self.df.loc[mask, 'id'].tolist(), ['1', '2', '3'])
        self.assertEqual(self.df.loc[mask, 'risk'].tolist(), ['Atenção', 'Recuperação', 'Saudável'])
        pd.testing.assert_frame_equal(self.df, before)

    def test_actions_exclude_sheet_inactive_and_manual_inactive(self):
        self.render('actions')
        self.assertEqual(self.ui.metrics['🔴 Contatos Urgentes'][0], '1')
        self.assertEqual(self.ui.metrics['🟡 Contatos de Atenção'][0], '1')
        self.assertEqual(self.ui.metrics['💰 Receita em Jogo'][0], 'R$ 3600.00')
        self.assertEqual(set(self.exports['dl_calls']['Cliente']),
                         {'Cliente sintético 1', 'Cliente sintético 2'})

    def test_manager_preserves_realized_revenue_but_limits_active_portfolio(self):
        self.render('manager')
        self.assertEqual(self.ui.metrics['Receita dez/26'][0], 'R$ 150600.00')
        table = self.table_with('Cobertura')
        self.assertEqual(table.iloc[0]['Receita no Mês'], 600)
        self.assertEqual(table.iloc[0]['Compraram no Mês'], '3/3')
        self.assertEqual(table.iloc[0]['R$ em Risco (ano)'], 3600)

    def test_churn_counts_ranking_and_exclusions_have_same_population(self):
        before = self.df.copy(deep=True)
        self.render('churn')
        self.assertEqual(self.ui.metrics['🔴 Recuperação (6+ meses)'][0], '1')
        self.assertEqual(self.ui.metrics['🟡 Atenção (3-5 meses)'][0], '1')
        self.assertEqual(self.ui.metrics['🟢 Saudáveis'][0], '1')
        self.assertEqual(self.ui.metrics['💰 Receita Total em Risco'][0], 'R$ 3600.00')
        self.assertEqual(self.table_with('Total Clientes').iloc[0]['Total Clientes'], 3)
        excluded = self.table_with('Inativação no App').set_index('Código')
        self.assertEqual(set(excluded.index), {'4', '5', '6', '7', '8'})
        self.assertEqual(excluded.loc['4', 'Status na Planilha'], 'Inativo')
        self.assertEqual(excluded.loc['4', 'Inativação no App'], 'Não')
        self.assertEqual(excluded.loc['7', 'Inativação no App'], 'Sim')
        pd.testing.assert_frame_equal(self.df, before)

    def test_empty_active_portfolio_has_no_ranking_crash(self):
        excluded = self.df.iloc[3:].copy()
        self.render('churn', excluded)
        self.assertEqual(self.ui.metrics['💰 Receita Total em Risco'][0], 'R$ 0.00')
        self.assertTrue(any('Nenhum cliente ativo para compor' in text for text in self.ui.texts))

    def test_reactivation_does_not_override_spreadsheet_and_uses_code(self):
        for page, key, button in (
            ('churn', 'reactivate_clients', 'btn_reactivate'),
            ('manager', 'mgr_react', 'btn_mgr_react'),
        ):
            with self.subTest(page=page):
                self.setUp()
                # A stale/invalid selection must not reach the write operation.
                self.ui.values[key] = ['5', '7']
                self.ui.pressed.add(button)
                self.render(page)
                self.assertEqual(self.ui.options[key], ['5'])
                self.assertEqual(self.reactivations, [['5']])

    def test_director_cannot_reactivate_clients(self):
        self.admin = False  # full data access, without admin approval rights
        self.ui.values.update({'reactivate_clients': ['5'], 'mgr_react': ['5']})
        self.ui.pressed.update({'btn_reactivate', 'btn_mgr_react'})
        self.render('churn')
        self.render('manager')
        self.assertNotIn('reactivate_clients', self.ui.options)
        self.assertNotIn('mgr_react', self.ui.options)
        self.assertEqual(self.reactivations, [])

    def test_mix_does_not_offer_manually_inactive_clients(self):
        self.ui.values['mix_client'] = None  # inspect selection, without building offers
        empty = pd.DataFrame()
        self.ns['page_mix'](self.df, empty, empty, empty, MONTHS, list(range(12)), MONTHS)
        self.assertEqual(set(self.ui.options['mix_client']),
                         {'1', '2', '3'})

    def render_recurrence(self, monthly, selected):
        # A ficha agora tem uma janela própria. Esta regressão cobre o helper
        # de recorrência que continua atendendo às demais páginas comerciais.
        return self.ns['_commercial_period_recurrence'](monthly, selected)

    def test_single_selected_month_does_not_use_all_historical_months(self):
        self.assertEqual(self.render_recurrence([20000] * 60, [59]), (1, 1))

    def test_recurrence_numerator_and_denominator_use_same_selected_months(self):
        monthly = [20000] + [0] * 59
        self.assertEqual(self.render_recurrence(monthly, [0, 10, 20, 30]), (1, 4))
        self.assertEqual(self.render_recurrence(monthly, [10, 20, 30]), (0, 3))
        self.assertEqual(self.render_recurrence(monthly, [0, 0, 10, -1, 60]), (1, 2))

    def test_empty_selection_has_no_historical_fallback(self):
        self.assertEqual(self.render_recurrence([20000] * 12, []), (0, 0))

    def test_annual_estimate_keeps_active_month_assumption_and_historical_fallback(self):
        estimate = self.ns['annual_value_estimate']
        self.assertEqual(estimate([20000, 20000] + [0] * 10), 240000)
        self.assertEqual(estimate([1000] + [0] * 12), 12000)
        self.assertEqual(estimate([0] * 12), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
