# -*- coding: utf-8 -*-
"""Análise descritiva de registros de garantia, sem interface ou persistência.

Cada registro não cancelado representa um caso, não uma unidade defeituosa.
Custos vêm exclusivamente de custo_total persistido; o catálogo fornece nomes.
Datas inválidas/futuras ficam ausentes e nunca viram duração zero.
"""
from collections import Counter, defaultdict
from datetime import date, datetime
import math
from numbers import Number

import pandas as pd


MISSING_SKU = '__SEM_SKU__'
PENDING_FREIGHT = 'Confirmado — aguardando R$ frete'
TECHNICAL_STATUSES = ('Aguardando chegada', 'Em bancada', 'Aguardando peça')
CLOSED_STATUSES = ('Concluída', PENDING_FREIGHT)
_STATUS_NAMES = {value.casefold(): value for value in
                 TECHNICAL_STATUSES + CLOSED_STATUSES + ('Cancelada',)}
_STATUS_NAMES.update({'aberta': 'Aguardando chegada', 'devolvida ao cliente': 'Concluída'})

FRAME_COLUMNS = ['id', 'sku', 'produto', 'canal', 'status', 'defeito', 'causa', 'resultado',
                 'criado', 'custo_registrado', 'encerrado', 'pendente_frete', 'ativo_tecnico',
                 'dias_empresa', 'dias_resolucao', 'data_envio', 'prioridade']
PRODUCT_COLUMNS = ['sku', 'produto', 'casos', 'abertos', 'encerrados', 'sem_diagnostico',
                   'fabricacao', 'custo_registrado', 'custos_informados', 'participacao']
_BOOL_COLUMNS = ('encerrado', 'pendente_frete', 'ativo_tecnico')
_FLOAT_COLUMNS = ('custo_registrado', 'dias_empresa', 'dias_resolucao')
_CASE_FIELDS = {'id', 'produto_sku', 'produto_nome', 'canal', 'status', 'defeito',
                'diagnostico_causa', 'resultado', 'criado_em', 'custo_total',
                'data_chegada', 'data_envio', 'prioridade'}


def _text(value, default=''):
    if isinstance(value, bool) or not isinstance(value, (str, Number)):
        return default
    if isinstance(value, Number):
        try:
            if not math.isfinite(value):
                return default
        except (TypeError, ValueError, OverflowError):
            return default
    result = str(value).strip()
    return result if result else default


def _sku(value):
    result = _text(value).upper()
    if result in ('', 'NAN', 'NAT', 'NONE', 'NULL', 'TRUE', 'FALSE'):
        return MISSING_SKU
    return result


def _other(value, detail, default):
    label = _text(value, default)
    if label.casefold() in ('outro', 'outra'):
        label = 'Outra' if label.casefold() == 'outra' else 'Outro'
        detail = _text(detail)
        return f'{label} ({detail})' if detail else label
    return label


def _parse_date(value):
    if not isinstance(value, (str, date, datetime)):
        return None
    try:
        if pd.isna(value):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        value = value.strip()
        if 'T' in value or ' ' in value:
            return datetime.fromisoformat(value).date()
        result = date.fromisoformat(value)
        return result if result.isoformat() == value else None
    except (TypeError, ValueError, OverflowError):
        return None


def _limit(value, label):
    parsed = _parse_date(value)
    if parsed is None:
        raise ValueError(f'{label} deve ser uma data válida.')
    return parsed


def _known_date(value, today):
    parsed = _parse_date(value)
    return parsed if parsed is not None and parsed <= today else None


def _cost(value):
    if isinstance(value, bool):
        return float('nan')
    try:
        result = float(value)
        if math.isfinite(result) and result >= 0:
            return result if result else 0.0
    except (TypeError, ValueError, OverflowError):
        pass
    return float('nan')


def _name(names, fallback):
    """Nome mais frequente; empate alfabético estável, independente da ordem."""
    counts = Counter(name for name in names if name)
    return min(counts, key=lambda name: (-counts[name], name.casefold(), name)) if counts else fallback


def _sum_costs(costs):
    values = costs.dropna().tolist()
    if not values:
        return float('nan')
    try:
        total = math.fsum(values)
        return total if math.isfinite(total) else float('nan')
    except (TypeError, ValueError, OverflowError):
        return float('nan')


