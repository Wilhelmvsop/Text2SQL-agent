import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from text2sql.agent.correction import Attempt, CorrectionLoop
from text2sql.db.connection import QueryResult
from text2sql.db.executor import SafeExecutor
from text2sql.errors import Text2SQLError
from text2sql.observability import log_result
from text2sql.retrieval.fewshot import FewShotRetriever
from text2sql.retrieval.schema_index import SchemaHit, SchemaRetriever


@dataclass
class Text2SQLResult:
    question: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    retrieved_tables: list[str] = field(default_factory=list)
    retrieval_scores: dict[str, float | None] = field(default_factory=dict)
    fewshot_examples: list[dict] = field(default_factory=list)
    generated_sql: str | None = None
    validation_attempts: list[Attempt] = field(default_factory=list)
    final_sql: str | None = None
    execution_result: QueryResult | None = None
    latency: float = 0.
    stage_latencies: dict[str, float] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    status: str = 'running'
    provider: str = ''
    embedding_provider: str = ''

    @property
    def validation_errors(self) -> list[str]:
        return [a.validation.error for a in self.validation_attempts if a.validation.error]

    def to_dict(self) -> dict:
        return {**asdict(self), 'validation_errors': self.validation_errors}


class Text2SQLAgent:
    def __init__(self, schema_retriever: SchemaRetriever, fewshot_retriever: FewShotRetriever,
                 correction: CorrectionLoop, executor: SafeExecutor, top_k: int = 4,
                 fewshot_k: int = 3, logger: logging.Logger | None = None,
                 full_schema: bool = False):
        if top_k < 1 or fewshot_k < 0:
            raise ValueError('Invalid retrieval limits')
        self.schema_retriever, self.fewshot_retriever = schema_retriever, fewshot_retriever
        self.correction, self.executor = correction, executor
        self.top_k, self.fewshot_k, self.logger, self.full_schema = top_k, fewshot_k, logger, full_schema

    def run(self, question: str) -> Text2SQLResult:
        result = Text2SQLResult(question)
        result.provider = self.correction.generator.provider.name
        result.embedding_provider = self.schema_retriever.index.embeddings.name
        started = time.perf_counter()
        try:
            if not question.strip() or len(question) > 10_000:
                raise ValueError('Question must contain 1 to 10000 characters')
            tick = time.perf_counter()
            if self.full_schema:
                hits = [SchemaHit(t, 0.) for t in self.schema_retriever.index.tables]
            else:
                hits = self.schema_retriever.retrieve_schema(question, self.top_k)
            tables = [hit.table for hit in hits]
            result.retrieved_tables = [t.name for t in tables]
            result.retrieval_scores = {h.table.name: None if self.full_schema else h.score for h in hits}
            result.stage_latencies['schema_retrieval'] = time.perf_counter() - tick
            tick = time.perf_counter()
            examples = self.fewshot_retriever.retrieve(question, set(result.retrieved_tables), self.fewshot_k)
            result.fewshot_examples = [asdict(h) for h in examples]
            result.stage_latencies['fewshot_retrieval'] = time.perf_counter() - tick
            tick = time.perf_counter()
            result.final_sql = self.correction.run(question, tables, examples, result.validation_attempts)
            result.stage_latencies['generation_and_validation'] = time.perf_counter() - tick
            if result.final_sql is None:
                result.status = 'validation_failed'
                result.error = result.validation_attempts[-1].validation.error
            else:
                tick = time.perf_counter()
                result.execution_result = self.executor.execute(result.final_sql, set(result.retrieved_tables))
                result.stage_latencies['execution'] = time.perf_counter() - tick
                result.status = 'success'
        except (Text2SQLError, ValueError) as exc:
            result.status = 'error'
            result.error = str(exc)
        finally:
            if result.validation_attempts:
                result.generated_sql = result.validation_attempts[0].raw_output
            for attempt in result.validation_attempts:
                for key, value in attempt.usage.items():
                    result.token_usage[key] = result.token_usage.get(key, 0) + value
            result.latency = time.perf_counter() - started
            log_result(self.logger, result.to_dict())
        return result
