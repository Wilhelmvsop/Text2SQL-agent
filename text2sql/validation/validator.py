from dataclasses import dataclass

from text2sql.db.connection import Database
from text2sql.errors import DatabaseValidationError, SafetyError
from text2sql.validation.safety import check_static, normalize_sql


@dataclass
class ValidationResult:
    valid: bool
    sql: str = ''
    error: str | None = None
    error_type: str | None = None
    stage: str = 'explain'
    retryable: bool = True


class SQLValidator:
    def __init__(self, database: Database):
        self.database = database

    def validate(self, output: str, allowed_tables: set[str]) -> ValidationResult:
        try:
            sql = normalize_sql(output)
        except SafetyError as exc:
            return ValidationResult(False, error=str(exc), error_type='format', stage='normalization')
        try:
            check_static(sql, allowed_tables, self.database.dialect)
        except SafetyError as exc:
            return ValidationResult(False, sql, str(exc), 'unsafe', 'static', False)
        except ValueError as exc:
            return ValidationResult(False, sql, str(exc), 'structure', 'static')
        try:
            self.database.explain(sql, allowed_tables)
        except DatabaseValidationError as exc:
            message = str(exc)
            lowered = message.lower()
            kind = next((kind for text, kind in [
                ('ambiguous', 'ambiguous_column'), ('no such column', 'unknown_column'),
                ('no such table', 'unknown_table'), ('no such function', 'unknown_function'),
                ('not authorized', 'authorization'), ('prohibited', 'authorization'),
                ('syntax', 'syntax'), ('interrupted', 'budget')]
                if text in lowered), 'database')
            return ValidationResult(False, sql, message, kind, 'explain', kind != 'authorization')
        return ValidationResult(True, sql)