def _catalog_names(products_df):
    names = defaultdict(list)
    if isinstance(products_df, pd.DataFrame) and {'code', 'name'}.issubset(products_df.columns):
        for code, name in products_df[['code', 'name']].itertuples(index=False, name=None):
            sku, name = _sku(code), _text(name)
            if sku != MISSING_SKU and name:
                names[sku].append(name)
    return {sku: _name(values, sku) for sku, values in names.items()}


def _frame(rows, indices=None):
    frame = pd.DataFrame(rows, columns=FRAME_COLUMNS, index=indices)
    for column in _BOOL_COLUMNS:
        frame[column] = frame[column].astype(bool)
    for column in _FLOAT_COLUMNS:
        frame[column] = frame[column].astype(float)
    # Preserva date/None em vez de converter ausências em timestamps/NaT.
    for column in ('criado', 'data_envio'):
        frame[column] = pd.Series([row[column] for row in rows], index=frame.index, dtype=object)
    return frame


def build_frame(registros, products_df=None, hoje=None):
    """Normaliza casos sem mutar registros ou catálogo.

    O índice preserva a posição de cada caso na lista original, inclusive os
    intervalos deixados por registros ignorados; serve para acessar o original.
    Canceladas são excluídas inclusive para administradores. Nomes legados
    Aberta/Devolvida ao cliente viram Aguardando chegada/Concluída. Um SKU é
    identificado pelo código em maiúsculas, nunca pelo nome; sem código usa
    MISSING_SKU. Nome do catálogo prevalece; o fallback é estável por SKU.

    custo_registrado é float finito não negativo ou NaN; zero é informado.
    ativo_tecnico cobre apenas os três estados técnicos abertos; pendência
    de frete já é encerramento operacional. dias_empresa usa chegada até hoje
    para ativos, mesmo reabertos (não estima o início de um novo ciclo).
    dias_resolucao usa somente chegada→envio de encerrados, sem datas futuras
    ou invertidas. criado é a data de cadastro: pode ser posterior à chegada
    e ao envio em registros retroativos, sem invalidar a duração física. Não há
    fallback por confirmação/abertura e nenhum custo é recalculado.
    """
    today = date.today() if hoje is None else _limit(hoje, 'Hoje')
    if not isinstance(registros, (list, tuple)):
        return _frame([])
    rows, indices, historical_names = [], [], defaultdict(list)
    for source_index, record in enumerate(registros):
        if not isinstance(record, dict) or not _CASE_FIELDS.intersection(record):
            continue
        raw_status = _text(record.get('status'), 'Não informado')
        status = _STATUS_NAMES.get(raw_status.casefold(), raw_status)
        if status == 'Cancelada':
            continue
        sku = _sku(record.get('produto_sku'))
        historical_names[sku].append(_text(record.get('produto_nome')))
        created = _known_date(record.get('criado_em'), today)
        arrival = _known_date(record.get('data_chegada'), today)
        shipped = _known_date(record.get('data_envio'), today)
        closed = status in CLOSED_STATUSES
        active = status in TECHNICAL_STATUSES
        company_days = (today - arrival).days if active and arrival is not None else float('nan')
        resolution_days = float('nan')
        if closed and arrival is not None and shipped is not None and arrival <= shipped:
            resolution_days = (shipped - arrival).days
        priority = _text(record.get('prioridade'), 'Normal')
        priority = {'normal': 'Normal', 'alta': 'Alta', 'urgente': 'Urgente'}.get(priority.casefold(), priority)
        rows.append({
            'id': _text(record.get('id'), 'Sem ID'), 'sku': sku, 'produto': '',
            'canal': _other(record.get('canal'), record.get('canal_outro'), 'Não informado'),
            'status': status,
            'defeito': _other(record.get('defeito'), record.get('defeito_outro'), 'Não informado'),
            'causa': _text(record.get('diagnostico_causa'), 'Sem diagnóstico'),
            'resultado': _text(record.get('resultado'), 'Sem resultado'),
            'criado': created, 'custo_registrado': _cost(record.get('custo_total')),
            'encerrado': closed, 'pendente_frete': status == PENDING_FREIGHT,
            'ativo_tecnico': active, 'dias_empresa': company_days,
            'dias_resolucao': resolution_days, 'data_envio': shipped, 'prioridade': priority,
        })
        indices.append(source_index)
    catalog = _catalog_names(products_df)
    canonical_names = {sku: catalog.get(sku) or _name(names, 'Produto não informado')
                       for sku, names in historical_names.items()}
    # Um código ausente não identifica um produto, mesmo que os nomes coincidam.
    canonical_names[MISSING_SKU] = 'Sem SKU informado'
    for row in rows:
        row['produto'] = canonical_names[row['sku']]
    return _frame(rows, indices)


