# -*- coding: utf-8 -*-
"""Regras da agenda comercial com dados sintéticos, sem estado real ou rede."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import unittest
from uuid import UUID

from agenda_comercial import (
    CHANNELS, OUTCOMES, ConflictError, build_agenda, register_contact, validate_state,
)


TODAY = date(2026, 9, 4)
NOW = datetime(2026, 9, 4, 10, 30)


def event_id(number):
    return str(UUID(int=number))


def empty_state():
    return {'schema_version': 1, 'clientes': {}}


def register(state, cid='1', number=1, **updates):
    args = {
        'client_id': cid, 'actor': 'vendedor_teste', 'channel': 'Ligação',
        'outcome': 'Retorno combinado', 'note': 'Contato de teste.',
        'next_action': 'Apresentar a proposta solicitada.', 'return_date': '2026-09-05',
        'closed': False, 'expected_version': state['clientes'].get(cid, {}).get('version', 0),
        'event_id': event_id(number), 'now': NOW,
    }
    args.update(updates)
    return register_contact(state, **args)


def client(cid, risk='Recuperação', value=1000, name=None):
    return {'id': str(cid), 'name': name or f'Cliente teste {cid}', 'vendor': 'Carteira teste',
            'risk': risk, 'months_since': 6 if risk == 'Recuperação' else 3,
            'valor_anual': value}


class RegisterTests(unittest.TestCase):
    def test_state_created_only_after_first_contact_with_trimmed_fields(self):
        source = empty_state()
        result = register(source, client_id=' 1 ', actor=' vendedor_teste ', note=' Teste ',
                          next_action=' Telefonar ', channel=' Ligação ', outcome=' Retorno combinado ')
        self.assertEqual(source, empty_state())
        self.assertIsNone(validate_state(result))
        record = result['clientes']['1']
        self.assertEqual(record['version'], 1)
        self.assertEqual(record['proxima_acao'], 'Telefonar')
        self.assertEqual(record['historico'][0]['observacao'], 'Teste')
        self.assertEqual(record['historico'][0]['em'], '2026-09-04T10:30:00')
        self.assertEqual(record['historico'][0]['user'], 'vendedor_teste')

    def test_contact_appends_history_without_mutating_input(self):
        initial = register(empty_state())
        saved = deepcopy(initial)
        updated = register(initial, number=2, outcome='Proposta enviada', next_action='Confirmar recebimento')
        self.assertEqual(initial, saved)
        self.assertEqual(updated['clientes']['1']['version'], 2)
        self.assertEqual(updated['clientes']['1']['historico'][0], saved['clientes']['1']['historico'][0])
        self.assertEqual(updated['clientes']['1']['historico'][1]['resultado'], 'Proposta enviada')
        self.assertIsNone(validate_state(updated))

    def test_conflict_on_same_client_does_not_overwrite(self):
        state = register(empty_state())
        original = deepcopy(state)
        with self.assertRaises(ConflictError):
            register(state, number=2, expected_version=0, note='Outra sessão')
        self.assertEqual(state, original)

    def test_update_of_another_client_does_not_conflict_or_lose_other_client(self):
        state = register(empty_state())
        other_updated = register(state, cid='2', number=2, expected_version=0)
        combined = register(other_updated, number=3, expected_version=1)
        self.assertEqual(combined['clientes']['1']['version'], 2)
        self.assertEqual(combined['clientes']['2'], other_updated['clientes']['2'])
        self.assertEqual(state['clientes']['1']['version'], 1)
        self.assertNotIn('2', state['clientes'])

    def test_identical_retry_is_idempotent_with_stale_version_and_new_time(self):
        state = register(empty_state(), return_date=TODAY)
        retried = register(state, return_date=TODAY, expected_version=0, now=NOW + timedelta(days=1))
        self.assertEqual(retried, state)
        self.assertIsNot(retried, state)
        self.assertIsNot(retried['clientes']['1']['historico'], state['clientes']['1']['historico'])

    def test_retry_of_old_event_never_undoes_later_contact(self):
        first = register(empty_state())
        latest = register(first, number=2, closed=True, outcome='Sem interesse')
        retried = register(latest, expected_version=0, now=NOW + timedelta(days=10))
        self.assertEqual(retried, latest)
        self.assertTrue(retried['clientes']['1']['encerrado'])

    def test_event_id_cannot_be_reused_for_different_content_or_client(self):
        state = register(empty_state())
        for changes in ({'note': 'Alterada'}, {'actor': 'outro_usuario'}, {'cid': '2'}):
            with self.subTest(changes=changes), self.assertRaises(ConflictError):
                register(state, **changes)

    def test_active_contact_requires_followup_action_and_date(self):
        for changes in ({'next_action': ''}, {'next_action': '   '},
                        {'return_date': None}, {'return_date': ''}, {'return_date': '2026-02-30'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                register(empty_state(), **changes)

    def test_new_followup_cannot_be_in_past_but_today_and_date_objects_work(self):
        with self.assertRaises(ValueError):
            register(empty_state(), return_date=TODAY - timedelta(days=1))
        state = register(empty_state(), return_date=TODAY)
        self.assertEqual(state['clientes']['1']['retorno_em'], '2026-09-04')

    def test_timezone_uses_local_date_supplied_by_caller(self):
        local_time = datetime(2026, 9, 4, 23, 30, tzinfo=timezone(timedelta(hours=-3)))
        state = register(empty_state(), return_date=TODAY, now=local_time)
        self.assertEqual(state['clientes']['1']['historico'][0]['em'], '2026-09-04T23:30:00-03:00')
        self.assertIsNone(validate_state(state))

    def test_close_clears_followup_and_does_not_change_other_client(self):
        state = register(register(empty_state()), cid='2', number=2)
        closed = register(state, number=3, closed=True, outcome='Sem interesse',
                          next_action='Campo antigo', return_date='2020-01-01')
        record = closed['clientes']['1']
        self.assertTrue(record['encerrado'])
        self.assertEqual(record['proxima_acao'], '')
        self.assertIsNone(record['retorno_em'])
        self.assertEqual(closed['clientes']['2'], state['clientes']['2'])
        self.assertEqual(set(record), {'version', 'retorno_em', 'proxima_acao', 'encerrado', 'historico'})
        self.assertIsNone(validate_state(closed))

    def test_manual_new_contact_reopens_closed_followup(self):
        closed = register(empty_state(), closed=True)
        reopened = register(closed, number=2, return_date=TODAY)
        items = build_agenda([client(1)], reopened, TODAY)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['category'], 'Hoje')
        self.assertFalse(reopened['clientes']['1']['encerrado'])

    def test_text_limits_and_enums_validate_before_writing(self):
        for changes in ({'note': 'x' * 2001}, {'next_action': 'x' * 301},
                        {'channel': 'SMS'}, {'outcome': 'Pedido confirmado'},
                        {'event_id': 'qualquer'}, {'actor': ''}, {'client_id': ''},
                        {'closed': 'false'}, {'expected_version': True}, {'expected_version': -1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                register(empty_state(), **changes)
        self.assertIn('Pedido informado', OUTCOMES)
        self.assertIn('WhatsApp', CHANNELS)
        self.assertIsNone(validate_state(register(empty_state(), note='x' * 2000, next_action='x' * 300)))


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.state = register(empty_state())

    def assert_invalid(self, state):
        with self.assertRaises(ValueError):
            validate_state(state)

    def test_bad_top_level_schema_is_rejected(self):
        for state in (None, [], {}, {'schema_version': True, 'clientes': {}},
                      {'schema_version': 2, 'clientes': {}}, {'schema_version': 1, 'clientes': []},
                      {'schema_version': 1, 'clientes': {}, 'extra': 1}):
            with self.subTest(state=state):
                self.assert_invalid(state)

    def test_corrupted_history_version_or_snapshot_is_rejected(self):
        mutations = [
            lambda r: r.update(version=2),
            lambda r: r.update(version=True),
            lambda r: r.update(historico=[]),
            lambda r: r.update(historico=None),
            lambda r: r.update(retorno_em='2026-09-06'),
            lambda r: r.update(proxima_acao='Outro resumo'),
            lambda r: r.update(encerrado=True),
            lambda r: r['historico'][0].update(canal='Não existe'),
            lambda r: r['historico'][0].update(em='sem data'),
            lambda r: r['historico'][0].update(user=''),
        ]
        for change in mutations:
            with self.subTest(change=change):
                state = deepcopy(self.state)
                change(state['clientes']['1'])
                self.assert_invalid(state)

    def test_active_history_without_followup_is_corrupt_even_if_snapshot_matches(self):
        for field, value in (('retorno_em', None), ('proxima_acao', '')):
            state = deepcopy(self.state)
            state['clientes']['1'][field] = value
            state['clientes']['1']['historico'][0][field] = value
            self.assert_invalid(state)

    def test_duplicate_ids_across_clients_or_in_one_history_are_rejected(self):
        state = deepcopy(self.state)
        state['clientes']['2'] = deepcopy(state['clientes']['1'])
        self.assert_invalid(state)
        state = deepcopy(self.state)
        record = state['clientes']['1']
        record['historico'].append(deepcopy(record['historico'][0]))
        record['version'] = 2
        self.assert_invalid(state)

    def test_historical_overdue_is_valid_but_before_contact_is_corrupt(self):
        self.assertIsNone(validate_state(self.state))
        state = deepcopy(self.state)
        record = state['clientes']['1']
        record['retorno_em'] = record['historico'][0]['retorno_em'] = '2026-09-03'
        self.assert_invalid(state)

    def test_register_rejects_corrupt_existing_state_without_silent_reset(self):
        corrupt = deepcopy(self.state)
        corrupt['clientes']['1']['version'] = 10
        original = deepcopy(corrupt)
        with self.assertRaises(ValueError):
            register(corrupt, cid='2', number=2)
        self.assertEqual(corrupt, original)


class BuildAgendaTests(unittest.TestCase):
    def test_unregistered_risks_only_with_urgency_and_value_sort(self):
        clients = [client(1, 'Atenção', 90000), client(2, 'Saudável', 999999),
                   client(3, 'Recuperação', 1000), client(4, 'Recuperação', 2000)]
        items = build_agenda(clients, empty_state(), TODAY)
        self.assertEqual([item['cid'] for item in items], ['4', '3', '1'])
        self.assertEqual([item['category'] for item in items], ['Recuperação', 'Recuperação', 'Atenção'])
        self.assertTrue(all(item['due_date'] is None for item in items))

    def test_future_return_stays_visible_and_suppresses_duplicate_risk(self):
        state = register(empty_state())
        items = build_agenda([client(1)], state, TODAY)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['category'], 'Programados')
        self.assertEqual(items[0]['due_date'], '2026-09-05')
        self.assertEqual(items[0]['suggested_action'], 'Apresentar a proposta solicitada.')

    def test_closed_never_resurrects_from_risk_or_age(self):
        state = register(empty_state(), closed=True)
        for day in (TODAY, TODAY + timedelta(days=400)):
            self.assertEqual(build_agenda([client(1)], state, day), [])

    def test_due_dates_turn_from_scheduled_to_today_to_overdue_without_mutation(self):
        state = register(empty_state())
        original = deepcopy(state)
        cats = [build_agenda([client(1)], state, day)[0]['category']
                for day in (TODAY, TODAY + timedelta(days=1), TODAY + timedelta(days=2))]
        self.assertEqual(cats, ['Programados', 'Hoje', 'Atrasados'])
        self.assertEqual(state, original)

    def test_order_is_overdue_date_then_value_today_risks_future(self):
        state = empty_state()
        for cid, due in (('1', '2026-09-02'), ('2', '2026-09-01'), ('3', '2026-09-02'),
                         ('4', '2026-09-04'), ('5', '2026-09-06'), ('8', '2026-09-05')):
            state = register(state, cid=cid, number=int(cid), return_date=due,
                             now=datetime(2026, 9, 1, 9))
        clients = [client(1, value=100), client(2, value=10), client(3, value=500),
                   client(4, 'Saudável', 1), client(5), client(6, 'Recuperação', 90000),
                   client(7, 'Atenção', 999999), client(8)]
        items = build_agenda(clients, state, TODAY)
        self.assertEqual([item['cid'] for item in items], ['2', '3', '1', '4', '6', '7', '8', '5'])

    def test_stable_ties_do_not_depend_on_input_order(self):
        clients = [client(2, name='Cliente A'), client(1, name='Cliente A'), client(3, name='Cliente B')]
        expected = build_agenda(clients, empty_state(), TODAY)
        self.assertEqual([item['cid'] for item in expected], ['1', '2', '3'])
        self.assertEqual(build_agenda(list(reversed(clients)), empty_state(), TODAY), expected)

    def test_state_does_not_expand_authorized_client_population(self):
        state = register(register(empty_state()), cid='2', number=2, return_date=TODAY)
        items = build_agenda([client(1)], state, TODAY)
        self.assertEqual([item['cid'] for item in items], ['1'])
        self.assertEqual(build_agenda([], state, TODAY), [])

    def test_duplicate_client_and_invalid_value_are_explicit_errors(self):
        for clients in ([client(1), client(1)], [client(1, value=float('nan'))],
                        [client(1, value=-1)], [client(1, value=float('inf'))]):
            with self.subTest(clients=clients), self.assertRaises(ValueError):
                build_agenda(clients, empty_state(), TODAY)

    def test_build_never_mutates_client_records_and_outputs_documented_fields(self):
        clients = [client(1)]
        before = deepcopy(clients)
        item = build_agenda(clients, empty_state(), TODAY)[0]
        self.assertEqual(clients, before)
        self.assertEqual(set(item), {'cid', 'name', 'vendor', 'risk', 'reason',
                                    'suggested_action', 'due_date', 'category', 'valor_anual'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
