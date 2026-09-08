from text2sql.agent.correction import CorrectionLoop
from text2sql.agent.pipeline import Text2SQLAgent
from text2sql.config import Config
from text2sql.db.connection import SQLiteDatabase
from text2sql.db.executor import SafeExecutor
from text2sql.db.seed import DESCRIPTIONS
from text2sql.generation.llm import FakeLLMProvider, LLMProvider, OpenAICompatibleProvider
from text2sql.generation.sql_generator import SQLGenerator
from text2sql.observability import trace_logger
from text2sql.retrieval.embeddings import (APIEmbeddingProvider, HashingEmbeddingProvider,
                                          SentenceTransformerEmbeddingProvider)
from text2sql.retrieval.fewshot import FewShotRetriever, load_examples
from text2sql.retrieval.schema_index import SchemaIndexer, SchemaRetriever
from text2sql.validation.validator import SQLValidator

DEMO_QUESTION = 'Which five customers spent the most money in 2025, excluding refunded orders?'
DEMO_CHINESE = '2025 年购买金额最高的五名客户是谁？排除已退款订单。'
DEMO_SQL = """SELECT c.customer_id, c.name, ROUND(SUM(i.quantity * i.unit_price), 2) AS revenue
FROM customers AS c JOIN orders AS o ON c.customer_id = o.customer_id
JOIN order_items AS i ON o.order_id = i.order_id
WHERE o.order_date >= '2025-01-01' AND o.order_date < '2026-01-01' AND o.status <> 'refunded'
GROUP BY c.customer_id, c.name ORDER BY revenue DESC, c.customer_id LIMIT 5"""


def build_agent(config: Config, provider: LLMProvider | None = None,
                full_schema: bool = False, fewshot_k: int = 3) -> Text2SQLAgent:
    db = SQLiteDatabase(config.db_path, DESCRIPTIONS)
    if config.embedding == 'hashing':
        embeddings = HashingEmbeddingProvider()
    elif config.embedding == 'sentence-transformers':
        embeddings = SentenceTransformerEmbeddingProvider(config.embedding_model)
    elif config.embedding == 'api':
        embeddings = APIEmbeddingProvider(config.embedding_base_url, config.embedding_model, config.embedding_api_key)
    else:
        raise ValueError(f'Unknown embedding provider: {config.embedding}')
    if provider is None:
        if config.llm == 'fake':
            provider = FakeLLMProvider(['SELECT nonexistent FROM customers', DEMO_SQL])
        elif config.llm == 'api':
            provider = OpenAICompatibleProvider(config.base_url, config.model, config.api_key)
        else:
            raise ValueError(f'Unknown LLM provider: {config.llm}')
    index = SchemaIndexer(db, embeddings)
    index.build_index()
    return Text2SQLAgent(SchemaRetriever(index), FewShotRetriever(load_examples(), embeddings),
                        CorrectionLoop(SQLGenerator(provider, db.dialect), SQLValidator(db), config.max_retries),
                        SafeExecutor(db), top_k=config.top_k, fewshot_k=fewshot_k,
                        logger=trace_logger(config.trace), full_schema=full_schema)