def filter_frame(frame, inicio=None, fim=None, canais=None, skus=None):
    """Cópia filtrada por data de registro inclusiva, canais e códigos.

    None significa sem filtro; lista vazia significa seleção vazia. Casos sem
    data de registro ficam fora quando qualquer limite de data é aplicado.
    Datas invertidas/inválidas provocam ValueError, sem ampliar a seleção.
    Mantém o índice de origem para rastrear os registros selecionados.
    """
    start = _limit(inicio, 'Início') if inicio is not None else None
    end = _limit(fim, 'Fim') if fim is not None else None
    if start is not None and end is not None and start > end:
        raise ValueError('A data inicial não pode ser posterior à final.')
    result = frame.copy(deep=True)
    if start is not None or end is not None:
        mask = result['criado'].map(lambda value: value is not None
                                    and (start is None or value >= start)
                                    and (end is None or value <= end))
        result = result.loc[mask.astype(bool)]
    if canais is not None:
        selected = [canais] if isinstance(canais, str) else canais
        result = result[result['canal'].isin([_text(value) for value in selected])]
    if skus is not None:
        selected = [skus] if isinstance(skus, str) else skus
        result = result[result['sku'].isin([_sku(value) for value in selected])]
    return result.copy(deep=True)


def product_summary(frame):
    """Uma linha por SKU, contagens e custos registrados da seleção.

    abertos = ativos técnicos; encerrados inclui pendência de frete. Status
    desconhecido permanece nos casos, sem ser inventado como aberto/encerrado.
    fabricacao conta apenas diagnóstico explícito 'Defeito de fabricação'.
    participacao é fração 0..1 dos casos da seleção, não taxa de defeito.
    Custos totalmente ausentes resultam em NaN, com custos_informados=0.
    """
    if frame.empty:
        return pd.DataFrame(columns=PRODUCT_COLUMNS)
    rows = []
    for sku, group in frame.groupby('sku', sort=False, dropna=False):
        costs = group['custo_registrado']
        rows.append({
            'sku': sku, 'produto': _name(group['produto'].tolist(), 'Produto não informado'),
            'casos': len(group), 'abertos': int(group['ativo_tecnico'].sum()),
            'encerrados': int(group['encerrado'].sum()),
            'sem_diagnostico': int(group['causa'].eq('Sem diagnóstico').sum()),
            'fabricacao': int(group['causa'].str.casefold().eq('defeito de fabricação').sum()),
            'custo_registrado': _sum_costs(costs),
            'custos_informados': int(costs.notna().sum()),
            'participacao': len(group) / len(frame),
        })
    return pd.DataFrame(rows, columns=PRODUCT_COLUMNS).sort_values(
        ['casos', 'produto', 'sku'], ascending=[False, True, True], kind='stable').reset_index(drop=True)


def monthly_summary(frame, inicio, fim):
    """Série mes (date, primeiro dia) / casos por data de registro.

    Completa todos os meses da faixa com zero; início/fim continuam inclusivos
    ao nível do dia. Não mistura entradas da coorte com saídas de outros meses.
    """
    start, end = _limit(inicio, 'Início'), _limit(fim, 'Fim')
    selected = filter_frame(frame, inicio=start, fim=end)
    counts = Counter(date(value.year, value.month, 1) for value in selected['criado'])
    months = []
    cursor = date(start.year, start.month, 1)
    last_month = date(end.year, end.month, 1)
    while cursor <= last_month:
        months.append({'mes': cursor, 'casos': counts[cursor]})
        if cursor == last_month:
            break
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    result = pd.DataFrame(months, columns=['mes', 'casos'])
    result['mes'] = pd.Series([item['mes'] for item in months], dtype=object)
    result['casos'] = result['casos'].astype(int)
    return result
