# -*- coding: utf-8 -*-
"""Regressões sintéticas da ficha; não abre planilhas, estado ou rede."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import unittest
from unittest.mock import patch

import pandas as pd

from ficha_cliente_dados import build_profile, product_series


def months_from(year, month, count):
    return [f'{(year * 12 + month - 1 + i) // 12:04d}-'
            f'{(year * 12 + month - 1 + i) % 12 + 1:02d}' for i in range(count)]


def clients(values, *, cid='001', **extra):
    return pd.DataFrame([{'id': cid, 'name': 'Empresa fictícia', 'vendor': 'Carteira A',
                          'state': 'SP', 'status': 'Ativo', 'risk': 'Atenção',
                          'monthly': values, 'last_purchase': '03/09/2026',
                          'months_since': 0, **extra}])


def sku_rows(*rows):
    return pd.DataFrame(rows, columns=['cod_cliente', 'sku', 'produto', 'mes', 'quantidade'])


class ClientIdentityTests(unittest.TestCase):
    def test_equal_names_keep_distinct_codes_and_product_histories(self):
        frame = pd.concat([clients([10], cid='001'), clients([90], cid='1')], ignore_index=True)
        sku = sku_rows(('001', 'P1', 'Produto A', 'jan/26', 2), ('1', 'P2', 'Produto B', 'jan/26', 8))
        profile = build_profile(frame, ' 001 ', ['jan/26'], sku)
        self.assertEqual(profile['client']['id'], '001')
        self.assertEqual(profile['metrics']['revenue'], 10)
        self.assertEqual([p['sku'] for p in profile['products']], ['P1'])
        with self.assertRaises(ValueError):
            product_series(profile, 'P2')

    def test_absent_or_invalid_id_never_falls_back_to_name(self):
        frame = clients([10])
        for cid in ('Empresa fictícia', '1', '001.0', 'ABC', '', None, True, 1):
            with self.subTest(cid=cid), self.assertRaises(ValueError):
                build_profile(frame, cid, ['jan/26'])

    def test_duplicate_selected_id_requires_base_review(self):
        frame = pd.concat([clients([10]), clients([20], name='Outro nome')], ignore_index=True)
        with self.assertRaisesRegex(ValueError, 'mais de um cadastro'):
            build_profile(frame, '001', ['jan/26'])

    def test_inactive_client_can_be_read_without_becoming_active(self):
        profile = build_profile(clients([20], status='Inativo'), '001', ['jan/26'])
        self.assertEqual(profile['client']['status'], 'Inativo')
        self.assertNotIn('can_save', profile)

    def test_inputs_and_returned_series_are_independent(self):
        frame = clients([1, 2])
        sku = sku_rows(('001', 'P', 'Produto', 'jan/26', 2))
        old_frame, old_sku = deepcopy(frame), deepcopy(sku)
        profile = build_profile(frame, '001', ['jan/26', 'fev/26'], sku)
        result = product_series(profile, 'P')
        result[0]['quantity'] = 999
        self.assertEqual(product_series(profile, 'P')[0]['quantity'], 2)
        pd.testing.assert_frame_equal(frame, old_frame)
        pd.testing.assert_frame_equal(sku, old_sku)


class MonthlyTests(unittest.TestCase):
    def test_windows_anchor_in_loaded_months_not_today(self):
        months = months_from(2021, 9, 30)
        frame = clients(list(range(1, 31)))
        p12 = build_profile(frame, '001', months, period='12m')
        p24 = build_profile(frame, '001', months, period='24m')
        full = build_profile(frame, '001', months, period='all')
        self.assertEqual(p12['period']['months'], months[-12:])
        self.assertEqual(p24['period']['months'], months[-24:])
        self.assertEqual(full['period']['months'], months)
        self.assertEqual(p12['metrics']['revenue'], sum(range(19, 31)))
        self.assertEqual(full['history']['revenue'], sum(range(1, 31)))

    def test_older_purchase_remains_visible_after_zero_recent_year(self):
        months = months_from(2023, 1, 24)
        frame = clients([100, 200] + [0] * 22)
        profile = build_profile(frame, '001', months)
        self.assertEqual(profile['metrics']['revenue'], 0)
        self.assertEqual(profile['history']['revenue'], 300)
        self.assertEqual(profile['history']['first_purchase_month'], '2023-01')
        self.assertEqual(profile['history']['last_purchase_month'], '2023-02')
        self.assertTrue(profile['history']['has_older_purchases'])
        self.assertIsNone(profile['metrics']['average_purchase_month'])
        self.assertEqual(profile['client']['last_purchase'], '03/09/2026')

    def test_frequency_and_purchase_month_average_share_the_window(self):
        profile = build_profile(clients([100, 0, 300, 0, 0, 200]), '001', months_from(2026, 1, 6))
        self.assertEqual(profile['metrics']['months_with_purchase'], 3)
        self.assertEqual(profile['metrics']['months_selected'], 6)
        self.assertEqual(profile['metrics']['frequency_pct'], 50)
        self.assertEqual(profile['metrics']['average_purchase_month'], 200)
        self.assertNotIn('ticket', profile['metrics'])

    def test_negative_month_keeps_revenue_but_is_not_a_purchase_month(self):
        profile = build_profile(clients([100, -20, 0]), '001', months_from(2026, 1, 3))
        self.assertEqual(profile['metrics']['revenue'], 80)
        self.assertEqual(profile['metrics']['months_with_purchase'], 1)
        self.assertEqual(profile['metrics']['average_purchase_month'], 80)

    def test_invalid_values_are_gaps_and_make_complete_metrics_unavailable(self):
        invalids = [None, '', '30', float('nan'), float('inf'), -float('inf'), True]
        frame = clients([10, *invalids, Decimal('2.50')])
        profile = build_profile(frame, '001', months_from(2026, 1, 9))
        self.assertEqual(profile['metrics']['revenue_known'], 12.5)
        self.assertEqual(profile['metrics']['months_valid'], 2)
        for key in ('revenue', 'frequency_pct', 'average_purchase_month'):
            self.assertIsNone(profile['metrics'][key])
        self.assertEqual(profile['coverage']['monthly_invalid_count'], 7)
        self.assertTrue(all(p['revenue'] is None for p in profile['monthly_series'][1:-1]))

    def test_invalid_old_data_does_not_hide_valid_recent_metrics(self):
        profile = build_profile(clients([None] + [5] * 12), '001', months_from(2025, 1, 13))
        self.assertEqual(profile['metrics']['revenue'], 60)
        self.assertIsNone(profile['history']['revenue'])
        self.assertEqual(profile['history']['revenue_known'], 60)

    def test_short_series_is_not_padded_with_zero(self):
        profile = build_profile(clients([10]), '001', ['jan/26', 'fev/26'])
        self.assertIsNone(profile['monthly_series'][1]['revenue'])
        self.assertIsNone(profile['metrics']['revenue'])
        self.assertEqual(profile['metrics']['revenue_known'], 10)

    def test_extra_values_without_month_are_not_attributed_to_dates(self):
        profile = build_profile(clients([10, 999]), '001', ['jan/26'])
        self.assertEqual(profile['history']['revenue'], 10)
        self.assertTrue(any('tamanho' in warning for warning in profile['warnings']))

    def test_no_months_has_no_totals_or_invented_observed_dates(self):
        profile = build_profile(clients([]), '001', [])
        self.assertIsNone(profile['metrics']['revenue'])
        self.assertIsNone(profile['history']['first_purchase_month'])
        self.assertIsNone(profile['period']['end'])
        self.assertEqual(profile['monthly_series'], [])

    def test_month_formats_reuse_project_parser_without_misreading_long_year(self):
        months = ['set/2025', datetime(2025, 10, 1), date(2025, 11, 1), '2025-12', 'JAN/26']
        profile = build_profile(clients([1] * 5), '001', months)
        self.assertEqual(profile['period']['months'], months_from(2025, 9, 5))

    def test_invalid_duplicate_or_unordered_axis_is_rejected(self):
        for axis in (['invalido'], ['jan/26', 'JAN/26'], ['fev/26', 'jan/26'], 'jan/26'):
            with self.subTest(axis=axis), self.assertRaises(ValueError):
                build_profile(clients([1, 2]), '001', axis)

    def test_unknown_period_is_rejected(self):
        with self.assertRaises(ValueError):
            build_profile(clients([1]), '001', ['jan/26'], period='since_forever')

    def test_legacy_zero_limitation_is_always_visible(self):
        profile = build_profile(clients([0, 10]), '001', ['jan/26', 'fev/26'])
        self.assertTrue(any('convertidas em zero' in warning for warning in profile['warnings']))


class ProductTests(unittest.TestCase):
    def test_products_use_exactly_same_window_as_monthly_metrics(self):
        months = months_from(2025, 1, 13)
        sku = sku_rows(('001', 'OLD', 'Antigo', 'jan/25', 90),
                       ('001', 'NEW', 'Atual', 'jan/26', 3),
                       ('001', 'FUTURE', 'Após a base', 'fev/26', 8))
        frame = clients([1] * 13)
        recent = build_profile(frame, '001', months, sku)
        full = build_profile(frame, '001', months, sku, period='all')
        self.assertEqual([p['sku'] for p in recent['products']], ['NEW'])
        self.assertEqual([p['sku'] for p in full['products']], ['OLD', 'NEW'])
        self.assertEqual([p['month'] for p in product_series(recent, 'NEW')], recent['period']['months'])

    def test_same_sku_different_names_is_one_product_with_latest_name(self):
        sku = sku_rows(('001', 'P', 'Nome antigo', 'jan/26', 2),
                       ('001', 'P', 'Nome atual', 'fev/26', 3),
                       ('001', 'P', 'Nome atual', 'fev/26', 1))
        frame = clients([1, 1])
        result = build_profile(frame, '001', ['jan/26', 'fev/26'], sku)
        reverse = build_profile(frame, '001', ['jan/26', 'fev/26'], sku.iloc[::-1])
        self.assertEqual(result['products'], reverse['products'])
        self.assertEqual(result['products'], [{'sku': 'P', 'product': 'Nome atual', 'quantity': 6,
                                             'months_with_purchase': 2, 'last_purchase_month': '2026-02'}])

    def test_quantity_series_preserves_unknown_months_even_if_other_client_bought(self):
        sku = sku_rows(('001', 'P', 'Produto', 'jan/26', 2),
                       ('999', 'P', 'Outro cliente', 'fev/26', 70))
        profile = build_profile(clients([1, 0, 0]), '001', months_from(2026, 1, 3), sku)
        self.assertEqual([p['quantity'] for p in product_series(profile, 'P')], [2, None, None])
        self.assertFalse(profile['coverage']['sku_coverage_confirmed'])
        self.assertEqual(profile['coverage']['sku_missing_selected_months'], ['2026-02', '2026-03'])
        self.assertEqual(profile['coverage']['sku_source_months_observed'], ['2026-01'])
        self.assertEqual(profile['products'][0]['product'], 'Produto')

    def test_other_client_rows_are_filtered_before_materializing_records(self):
        sku = sku_rows(('001', 'P', 'Produto', 'jan/26', 2),
                       ('999', 'OTHER', 'Outra carteira', 'mar/26', 50))
        original = pd.DataFrame.to_dict
        seen = []

        def capture(frame, *args, **kwargs):
            seen.extend(frame['cod_cliente'].tolist())
            return original(frame, *args, **kwargs)

        with patch.object(pd.DataFrame, 'to_dict', capture):
            profile = build_profile(clients([1, 0, 0]), '001', months_from(2026, 1, 3), sku)
        self.assertEqual(seen, ['001'])
        self.assertNotIn('2026-03', profile['coverage']['sku_source_months_observed'])

    def test_invalid_quantity_and_month_do_not_create_products(self):
        sku = sku_rows(('001', 'P', 'Produto', 'jan/26', 0),
                       ('001', 'P', 'Produto', 'jan/26', -1),
                       ('001', 'P', 'Produto', 'jan/26', float('nan')),
                       ('001', 'P', 'Produto', 'jan/26', True),
                       ('001', 'P', 'Produto', 'invalido', 3),
                       ('001', '', 'Produto', 'jan/26', 3),
                       ('001', 'OK', None, 'jan/26', 1.5))
        profile = build_profile(clients([1]), '001', ['jan/26'], sku)
        self.assertEqual([p['sku'] for p in profile['products']], ['OK'])
        self.assertEqual(profile['products'][0]['quantity'], 1.5)
        self.assertEqual(profile['products'][0]['product'], 'OK')
        self.assertEqual(profile['coverage']['sku_invalid_rows'], 6)

    def test_missing_product_schema_keeps_monthly_analysis(self):
        for sku in (None, pd.DataFrame(), pd.DataFrame({'produto': ['Exemplo']})):
            with self.subTest(schema=type(sku).__name__):
                profile = build_profile(clients([10]), '001', ['jan/26'], sku)
                self.assertEqual(profile['metrics']['revenue'], 10)
                self.assertEqual(profile['products'], [])
                self.assertFalse(profile['coverage']['sku_available'])

    def test_product_totals_reconcile_with_available_series_without_revenue(self):
        sku = sku_rows(('001', 'A', 'Produto A', 'jan/26', 2),
                       ('001', 'A', 'Produto A', 'mar/26', 4),
                       ('001', 'B', 'Produto B', 'fev/26', 1))
        profile = build_profile(clients([10, 20, 30]), '001', months_from(2026, 1, 3), sku)
        for product in profile['products']:
            series = product_series(profile, product['sku'])
            self.assertEqual(product['quantity'], sum(p['quantity'] or 0 for p in series))
            self.assertFalse(any('revenue' in key or 'preco' in key for key in product))

    def test_missing_client_products_never_fall_back_to_another_client(self):
        sku = sku_rows(('999', 'P', 'Produto', 'jan/26', 2))
        profile = build_profile(clients([10]), '001', ['jan/26'], sku)
        self.assertEqual(profile['products'], [])
        self.assertEqual(profile['sku_series'], {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
