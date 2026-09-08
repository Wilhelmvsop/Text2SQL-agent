import unittest
from unittest.mock import patch

from text2sql.errors import ProviderError
from text2sql.generation.llm import OpenAICompatibleProvider
from text2sql.http import post_json
from text2sql.retrieval.embeddings import APIEmbeddingProvider


class ProviderTests(unittest.TestCase):
    def test_llm_usage(self):
        data = {'choices': [{'message': {'content': 'SELECT 1'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13}}
        with patch('text2sql.generation.llm.post_json', return_value=data) as call:
            response = OpenAICompatibleProvider('https://example.test/v1', 'model').complete([])
            self.assertEqual(response.usage['total_tokens'], 13)
            self.assertEqual(call.call_args.args[3]['temperature'], 0)
        data['choices'][0]['finish_reason'] = 'length'
        with patch('text2sql.generation.llm.post_json', return_value=data), self.assertRaises(ProviderError):
            OpenAICompatibleProvider('https://example.test/v1', 'model').complete([])

    def test_embedding_order_and_malformed_response(self):
        provider = APIEmbeddingProvider('https://example.test/v1', 'model')
        data = {'data': [{'index': 1, 'embedding': [0, 1]}, {'index': 0, 'embedding': [1, 0]}]}
        with patch('text2sql.retrieval.embeddings.post_json', return_value=data):
            self.assertEqual(provider.embed(['a', 'b']).tolist(), [[1, 0], [0, 1]])
        with patch('text2sql.retrieval.embeddings.post_json', return_value={}), self.assertRaises(ProviderError):
            provider.embed(['a'])

    def test_no_plaintext_remote_credentials(self):
        with self.assertRaises(ProviderError):
            post_json('http://example.test', 'chat/completions', 'test-secret', {})
