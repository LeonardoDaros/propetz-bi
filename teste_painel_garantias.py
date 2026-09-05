# -*- coding: utf-8 -*-
"""Regressões analíticas do painel de garantias; somente dados sintéticos."""
from copy import deepcopy
from datetime import date, datetime
import math
import unittest

import pandas as pd

from garantia_analytics import (
    FRAME_COLUMNS, PRODUCT_COLUMNS, MISSING_SKU, PENDING_FREIGHT,
    build_frame, filter_frame, product_summary, monthly_summary,
)


TODAY = date(2026, 9, 4)


def case(gid='G-1', **changes):
    record = {
        'id': gid, 'produto_sku': 'SKU-A', 'produto_nome': 'Produto teste',
        'canal': 'Distribuição', 'status': 'Concluída', 'defeito': 'Não liga',
        'diagnostico_causa': 'Defeito de fabricação', 'resultado': 'Consertada',
        'criado_em': '2026-08-01 10:00', 'data_chegada': '2026-08-03',
        'data_envio': '2026-08-06', 'prioridade': 'Normal', 'custo_total': 40.0,
    }
    record.update(changes)
    return record


class FrameTests(unittest.TestCase):
    def test_empty_and_malformed_inputs_have_complete_safe_schema(self):
        for records in (None, {}, 'texto', [], [None, 'texto', 1, {}, {'foo': 'bar'}]):
            with self.subTest(records=records):
                frame = build_frame(records, hoje=TODAY)
                self.assertTrue(frame.empty)
                self.assertEqual(frame.columns.tolist(), FRAME_COLUMNS)
                self.assertEqual(frame['encerrado'].dtype, bool)
                self.assertEqual(frame['dias_resolucao'].dtype, float)
                self.assertEqual(product_summary(frame).columns.tolist(), PRODUCT_COLUMNS)
                self.assertTrue(filter_frame(frame, inicio=TODAY).empty)

    def test_cancelled_excluded_and_index_tracks_original_records(self):
        records = [case('CANCELADA', status=' Cancelada '), None,
                   case('ATIVA', status='Aberta'), {'foo': 'bar'},
                   case('ENCERRADA', status='Devolvida ao cliente')]
        frame = build_frame(records, hoje=TODAY)
        self.assertEqual(frame.index.tolist(), [2, 4])
        self.assertEqual(frame['id'].tolist(), ['ATIVA', 'ENCERRADA'])
        self.assertEqual(frame['status'].tolist(), ['Aguardando chegada', 'Concluída'])
        filtered = filter_frame(frame, inicio='2026-08-01', fim='2026-08-01')
        self.assertEqual([records[i]['id'] for i in filtered.index], filtered['id'].tolist())
        self.assertIsInstance(filtered.loc[4, 'criado'], date)

    def test_same_sku_and_name_variants_have_catalog_canonical_identity(self):
        records = [case('1', produto_sku=' sku-a ', produto_nome='Nome antigo'),
                   case('2', produto_sku='SKU-A', produto_nome='Nome novo')]
        catalog = pd.DataFrame([{'code': ' sku-A ', 'name': 'Nome do catálogo', 'custo_unitario': 999999}])
        frame = build_frame(records, catalog, TODAY)
        self.assertEqual(frame['sku'].tolist(), ['SKU-A', 'SKU-A'])
        self.assertEqual(frame['produto'].tolist(), ['Nome do catálogo'] * 2)
        summary = product_summary(frame)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary.iloc[0]['casos'], 2)
        self.assertEqual(summary.iloc[0]['custo_registrado'], 80)

    def test_fallback_name_is_stable_with_reversed_order(self):
        records = [case('1', produto_nome='Nome B'), case('2', produto_nome='Nome A')]
        names = build_frame(records, hoje=TODAY)['produto'].tolist()
        reversed_names = build_frame(list(reversed(records)), hoje=TODAY)['produto'].tolist()
        self.assertEqual(names, ['Nome A', 'Nome A'])
        self.assertEqual(reversed_names, names)

    def test_missing_boolean_and_nan_skus_use_sentinel_without_name_matching(self):
        missing = (None, '', ' ', True, False, float('nan'), 'NaN', 'False', [], {})
        records = [case(str(i), produto_sku=sku, produto_nome='Produto teste')
                   for i, sku in enumerate(missing)] + [case('VALIDO')]
        catalog = pd.DataFrame([{'code': 'SKU-A', 'name': 'Produto teste'}])
        frame = build_frame(records, catalog, TODAY)
        self.assertEqual(frame['sku'].tolist(), [MISSING_SKU] * len(missing) + ['SKU-A'])
        summary = product_summary(frame).set_index('sku')
        self.assertEqual(summary.loc[MISSING_SKU, 'casos'], len(missing))
        self.assertEqual(summary.loc[MISSING_SKU, 'produto'], 'Sem SKU informado')

    def test_other_values_and_missing_diagnosis_are_explicit(self):
        frame = build_frame([case(canal='Outro', canal_outro=' Loja parceira ',
                                 defeito='Outro', defeito_outro=' Falha intermitente ',
                                 diagnostico_causa=None, resultado=None)], hoje=TODAY)
        row = frame.iloc[0]
        self.assertEqual(row['canal'], 'Outro (Loja parceira)')
        self.assertEqual(row['defeito'], 'Outro (Falha intermitente)')
        self.assertEqual(row['causa'], 'Sem diagnóstico')
        self.assertEqual(row['resultado'], 'Sem resultado')

    def test_pending_freight_is_operationally_closed_not_technical_backlog(self):
        frame = build_frame([case(status=PENDING_FREIGHT)], hoje=TODAY)
        row = frame.iloc[0]
        self.assertTrue(row['encerrado'])
        self.assertTrue(row['pendente_frete'])
        self.assertFalse(row['ativo_tecnico'])
        self.assertEqual(row['dias_resolucao'], 3)
        self.assertTrue(math.isnan(row['dias_empresa']))

    def test_inputs_are_not_mutated_even_with_nested_data_or_catalog(self):
        records = [case(pecas=[{'qtd': 1, 'custo': 99999}]), case('C', status='Cancelada')]
        original = deepcopy(records)
        catalog = pd.DataFrame([{'code': 'SKU-A', 'name': 'Nome atual'}])
        before_catalog = catalog.copy(deep=True)
        frame = build_frame(records, catalog, TODAY)
        before_frame = frame.copy(deep=True)
        filter_frame(frame, inicio='2026-08-01')
        product_summary(frame)
        monthly_summary(frame, date(2026, 8, 1), TODAY)
        self.assertEqual(records, original)
        pd.testing.assert_frame_equal(catalog, before_catalog)
        pd.testing.assert_frame_equal(frame, before_frame)


