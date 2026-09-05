"""Independent review regression: timeout is transport failure before spend."""

import tempfile

from dagwell.ledger import events as ev
from helpers import artifact_evidence
from tests_scenario import S


def test_verification_refused_after_zero_exit_timeout():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ev('node_returned', node_id='a', attempt=1, exit_code=0,
             output_evidence=artifact_evidence(), transport={'timed_out': True})
        before = s.led.path.read_bytes()
        try:
            s.request()
        except ev.EventValidationError:
            pass
        else:
            raise AssertionError('verification accepted after transport timeout')
        assert s.led.path.read_bytes() == before
        assert s.fold()['nodes']['a']['state'] == 'failed'
        assert s.fold()['run_state'] == 'stalled'


if __name__ == '__main__':
    test_verification_refused_after_zero_exit_timeout()
    print('test_core_review: 1 test PASS')
