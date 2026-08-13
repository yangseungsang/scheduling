"""Tests for the DynReady integration client."""

from unittest.mock import Mock, patch

from app.features.schedule.integrations.dyn_ready import DynReadyClient


def test_dyn_ready_groups_test_items_by_test_round():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        'data': [{
            'doc_id': 1,
            'doc_name': '시스템',
            'identifiers': [
                {
                    'test_id': 'TC-001', 'func_name': '로그인', 'exam_no': 1,
                    'estimated_minutes': 30, 'pf_num': 17, 'owner': '홍길동',
                },
                {
                    'test_id': 'TC-002', 'func_name': '로그아웃', 'exam_no': 2,
                    'estimated_minutes': 20, 'pf_num': 3,
                },
            ],
        }],
    }

    with patch(
        'app.features.schedule.integrations.dyn_ready.requests.get',
        return_value=response,
    ):
        data = DynReadyClient().get_test_data_all()

    assert [item['test_round'] for item in data] == [1, 2]
    assert data[0]['test_items'][0] == {
        'id': 'TC-001',
        'name': '로그인',
        'estimated_minutes': 30,
        'total_count': 17,
        'owners': ['홍길동'],
    }
