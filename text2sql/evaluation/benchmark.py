import json
from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    difficulty: str
    question: str
    tables: list[str]
    sql: str
    ordered: bool = False


def load_benchmark() -> list[BenchmarkCase]:
    return [BenchmarkCase(**row) for row in json.loads(files('text2sql').joinpath('assets/benchmark.json').read_text())]
