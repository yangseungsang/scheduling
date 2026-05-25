"""Tests for std_list model — MySQL cache and fetch."""
import pytest
from unittest.mock import patch, MagicMock


def test_load_cache_returns_empty_when_no_file(tmp_path, monkeypatch):
    """캐시 파일이 없으면 빈 리스트를 반환한다."""
    from app import create_app
    import os, json
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)
    for name in ('users', 'locations', 'tasks', 'schedule_blocks',
                 'versions', 'procedures', 'settings'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump({} if name == 'settings' else [], f)
    app = create_app()
    app.config['DATA_DIR'] = data_dir
    app.config['TESTING'] = True
    with app.app_context():
        from app.features.schedule.models.std_list import load_cache
        assert load_cache() == []


def test_save_and_load_cache(tmp_path):
    """저장한 캐시를 다시 읽으면 동일한 데이터를 반환한다."""
    from app import create_app
    import os, json
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)
    for name in ('users', 'locations', 'tasks', 'schedule_blocks',
                 'versions', 'procedures'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump([], f)
    with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
        json.dump({
            'work_start': '08:00', 'work_end': '17:00',
            'actual_work_start': '08:30', 'actual_work_end': '16:30',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [], 'grid_interval_minutes': 15,
            'max_schedule_days': 14, 'block_color_by': 'assignee',
        }, f)

    app = create_app()
    app.config['DATA_DIR'] = data_dir
    app.config['TESTING'] = True

    rows = [
        {'test_info': 'TC-001', 'exam_no': 1},
        {'test_info': 'TC-001', 'exam_no': 2},
    ]
    with app.app_context():
        from app.features.schedule.models.std_list import save_cache, load_cache
        save_cache(rows)
        assert load_cache() == rows


def test_fetch_from_mysql_returns_rows():
    """MySQL 연결 성공 시 test_info, exam_no 행을 반환한다."""
    from app.features.schedule.models import std_list as std_list_mod
    import importlib
    importlib.reload(std_list_mod)

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: mock_cursor
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.return_value = [
        {'test_info': 'TC-001', 'exam_no': 1},
        {'test_info': 'TC-001', 'exam_no': 2},
        {'test_info': 'TC-002', 'exam_no': 1},
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch('app.features.schedule.models.std_list.pymysql.connect',
               return_value=mock_conn):
        result = std_list_mod.fetch_from_mysql()

    assert len(result) == 3
    assert result[0] == {'test_info': 'TC-001', 'exam_no': 1}
    assert result[2] == {'test_info': 'TC-002', 'exam_no': 1}
