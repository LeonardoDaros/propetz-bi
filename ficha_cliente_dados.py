# -*- coding: utf-8 -*-
"""Cálculos puros da ficha comercial, sem I/O, Streamlit ou integração externa.

O chamador fornece somente os clientes autorizados e revalida a carteira ao
salvar contatos. Este módulo seleciona por código exato, nunca por nome.
Os períodos são os meses carregados, sem completar a série até a data atual.
O loader legado já converteu ausências mensais em zero e descartou quantidades
não positivas: a ficha não consegue reconstruir cobertura a partir disso.
"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import math
from numbers import Real
import re

import pandas as pd

from util_comum import parse_label_ym


PERIODS = {'12m': '12 meses', '24m': '24 meses', 'all': 'Histórico disponível'}

_MONTHLY_LIMIT = (
    'Na base mensal, células vazias ou inválidas podem ter sido convertidas '
    'em zero no carregamento. Esta ficha não recupera essa distinção.'
)
_SKU_LIMIT = (
    'A fonte de produtos mantém registros positivos e não informa cobertura '
    'completa por mês. Mês sem registro não comprova quantidade zero. '
    'O último mês observado não determina o fim da cobertura do arquivo.'
)


def _key(value):
    """Não une 001, 1, 1.0 nem variações de caixa de um identificador."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _sum(values):
    try:
        result = math.fsum(values)
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _month(value):
    """Reusa o parser do projeto e aceita também YYYY-MM e ano PT de 4 dígitos."""
    if not isinstance(value, (str, date, datetime)):
        return None
    label = str(value).strip()
    if re.fullmatch(r'\d{4}-\d{2}', label):
        label += '-01'
    long_year = re.fullmatch(r'([^/]+)/([0-9]{4})', label)
    if long_year:
        # O parser legado pressupõe ano com dois dígitos; não o alteramos.
        parsed = parse_label_ym(long_year[1] + '/' + long_year[2][-2:])
        parsed = (int(long_year[2]), parsed[1]) if parsed else None
    else:
        parsed = parse_label_ym(label)
    if not parsed:
        return None
    try:
        date(parsed[0], parsed[1], 1)
    except (ValueError, TypeError):
        return None
    return f'{parsed[0]:04d}-{parsed[1]:02d}'


def _axis(months):
    if months is None:
        return []
    if isinstance(months, (str, bytes, dict)):
        raise ValueError('A lista de meses da base é inválida.')
    try:
        labels = list(months)
    except TypeError:
        raise ValueError('A lista de meses da base é inválida.') from None
    axis = []
    for label in labels:
        month = _month(label)
        if month is None:
            raise ValueError('Há um mês inválido na base mensal.')
        if axis and month <= axis[-1]['month']:
            raise ValueError('Os meses devem ser únicos e estar em ordem cronológica.')
        axis.append({'month': month, 'label': str(label).strip()})
    return axis


def _selected_client(df_clients, client_id):
    cid = _key(client_id)
    if cid is None:
        raise ValueError('Informe um código de cliente válido em texto.')
    if not isinstance(df_clients, pd.DataFrame) or 'id' not in df_clients.columns:
        raise ValueError('A base de clientes não contém códigos válidos.')
    found = df_clients[df_clients['id'].map(_key).eq(cid)]
    if found.empty:
        raise ValueError('Cliente não encontrado na carteira disponível.')
    if len(found) != 1:
        raise ValueError('Há mais de um cadastro com esse código. Revise a base antes de consultar.')
    return found.iloc[0].to_dict(), cid


def _sku_data(df_sku, cid, selected_axis):
    """Soma só o cliente e a janela pedidos. Ausências da série ficam None."""
    coverage = {
        'sku_available': False,
        'sku_source_months_observed': [],
        'sku_selected_months_observed': [],
        'sku_missing_selected_months': [p['month'] for p in selected_axis],
        'sku_coverage_confirmed': False,
        'sku_invalid_rows': 0,
    }
    required = {'cod_cliente', 'sku', 'mes', 'quantidade'}
    if (not isinstance(df_sku, pd.DataFrame) or df_sku.empty
            or not required.issubset(df_sku.columns)):
        return [], {}, coverage, ['Não há uma fonte de produtos por cliente e mês disponível para esta ficha.']

    coverage['sku_available'] = True
    window = {p['month'] for p in selected_axis}
    source_months = set()
    quantities, names = {}, {}
    invalid = 0
    # Recorta pelo ID antes de converter em registros. Nem os metadados de
    # meses desta ficha devem depender de compras de outra carteira.
    mine = df_sku[df_sku['cod_cliente'].map(_key).eq(cid)]
    for row in mine.to_dict('records'):
        row_cid, sku = _key(row.get('cod_cliente')), _key(row.get('sku'))
        month, quantity = _month(row.get('mes')), _number(row.get('quantidade'))
        valid = row_cid is not None and sku is not None and month is not None and quantity is not None and quantity > 0
        if valid:
            source_months.add(month)
        if not valid:
            invalid += 1
            continue
        if month not in window:
            continue
        quantities.setdefault(sku, {}).setdefault(month, []).append(quantity)
        name = _key(row.get('produto')) or sku
        names.setdefault(sku, []).append((month, name))

    products, series = [], {}
    for sku, by_month in quantities.items():
        totals = {month: _sum(values) for month, values in by_month.items()}
        quantity = _sum(value for value in totals.values() if value is not None)
        if quantity is None or any(value is None for value in totals.values()):
            invalid += sum(len(values) for values in by_month.values())
            continue
        # O nome mais recente do próprio cliente evita duplicar o SKU por grafia.
        # Empates são estáveis mesmo que a fonte mude a ordem das linhas.
        product = sorted(names[sku], key=lambda p: (p[0], p[1].casefold(), p[1]))[-1][1]
        products.append({'sku': sku, 'product': product, 'quantity': quantity,
                         'months_with_purchase': len(totals),
                         'last_purchase_month': max(totals)})
        series[sku] = [dict(point, quantity=totals.get(point['month'])) for point in selected_axis]
    products.sort(key=lambda p: (-p['quantity'], p['product'].casefold(), p['sku']))
    coverage.update({
        'sku_source_months_observed': sorted(source_months),
        'sku_selected_months_observed': sorted(source_months & window),
        'sku_missing_selected_months': sorted(window - source_months),
        'sku_invalid_rows': invalid,
    })
    warnings = [_SKU_LIMIT]
    if invalid:
        warnings.append('Registros de produto deste cliente com código, mês ou quantidade inválida foram excluídos. Os totais podem estar incompletos.')
    if window - source_months:
        warnings.append('Parte do período mensal selecionado não tem registros de produtos deste cliente. Compare apenas os meses com informação disponível, sem presumir cobertura completa.')
    if not products:
        warnings.append('Nenhum registro positivo de produto deste cliente foi localizado no período selecionado; isso não prova ausência de compras.')
    return products, series, coverage, warnings


