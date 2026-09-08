import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import traverse_scope
from sqlglot.tokens import TokenType

from text2sql.errors import SafetyError

FORBIDDEN = frozenset({'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE', 'CREATE',
                       'ATTACH', 'DETACH', 'PRAGMA', 'VACUUM', 'REINDEX', 'REPLACE',
                       'GRANT', 'REVOKE', 'COMMIT', 'ROLLBACK', 'BEGIN', 'COPY', 'INTO'})


def normalize_sql(output: str) -> str:
    if not isinstance(output, str) or len(output) > 100_000:
        raise SafetyError('SQL output must be text of at most 100000 characters')
    sql = output.strip()
    # Only recognize an entire wrapper; never discard an unexamined suffix.
    sql = re.sub(r'\A(?:Here is (?:the )?SQL|SQL)\s*:\s*', '', sql, flags=re.I)
    fence = re.fullmatch(r'```(?:sql|sqlite)?\s*\n?(.*?)\n?```', sql, flags=re.I | re.S)
    if fence:
        sql = fence.group(1).strip()
    if not sql or '```' in sql:
        raise SafetyError('Empty SQL or unrecognized markdown wrapper')
    return sql


def check_static(sql: str, allowed_tables: set[str], dialect: str = 'sqlite') -> exp.Expression:
    try:
        tokens = sqlglot.Dialect.get_or_raise(dialect).tokenize(sql)
        if len(tokens) > 10_000:
            raise SafetyError('SQL token budget exceeded')
        depth = 0
        for token in tokens:
            if token.token_type == TokenType.L_PAREN:
                depth += 1
                if depth > 64:
                    raise SafetyError('SQL nesting budget exceeded')
            elif token.token_type == TokenType.R_PAREN:
                depth -= 1
            if token.token_type not in {TokenType.STRING, TokenType.IDENTIFIER}:
                if token.text.upper() in FORBIDDEN:
                    # REPLACE() is a safe string function, not a write statement.
                    if token.text.upper() == 'REPLACE' and re.search(r'\breplace\s*\(', sql, re.I):
                        continue
                    raise SafetyError(f'Forbidden SQL keyword: {token.text.upper()}')
        statements = sqlglot.parse(sql, read=dialect)
    except (ParseError, sqlglot.errors.TokenError) as exc:
        raise ValueError(f'SQL parse error: {exc}') from exc
    if len(statements) != 1 or statements[0] is None:
        raise SafetyError('Exactly one SQL statement is required')
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise SafetyError('Only SELECT or WITH ... SELECT queries are allowed')
    banned_nodes = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
                    exp.Command, exp.Into, exp.Transaction)
    if any(isinstance(node, banned_nodes) for node in tree.walk()):
        raise SafetyError('Non-read-only AST node')
    allowed = {name.casefold() for name in allowed_tables}
    for scope in traverse_scope(tree):
        for source in scope.sources.values():
            if isinstance(source, exp.Table):
                if not isinstance(source.this, exp.Identifier) or source.db or source.catalog:
                    raise SafetyError('Table functions and qualified databases are forbidden')
                if source.name.casefold() not in allowed:
                    raise ValueError(f'Table outside retrieved schema: {source.name}')
    for join in tree.find_all(exp.Join):
        if join.args.get('method') == 'NATURAL' or not (join.args.get('on') or join.args.get('using')):
            raise ValueError('Every JOIN must have an explicit ON or USING condition')
    for select in tree.find_all(exp.Select):
        for projection in select.expressions:
            if isinstance(projection, exp.Star) or (isinstance(projection, exp.Column) and projection.is_star):
                raise ValueError('Enumerate output columns instead of SELECT *')
    return tree
