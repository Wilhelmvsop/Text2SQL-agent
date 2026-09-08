import hashlib
import re
from typing import Protocol

import numpy as np

from text2sql.errors import ProviderError
from text2sql.http import post_json


class EmbeddingProvider(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbeddingProvider:
    """Offline lexical baseline, NOT a pretrained semantic model."""
    name = 'hashing-8192-v1'
    stopwords = frozenset('a an the of in on at by for from to with and or is are was were be '
                          'which who what how many much all each their have has had do does '
                          'did show list find give me most highest lowest top five three excluding '
                          'table description columns primary key integer text date decimal not null'.split())

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), 8192), dtype=np.float64)
        for i, text in enumerate(texts):
            tokens = re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]', text.lower().replace('_', ' '))
            for token in tokens:
                if token in self.stopwords:
                    continue
                token = token[:-1] if len(token) > 3 and token.endswith('s') else token
                digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
                vectors[i, int.from_bytes(digest, 'little') % 8192] = 1
        return vectors


class MockEmbeddingProvider:
    name = 'mock'

    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray([self.vectors[t] for t in texts], dtype=float)


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model: str = 'sentence-transformers/all-MiniLM-L6-v2'):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model)
        self.name = model

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)


class APIEmbeddingProvider:
    def __init__(self, base_url: str, model: str, api_key: str = ''):
        self.base_url, self.name, self.api_key = base_url, model, api_key

    def embed(self, texts: list[str]) -> np.ndarray:
        response = post_json(self.base_url, 'embeddings', self.api_key,
                             {'model': self.name, 'input': texts})
        try:
            data = sorted(response['data'], key=lambda row: row['index'])
            if [r['index'] for r in data] != list(range(len(texts))):
                raise ValueError('Invalid embedding indices')
            return np.asarray([row['embedding'] for row in data], dtype=float)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError('Malformed embedding response') from exc


def normalized(vectors: np.ndarray, count: int) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=float)
    if vectors.ndim != 2 or vectors.shape[0] != count or vectors.shape[1] == 0 or not np.isfinite(vectors).all():
        raise ProviderError('Embedding shape or finite-value validation failed')
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return np.divide(vectors, norms, out=np.zeros_like(vectors), where=norms != 0)
