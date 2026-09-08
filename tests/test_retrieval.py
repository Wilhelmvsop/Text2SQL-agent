import numpy as np

from tests.helpers import DatabaseTest
from text2sql.errors import ProviderError
from text2sql.retrieval.embeddings import HashingEmbeddingProvider, MockEmbeddingProvider, normalized
from text2sql.retrieval.schema_index import SchemaIndexer, SchemaRetriever
from text2sql.retrieval.fewshot import FewShotRetriever, load_examples


class RetrievalTests(DatabaseTest):
    def test_cosine_ranking_and_topk(self):
        vectors = {t.text(): [1., 0.] if t.name == 'customers' else [0., 1.] for t in self.tables}
        vectors['buyers'] = [3., 0.]
        index = SchemaIndexer(self.db, MockEmbeddingProvider(vectors))
        index.build_index()
        hits = SchemaRetriever(index).retrieve_schema('buyers', 2)
        self.assertEqual(hits[0].table.name, 'customers')
        self.assertAlmostEqual(hits[0].score, 1.)
        self.assertEqual(len(hits), 2)

    def test_offline_ranking(self):
        index = SchemaIndexer(self.db, HashingEmbeddingProvider())
        index.build_index()
        retriever = SchemaRetriever(index)
        self.assertEqual(retriever.retrieve_schema('customers country Canada', 1)[0].table.name, 'customers')
        with self.assertRaises(ValueError):
            retriever.retrieve_schema('question', 0)

    def test_embedding_checks(self):
        np.testing.assert_equal(normalized(np.zeros((1, 3)), 1), [[0, 0, 0]])
        with self.assertRaises(ProviderError):
            normalized(np.array([[float('nan')]]), 1)

    def test_fewshot_schema_filter(self):
        retriever = FewShotRetriever(load_examples(), HashingEmbeddingProvider())
        hits = retriever.retrieve('customers spending orders', {'customers'})
        self.assertEqual([hit.example.id for hit in hits], ['fs1'])
        self.assertEqual(retriever.retrieve('anything', set()), [])
