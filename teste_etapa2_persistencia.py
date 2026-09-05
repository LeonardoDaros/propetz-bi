"""Agenda: adaptador real por AST, API falsa e arquivos temporarios sinteticos.

Nao importa app.py, nao consulta secrets/usuarios reais e nao usa rede. Apenas
agenda_comercial (pura) e as funcoes do adaptador sao executadas. Falhas retornam
exit code nao zero para permitir regressao automatizada.
"""
import ast
import base64
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import uuid

import pandas as pd

import agenda_comercial as agenda


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
EMPTY = {'schema_version': 1, 'clientes': {}}
APP_TREE = ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8-sig'))
FUNCTIONS = [copy.deepcopy(node) for node in APP_TREE.body if isinstance(node, ast.FunctionDef)]
for node in FUNCTIONS:
    node.decorator_list = []
FUNCTION_CODE = compile(ast.Module(body=FUNCTIONS, type_ignores=[]), '<app-functions-only>', 'exec')


def event(state, cid='C1', eid=None, actor='seller', expected=0, note='Teste sintetico'):
    return agenda.register_contact(state, client_id=cid, actor=actor, channel='Ligação',
        outcome='Retorno combinado', note=note, next_action='Retornar sobre proposta',
        return_date='2026-09-05', closed=False, expected_version=expected,
        event_id=eid or str(uuid.uuid4()), now=NOW)


class FakeAPI:
    class RequestException(Exception):
        pass

    def __init__(self):
        self.state = copy.deepcopy(EMPTY)
        self.sha = 'synthetic-revision-1'
        self.status = 200
        self.branch_status = 200
        self.puts = []
        self.gets = []
        self.before_put = None
        self.drop_after_commit = False
        self.fail_confirmation = False
        self.raw_mode = False

    def get(self, url, **kwargs):
        self.gets.append(url)
        if '/git/ref/heads/' in url:
            return types.SimpleNamespace(status_code=self.branch_status)
        if self.status == 'timeout':
            raise self.RequestException('synthetic timeout')
        if self.status != 200 or self.state is None:
            return types.SimpleNamespace(status_code=404 if self.state is None else self.status)
        content = json.dumps(self.state).encode('utf-8')
        if kwargs.get('headers', {}).get('Accept') == 'application/vnd.github.raw+json':
            return types.SimpleNamespace(status_code=200, content=content)
        metadata = {'sha': self.sha,
                    'encoding': 'none' if self.raw_mode else 'base64',
                    'content': '' if self.raw_mode else base64.b64encode(content).decode('ascii')}
        return types.SimpleNamespace(status_code=200, json=lambda: metadata)

    def put(self, url, **kwargs):
        payload = kwargs['json']
        self.puts.append(copy.deepcopy(payload))
        if self.before_put:
            callback, self.before_put = self.before_put, None
            status = callback()
            return types.SimpleNamespace(status_code=status)
        if self.state is not None and payload.get('sha') != self.sha:
            return types.SimpleNamespace(status_code=409)
        self.state = json.loads(base64.b64decode(payload['content']).decode('utf-8'))
        self.sha = 'synthetic-revision-' + str(len(self.puts) + 1)
        if self.drop_after_commit:
            self.drop_after_commit = False
            if self.fail_confirmation:
                self.status = 503
            raise self.RequestException('synthetic connection dropped after commit')
        return types.SimpleNamespace(status_code=200)


class AgendaPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='propetz-agenda-synthetic-')
        self.path = Path(self.temp.name) / 'agenda_comercial.json'
        self.api = FakeAPI()
        self.user = {'name': 'Vendedor teste', 'role': 'vendedor', 'vendor_filter': 'Carteira A'}
        self.clients = pd.DataFrame([
            {'id': 'C1', 'name': 'Cliente sintetico A', 'vendor': 'Carteira A', 'status': 'Ativo'},
            {'id': 'C2', 'name': 'Cliente sintetico B', 'vendor': 'Carteira B', 'status': 'Ativo'}])
        self.ns = {'os': os, 'json': json, 'base64': base64, 'uuid': uuid,
                   'datetime': datetime, 'agenda': agenda, 'pd': pd,
                   'yaml': types.SimpleNamespace(YAMLError=type('SyntheticYamlError', (Exception,), {})),
                   'requests': self.api,
                   'st': types.SimpleNamespace(session_state={'authenticated': True, 'username': 'seller',
                       'role': 'vendedor', 'vendor_filter': 'Carteira A'}),
                   'AGENDA_FILE': str(self.path), '_STATE_RAW_CACHE': {},
                   '_GH_WRITE_LOCK': threading.Lock(), '_GH_API': 'https://synthetic.invalid',
                   '_GH_REPO': 'synthetic/repo', '_GH_STATE_BRANCH': 'state',
                   '_SESSION_INATIVIDADE': 10800, '_SESSION_MAX': 43200}
        exec(FUNCTION_CODE, self.ns)
        self.ns.update({'_gh_token': lambda: 'synthetic-only', '_agenda_now': lambda: NOW,
                        'load_users': lambda: {'users': {'seller': copy.deepcopy(self.user)}},
                        'load_data': lambda: (self.clients.copy(),), 'load_inactive_clients': lambda: set()})

    def tearDown(self):
        self.temp.cleanup()

    def save(self, cid='C1', eid=None, expected=0, note='Teste sintetico'):
        return self.ns['save_agenda_contact'](cid, expected_version=expected,
            event_id=eid or str(uuid.uuid4()), channel='Ligação', outcome='Retorno combinado',
            note=note, next_action='Retornar sobre proposta', return_date='2026-09-05', closed=False)

    def local(self, state):
        self.path.write_text(json.dumps(state), encoding='utf-8')

    def test_remote_failure_never_falls_back_or_puts(self):
        self.local(event(EMPTY))
        before = self.path.read_bytes()
        for status in (401, 403, 500, 'timeout'):
            with self.subTest(status=status):
                self.api.status = status
                with self.assertRaises(ValueError): self.ns['load_agenda']()
                with self.assertRaises(ValueError): self.save()
                self.assertFalse(self.api.puts)
                self.assertEqual(self.path.read_bytes(), before)

    def test_remote_failure_without_local_is_not_empty_agenda(self):
        self.api.status = 503
        with self.assertRaises(ValueError): self.ns['load_agenda']()
        with self.assertRaises(ValueError): self.save()
        self.assertFalse(self.api.puts)
        self.assertFalse(self.path.exists())

    def test_remote_malformed_state_never_puts(self):
        self.api.state = {'invalid': 'synthetic'}
        with self.assertRaises(ValueError): self.ns['load_agenda']()
        with self.assertRaises(ValueError): self.save()
        self.assertFalse(self.api.puts)

    def test_404_requires_accessible_branch(self):
        self.api.state = None
        self.api.branch_status = 404
        with self.assertRaises(ValueError): self.ns['load_agenda']()
        with self.assertRaises(ValueError): self.save()
        self.assertFalse(self.api.puts)

    def test_real_404_without_local_creates_first_event(self):
        self.api.state = None
        self.assertEqual(self.ns['load_agenda'](), EMPTY)
        self.assertIn('confirmação no servidor', self.save())
        self.assertNotIn('sha', self.api.puts[0])
        self.assertEqual(self.api.state['clientes']['C1']['version'], 1)

    def test_remote_empty_or_absent_preserves_unpublished_local_history(self):
        self.local(event(EMPTY))
        before = self.path.read_bytes()
        for remote in (None, EMPTY):
            with self.subTest(remote_exists=remote is not None):
                self.api.state = copy.deepcopy(remote)
                with self.assertRaisesRegex(ValueError, 'conciliação'): self.ns['load_agenda']()
                with self.assertRaisesRegex(ValueError, 'conciliação'): self.save()
                self.assertFalse(self.api.puts)
                self.assertEqual(self.path.read_bytes(), before)

    def test_different_nonempty_remote_also_preserves_unpublished_local(self):
        self.local(event(EMPTY))
        self.api.state = event(EMPTY, cid='C2')
        with self.assertRaisesRegex(ValueError, 'conciliação'): self.save()
        self.assertFalse(self.api.puts)

    def test_remote_superset_of_local_history_is_accepted(self):
        state = event(EMPTY)
        self.local(state)
        self.api.state = event(state, cid='C2')
        self.assertEqual(self.ns['load_agenda'](), self.api.state)

    def test_raw_mode_large_history_remains_valid(self):
        self.api.raw_mode = True
        self.api.state = event(EMPTY)
        self.assertEqual(self.ns['load_agenda'](), self.api.state)
        self.assertEqual(len(self.api.gets), 2)

    def test_local_replace_failure_never_announces_success(self):
        self.ns['_gh_token'] = lambda: None
        self.local(event(EMPTY))
        before = self.path.read_bytes()
        with patch.object(os, 'replace', side_effect=PermissionError('synthetic filesystem failure')):
            with self.assertRaises(OSError): self.save(expected=1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(list(self.path.parent.glob('*.tmp')))
        self.assertFalse(self.api.puts)

    def test_local_success_is_explicitly_local_and_idempotent(self):
        self.ns['_gh_token'] = lambda: None
        eid = str(uuid.uuid4())
        self.assertIn('apenas neste servidor', self.save(eid=eid))
        self.assertIn('apenas neste servidor', self.save(eid=eid))
        self.assertEqual(json.loads(self.path.read_text())['clientes']['C1']['version'], 1)
        self.assertFalse(self.api.gets)

    def test_wallet_changed_since_render_cannot_write_old_client(self):
        self.user['vendor_filter'] = 'Carteira B'
        with self.assertRaises(ValueError): self.save('C1')
        self.assertFalse(self.api.puts)
        self.assertFalse(self.api.gets)

    def test_warranty_profile_cannot_write(self):
        for role in ('garantia', 'garantia_master'):
            with self.subTest(role=role):
                self.user['role'] = role
                with self.assertRaises(ValueError): self.save()
                self.assertFalse(self.api.puts)

    def test_expired_session_cannot_write(self):
        self.ns['st'].session_state['_last_seen'] = 1
        with self.assertRaises(ValueError): self.save()
        self.assertFalse(self.api.puts)

    def test_inactive_client_cannot_write(self):
        self.ns['load_inactive_clients'] = lambda: {'C1'}
        with self.assertRaises(ValueError): self.save()
        self.assertFalse(self.api.puts)

    def test_wallet_is_revalidated_after_conflict(self):
        def concurrent_change():
            self.user['vendor_filter'] = 'Carteira B'
            return 409
        self.api.before_put = concurrent_change
        with self.assertRaises(ValueError): self.save()
        self.assertEqual(len(self.api.puts), 1)
        self.assertEqual(self.api.state, EMPTY)

    def test_409_preserves_other_clients_and_retries_current_event(self):
        def concurrent_change():
            self.api.state = event(EMPTY, cid='C2')
            self.api.sha = 'synthetic-concurrent-revision'
            return 409
        self.api.before_put = concurrent_change
        self.save()
        self.assertEqual(set(self.api.state['clientes']), {'C1', 'C2'})
        self.assertEqual(len(self.api.puts), 2)

    def test_client_version_conflict_never_overwrites(self):
        self.api.state = event(EMPTY)
        before = copy.deepcopy(self.api.state)
        with self.assertRaises(agenda.ConflictError): self.save(expected=0)
        self.assertEqual(self.api.state, before)
        self.assertFalse(self.api.puts)

    def test_uncertain_write_is_confirmed_without_duplicate(self):
        self.api.drop_after_commit = True
        eid = str(uuid.uuid4())
        self.assertIn('confirmação no servidor', self.save(eid=eid))
        self.save(eid=eid)
        self.assertEqual(self.api.state['clientes']['C1']['version'], 1)
        self.assertEqual(len(self.api.puts), 1)

    def test_uncertain_write_and_failed_read_retry_same_event(self):
        self.api.drop_after_commit = True
        self.api.fail_confirmation = True
        eid = str(uuid.uuid4())
        with self.assertRaises(ValueError): self.save(eid=eid)
        self.api.status = 200
        self.assertIn('confirmação no servidor', self.save(eid=eid))
        self.assertEqual(self.api.state['clientes']['C1']['version'], 1)
        self.assertEqual(len(self.api.puts), 1)

    def test_reused_event_with_different_payload_is_rejected(self):
        eid = str(uuid.uuid4())
        self.save(eid=eid)
        with self.assertRaises(agenda.ConflictError): self.save(eid=eid, note='Changed synthetic content')
        self.assertEqual(len(self.api.puts), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
