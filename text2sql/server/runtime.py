import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from text2sql.agent.pipeline import Text2SQLAgent
from text2sql.config import Config
from text2sql.db.connection import SQLiteDatabase
from text2sql.db.schema import TableSchema
from text2sql.db.seed import DESCRIPTIONS
from text2sql.validation.validator import SQLValidator

EDITABLE = ('db_path', 'base_url', 'model', 'api_key', 'embedding', 'embedding_model',
            'embedding_base_url', 'embedding_api_key', 'top_k', 'max_retries')
SECRETS = ('api_key', 'embedding_api_key')


def merge(base: Config, overrides: dict) -> Config:
    """The web app only runs against a real model, so the scripted 'fake' provider is never used."""
    values = {k: Path(v) if k == 'db_path' else v for k, v in overrides.items() if k in EDITABLE}
    return replace(base, **values, llm='api')


def model_configured(config: Config) -> bool:
    return bool(config.model.strip() and config.base_url.strip())


def public_settings(config: Config) -> dict:
    """Settings safe to send to the browser: secrets are reported as set/unset only."""
    values = {k: str(getattr(config, k)) if k == 'db_path' else getattr(config, k)
              for k in EDITABLE if k not in SECRETS}
    return {**values, **{f'{k}_set': bool(getattr(config, k)) for k in SECRETS}}


@dataclass
class Snapshot:
    config: Config
    database: SQLiteDatabase | None = None
    tables: list[TableSchema] = field(default_factory=list)
    validator: SQLValidator | None = None
    agent: Text2SQLAgent | None = None
    error: str | None = None

    @property
    def ready(self) -> bool:
        return self.database is not None and self.agent is not None and self.error is None


class Runtime:
    """Holds the live agent and database; settings changes build a new snapshot and swap it in."""

    def __init__(self, config: Config, agent_factory: Callable[[Config], Text2SQLAgent]):
        self.agent_factory = agent_factory
        self._lock = threading.Lock()
        try:
            self.current = self.build(config)
        except Exception as exc:  # start anyway so the settings page can repair the config
            self.current = Snapshot(config, error=str(exc) or type(exc).__name__)

    def build(self, config: Config) -> Snapshot:
        if config.db_path.resolve() == config.history_path.resolve():
            # Querying the app's own store would expose saved settings, including API keys.
            raise ValueError(f"{config.db_path} is this app's own history and settings file. "
                             'Choose the database you want to query.')
        if not config.db_path.exists():
            return Snapshot(config)
        database = SQLiteDatabase(config.db_path, DESCRIPTIONS)
        tables = database.introspect()
        if not tables:
            raise ValueError(f'{config.db_path} contains no tables')
        # Without a model the database still loads, so setup can show it, but nothing can run.
        agent = self.agent_factory(config) if model_configured(config) else None
        return Snapshot(config, database, tables, SQLValidator(database), agent)

    def apply(self, config: Config) -> Snapshot:
        snapshot = self.build(config)
        with self._lock:
            self.current = snapshot
        return snapshot