def build_profile(df_clients, client_id, months, df_sku=None, *, period='12m'):
    """Retorna a ficha do ID exato em uma janela dos meses carregados.

    ``df_clients`` deve ser o DataFrame já limitado à carteira autorizada.
    ``period`` é '12m', '24m' ou 'all' (constante PERIODS).
    Não aplica filtro de ativo: consulta histórica é permitida; escrita é do app.

    ``metrics.revenue``, ``frequency_pct`` e ``average_purchase_month`` ficam
    None se a janela estiver vazia ou contiver valor ainda reconhecível como
    inválido. ``revenue_known`` soma os valores válidos, sem garantir completude.
    A primeira/última compra histórica usa meses positivos observados e nunca
    substitui a última compra recente que o chamador recebeu do Silver.
    """
    if not isinstance(period, str) or period not in PERIODS:
        raise ValueError('Escolha 12 meses, 24 meses ou histórico disponível.')
    source, cid = _selected_client(df_clients, client_id)
    axis = _axis(months)
    raw = source.get('monthly')
    raw = list(raw) if isinstance(raw, (list, tuple, pd.Series)) else []
    values = [_number(raw[i]) if i < len(raw) else None for i in range(len(axis))]
    full_series = [dict(point, revenue=value, purchase=(value > 0 if value is not None else None))
                   for point, value in zip(axis, values)]
    count = {'12m': 12, '24m': 24}.get(period, len(axis))
    selected = full_series[-count:] if count else []
    selected_axis = [{'month': p['month'], 'label': p['label']} for p in selected]
    selected_values = [p['revenue'] for p in selected if p['revenue'] is not None]
    purchases = sum(p['purchase'] is True for p in selected)
    known_sum = _sum(selected_values)
    complete = bool(selected) and len(selected_values) == len(selected) and known_sum is not None
    positive = [p['month'] for p in full_series if p['purchase'] is True]
    full_sum = _sum(v for v in values if v is not None)
    historical_complete = bool(axis) and all(v is not None for v in values) and full_sum is not None
    client = {field: deepcopy(source.get(field)) for field in
              ('name', 'state', 'vendor', 'status', 'risk', 'last_purchase', 'months_since')}
    client['id'] = cid
    products, series, sku_coverage, sku_warnings = _sku_data(df_sku, cid, selected_axis)
    warnings = [_MONTHLY_LIMIT] + sku_warnings
    if len(raw) != len(axis):
        warnings.append('O tamanho da série do cliente difere da lista de meses; valores sem mês foram desconsiderados e meses sem valor ficaram sem informação.')
    if any(v is None for v in values):
        warnings.append('Há valores mensais ausentes ou inválidos ainda identificáveis. Indicadores que exigem o período completo ficam indisponíveis.')
    if known_sum is None or full_sum is None:
        warnings.append('A soma dos valores não pôde ser representada com segurança; o total correspondente ficou indisponível.')
    if not axis:
        warnings.append('A base não informa meses disponíveis para esta ficha.')

    return {
        'client': client,
        'period': {'key': period, 'label': PERIODS[period],
                   'start': selected[0]['month'] if selected else None,
                   'end': selected[-1]['month'] if selected else None,
                   'months': [p['month'] for p in selected], 'count': len(selected)},
        'metrics': {'revenue': known_sum if complete else None, 'revenue_known': known_sum,
                    'months_with_purchase': purchases, 'months_selected': len(selected),
                    'months_valid': len(selected_values),
                    'frequency_pct': purchases / len(selected) * 100 if complete else None,
                    'average_purchase_month': known_sum / purchases if complete and purchases else None},
        'history': {'revenue': full_sum if historical_complete else None, 'revenue_known': full_sum,
                    'first_purchase_month': positive[0] if positive else None,
                    'last_purchase_month': positive[-1] if positive else None,
                    'months_with_purchase': len(positive),
                    'has_older_purchases': bool(positive and selected and positive[0] < selected[0]['month'])},
        'monthly_series': selected,
        'products': products,
        'sku_series': series,
        'coverage': {'monthly_start': axis[0]['month'] if axis else None,
                     'monthly_end': axis[-1]['month'] if axis else None,
                     'monthly_invalid_count': sum(v is None for v in values), **sku_coverage},
        'warnings': warnings,
    }


def product_series(profile, sku):
    """Quantidade do SKU selecionado, sem buscar outra pessoa ou outra janela."""
    key = _key(sku)
    if key is None or key not in profile.get('sku_series', {}):
        raise ValueError('O produto não está disponível no período deste cliente.')
    return deepcopy(profile['sku_series'][key])
