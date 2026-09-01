"""동기화 서비스 — 외부 프로바이더 데이터를 로컬 모델에 병합한다.

외부 데이터 소스(프로바이더)로부터 버전 정보와 시험 데이터를 가져와
공유 JSON catalog에 추가/갱신/비활성화하는 기능을 제공한다.
공급자가 제공하는 (document_id, test_round) 조합별로 독립 시험 절차서를 생성한다.
"""

from app.features.schedule.services import test_procedures as procedure, blocks as schedule_block
from app.features.schedule.services.test_procedures import TestProcedureService
from app.repositories import get_repository


def _procedure_blocks(procedure_id):
    """procedure_id에 연결된 스케줄 블록 목록을 반환한다."""
    return [b for b in schedule_block.get_all() if b.get('procedure_id') == procedure_id]


def _scheduled_test_item_ids(procedure_dict):
    """해당 procedure에서 이미 스케줄 블록에 배치된 시험 항목 ID 집합을 반환한다.

    test_item_ids=None인 블록은 procedure 전체가 배치된 것으로 간주한다.
    """
    test_items = [
        i.get('id') for i in procedure_dict.get('test_items', [])
        if isinstance(i, dict) and i.get('id')
    ]
    scheduled = set()
    for block in _procedure_blocks(procedure_dict['id']):
        block_ids = block.get('test_item_ids')
        if block_ids is None:
            scheduled.update(test_items)
        else:
            scheduled.update(block_ids)
    return scheduled


def _merge_preserving_scheduled_removed(existing, incoming, warnings):
    """동기화에서 삭제된 시험 항목 중 이미 배치된 항목은 보존한다."""
    incoming_ids = {
        i.get('id') for i in incoming
        if isinstance(i, dict) and i.get('id')
    }
    scheduled_ids = _scheduled_test_item_ids(existing)
    merged = list(incoming)

    for old in existing.get('test_items', []):
        if not isinstance(old, dict):
            continue
        old_id = old.get('id')
        if not old_id or old_id in incoming_ids:
            continue
        if old_id in scheduled_ids:
            merged.append(old)
            warnings.append(
                f"{existing.get('document_name', '')} / {old_id}: "
                "이미 스케줄 블록에 배치되어 동기화 삭제를 건너뜀"
            )

    return merged


class SyncService:
    """외부 프로바이더와의 데이터 동기화를 수행하는 서비스 클래스."""

    @staticmethod
    def sync_test_data(client, version_id=None):
        """프로바이더로부터 시험 데이터를 동기화한다.

        공급자가 제공한 (document_id, test_round) 조합별로 시험 절차서를 생성·갱신한다.

        Args:
            client: 시험 데이터를 반환하는 외부 연동 클라이언트.
        Returns:
            dict: {'added': int, 'updated': int, 'deleted': int,
                   'cancelled': int, 'warnings': list}
        """
        return SyncService.sync_test_rows(client.get_test_data_all(), version_id)

    @staticmethod
    def sync_test_rows(external, version_id=None):
        """Synchronize already-fetched provider rows without another network call."""
        if version_id is not None:
            get_repository().set_version_id(version_id)
        return _sync_test_data_orm(external)


def _sync_test_data_orm(external):
    """Merge normalized provider rows using the procedure service API."""
    service = TestProcedureService(get_repository())
    synced_combos = set()
    added = updated = deleted = 0
    warnings = []

    for item in external:
        try:
            document_id = int(item.get('document_id'))
        except (TypeError, ValueError):
            warnings.append(f"잘못된 document_id, 건너뜀: {item}")
            continue

        document_name = item.get('document_name') or item.get('section_name', '')
        test_items = item.get('test_items', [])
        combos_to_sync = [(item.get('test_round'), test_items)]

        for test_round, idents in combos_to_sync:
            synced_combos.add((document_id, test_round))
            existing = procedure.get_by_document_and_round(document_id, test_round)
            if existing:
                idents = _merge_preserving_scheduled_removed(
                    existing, idents, warnings,
                )
                service.update_procedure(existing['id'], {
                    **existing,
                    'document_id': document_id,
                    'test_round': test_round,
                    'document_name': document_name,
                    'test_items': idents,
                    'estimated_minutes': sum(
                        i.get('estimated_minutes', 0)
                        for i in idents
                        if isinstance(i, dict)
                    ),
                })
                updated += 1
            else:
                service.create_procedure({
                    'document_id': document_id,
                    'test_round': test_round,
                    'assignee_names': [],
                    'document_name': document_name,
                    'test_items': idents,
                    'estimated_minutes': sum(
                        i.get('estimated_minutes', 0)
                        for i in idents
                        if isinstance(i, dict)
                    ),
                })
                added += 1

    for t in procedure.get_all():
        did = t.get('document_id')
        if did is None:
            continue
        try:
            did = int(did)
        except (TypeError, ValueError):
            pass
        combo = (did, t.get('test_round'))
        if combo not in synced_combos:
            if _procedure_blocks(t['id']):
                warnings.append(
                    f"{t.get('document_name', '')}: 이미 스케줄 블록에 배치되어 "
                    "동기화 삭제를 건너뜀"
                )
                continue
            service.delete_procedure(t['id'])
            deleted += 1

    return {'added': added, 'updated': updated,
            'deleted': deleted, 'cancelled': deleted,
            'warnings': warnings}
