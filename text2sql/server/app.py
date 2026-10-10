import asyncio
import json
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from pathlib import Path
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from text2sql.agent.pipeline import Text2SQLAgent, Text2SQLResult
from text2sql.config import Config
from text2sql.db.seed import seed_database
from text2sql.errors import Text2SQLError
from text2sql.factory import build_agent
from text2sql.generation.llm import LLMProvider, OpenAICompatibleProvider
from text2sql.server.runtime import EDITABLE, Runtime, Snapshot, merge, model_configured, public_settings
from text2sql.server.store import AppStore
from text2sql.server.uploads import UploadError, prepare, receive, upload_target

WEB_DIST = Path(__file__).resolve().parents[2] / 'web' / 'dist'
MODEL_FIELDS = ('base_url', 'model', 'api_key')


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10_000)


class SqlRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=100_000)


class ExecuteRequest(SqlRequest):
    question: str = Field(default='', max_length=10_000)
    parent_id: str | None = None


class StarRequest(BaseModel):
    starred: bool


class SettingsUpdate(BaseModel):
    """Omitted fields keep their value; secrets are write-only and an empty string clears them."""
    db_path: str | None = Field(default=None, min_length=1, max_length=1000)
    base_url: str | None = Field(default=None, max_length=2000)
    model: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=1000)
    embedding: Literal['hashing', 'sentence-transformers', 'api'] | None = None
    embedding_model: str | None = Field(default=None, max_length=200)
    embedding_base_url: str | None = Field(default=None, max_length=2000)
    embedding_api_key: str | None = Field(default=None, max_length=1000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    max_retries: int | None = Field(default=None, ge=0, le=10)


def connect(config: Config) -> LLMProvider:
    return OpenAICompatibleProvider(config.base_url, config.model, config.api_key, timeout=20)


def create_app(config: Config | None = None,
               agent_factory: Callable[[Config], Text2SQLAgent] | None = None,
               provider_factory: Callable[[Config], LLMProvider] = connect) -> FastAPI:
    base = config or Config.from_env()
    agent_factory = agent_factory or build_agent
    state: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state['store'] = store = AppStore(base.history_path)
        state['runtime'] = await run_in_threadpool(Runtime, merge(base, store.settings()), agent_factory)
        yield

    app = FastAPI(title='Text2SQL Agent', lifespan=lifespan)

    def runtime() -> Runtime:
        return state['runtime']

    def store() -> AppStore:
        return state['store']

    def ready() -> Snapshot:
        snapshot = runtime().current
        if snapshot.error:
            raise HTTPException(503, f'Configuration error: {snapshot.error}. Fix it in Settings.')
        if snapshot.database is None:
            raise HTTPException(503, 'No database is configured. Create the demo database or set a path in Settings.')
        if snapshot.agent is None:
            raise HTTPException(503, 'No model is connected. Connect a model in Settings to use the app.')
        return snapshot

    def save(result: Text2SQLResult) -> dict:
        trace = result.to_dict()
        execution = trace.pop('execution_result')
        last = result.validation_attempts[-1].validation if result.validation_attempts else None
        return store().add(
            kind='agent', question=result.question, status=result.status, error=result.error,
            error_type=None if last is None or last.valid else last.error_type,
            final_sql=result.final_sql, result=execution, latency=result.latency, trace=trace)

    # --- status and settings -------------------------------------------------------------

    @app.get('/api/health')
    def health() -> dict:
        snapshot = runtime().current
        config = snapshot.config
        return {'status': 'ok', 'ready': snapshot.ready, 'error': snapshot.error,
                'model_connected': snapshot.agent is not None, 'model': config.model,
                'database_exists': config.db_path.exists(), 'db_path': str(config.db_path),
                'max_rows': snapshot.database.max_rows if snapshot.database else None}

    @app.get('/api/settings')
    def get_settings() -> dict:
        return public_settings(runtime().current.config)

    def candidate(body: SettingsUpdate) -> Config:
        return merge(runtime().current.config, body.model_dump(exclude_none=True))

    def check_connection(config: Config) -> str:
        """Send one tiny request to the model; raises ValueError with a readable reason on failure."""
        if not model_configured(config):
            raise ValueError('Enter an API base URL and a model name')
        started = time.perf_counter()
        try:
            provider_factory(config).complete([{'role': 'user', 'content': 'Reply with the single word OK.'}])
        except Text2SQLError as exc:
            message = str(exc)
            if 'transport' in message:
                message = f'Could not reach {config.base_url} ({message})'
            raise ValueError(message) from exc
        return f'{config.model} responded in {time.perf_counter() - started:.2f}s'

    @app.put('/api/settings')
    async def put_settings(body: SettingsUpdate) -> dict:
        current, config = runtime().current, candidate(body)
        # Only a model that answers can be saved; unchanged model settings are not re-checked.
        changed = any(getattr(config, k) != getattr(current.config, k) for k in MODEL_FIELDS)
        if model_configured(config) and (changed or current.agent is None):
            try:
                await run_in_threadpool(check_connection, config)
            except ValueError as exc:
                raise HTTPException(400, f'Could not connect to the model: {exc}') from exc
        await commit(config)
        return public_settings(config)

    async def commit(config: Config) -> None:
        """Switch to config and persist it, or keep the previous working configuration."""
        try:
            await run_in_threadpool(runtime().apply, config)
        except Exception as exc:
            raise HTTPException(400, f'Settings not applied: {exc or type(exc).__name__}') from exc
        values = {k: getattr(config, k) for k in EDITABLE}
        store().save_settings({**values, 'db_path': str(config.db_path)})

    @app.delete('/api/settings')
    async def reset_settings() -> dict:
        store().save_settings({})
        state['runtime'] = await run_in_threadpool(Runtime, base, agent_factory)
        return public_settings(base)

    @app.post('/api/settings/test')
    async def test_settings(body: SettingsUpdate) -> dict:
        try:
            return {'ok': True, 'message': await run_in_threadpool(check_connection, candidate(body))}
        except ValueError as exc:
            return {'ok': False, 'message': str(exc)}

    @app.post('/api/database/demo')
    async def create_demo_database() -> dict:
        config = runtime().current.config
        if config.db_path.exists():
            raise HTTPException(409, f'{config.db_path} already exists')
        counts = await run_in_threadpool(seed_database, config.db_path)
        try:
            await run_in_threadpool(runtime().apply, config)
        except Exception as exc:
            raise HTTPException(400, f'Database created but the agent failed to load: {exc}') from exc
        return {'db_path': str(config.db_path), 'rows': counts}

    @app.post('/api/database/upload')
    async def upload_database(request: Request, filename: str = Query(min_length=1, max_length=255)) -> dict:
        """Store an uploaded SQLite file in the uploads folder and connect to it."""
        directory = base.history_path.resolve().parent / 'uploads'
        directory.mkdir(parents=True, exist_ok=True)
        target = upload_target(directory, filename)
        partial = target.with_suffix('.part')
        try:
            await receive(request.stream(), partial)
            tables = await run_in_threadpool(prepare, partial)
            partial.rename(target)
        except UploadError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        finally:
            partial.unlink(missing_ok=True)
        try:
            await commit(replace(runtime().current.config, db_path=target))
        except HTTPException:
            target.unlink(missing_ok=True)
            raise
        return {'db_path': str(target), 'name': filename, 'tables': tables}

    # --- querying ------------------------------------------------------------------------

    @app.get('/api/schema')
    def schema() -> dict:
        return {'tables': [asdict(t) for t in ready().tables]}

    @app.post('/api/queries')
    async def ask(body: AskRequest) -> dict:
        snapshot = ready()
        result = await run_in_threadpool(snapshot.agent.run, body.question)
        return save(result)

    @app.post('/api/queries/stream')
    async def ask_stream(body: AskRequest) -> StreamingResponse:
        agent = ready().agent
        loop = asyncio.get_running_loop()
        events: asyncio.Queue = asyncio.Queue()

        def on_event(stage: str, payload: dict) -> None:
            loop.call_soon_threadsafe(events.put_nowait, (stage, payload))

        async def run() -> None:
            try:
                result = await run_in_threadpool(agent.run, body.question, on_event)
                events.put_nowait(('done', await run_in_threadpool(save, result)))
            except Exception as exc:  # surfaced to the client instead of a dropped stream
                events.put_nowait(('error', {'detail': str(exc)}))

        async def stream():
            task = asyncio.create_task(run())
            try:
                while True:
                    stage, payload = await events.get()
                    yield f'event: {stage}\ndata: {json.dumps(payload, default=str)}\n\n'
                    if stage in ('done', 'error'):
                        break
            finally:
                await task

        return StreamingResponse(stream(), media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.post('/api/sql/validate')
    async def validate(body: SqlRequest) -> dict:
        snapshot = ready()
        tables = {t.name for t in snapshot.tables}
        return asdict(await run_in_threadpool(snapshot.validator.validate, body.sql, tables))

    @app.post('/api/sql/execute')
    async def execute(body: ExecuteRequest) -> dict:
        snapshot = ready()
        tables = {t.name for t in snapshot.tables}

        def run() -> dict:
            started = time.perf_counter()
            validation = snapshot.validator.validate(body.sql, tables)
            fields = {'kind': 'manual', 'question': body.question, 'parent_id': body.parent_id,
                      'trace': {'validation': asdict(validation)}}
            if not validation.valid:
                return store().add(**fields, status='validation_failed', error=validation.error,
                                   error_type=validation.error_type, final_sql=validation.sql or body.sql,
                                   latency=time.perf_counter() - started)
            try:
                result = snapshot.database.execute_readonly(validation.sql, tables)
            except Text2SQLError as exc:
                return store().add(**fields, status='error', error=str(exc), error_type='execution',
                                   final_sql=validation.sql, latency=time.perf_counter() - started)
            return store().add(**fields, status='success', final_sql=validation.sql,
                               result=asdict(result), latency=time.perf_counter() - started)
        return await run_in_threadpool(run)

    # --- history -------------------------------------------------------------------------

    @app.get('/api/history')
    def history(search: str = Query('', max_length=500), status: str | None = None,
                starred: bool | None = None, limit: int = Query(50, ge=1, le=200),
                offset: int = Query(0, ge=0)) -> dict:
        items, total = store().list(search, status, starred, limit, offset)
        return {'items': items, 'total': total}

    @app.get('/api/history/{query_id}')
    def history_item(query_id: str) -> dict:
        record = store().get(query_id)
        if record is None:
            raise HTTPException(404, 'Query not found')
        return record

    @app.patch('/api/history/{query_id}')
    def star(query_id: str, body: StarRequest) -> dict:
        if not store().set_starred(query_id, body.starred):
            raise HTTPException(404, 'Query not found')
        return {'id': query_id, 'starred': body.starred}

    @app.delete('/api/history/{query_id}', status_code=204)
    def delete(query_id: str) -> None:
        if not store().delete(query_id):
            raise HTTPException(404, 'Query not found')

    if WEB_DIST.is_dir():
        app.mount('/assets', StaticFiles(directory=WEB_DIST / 'assets'), name='assets')

        @app.get('/{path:path}', include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith('api/'):
                raise HTTPException(404, 'Not found')
            return FileResponse(WEB_DIST / 'index.html')

    return app
