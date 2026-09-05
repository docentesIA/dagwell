"""Release regressions: fake executors only, no inference or network."""

import json
import os
import shlex
import signal
import sys
import tempfile
import time
from pathlib import Path

from dagwell.adapters.registry import RegistryValidationError, validate_registry
from dagwell.adapters.transports import subprocess_transport as st


def binding(**changes):
    result = {"binding_id": "fake", "transport": "subprocess", "platform": "fake",
              "invocation": shlex.quote(sys.executable) + " -c {mission}",
              "timeout_seconds": 5,
              "models": [{"model_id": "fake", "family": "test-fake",
                          "tiers": ["simple"], "relative_cost": 1}]}
    result.update(changes)
    return result


def test_registry_rejects_templates_and_nonfinite_numbers():
    bad = [binding(invocation=value) for value in (
        'fake "{mission}', 'fake prefix-{mission}', 'fake {mission} prefix-{mission}',
        'fake {mission}\x00', '{mission}')]
    bad += [binding(timeout_seconds=value) for value in (float('nan'), float('inf'))]
    for value in (float('nan'), float('inf')):
        item = binding()
        item['models'][0]['relative_cost'] = value
        bad.append(item)
    bad += [binding(probe=value) for value in ('fake "', [], ' ', 'fake\x00')]
    for item in bad:
        try:
            validate_registry({'bindings': [item]})
        except RegistryValidationError:
            pass
        else:
            raise AssertionError(f'malformed binding accepted: {item!r}')


def test_attempt_cwd_and_out_absolute_or_relative():
    with tempfile.TemporaryDirectory() as tmp:
        original = Path.cwd()
        try:
            os.chdir(tmp)
            for relative in (False, True):
                attempt = Path(tmp) / ('relative' if relative else 'absolute')
                attempt.mkdir()
                out = attempt / 'output.json'
                argument = str(out.relative_to(tmp)) if relative else str(out)
                facts = st.execute(binding(),
                    "import os,json;from pathlib import Path;"
                    "Path('companion.txt').write_text('isolated');"
                    "Path(os.environ['OUT']).write_text(json.dumps([os.getcwd(),os.environ['OUT']]))",
                    argument, env=dict(os.environ))
                assert facts['exit_code'] == 0
                assert json.loads(out.read_text()) == [str(attempt), str(out)]
                assert (attempt / 'companion.txt').read_text() == 'isolated'
            assert not (Path(tmp) / 'companion.txt').exists()
        finally:
            os.chdir(original)


def test_missing_executable_records_spawn_failure_without_fake_exit():
    with tempfile.TemporaryDirectory() as tmp:
        facts = st.execute(binding(invocation='dagwell-missing-executor-xyz {mission}'),
                           'mission', str(Path(tmp) / 'out'), env=dict(os.environ))
        assert facts['exit_code'] is None
        assert facts['timed_out'] is False
        assert facts['transport_error'] == {'type': 'FileNotFoundError', 'errno': 2}


def test_timeout_cleans_descendant_after_parent_exits_zero():
    with tempfile.TemporaryDirectory() as tmp:
        old_grace = st.GRACE_SECONDS
        st.GRACE_SECONDS = 0.15
        pid_file = Path(tmp) / 'descendant.pid'
        descendant = None
        try:
            mission = (
                "import os,signal,sys,time;from pathlib import Path;"
                "signal.signal(signal.SIGINT,lambda *_: sys.exit(0));"
                "pid=os.fork();"
                "\nif pid == 0:\n"
                " signal.signal(signal.SIGINT,signal.SIG_IGN)\n"
                " signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                f" Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
                " time.sleep(60)\n"
                "else:\n time.sleep(60)\n")
            facts = st.execute(binding(timeout_seconds=0.5), mission,
                               str(Path(tmp) / 'out'), env=dict(os.environ))
            descendant = int(pid_file.read_text())
            assert facts['timed_out'] is True
            assert facts['exit_code'] == 0  # retain the real process status
            # An orphan zombie can wait for PID 1 to reap; it cannot do work.
            for _ in range(100):
                stat = Path(f'/proc/{descendant}/stat')
                if not stat.exists() or stat.read_text().split()[2] == 'Z':
                    break
                time.sleep(0.01)
            else:
                raise AssertionError('descendant survives timeout ladder')
        finally:
            st.GRACE_SECONDS = old_grace
            if descendant is None and pid_file.exists():
                descendant = int(pid_file.read_text())
            if descendant:
                try:
                    os.kill(descendant, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == '__main__':
    fns = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    for fn in fns:
        fn()
    print(f'test_transport_release: {len(fns)} tests PASS')
