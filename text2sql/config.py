import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    db_path: Path = Path('data/database.db')
    llm: str = 'fake'
    base_url: str = 'http://localhost:11434/v1'
    model: str = ''
    api_key: str = field(default='', repr=False)
    embedding: str = 'hashing'
    embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    embedding_base_url: str = ''
    embedding_api_key: str = field(default='', repr=False)
    top_k: int = 4
    max_retries: int = 3
    trace: Path = Path('traces/queries.jsonl')

    @classmethod
    def from_env(cls) -> 'Config':
        get = os.environ.get
        return cls(db_path=Path(get('TEXT2SQL_DB', 'data/database.db')),
                   llm=get('TEXT2SQL_LLM', 'fake'), base_url=get('TEXT2SQL_BASE_URL', 'http://localhost:11434/v1'),
                   model=get('TEXT2SQL_MODEL', ''), api_key=get('TEXT2SQL_API_KEY', get('OPENAI_API_KEY', '')),
                   embedding=get('TEXT2SQL_EMBEDDING', 'hashing'),
                   embedding_model=get('TEXT2SQL_EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2'),
                   embedding_base_url=get('TEXT2SQL_EMBEDDING_BASE_URL', ''),
                   embedding_api_key=get('TEXT2SQL_EMBEDDING_API_KEY', ''),
                   top_k=int(get('TEXT2SQL_TOP_K', '4')), max_retries=int(get('TEXT2SQL_MAX_RETRIES', '3')),
                   trace=Path(get('TEXT2SQL_TRACE', 'traces/queries.jsonl')))
