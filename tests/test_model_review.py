"""Independent v1.1 review: malformed argv data must fail before dispatch."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from dagwell.adapters import worker
from dagwell.adapters.registry import RegistryValidationError, load_registry
from dagwell.adapters.transports.subprocess_transport import TransportError
from test_worker import REGISTRY_TEXT, _graph_text, _setup


def test_unrepresentable_mission_refused_before_dispatch_or_attempt_directory():
    for mission in ('pass\x00', 'pass\ud800'):
        with tempfile.TemporaryDirectory() as tmp:
            led, graph, rid, reg = _setup(tmp, _graph_text(mission=mission))
            before = led.path.read_bytes()
            with patch.object(worker.st, 'execute',
                              side_effect=AssertionError('invalid argv reached executor')) as execute:
                try:
                    worker.work(led, graph, rid, reg, tmp, go=True)
                except TransportError:
                    pass
                else:
                    raise AssertionError('invalid mission accepted for dispatch')
                execute.assert_not_called()
            assert led.path.read_bytes() == before
            assert not (Path(tmp) / 'runs').exists()


def test_unrepresentable_model_refused_at_registry_load():
    for model in ('invalid\x00', 'invalid\ud800'):
        registry = json.loads(REGISTRY_TEXT)
        registry['bindings'][0]['models'][0]['model_id'] = model
        try:
            load_registry(json.dumps(registry))
        except RegistryValidationError:
            pass
        else:
            raise AssertionError('invalid model accepted at registry load')


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().copy().items()) if k.startswith('test_')]
    for test in tests:
        test()
    print(f'test_model_review: {len(tests)} tests PASS')
