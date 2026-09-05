# -*- coding: utf-8 -*-
"""Agenda comercial pura: validação, histórico e priorização por cliente.

Não acessa Streamlit, arquivos, rede ou relógio do sistema. O chamador fornece
datas e IDs e deve revalidar autorização/carteira antes de persistir uma escrita.
Encerrar um acompanhamento nunca inativa o cliente comercial.
"""
from copy import deepcopy
from datetime import date, datetime
import math
from uuid import UUID


CHANNELS = ('WhatsApp', 'Ligação', 'E-mail', 'Visita', 'Outro')
OUTCOMES = ('Sem resposta', 'Contato realizado', 'Retorno combinado',
            'Proposta enviada', 'Pedido informado', 'Sem interesse')


class ConflictError(ValueError):
    """O cliente foi alterado ou um ID de evento foi reutilizado indevidamente."""


_CLIENT_FIELDS = {'version', 'retorno_em', 'proxima_acao', 'encerrado', 'historico'}
_EVENT_FIELDS = {'id', 'em', 'user', 'canal', 'resultado', 'observacao',
                 'proxima_acao', 'retorno_em', 'encerrado'}
_SNAPSHOT_FIELDS = ('retorno_em', 'proxima_acao', 'encerrado')


def _text(value, label, *, maximum=None, required=True):
    if not isinstance(value, str):
        raise ValueError(f'{label} deve ser texto.')
    value = value.strip()
    if required and not value:
        raise ValueError(f'{label} é obrigatório.')
    if maximum is not None and len(value) > maximum:
        raise ValueError(f'{label} deve ter no máximo {maximum} caracteres.')
    return value


def _date(value, label):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        value = value.strip()
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        except ValueError:
            pass
    raise ValueError(f'{label} deve ser uma data válida no formato YYYY-MM-DD.')


def _datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        value = value.strip()
        if 'T' in value or ' ' in value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                pass
    raise ValueError('Data e hora do contato inválidas.')


def _event_id(value):
    value = _text(value, 'ID do evento')
    try:
        return str(UUID(value))
    except ValueError:
        raise ValueError('ID do evento deve ser um UUID válido.') from None


def _contact_payload(*, actor, channel, outcome, note, next_action, return_date, closed):
    actor = _text(actor, 'Usuário')
    channel = _text(channel, 'Canal')
    outcome = _text(outcome, 'Resultado')
    if channel not in CHANNELS:
        raise ValueError('Selecione um canal válido.')
    if outcome not in OUTCOMES:
        raise ValueError('Selecione um resultado válido.')
    if type(closed) is not bool:
        raise ValueError('Encerramento deve ser verdadeiro ou falso.')
    note = _text(note, 'Observação', maximum=2000, required=False)
    if closed:
        next_action, return_date = '', None
    else:
        next_action = _text(next_action, 'Próxima ação', maximum=300)
        return_date = _date(return_date, 'Data de retorno').isoformat()
    return {'user': actor, 'canal': channel, 'resultado': outcome, 'observacao': note,
            'proxima_acao': next_action, 'retorno_em': return_date, 'encerrado': closed}


