import time
from dataclasses import dataclass

from text2sql.db.schema import TableSchema
from text2sql.generation.llm import LLMProvider, LLMResponse
from text2sql.generation.prompts import build_messages
from text2sql.retrieval.fewshot import ExampleHit


@dataclass
class Generation:
    response: LLMResponse
    prompt_chars: int
    latency: float


class SQLGenerator:
    def __init__(self, provider: LLMProvider, dialect: str = 'sqlite'):
        self.provider, self.dialect = provider, dialect

    def generate_sql(self, question: str, schema_context: list[TableSchema], examples: list[ExampleHit],
                     previous_sql: str | None = None, error: str | None = None) -> Generation:
        messages = build_messages(question, schema_context, examples, self.dialect, previous_sql, error)
        started = time.perf_counter()
        response = self.provider.complete(messages)
        return Generation(response, sum(len(m['content']) for m in messages), time.perf_counter() - started)
