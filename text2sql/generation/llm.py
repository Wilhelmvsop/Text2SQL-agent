from dataclasses import dataclass, field
from typing import Protocol

from text2sql.errors import ProviderError
from text2sql.http import post_json


@dataclass
class LLMResponse:
    text: str
    usage: dict[str, int] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str

    def complete(self, messages: list[dict[str, str]]) -> LLMResponse: ...


class FakeLLMProvider:
    """Scripted responses only. Never use its scores as model capability evidence."""
    name = 'fake-scripted'

    def __init__(self, responses: list[str]):
        self.responses = iter(responses)
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        self.calls.append(messages)
        try:
            return LLMResponse(next(self.responses))
        except StopIteration as exc:
            raise ProviderError('Fake response script exhausted') from exc


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, model: str, api_key: str = '', timeout: float = 60.):
        if not model.strip():
            raise ValueError('A model name is required for real generation')
        self.base_url, self.name, self.api_key, self.timeout = base_url, model, api_key, timeout

    def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        data = post_json(self.base_url, 'chat/completions', self.api_key,
                         {'model': self.name, 'messages': messages, 'temperature': 0,
                          'max_tokens': 1500}, self.timeout)
        try:
            choice = data['choices'][0]
            if choice.get('finish_reason') == 'length':
                raise ProviderError('Model output was truncated')
            content = choice['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise ProviderError('Model returned no text')
            usage = {k: int(v) for k, v in (data.get('usage') or {}).items()
                     if k in {'prompt_tokens', 'completion_tokens', 'total_tokens'} and isinstance(v, int)}
            return LLMResponse(content, usage)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError('Malformed LLM response') from exc