def validate_state(state):
    """Valida o estado completo sem modificá-lo; retorna None ou lança ValueError.

    Estado inicial: {'schema_version': 1, 'clientes': {}}. Um cliente só passa
    a existir após seu primeiro evento. Versão corresponde ao total de eventos;
    o resumo atual deve refletir exatamente o último evento do histórico.
    Datas de retorno históricas podem estar vencidas hoje, mas não podem
    anteceder a data em que o respectivo contato foi registrado.
    """
    if not isinstance(state, dict) or set(state) != {'schema_version', 'clientes'}:
        raise ValueError('Estrutura da agenda inválida.')
    if type(state['schema_version']) is not int or state['schema_version'] != 1:
        raise ValueError('Versão do formato da agenda não suportada.')
    if not isinstance(state['clientes'], dict):
        raise ValueError('Cadastro de clientes da agenda inválido.')

    event_ids = set()
    for cid, record in state['clientes'].items():
        if not isinstance(cid, str) or not cid.strip() or cid != cid.strip():
            raise ValueError('Código de cliente da agenda inválido.')
        if not isinstance(record, dict) or set(record) != _CLIENT_FIELDS:
            raise ValueError('Estrutura do acompanhamento de cliente inválida.')
        history = record['historico']
        if (not isinstance(history, list) or not history
                or type(record['version']) is not int or record['version'] != len(history)):
            raise ValueError('Versão e histórico do cliente são inconsistentes.')
        if type(record['encerrado']) is not bool:
            raise ValueError('Estado de encerramento do cliente inválido.')
        for event in history:
            if not isinstance(event, dict) or set(event) != _EVENT_FIELDS:
                raise ValueError('Estrutura de evento da agenda inválida.')
            eid = _event_id(event['id'])
            if event['id'] != eid or eid in event_ids:
                raise ValueError('ID de evento inválido ou repetido na agenda.')
            event_ids.add(eid)
            if not isinstance(event['em'], str):
                raise ValueError('Data e hora do histórico devem estar em texto ISO.')
            registered_at = _datetime(event['em'])
            payload = _contact_payload(
                actor=event['user'], channel=event['canal'], outcome=event['resultado'],
                note=event['observacao'], next_action=event['proxima_acao'],
                return_date=event['retorno_em'], closed=event['encerrado'])
            if any(event[key] != value for key, value in payload.items()):
                raise ValueError('Campos do histórico da agenda são inconsistentes.')
            if (payload['retorno_em'] is not None
                    and _date(payload['retorno_em'], 'Data de retorno') < registered_at.date()):
                raise ValueError('Retorno histórico anterior ao registro do contato.')
        if any(record[field] != history[-1][field] for field in _SNAPSHOT_FIELDS):
            raise ValueError('Resumo do cliente diverge do último evento da agenda.')


def register_contact(state, *, client_id, actor, channel, outcome, note,
                     next_action, return_date, closed, expected_version, event_id, now):
    """Acrescenta um contato em cópia do estado, com concorrência por cliente.

    expected_version=0 cria o primeiro acompanhamento. Em caso de conflito,
    o chamador deve recarregar o cliente e solicitar revisão do registro.
    Repetir o mesmo event_id e conteúdo é idempotente, inclusive após outra
    atualização ou mudança de dia: preserva a data/hora original e o estado
    mais recente. O mesmo ID com outro conteúdo ou cliente gera ConflictError.

    now pode ser datetime ou ISO com hora; sua data local é a referência para
    validar retorno hoje/futuro. O chamador define o fuso correto.
    """
    validate_state(state)
    client_id = _text(client_id, 'Código do cliente')
    if type(expected_version) is not int or expected_version < 0:
        raise ValueError('Versão esperada do cliente inválida.')
    event_id = _event_id(event_id)
    registered_at = _datetime(now)
    payload = _contact_payload(actor=actor, channel=channel, outcome=outcome, note=note,
                               next_action=next_action, return_date=return_date, closed=closed)

    # Antes de testar versão ou prazo: o evento pode ter sido salvo num retry
    # anterior, inclusive em outro dia. Nunca o reinsere nem desfaz um posterior.
    for cid, record in state['clientes'].items():
        for existing in record['historico']:
            if existing['id'] == event_id:
                if cid == client_id and all(existing[key] == value for key, value in payload.items()):
                    return deepcopy(state)
                raise ConflictError('Esse ID de contato já foi usado em outro registro.')

    previous = state['clientes'].get(client_id)
    version = previous['version'] if previous else 0
    if expected_version != version:
        raise ConflictError('Este cliente foi atualizado. Recarregue e revise o contato antes de salvar.')
    if payload['retorno_em'] is not None and _date(payload['retorno_em'], 'Data de retorno') < registered_at.date():
        raise ValueError('A data de retorno deve ser hoje ou uma data futura.')

    new_state = deepcopy(state)
    history = new_state['clientes'].get(client_id, {}).get('historico', [])
    history.append({'id': event_id, 'em': registered_at.isoformat(timespec='seconds'), **payload})
    new_state['clientes'][client_id] = {
        'version': version + 1, 'retorno_em': payload['retorno_em'],
        'proxima_acao': payload['proxima_acao'], 'encerrado': payload['encerrado'],
        'historico': history,
    }
    return new_state


