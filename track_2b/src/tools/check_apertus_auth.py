"""Status-only local Apertus authentication and minimal inference check.

Run in the local ``trial`` or ``worker`` container. This intentionally prints
no key, response body, or provider error body.
"""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from intelligence.trial import (  # noqa: E402
    LOCAL_TEXT_MODEL,
    TrialError,
    available_models,
    configuration,
    request_json,
)


def main():
    key_file = os.environ.get('LLM_API_KEY_FILE', '')
    status = {
        'endpoint_is_expected_local': os.environ.get('LLM_BASE_URL', '') == 'http://inference:8080/v1',
        'model': os.environ.get('LLM_NAME', ''),
        'key_file_configured': bool(key_file),
        'key_file_exists': bool(key_file) and Path(key_file).is_file(),
        'key_file_readable': bool(key_file) and os.access(key_file, os.R_OK),
        'legacy_key_env_populated': bool(os.environ.get('LLM_API_KEY', '')),
    }

    try:
        config = configuration()
    except TrialError as error:
        status.update({'configuration': 'unavailable', 'safe_error': str(error)})
        print(json.dumps(status, sort_keys=True))
        return 1

    status['effective_credential_loaded'] = bool(config.get('key'))
    # This diagnostic must never send data to a hosted or unrelated endpoint.
    if config['base'] != 'http://inference:8080/v1' or config['model'] != LOCAL_TEXT_MODEL:
        status.update({'endpoint': 'redacted_unexpected_target', 'configuration': 'unexpected_local_target', 'models_auth': 'not_attempted',
                       'completion_auth': 'not_attempted'})
        print(json.dumps(status, sort_keys=True))
        return 2

    status['endpoint'] = config['base']
    try:
        model_ids = available_models(config)
        status['models_auth'] = 'ok'
        status['configured_model_listed'] = config['model'] in model_ids
    except TrialError as error:
        status.update({'models_auth': 'failed', 'safe_error': str(error)})
        print(json.dumps(status, sort_keys=True))
        return 1

    started = time.perf_counter()
    try:
        response = request_json(config, 'chat/completions', {
            'model': config['model'],
            'temperature': 0,
            'max_tokens': 8,
            'stream': False,
            'messages': [{'role': 'user', 'content':
                'Synthetic connectivity check only. Reply exactly READY.'}],
        })
        status.update({
            'completion_auth': 'ok',
            'completion_latency_seconds': round(time.perf_counter() - started, 3),
            'response_has_choices': bool(response.get('choices')),
        })
    except TrialError as error:
        status.update({
            'completion_auth': 'failed',
            'completion_latency_seconds': round(time.perf_counter() - started, 3),
            'safe_error': str(error),
        })
        print(json.dumps(status, sort_keys=True))
        return 1

    print(json.dumps(status, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
