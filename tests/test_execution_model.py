"""Tests for ExecutionRepository.get_by_test_item_and_procedure."""
import pytest
from app import create_app
from tests.conftest import configure_test_storage


def _make_app(tmp_path):
    app = create_app()
    app.config['TESTING'] = True
    configure_test_storage(app, tmp_path)
    with app.app_context():
        from app.features.schedule.services.test_procedures import TestProcedureService

        service = TestProcedureService(app.config['DOMAIN_DATA_DIR'])
        service.create_procedure({
            'id': 't_procedure1', 'document_id': 1, 'document_name': '1차',
            'test_round': 1, 'test_items': [{'id': 'TC-001'}],
        })
        service.create_procedure({
            'id': 't_procedure2', 'document_id': 1, 'document_name': '2차',
            'test_round': 2, 'test_items': [{'id': 'TC-001'}],
        })
    return app


class TestGetByTestItemAndTestProcedure:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.app = _make_app(tmp_path)

    def test_returns_correct_execution_by_procedure_scope(self):
        """동일 test_item_id가 두 태스크에 있을 때 procedure_id로 올바른 실행을 반환한다."""
        from app.features.execution.repository import ExecutionRepository
        with self.app.app_context():
            ex1 = ExecutionRepository.start('TC-001', 't_procedure1', total_count=10)
            ex2 = ExecutionRepository.start('TC-001', 't_procedure2', total_count=10)

            found1 = ExecutionRepository.get_by_test_item_and_procedure('TC-001', 't_procedure1')
            found2 = ExecutionRepository.get_by_test_item_and_procedure('TC-001', 't_procedure2')

            assert found1 is not None
            assert found1['procedure_id'] == 't_procedure1'
            assert found2 is not None
            assert found2['procedure_id'] == 't_procedure2'
            assert (
                found1['procedure_id'], found1['test_item_id']
            ) != (
                found2['procedure_id'], found2['test_item_id']
            )

    def test_returns_none_when_not_found(self):
        """일치하는 레코드가 없으면 None을 반환한다."""
        from app.features.execution.repository import ExecutionRepository
        with self.app.app_context():
            result = ExecutionRepository.get_by_test_item_and_procedure('TC-999', 't_none')
            assert result is None
