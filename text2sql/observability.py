import json
import logging
from pathlib import Path


def trace_logger(path: Path) -> logging.Logger:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f'text2sql.trace.{path}')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.FileHandler(path, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    return logger


def log_result(logger: logging.Logger | None, result: dict) -> None:
    if logger is not None:
        logger.info(json.dumps({'event': 'query_finished', **result}, ensure_ascii=False, default=str))
