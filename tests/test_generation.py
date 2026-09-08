import json

from tests.helpers import DatabaseTest
from text2sql.generation.llm import FakeLLMProvider
from text2sql.generation.sql_generator import SQLGenerator


class GenerationTests(DatabaseTest):
    def test_grounded_prompt_and_correction(self):
        provider = FakeLLMProvider(['SELECT 1', 'SELECT 2'])
        generator = SQLGenerator(provider)
        selected = [t for t in self.tables if t.name == 'customers']
        self.assertEqual(generator.generate_sql('Count customers', selected, []).response.text, 'SELECT 1')
        generator.generate_sql('Count customers', selected, [], 'SELECT bogus', 'no such column')
        payload = json.loads(provider.calls[1][1]['content'])
        self.assertIn('Table: customers', payload['schema_context'])
        self.assertNotIn('Table: payments', payload['schema_context'])
        self.assertEqual(payload['correction']['validation_error'], 'no such column')
        self.assertIn('sqlite', provider.calls[0][0]['content'])
