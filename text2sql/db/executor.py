from text2sql.db.connection import Database, QueryResult
from text2sql.errors import SafetyError
from text2sql.validation.validator import SQLValidator


class SafeExecutor:
    """Public execution boundary: revalidate even if the caller bypasses the agent."""
    def __init__(self, database: Database):
        self.database = database

    def execute(self, sql: str, allowed_tables: set[str]) -> QueryResult:
        result = SQLValidator(self.database).validate(sql, allowed_tables)
        if not result.valid:
            raise SafetyError(result.error or 'Validation failed')
        return self.database.execute_readonly(result.sql, allowed_tables)
