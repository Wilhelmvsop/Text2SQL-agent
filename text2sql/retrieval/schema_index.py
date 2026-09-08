from dataclasses import dataclass

import numpy as np

from text2sql.db.connection import Database
from text2sql.db.schema import TableSchema
from text2sql.errors import ProviderError
from text2sql.retrieval.embeddings import EmbeddingProvider, normalized


@dataclass(frozen=True)
class SchemaHit:
    table: TableSchema
    score: float


class SchemaIndexer:
    def __init__(self, database: Database, embeddings: EmbeddingProvider):
        self.database, self.embeddings = database, embeddings
        self.tables: list[TableSchema] = []
        self.vectors: np.ndarray | None = None

    def build_index(self) -> None:
        tables = self.database.introspect()
        if not tables:
            raise ValueError('Cannot index an empty schema')
        vectors = normalized(self.embeddings.embed([t.text() for t in tables]), len(tables))
        self.tables, self.vectors = tables, vectors


class SchemaRetriever:
    def __init__(self, index: SchemaIndexer):
        self.index = index

    def retrieve_schema(self, question: str, top_k: int = 4) -> list[SchemaHit]:
        if not question.strip() or top_k < 1:
            raise ValueError('Question must be nonempty and top_k positive')
        if self.index.vectors is None:
            raise ValueError('Call build_index() first')
        query = normalized(self.index.embeddings.embed([question]), 1)
        if query.shape[1] != self.index.vectors.shape[1]:
            raise ProviderError('Embedding dimensions changed after indexing')
        scores = self.index.vectors @ query[0]
        order = np.argsort(-scores, kind='stable')[:top_k]
        return [SchemaHit(self.index.tables[i], float(scores[i])) for i in order]
