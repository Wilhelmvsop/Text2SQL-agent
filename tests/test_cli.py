import json
import os
import subprocess
import sys
from pathlib import Path

from tests.helpers import DatabaseTest


class CLITests(DatabaseTest):
    def test_demo_and_json_trace(self):
        trace = Path(self.temp.name) / 'trace.jsonl'
        env = {k: v for k, v in os.environ.items() if not k.startswith('TEXT2SQL_')}
        env['TEXT2SQL_TRACE'] = str(trace)
        process = subprocess.run([sys.executable, '-m', 'text2sql.cli', '--demo', '--json', '--db', str(self.path)],
                                 capture_output=True, text=True, env=env)
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        result = json.loads(process.stdout)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(result['execution_result']['rows']), 5)
        recorded = json.loads(trace.read_text())
        self.assertEqual(recorded['trace_id'], result['trace_id'])
        self.assertEqual(len(recorded['validation_attempts']), 2)
        self.assertNotIn('api_key', trace.read_text())

    def test_fake_rejects_arbitrary_question(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('TEXT2SQL_')}
        process = subprocess.run([sys.executable, '-m', 'text2sql.cli', '--llm', 'fake', '--db', str(self.path),
                                  '-q', 'Invent an answer'], capture_output=True, text=True, env=env)
        self.assertEqual(process.returncode, 2)
