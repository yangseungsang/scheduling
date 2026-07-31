import json
import os
import builtins

from app import create_app


def _make_app(tmp_path):
    data_dir = str(tmp_path / 'data')
    exec_dir = str(tmp_path / 'exec_data')
    os.makedirs(data_dir)
    os.makedirs(exec_dir)
    app = create_app()
    app.config['DATA_DIR'] = data_dir
    app.config['EXECUTION_DATA_DIR'] = exec_dir
    app.config['TESTING'] = True
    return app


def _tracking_lock(calls):
    class TrackingLock:
        def __init__(self, path, mode='r', **kwargs):
            calls.append({'path': path, 'mode': mode, 'kwargs': kwargs})
            self.path = path
            self.mode = mode
            self.kwargs = kwargs
            self.file = None

        def __enter__(self):
            self.file = builtins.open(
                self.path,
                self.mode,
                encoding=self.kwargs.get('encoding'),
            )
            return self.file

        def __exit__(self, exc_type, exc, tb):
            self.file.close()

    return TrackingLock


def test_schedule_store_reads_and_writes_utf8(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    calls = []

    with app.app_context():
        from app.features.schedule import store

        monkeypatch.setattr(store.portalocker, 'Lock', _tracking_lock(calls))

        store.write_json('users.json', [{'name': '시험 담당자 — 홍길동'}])
        assert store.read_json('users.json') == [{'name': '시험 담당자 — 홍길동'}]

    assert [call['kwargs'].get('encoding') for call in calls] == ['utf-8', 'utf-8']


def test_schedule_store_transaction_locks_read_modify_write(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    calls = []

    with app.app_context():
        from app.features.schedule import store

        monkeypatch.setattr(store.portalocker, 'Lock', _tracking_lock(calls))

        result = store.transact_json(
            'users.json',
            lambda users: users.append({'name': '트랜잭션 — 정상'}) or 'ok',
        )

        assert result == 'ok'
        assert store.read_json('users.json') == [{'name': '트랜잭션 — 정상'}]

    assert calls[0]['mode'] == 'r+'
    assert calls[0]['kwargs'].get('encoding') == 'utf-8'


def test_execution_store_reads_and_writes_utf8(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    calls = []

    with app.app_context():
        from app.features.execution import store

        monkeypatch.setattr(store.portalocker, 'Lock', _tracking_lock(calls))

        store.write_json('executions.json', [{'comment': '완료 — 정상'}])
        assert store.read_json('executions.json') == [{'comment': '완료 — 정상'}]

    assert [call['kwargs'].get('encoding') for call in calls] == ['utf-8', 'utf-8']


def test_execution_store_transaction_locks_read_modify_write(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    calls = []

    with app.app_context():
        from app.features.execution import store

        monkeypatch.setattr(store.portalocker, 'Lock', _tracking_lock(calls))

        result = store.transact_json(
            'executions.json',
            lambda executions: executions.append({'comment': '실행 — 정상'}) or 'ok',
        )

        assert result == 'ok'
        assert store.read_json('executions.json') == [{'comment': '실행 — 정상'}]

    assert calls[0]['mode'] == 'r+'
    assert calls[0]['kwargs'].get('encoding') == 'utf-8'


def test_dyn_ready_meta_uses_utf8(tmp_path):
    app = _make_app(tmp_path)

    with app.app_context():
        from app.features.schedule.providers import dyn_ready

        meta = {'updated_at': '2026-07-06T00:00:00', 'label': '메타 — 정상'}
        dyn_ready._save_meta(meta)
        assert dyn_ready._load_meta() == meta

        path = os.path.join(app.config['DATA_DIR'], 'dyn_ready_meta.json')
        with open(path, encoding='utf-8') as f:
            assert json.load(f) == meta
