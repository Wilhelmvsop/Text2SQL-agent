from dataclasses import dataclass

from text2sql.db.schema import TableSchema
from text2sql.generation.sql_generator import SQLGenerator
from text2sql.retrieval.fewshot import ExampleHit
from text2sql.validation.validator import SQLValidator, ValidationResult


@dataclass
class Attempt:
    number: int
    raw_output: str
    validation: ValidationResult
    prompt_chars: int
    generation_latency: float
    usage: dict[str, int]


class CorrectionLoop:
    def __init__(self, generator: SQLGenerator, validator: SQLValidator, max_retries: int = 3):
        if max_retries < 0:
            raise ValueError('max_retries must be nonnegative')
        self.generator, self.validator, self.max_retries = generator, validator, max_retries

    def run(self, question: str, tables: list[TableSchema], examples: list[ExampleHit],
            attempts: list[Attempt]) -> str | None:
        previous_sql = error = None
        for index in range(self.max_retries + 1):
            generation = self.generator.generate_sql(question, tables, examples, previous_sql, error)
            validation = self.validator.validate(generation.response.text, {t.name for t in tables})
            attempts.append(Attempt(index + 1, generation.response.text, validation,
                                    generation.prompt_chars, generation.latency, generation.response.usage))
            if validation.valid:
                return validation.sql
            if not validation.retryable:
                return None
            previous_sql = validation.sql or generation.response.text
            error = f'{validation.error_type}: {validation.error}'
        return None
