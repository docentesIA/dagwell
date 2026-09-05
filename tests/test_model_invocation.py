"""Adapter v1.1: selected models reach argv without shell interpolation."""

import json
import os
import shlex
import sys
import tempfile
from pathlib import Path

from dagwell.adapters.registry import RegistryValidationError, validate_registry
from dagwell.adapters.transports import subprocess_transport as st
from test_transport_release import binding


def refuses(error, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except error:
        return
    raise AssertionError(f'expected {error.__name__}')


def test_model_and_mission_substitute_once_as_single_arguments():
    model = 'model spaces;$(touch forbidden) {mission}'
    mission = 'mission spaces;`touch forbidden` {model_id}'
    assert st.build_argv('executor --model {model_id} -p {mission}', mission,
                         model_id=model) == ['executor', '--model', model, '-p', mission]
    assert st.build_argv('executor --model fixed {mission}', mission) == [
        'executor', '--model', 'fixed', mission]


def test_model_marker_requires_explicit_value_and_valid_position():
    for value in (None, '', 7, 'bad\x00model'):
        refuses(st.TransportError, st.build_argv,
                'executor {model_id} {mission}', 'work', model_id=value)
    for invocation in ('{model_id} {mission}',
                       'executor --model={model_id} {mission}',
                       'executor {model_id} prefix-{model_id} {mission}'):
        refuses(st.TransportError, st.build_argv, invocation, 'work', model_id='fake')


def test_registry_refuses_ambiguous_models_and_accepts_literal_single_model():
    item = binding()
    validate_registry({'bindings': [item]})
    item['models'].append(dict(item['models'][0], model_id='second'))
    refuses(RegistryValidationError, validate_registry, {'bindings': [item]})
    item['invocation'] += ' --model {model_id}'
    validate_registry({'bindings': [item]})
    item['models'][0]['model_id'] = 'invalid\x00model'
    refuses(RegistryValidationError, validate_registry, {'bindings': [item]})


def test_fake_executor_captures_exact_selected_model():
    with tempfile.TemporaryDirectory() as tmp:
        script = "import json,os,sys;open(os.environ['OUT'],'w').write(json.dumps(sys.argv[1:]))"
        item = binding(invocation=shlex.quote(sys.executable) + ' -c '
                       + shlex.quote(script) + ' --model {model_id} {mission}')
        mission = 'keep {model_id} and $OUT literal; no shell'
        for attempt, selected in enumerate(('small', 'large with spaces;$(literal)'), 1):
            directory = Path(tmp) / f't{attempt}'
            directory.mkdir()
            out = directory / 'captured.json'
            facts = st.execute(item, mission, str(out), env=dict(os.environ),
                               model_id=selected)
            assert facts['exit_code'] == 0
            assert json.loads(out.read_text()) == ['--model', selected, mission]


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    for test in tests:
        test()
    print(f'test_model_invocation: {len(tests)} tests PASS')
