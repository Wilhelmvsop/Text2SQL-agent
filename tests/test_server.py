import json
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:  # the web extra is optional
    TestClient = None

from text2sql.config import Config
from text2sql.db.seed import seed_database
from text2sql.errors import ProviderError
from text2sql.factory import DEMO_QUESTION, DEMO_SQL, build_agent
from text2sql.generation.llm import FakeLLMProvider


class UnreachableProvider:
    name = 'unreachable'

    def complete(self, messages):
        raise ProviderError('Provider HTTP 401')


@unittest.skipIf(TestClient is None, 'install the [web] extra to test the server')
class ServerTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        seed_database(self.dir / 'shop.db')
        self.model_reachable = True
        self.config = Config(db_path=self.dir / 'shop.db', history_path=self.dir / 'app.db',
                             trace=self.dir / 'trace.jsonl', model='test-model', base_url='http://model.test/v1')
        self.client = self.start(self.config)

    def start(self, config):
        """Run the app with a scripted model: a wrong first query, then the corrected one."""
        from text2sql.server.app import create_app
        agent_factory = lambda c: build_agent(c, provider=FakeLLMProvider(['SELECT nonexistent FROM customers', DEMO_SQL] * 5))
        provider_factory = lambda c: FakeLLMProvider(['OK']) if self.model_reachable else UnreachableProvider()
        client = TestClient(create_app(config, agent_factory, provider_factory))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def test_health_reports_connected_model(self):
        body = self.client.get('/api/health').json()
        self.assertTrue(body['ready'])
        self.assertTrue(body['model_connected'])
        self.assertEqual(body['model'], 'test-model')

    def test_app_is_locked_until_a_model_is_connected(self):
        from dataclasses import replace
        client = self.start(replace(self.config, model='', history_path=self.dir / 'other.db'))
        body = client.get('/api/health').json()
        self.assertFalse(body['ready'])
        self.assertFalse(body['model_connected'])
        self.assertTrue(body['database_exists'])
        for method, path, payload in [('post', '/api/queries', {'question': 'How many customers?'}),
                                      ('post', '/api/sql/validate', {'sql': 'SELECT 1'}),
                                      ('post', '/api/sql/execute', {'sql': 'SELECT 1'}),
                                      ('get', '/api/schema', None)]:
            response = getattr(client, method)(path, **({'json': payload} if payload else {}))
            self.assertEqual(response.status_code, 503, path)
            self.assertIn('No model is connected', response.json()['detail'])
        saved = client.put('/api/settings', json={'model': 'gpt-test', 'base_url': 'https://api.test/v1'})
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(client.get('/api/health').json()['ready'])

    def test_demo_question_runs_corrects_and_is_saved(self):
        record = self.client.post('/api/queries', json={'question': DEMO_QUESTION}).json()
        self.assertEqual(record['status'], 'success')
        self.assertEqual(len(record['trace']['validation_attempts']), 2)
        self.assertEqual(len(record['result']['rows']), 5)
        saved = self.client.get(f"/api/history/{record['id']}").json()
        self.assertEqual(saved['final_sql'], record['final_sql'])
        self.assertEqual(self.client.get('/api/history').json()['total'], 1)

    def test_stream_emits_stages_then_done(self):
        with self.client.stream('POST', '/api/queries/stream', json={'question': DEMO_QUESTION}) as response:
            events = [line[7:] for line in response.iter_lines() if line.startswith('event: ')]
        self.assertEqual(events, ['schema_retrieval', 'fewshot_retrieval', 'attempt', 'attempt',
                                  'execution', 'done'])

    def test_validate_classifies_errors(self):
        ok = self.client.post('/api/sql/validate', json={'sql': DEMO_SQL}).json()
        self.assertTrue(ok['valid'])
        bad = self.client.post('/api/sql/validate', json={'sql': 'SELECT nme FROM customers'}).json()
        self.assertEqual(bad['error_type'], 'unknown_column')
        unsafe = self.client.post('/api/sql/validate', json={'sql': 'DROP TABLE customers'}).json()
        self.assertFalse(unsafe['valid'])
        self.assertFalse(unsafe['retryable'])

    def test_execute_refuses_writes_and_links_to_parent(self):
        parent = self.client.post('/api/queries', json={'question': DEMO_QUESTION}).json()
        for sql in ['DELETE FROM customers', 'UPDATE customers SET name = 1',
                    'SELECT 1; DROP TABLE customers']:
            record = self.client.post('/api/sql/execute', json={'sql': sql}).json()
            self.assertEqual(record['status'], 'validation_failed', sql)
        record = self.client.post('/api/sql/execute', json={
            'sql': 'SELECT COUNT(*) AS n FROM customers', 'parent_id': parent['id']}).json()
        self.assertEqual(record['result']['rows'], [[60]])
        self.assertEqual(record['parent_id'], parent['id'])

    def test_history_filters_star_and_delete(self):
        self.client.post('/api/sql/execute', json={'sql': 'SELECT COUNT(*) FROM orders', 'question': 'orders'})
        failed = self.client.post('/api/sql/execute', json={'sql': 'SELECT nope FROM orders'}).json()
        self.assertEqual(self.client.get('/api/history?status=failed').json()['total'], 1)
        self.assertEqual(self.client.get('/api/history?search=orders').json()['total'], 2)
        self.client.patch(f"/api/history/{failed['id']}", json={'starred': True})
        starred = self.client.get('/api/history?starred=true').json()['items']
        self.assertEqual([i['id'] for i in starred], [failed['id']])
        self.assertEqual(self.client.delete(f"/api/history/{failed['id']}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/history/{failed['id']}").status_code, 404)

    def test_settings_hide_secrets_and_persist(self):
        response = self.client.put('/api/settings', json={'top_k': 2, 'api_key': 'sk-secret'})
        self.assertEqual(response.status_code, 200)
        body = self.client.get('/api/settings').json()
        self.assertEqual(body['top_k'], 2)
        self.assertTrue(body['api_key_set'])
        self.assertNotIn('sk-secret', json.dumps(body))
        from text2sql.server.app import create_app
        with TestClient(create_app(self.config)) as restarted:
            body = restarted.get('/api/settings').json()
        self.assertEqual((body['top_k'], body['api_key_set']), (2, True))

    def test_unreachable_model_is_not_saved(self):
        self.model_reachable = False
        test = self.client.post('/api/settings/test', json={'model': 'other-model'}).json()
        self.assertEqual(test, {'ok': False, 'message': 'Provider HTTP 401'})
        response = self.client.put('/api/settings', json={'model': 'other-model', 'top_k': 2})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Could not connect to the model', response.json()['detail'])
        self.assertEqual(self.client.get('/api/settings').json()['model'], 'test-model')
        self.assertTrue(self.client.get('/api/health').json()['ready'])

    def test_unchanged_model_settings_are_not_rechecked(self):
        self.model_reachable = False
        self.assertEqual(self.client.put('/api/settings', json={'top_k': 2}).status_code, 200)

    def test_app_store_cannot_be_used_as_the_query_database(self):
        response = self.client.put('/api/settings', json={'db_path': str(self.config.history_path)})
        self.assertEqual(response.status_code, 400)
        self.assertIn("app's own history and settings file", response.json()['detail'])
        self.assertEqual(self.client.get('/api/health').json()['db_path'], str(self.config.db_path))

    def upload(self, data: bytes, filename: str = 'shop.db'):
        return self.client.post('/api/database/upload', params={'filename': filename}, content=data,
                                headers={'Content-Type': 'application/octet-stream'})

    def make_database(self, name: str, wal: bool = False) -> bytes:
        import sqlite3
        path = self.dir / name
        conn = sqlite3.connect(path)
        if wal:
            conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE books (book_id INTEGER PRIMARY KEY, title TEXT, year INTEGER)')
        conn.executemany('INSERT INTO books VALUES (?, ?, ?)', [(1, 'Dune', 1965), (2, 'Emma', 1815)])
        conn.commit()
        conn.close()  # checkpoints a WAL file; its header still says WAL mode
        return path.read_bytes()

    def test_uploaded_database_is_connected_and_queryable(self):
        response = self.upload(self.make_database('books.db'), 'My Books.sqlite')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['tables'], 1)
        uploaded = Path(body['db_path'])
        self.assertEqual(uploaded.parent, self.dir / 'uploads')
        self.assertTrue(uploaded.name.startswith('My_Books-'))
        self.assertEqual(self.client.get('/api/health').json()['db_path'], str(uploaded))
        self.assertEqual([t['name'] for t in self.client.get('/api/schema').json()['tables']], ['books'])
        record = self.client.post('/api/sql/execute', json={'sql': 'SELECT title FROM books ORDER BY year'}).json()
        self.assertEqual(record['result']['rows'], [['Emma'], ['Dune']])
        self.assertEqual(self.client.get('/api/settings').json()['db_path'], str(uploaded))

    def test_wal_mode_upload_still_opens_read_only(self):
        data = self.make_database('wal.db', wal=True)
        self.assertEqual(data[18:20], b'\x02\x02')  # file format: WAL
        response = self.upload(data)
        self.assertEqual(response.status_code, 200, response.text)
        record = self.client.post('/api/sql/execute', json={'sql': 'SELECT COUNT(*) AS n FROM books'}).json()
        self.assertEqual(record['result']['rows'], [[2]])

    def test_invalid_uploads_are_rejected_and_keep_current_database(self):
        import sqlite3
        empty = self.dir / 'empty.db'
        sqlite3.connect(empty).execute('PRAGMA user_version=1').connection.close()
        for data, message in [(b'name,age\nAna,3\n', 'not a SQLite database'), (b'', 'empty'),
                              (empty.read_bytes(), 'no tables')]:
            response = self.upload(data)
            self.assertEqual(response.status_code, 400, message)
            self.assertIn(message, response.json()['detail'])
        self.assertEqual(self.client.get('/api/health').json()['db_path'], str(self.config.db_path))
        self.assertEqual(list((self.dir / 'uploads').iterdir()), [])

    def test_upload_filename_cannot_escape_the_uploads_folder(self):
        body = self.upload(self.make_database('x.db'), '../../etc/passwd').json()
        self.assertEqual(Path(body['db_path']).parent, self.dir / 'uploads')

    def test_oversized_upload_is_refused(self):
        from unittest import mock
        with mock.patch('text2sql.server.uploads.UPLOAD_LIMIT', 1024):
            response = self.upload(self.make_database('big.db'))
        self.assertEqual(response.status_code, 413)

    def test_demo_database_can_be_created_from_settings(self):
        target = self.dir / 'new' / 'demo.db'
        self.assertEqual(self.client.put('/api/settings', json={'db_path': str(target)}).status_code, 200)
        self.assertFalse(self.client.get('/api/health').json()['ready'])
        self.assertEqual(self.client.post('/api/sql/validate', json={'sql': 'SELECT 1'}).status_code, 503)
        self.assertEqual(self.client.post('/api/database/demo').status_code, 200)
        self.assertTrue(self.client.get('/api/health').json()['ready'])
        self.assertEqual(self.client.post('/api/database/demo').status_code, 409)


if __name__ == '__main__':
    unittest.main()