class CostTests(unittest.TestCase):
    def test_zero_is_recorded_and_current_catalog_or_parts_never_recalculate_cost(self):
        records = [case(custo_total=0, pecas=[{'qtd': 10, 'custo': 1000}])]
        catalog = pd.DataFrame([{'code': 'SKU-A', 'name': 'Nome', 'custo_unitario': 50000}])
        frame = build_frame(records, catalog, TODAY)
        self.assertEqual(frame.iloc[0]['custo_registrado'], 0)
        summary = product_summary(frame).iloc[0]
        self.assertEqual(summary['custos_informados'], 1)
        self.assertEqual(summary['custo_registrado'], 0)

    def test_missing_invalid_negative_and_overflow_costs_remain_nan(self):
        values = [None, '', 'R$ 10', '1e999', float('nan'), float('inf'), -2, True, [], 10 ** 1000]
        frame = build_frame([case(str(i), custo_total=value) for i, value in enumerate(values)], hoje=TODAY)
        self.assertTrue(frame['custo_registrado'].isna().all())
        summary = product_summary(frame).iloc[0]
        self.assertEqual(summary['custos_informados'], 0)
        self.assertTrue(math.isnan(summary['custo_registrado']))

    def test_partially_known_costs_sum_only_informed_and_reconcile(self):
        records = [case('1', custo_total=0), case('2', custo_total=12.5),
                   case('3', custo_total=None), case('4', produto_sku='SKU-B', custo_total='7.5')]
        frame = build_frame(records, hoje=TODAY)
        summary = product_summary(frame)
        self.assertEqual(summary['custos_informados'].sum(), 3)
        self.assertEqual(summary['custo_registrado'].sum(), 20)
        self.assertEqual(summary['custo_registrado'].sum(), frame['custo_registrado'].sum())

    def test_sum_overflow_does_not_produce_infinity(self):
        frame = build_frame([case('1', custo_total=1e308), case('2', custo_total=1e308)], hoje=TODAY)
        summary = product_summary(frame).iloc[0]
        self.assertEqual(summary['custos_informados'], 2)
        self.assertTrue(math.isnan(summary['custo_registrado']))


