import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from text2sql.config import Config
from text2sql.db.seed import seed_database
from text2sql.errors import Text2SQLError
from text2sql.factory import DEMO_CHINESE, DEMO_QUESTION, build_agent


def report_summary(report: dict) -> dict:
    return {k: report_summary(v) if isinstance(v, dict) else v
            for k, v in report.items() if k != 'cases'}


def display(result, json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    print(f'Provider: {result.provider}')
    print('Retrieved Tables:', ', '.join(result.retrieved_tables))
    print('Similarity Scores:', result.retrieval_scores)
    print('Few-shot Examples:', [h['example']['id'] for h in result.fewshot_examples])
    for attempt in result.validation_attempts:
        print(f'\n{"Generated SQL" if attempt.number == 1 else "Correction SQL"}:\n{attempt.raw_output}')
        print(f'Validation Attempt {attempt.number}: {"Passed" if attempt.validation.valid else "Failed"}')
        if attempt.validation.error:
            print(f'Reason [{attempt.validation.stage}]: {attempt.validation.error}')
    print(f'\nFinal SQL:\n{result.final_sql or "(none)"}')
    if result.execution_result:
        print('Columns:', result.execution_result.columns)
        for row in result.execution_result.rows:
            print(row)
        if result.execution_result.truncated:
            print('(Result truncated)')
    if result.error:
        print('Error:', result.error)
    print(f'Status: {result.status}; Latency: {result.latency:.3f}s; Trace: {result.trace_id}')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Schema-grounded text-to-SQL agent')
    parser.add_argument('--init-db', action='store_true')
    parser.add_argument('--db', type=Path)
    parser.add_argument('--question', '-q')
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--llm', choices=['fake', 'api'])
    parser.add_argument('--top-k', type=int)
    parser.add_argument('--full-schema', action='store_true')
    parser.add_argument('--evaluate', action='store_true')
    parser.add_argument('--smoke', action='store_true', help='Oracle replay, never a model benchmark')
    parser.add_argument('--ablation', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('reports/local-evaluation.json'))
    args = parser.parse_args(argv)
    try:
        config = Config.from_env()
        for name, value in [('db_path', args.db), ('llm', args.llm), ('top_k', args.top_k)]:
            if value is not None:
                config = replace(config, **{name: value})
        if args.init_db:
            print(json.dumps(seed_database(config.db_path), indent=2))
            return 0
        if not config.db_path.exists():
            raise ValueError('Database not found. Run python -m text2sql.cli --init-db first.')
        if args.evaluate or args.ablation:
            from text2sql.evaluation.evaluator import run_evaluation, run_ablation
            report = (run_ablation(config, args.smoke) if args.ablation else
                      run_evaluation(config, args.smoke, args.full_schema))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report_summary(report), ensure_ascii=False, indent=2))
            print('Report:', args.output)
            return 0
        if args.demo:
            config = replace(config, llm='fake')
        if config.llm == 'fake':
            print('FAKE MODE: scripted workflow demo only; no real LLM inference.', file=sys.stderr)
        agent = None
        while True:
            question = DEMO_QUESTION if args.demo else args.question
            if question is None:
                try:
                    question = input(f'Question (Enter for demo, quit to exit):\n> ').strip()
                except EOFError:
                    return 0
                if question.lower() in {'quit', 'exit'}:
                    return 0
                question = question or DEMO_QUESTION
            if config.llm == 'fake' and question not in {DEMO_QUESTION, DEMO_CHINESE}:
                raise ValueError('Fake mode supports only the preset --demo question. Configure --llm api for arbitrary questions.')
            if agent is None or config.llm == 'fake':
                agent = build_agent(config, full_schema=args.full_schema)
            result = agent.run(question)
            display(result, args.json)
            if args.demo or args.question:
                return 0 if result.status == 'success' else 1
    except (Text2SQLError, ValueError, OSError, ImportError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
