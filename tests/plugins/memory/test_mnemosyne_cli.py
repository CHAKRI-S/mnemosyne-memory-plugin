import json
import subprocess
import sys
from pathlib import Path


def test_mnemosyne_cli_status_search_remember_inspect_forget(tmp_path):
    project_root = Path(__file__).resolve().parents[3]
    hermes_source = Path('/Users/tik/.hermes/hermes-agent')
    pythonpath = f"{project_root}:{hermes_source}"

    base = [sys.executable, '-m', 'plugins.memory.mnemosyne.cli', '--storage-path', str(tmp_path / 'mnemosyne')]

    remembered = subprocess.run(
        base + ['remember', 'CLI memory service routes deterministic operations.', '--type', 'fact', '--metadata', '{"project":"Mnemosyne"}'],
        text=True,
        capture_output=True,
        check=True,
        env={**__import__('os').environ, 'PYTHONPATH': pythonpath},
    )
    remembered_payload = json.loads(remembered.stdout)
    memory_id = remembered_payload['id']

    searched = subprocess.run(
        base + ['search', 'CLI memory', '--filter', 'project=Mnemosyne'],
        text=True,
        capture_output=True,
        check=True,
        env={**__import__('os').environ, 'PYTHONPATH': pythonpath},
    )
    assert json.loads(searched.stdout)['items'][0]['id'] == memory_id

    inspected = subprocess.run(
        base + ['inspect', memory_id],
        text=True,
        capture_output=True,
        check=True,
        env={**__import__('os').environ, 'PYTHONPATH': pythonpath},
    )
    assert json.loads(inspected.stdout)['item']['metadata']['project'] == 'Mnemosyne'

    status = subprocess.run(
        base + ['status'],
        text=True,
        capture_output=True,
        check=True,
        env={**__import__('os').environ, 'PYTHONPATH': pythonpath},
    )
    status_payload = json.loads(status.stdout)
    assert status_payload['provider'] == 'mnemosyne'
    assert status_payload['write_policy'] == 'single'
    assert status_payload['counts']['total'] == 1

    forgotten = subprocess.run(
        base + ['forget', memory_id],
        text=True,
        capture_output=True,
        check=True,
        env={**__import__('os').environ, 'PYTHONPATH': pythonpath},
    )
    assert json.loads(forgotten.stdout)['forgotten'] == 1


def test_cli_query_forget_rejects_multiple_matches(tmp_path):
    project_root = Path(__file__).resolve().parents[3]
    hermes_source = Path('/Users/tik/.hermes/hermes-agent')
    env = {**__import__('os').environ, 'PYTHONPATH': f"{project_root}:{hermes_source}"}
    base = [sys.executable, '-m', 'plugins.memory.mnemosyne.cli', '--storage-path', str(tmp_path / 'mnemosyne')]

    subprocess.run(base + ['remember', 'duplicate cli guarded memory one'], text=True, capture_output=True, check=True, env=env)
    subprocess.run(base + ['remember', 'duplicate cli guarded memory two'], text=True, capture_output=True, check=True, env=env)

    result = subprocess.run(base + ['forget-query', 'duplicate cli guarded memory'], text=True, capture_output=True, env=env)
    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert payload['success'] is False
    assert 'multiple' in payload['error'].lower()
