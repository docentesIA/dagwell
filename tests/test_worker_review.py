"""Independent release review: pilot contention, read isolation and CLI facts."""

import json
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from dagwell import operations
from dagwell.adapters import worker
from dagwell.fold import fold
from dagwell.ledger import LedgerIntegrityError
from test_cli import run
from test_worker import REGISTRY_TEXT, _graph_text, _setup


def test_second_pilot_refuses_while_status_remains_readable():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text())
        started, release = threading.Event(), threading.Event()
        results, errors = [], []

        def execute(binding, mission, out_path, *, env):
            started.set()
            assert release.wait(5), 'test executor was not released'
            Path(out_path).write_text('review artifact')
            return {'exit_code': 0, 'timed_out': False, 'duration_seconds': 0}

        def first():
            try:
                results.extend(worker.work(led, graph, rid, reg, tmp, go=True))
            except Exception as exc:
                errors.append(exc)

        with patch.object(worker.st, 'execute', side_effect=execute) as executor:
            thread = threading.Thread(target=first, daemon=True)
            thread.start()
            try:
                assert started.wait(5)
                assert fold(graph, led.run(rid), rid)['nodes']['task']['state'] == 'running'
                try:
                    worker.work(led, graph, rid, reg, tmp, go=True)
                except operations.OperationRefused as exc:
                    assert 'another worker' in str(exc)
                else:
                    raise AssertionError('second pilot acquired the active run')
            finally:
                release.set()
                thread.join(5)
            assert not thread.is_alive()
            assert not errors, errors
            assert executor.call_count == 1
        assert results[0]['action'] == 'executed'
        assert worker.work(led, graph, rid, reg, tmp, go=True) == []


def test_graph_mismatch_and_sequence_gap_refuse_before_probe():
    for defect in ('graph', 'gap'):
        with tempfile.TemporaryDirectory() as tmp:
            led, graph, rid, reg = _setup(tmp, _graph_text())
            if defect == 'graph':
                graph = dict(graph, graph_version='sha256:' + '00' * 32)
            else:
                operations.dispatch(led, graph, rid, 'task')
                operations.record_return(led, graph, rid, 'task', 1, 1)
                rows = led.run(rid)
                led.path.write_text('\n'.join(json.dumps(e) for e in (rows[0], rows[2])) + '\n')
            before = led.path.read_bytes()
            with patch.object(worker.st, 'probe') as probe:
                for go in (False, True):
                    try:
                        worker.work(led, graph, rid, reg, tmp, go=go)
                    except (operations.OperationRefused, LedgerIntegrityError):
                        pass
                    else:
                        raise AssertionError(f'{defect} accepted')
                probe.assert_not_called()
            assert led.path.read_bytes() == before
            assert not (Path(tmp) / 'runs').exists()


def test_cli_reports_nonzero_with_evidence_as_failure():
    mission = "import os;open(os.environ['OUT'],'w').write('partial');raise SystemExit(9)"
    with tempfile.TemporaryDirectory() as tmp:
        text = _graph_text(mission=mission)
        led, graph, rid, reg = _setup(tmp, text)
        graph_path, registry_path = Path(tmp) / 'g.json', Path(tmp) / 'registry.json'
        graph_path.write_text(text)
        registry_path.write_text(REGISTRY_TEXT)
        rc, out, err = run('work', '--ledger', str(led.path), '--graph', str(graph_path),
                           '--run', rid, '--registry', str(registry_path),
                           '--data-dir', tmp, '--go')
        assert rc == 1, (rc, out, err)
        assert 'failed' in out and 'exit 9' in out
        assert 'verifications are now due' not in out
        assert fold(graph, led.run(rid), rid)['nodes']['task']['state'] == 'failed'


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().copy().items()) if k.startswith('test_')]
    for test in tests:
        test()
    print(f'test_worker_review: {len(tests)} tests PASS')
