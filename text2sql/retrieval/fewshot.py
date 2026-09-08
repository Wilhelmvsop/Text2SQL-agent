import json
from dataclasses import dataclass
from importlib.resources import files

import numpy as np

from text2sql.errors import ProviderError
from text2sql.retrieval.embeddings import EmbeddingProvider, normalized


@dataclass(frozen=True)
class Example:
    id: str
    question: str
    tables: list[str]
    sql: str


@dataclass(frozen=True)
class ExampleHit:
    example: Example
    score: float


def load_examples() -> list[Example]:
    return [Example(**row) for row in json.loads(files('text2sql').joinpath('assets/fewshot.json').read_text())]


class FewShotRetriever:
    def __init__(self, examples: list[Example], embeddings: EmbeddingProvider):
        if len({e.id for e in examples}) != len(examples):
            raise ValueError('Example IDs must be unique')
        self.examples, self.embeddings = examples, embeddings
        self.vectors = normalized(embeddings.embed([e.question for e in examples]), len(examples)) if examples else None

    def retrieve(self, question: str, allowed_tables: set[str], top_k: int = 3) -> list[ExampleHit]:
        if top_k < 0:
            raise ValueError('top_k cannot be negative')
        if self.vectors is None or top_k == 0:
            return []
        query = normalized(self.embeddings.embed([question]), 1)
        if query.shape[1] != self.vectors.shape[1]:
            raise ProviderError('Embedding dimensions changed')
        scores = self.vectors @ query[0]
        candidates = [i for i in np.argsort(-scores, kind='stable')
                      if set(self.examples[i].tables) <= allowed_tables]
        return [ExampleHit(self.examples[i], float(scores[i])) for i in candidates[:top_k]]