class DateTests(unittest.TestCase):
    def test_active_time_uses_arrival_and_does_not_freeze_on_old_shipping(self):
        frame = build_frame([case(status='Em bancada', data_chegada='2026-09-01',
                                 data_envio='2026-09-02')], hoje=TODAY)
        self.assertEqual(frame.iloc[0]['dias_empresa'], 3)
        self.assertTrue(math.isnan(frame.iloc[0]['dias_resolucao']))

    def test_no_arrival_never_falls_back_to_registration_for_duration(self):
        records = [case('1', data_chegada=None), case('2', status='Em bancada', data_chegada='')]
        frame = build_frame(records, hoje=TODAY)
        self.assertTrue(frame['dias_resolucao'].isna().all())
        self.assertTrue(frame['dias_empresa'].isna().all())

    def test_closed_duration_only_valid_arrival_to_shipping(self):
        records = [case('VALIDO'), case('ZERO', data_envio='2026-08-03'),
                   case('FUTURO', data_envio='2027-08-03'),
                   case('INVERSO', data_envio='2026-08-02'),
                   case('AUSENTE', data_envio=''),
                   case('ANTES_REGISTRO', criado_em='2026-08-04'),
                   case('REGISTRO_AUSENTE', criado_em=None)]
        frame = build_frame(records, hoje=TODAY).set_index('id')
        self.assertEqual(frame.loc['VALIDO', 'dias_resolucao'], 3)
        self.assertEqual(frame.loc['ZERO', 'dias_resolucao'], 0)
        self.assertEqual(frame.loc['REGISTRO_AUSENTE', 'dias_resolucao'], 3)
        self.assertEqual(frame.loc['ANTES_REGISTRO', 'dias_resolucao'], 3)
        for cid in ('FUTURO', 'INVERSO', 'AUSENTE'):
            self.assertTrue(math.isnan(frame.loc[cid, 'dias_resolucao']))

    def test_retroactive_registration_preserves_real_arrival_to_shipping_duration(self):
        record = case(criado_em='2026-08-10 10:00', data_chegada='2026-08-03', data_envio='2026-08-06')
        original = deepcopy(record)
        frame = build_frame([record], hoje=TODAY)
        self.assertEqual(frame.iloc[0]['dias_resolucao'], 3)
        self.assertEqual(frame.iloc[0]['criado'], date(2026, 8, 10))
        self.assertEqual(frame.iloc[0]['data_envio'], date(2026, 8, 6))
        self.assertEqual(record, original)

    def test_invalid_future_and_nat_dates_become_none(self):
        values = ['errada', '2026-02-30', '2027-01-01', pd.NaT, None, True,
                  '2026-08-01 texto inválido']
        frame = build_frame([case(str(i), criado_em=value, data_chegada=value, data_envio=value)
                             for i, value in enumerate(values)], hoje=TODAY)
        self.assertTrue(all(value is None for value in frame['criado']))
        self.assertTrue(all(value is None for value in frame['data_envio']))
        self.assertTrue(frame['dias_resolucao'].isna().all())

    def test_date_and_datetime_objects_keep_calendar_dates(self):
        frame = build_frame([case(criado_em=datetime(2026, 8, 1, 23, 59),
                                 data_chegada=date(2026, 8, 3), data_envio=date(2026, 8, 6))], hoje=TODAY)
        self.assertEqual(frame.iloc[0]['criado'], date(2026, 8, 1))
        self.assertEqual(frame.iloc[0]['data_envio'], date(2026, 8, 6))
        self.assertEqual(frame.iloc[0]['dias_resolucao'], 3)