def build_agenda(clients, state, today):
    """Cria itens apenas para os clientes autorizados/ativos passados pelo caller.

    clients é lista de dicts com id, name, vendor, risk, months_since e
    valor_anual. O módulo não consulta nem amplia essa população. Um retorno
    programado substitui a sugestão automática de risco, mesmo quando futuro.
    Acompanhamentos encerrados só voltam por novo registro manual.

    Itens têm cid, name, vendor, risk, reason, suggested_action, due_date
    (ISO ou None), category e valor_anual. Categorias na ordem: Atrasados,
    Hoje, Recuperação, Atenção, Programados.
    """
    validate_state(state)
    today = _date(today, 'Data de referência')
    if not isinstance(clients, list):
        raise ValueError('Clientes da agenda devem ser uma lista de registros.')
    items, seen = [], set()
    for client in clients:
        if not isinstance(client, dict):
            raise ValueError('Cliente da agenda inválido.')
        cid = _text(client.get('id'), 'Código do cliente')
        if cid in seen:
            raise ValueError('Código de cliente repetido na carteira fornecida.')
        seen.add(cid)
        name = _text(client.get('name'), 'Nome do cliente')
        vendor = _text(client.get('vendor', ''), 'Vendedor', required=False)
        risk = _text(client.get('risk', ''), 'Risco', required=False)
        try:
            value = float(client.get('valor_anual', 0))
        except (TypeError, ValueError, OverflowError):
            raise ValueError('Valor anual do cliente inválido.') from None
        if not math.isfinite(value) or value < 0:
            raise ValueError('Valor anual do cliente inválido.')

        record = state['clientes'].get(cid)
        due_date = None
        if record:
            if record['encerrado']:
                continue
            due = _date(record['retorno_em'], 'Data de retorno')
            due_date = due.isoformat()
            suggested_action = record['proxima_acao']
            if due < today:
                category = 'Atrasados'
                days = (today - due).days
                reason = f'Retorno vencido há {days} dia(s).'
            elif due == today:
                category, reason = 'Hoje', 'Retorno combinado para hoje.'
            else:
                category = 'Programados'
                reason = f'Retorno programado para {due:%d/%m/%Y}.'
        elif risk in ('Recuperação', 'Atenção'):
            category = risk
            months_since = client.get('months_since')
            if isinstance(months_since, (int, float)) and math.isfinite(months_since) and months_since >= 0:
                reason = ('Sem compra registrada.' if months_since >= 999
                          else f'Sem comprar há {int(months_since)} meses.')
            else:
                reason = f'Cliente classificado em {risk.lower()}.'
            suggested_action = ('Retomar contato para entender a ausência de compras.'
                                if risk == 'Recuperação' else
                                'Entrar em contato antes de avançar para recuperação.')
        else:
            continue
        items.append({'cid': cid, 'name': name, 'vendor': vendor, 'risk': risk,
                      'reason': reason, 'suggested_action': suggested_action,
                      'due_date': due_date, 'category': category, 'valor_anual': value})

    category_order = {'Atrasados': 0, 'Hoje': 1, 'Recuperação': 2, 'Atenção': 3, 'Programados': 4}
    risk_order = {'Recuperação': 0, 'Atenção': 1, 'Saudável': 2}

    def sort_key(item):
        category = item['category']
        common = (category_order[category],)
        stable = (item['name'].casefold(), item['cid'])
        if category == 'Atrasados':
            return common + (item['due_date'], -item['valor_anual']) + stable
        if category == 'Programados':
            return common + (item['due_date'],) + stable
        return common + (risk_order.get(item['risk'], 3), -item['valor_anual']) + stable

    return sorted(items, key=sort_key)
