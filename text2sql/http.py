import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from text2sql.errors import ProviderError


def post_json(base_url: str, endpoint: str, api_key: str, payload: dict,
              timeout: float = 60.0) -> dict[str, Any]:
    parsed = urlparse(base_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ProviderError('Invalid provider URL')
    if api_key and parsed.scheme != 'https' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ProviderError('Remote API keys require HTTPS')
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    request = urllib.request.Request(base_url.rstrip('/') + '/' + endpoint,
                                     json.dumps(payload).encode(), headers=headers, method='POST')

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ProviderError('Provider response exceeded size limit')
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        # Do not log response bodies or headers, which may echo credentials.
        raise ProviderError(f'Provider HTTP {exc.code}') from exc
    except (OSError, ValueError) as exc:
        raise ProviderError(f'Provider transport/JSON failure: {type(exc).__name__}') from exc
