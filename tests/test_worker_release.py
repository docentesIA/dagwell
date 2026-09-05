"""Release regressions: synthetic executors, isolated data, no provider calls."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from dagwell import human, operations, runtime
from dagwell.adapters import worker
from dagwell.fold import fold
from dagwell.adapters.registry import load_registry
from test_worker import _graph_text, _setup
from test_cli import run


def test_unknown_run_refused_before_probe_or_directory():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text())
        for go in (False, True):
            with patch.object(worker.st, 'probe') as probe:
                try:
                    worker.work(led, graph, 'unknown', reg, tmp, go=go)
                except operations.OperationRefused:
                    pass
                else:
                    raise AssertionError('unknown run accepted')
                probe.assert_not_called()
        assert not (Path(tmp) / 'runs').exists()


def test_plan_unknown_run_never_probes():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text())
        with patch.object(worker.st, 'probe') as probe:
            try:
                worker.plan(graph, led, 'unknown', reg)
            except operations.OperationRefused:
                pass
            else:
                raise AssertionError('unknown run planned')
            probe.assert_not_called()


def test_nonzero_exit_with_artifact_matches_fold_and_cli():
    mission = "import os;open(os.environ['OUT'],'w').write('partial');raise SystemExit(7)"
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text(mission=mission))
        result, = worker.work(led, graph, rid, reg, tmp, go=True)
        assert result['exit_code'] == 7 and result['evidence_id']
        assert result['action'] == fold(graph, led.run(rid), rid)['nodes']['task']['state'] == 'failed'


def test_existing_attempt_directory_is_never_reused():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text())
        adir = Path(tmp) / 'runs' / 'wk' / rid / 'task' / 't1'
        adir.mkdir(parents=True)
        (adir / 'out').write_text('history')
        with patch.object(worker.st, 'execute') as execute:
            try:
                worker.work(led, graph, rid, reg, tmp, go=True)
            except (FileExistsError, operations.OperationRefused):
                pass
            else:
                raise AssertionError('existing directory reused')
            execute.assert_not_called()
        assert (adir / 'out').read_text() == 'history'


def test_stale_attempt_never_dispatches_new_attempt_into_old_directory():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text())
        original_dispatch = operations.dispatch

        def interleaved(*args, **kwargs):
            original_dispatch(led, graph, rid, 'task')
            operations.record_return(led, graph, rid, 'task', 1, 1)
            human.human_retry(led, graph, rid, 'task', actor='test-human')
            return original_dispatch(*args, **kwargs)

        with patch.object(operations, 'dispatch', side_effect=interleaved):
            with patch.object(worker.st, 'execute') as execute:
                try:
                    worker.work(led, graph, rid, reg, tmp, go=True)
                except operations.OperationRefused:
                    pass
                else:
                    raise AssertionError('stale attempt executed')
                execute.assert_not_called()
        assert len([e for e in led.run(rid) if e['event_type'] == 'node_dispatched']) == 1


def test_missing_executable_refused_before_dispatch():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text())
        reg['bindings']['py-cli']['invocation'] = '/no-such-dagwell-executor {mission}'
        result, = worker.work(led, graph, rid, reg, tmp, go=True)
        assert result['action'] == 'refused'
        assert len(led.run(rid)) == 1
        assert not (Path(tmp) / 'runs').exists()


def test_spawn_race_preserves_dispatch_without_fictitious_return():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text())
        error = {'exit_code': None, 'timed_out': False,
                 'transport_error': {'type': 'PermissionError', 'errno': 13}}
        with patch.object(worker.st, 'execute', return_value=error):
            try:
                worker.work(led, graph, rid, reg, tmp, go=True)
            except operations.OperationRefused as exc:
                assert 'remains in flight' in str(exc)
            else:
                raise AssertionError('spawn error ignored')
        assert [e['event_type'] for e in led.run(rid)] == ['run_created', 'node_dispatched']
        assert fold(graph, led.run(rid), rid)['nodes']['task']['state'] == 'running'


def test_worker_timeout_exit_zero_is_failed():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text())

        def timed_out(binding, mission, out_path, **kwargs):
            Path(out_path).write_text('partial')
            return {'exit_code': 0, 'timed_out': True, 'duration_seconds': 0.1}

        with patch.object(worker.st, 'execute', side_effect=timed_out):
            result, = worker.work(led, graph, rid, reg, tmp, go=True)
        assert result['action'] == 'failed' and result['exit_code'] == 0
        assert led.run(rid)[-1]['transport']['timed_out'] is True


def test_relative_data_directory_and_declared_waiver(tmp_unused=None):
    import os
    text = json.loads(_graph_text())
    node = text['nodes'][0]
    node.pop('verifications')
    node['no_verification'] = 'synthetic fixture only'
    node['mission'] = "import os;from pathlib import Path;Path('out').write_text(str(Path.cwd()))"
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, json.dumps(text))
        # Relative to the invoking directory; transport must still see an
        # absolute OUT and write its relative file in the attempt directory.
        result, = worker.work(led, graph, rid, reg, os.path.relpath(tmp), go=True)
        assert result['action'] == 'completed'
        adir = Path(result['attempt_dir'])
        assert adir.is_absolute() and (adir / 'out').read_text() == str(adir)


def test_symlink_attempt_ancestor_and_output_are_not_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text())
        dest = Path(tmp) / 'unrelated'
        dest.mkdir()
        (Path(tmp) / 'runs').symlink_to(dest, target_is_directory=True)
        try:
            worker.work(led, graph, rid, reg, tmp, go=True)
        except operations.OperationRefused:
            pass
        else:
            raise AssertionError('symlink ancestor accepted')
        assert not list(dest.iterdir()) and len(led.run(rid)) == 1
        (dest / 'real').write_text('history')
        (dest / 'out').symlink_to(dest / 'real')
        assert worker._artifact_evidence_from_disk(dest, 'out') is None


def test_selected_models_reach_real_executor_and_match_ledger():
    mission = ("import os,sys,json;from pathlib import Path;"
               "Path(os.environ['OUT']).write_text(json.dumps(sys.argv[1:]))")
    for tier, expected in [('simple', 'cheap'), ('frontier', 'dear')]:
        with tempfile.TemporaryDirectory() as tmp:
            led, graph, rid, reg = _setup(tmp, _graph_text(tier=tier, mission=mission))
            result, = worker.work(led, graph, rid, reg, tmp, go=True)
            captured = json.loads((Path(result['attempt_dir']) / 'out').read_text())
            dispatch = next(e for e in led.run(rid) if e['event_type'] == 'node_dispatched')
            assert captured == [expected]
            assert dispatch['transport']['model_id'] == captured[0]
            assert dispatch['transport']['registry_digest'] == reg['registry_digest']


def test_literal_single_model_binding_stays_compatible():
    from test_worker import REGISTRY_TEXT
    data = json.loads(REGISTRY_TEXT)
    binding = data['bindings'][0]
    binding['models'] = binding['models'][:1]
    binding['invocation'] = binding['invocation'].replace('{model_id}', 'cheap')
    mission = "import os,sys;open(os.environ['OUT'],'w').write(sys.argv[1])"
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, _ = _setup(tmp, _graph_text(mission=mission))
        reg = load_registry(json.dumps(data))
        result, = worker.work(led, graph, rid, reg, tmp, go=True)
        assert (Path(result['attempt_dir']) / 'out').read_text() == 'cheap'


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().copy().items()) if k.startswith('test_')]
    for test in tests:
        test()
    print(f'test_worker_release: {len(tests)} tests PASS')