class FilterAndSummaryTests(unittest.TestCase):
    def setUp(self):
        self.records = [case('1', criado_em='2026-07-31', canal='Varejo'),
                        case('2', criado_em='2026-08-01', status='Em bancada', diagnostico_causa=''),
                        case('3', criado_em='2026-08-31', produto_sku='SKU-B', canal='Varejo'),
                        case('4', criado_em='2026-09-01', status=PENDING_FREIGHT),
                        case('5', criado_em=None, produto_sku=None, status='Em bancada')]
        self.frame = build_frame(self.records, hoje=TODAY)

    def test_inclusive_dates_exclude_missing_and_preserve_original_indexes(self):
        selected = filter_frame(self.frame, inicio='2026-08-01', fim='2026-08-31')
        self.assertEqual(selected['id'].tolist(), ['2', '3'])
        self.assertEqual(selected.index.tolist(), [1, 2])
        self.assertEqual([self.records[i]['id'] for i in selected.index], ['2', '3'])

    def test_channel_sku_and_explicit_empty_filters(self):
        selected = filter_frame(self.frame, canais=['Varejo'], skus=[' sku-b '])
        self.assertEqual(selected['id'].tolist(), ['3'])
        self.assertTrue(filter_frame(self.frame, canais=[]).empty)
        self.assertTrue(filter_frame(self.frame, skus=[]).empty)
        self.assertEqual(len(filter_frame(self.frame)), 5)
        self.assertEqual(filter_frame(self.frame, skus=[MISSING_SKU])['id'].tolist(), ['5'])

    def test_invalid_or_inverted_range_never_widens_results(self):
        for start, end in (('texto', '2026-09-04'), ('2026-09-04', '2026-09-03')):
            with self.subTest(start=start), self.assertRaises(ValueError):
                filter_frame(self.frame, inicio=start, fim=end)

    def test_case_status_cost_and_participation_totals_reconcile(self):
        selected = filter_frame(self.frame, inicio='2026-08-01', fim=TODAY)
        summary = product_summary(selected)
        self.assertEqual(summary['casos'].sum(), len(selected))
        self.assertEqual(summary['abertos'].sum(), selected['ativo_tecnico'].sum())
        self.assertEqual(summary['encerrados'].sum(), selected['encerrado'].sum())
        self.assertEqual(summary['sem_diagnostico'].sum(), 1)
        self.assertEqual(summary['fabricacao'].sum(), 2)
        self.assertAlmostEqual(summary['participacao'].sum(), 1.0)
        self.assertEqual(summary['custo_registrado'].sum(), selected['custo_registrado'].sum())

    def test_monthly_is_case_creation_only_with_zeros_and_partial_month_limits(self):
        result = monthly_summary(self.frame, date(2026, 8, 15), date(2026, 10, 4))
        self.assertEqual(result.columns.tolist(), ['mes', 'casos'])
        self.assertEqual(result['mes'].tolist(), [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)])
        self.assertEqual(result['casos'].tolist(), [1, 1, 0])
        self.assertEqual(result['casos'].sum(), len(filter_frame(self.frame, inicio='2026-08-15', fim='2026-10-04')))

    def test_empty_monthly_range_has_zero_months_across_year_boundary(self):
        result = monthly_summary(build_frame([], hoje=TODAY), date(2025, 12, 15), date(2026, 2, 3))
        self.assertEqual(result['mes'].tolist(), [date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)])
        self.assertEqual(result['casos'].tolist(), [0, 0, 0])

    def test_unknown_status_remains_visible_without_inventing_classification(self):
        frame = build_frame([case(status='Status legado desconhecido')], hoje=TODAY)
        row = product_summary(frame).iloc[0]
        self.assertEqual(row['casos'], 1)
        self.assertEqual(row['abertos'], 0)
        self.assertEqual(row['encerrados'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
