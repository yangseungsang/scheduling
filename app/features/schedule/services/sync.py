"""동기화 서비스 — 외부 프로바이더 데이터를 로컬 모델에 병합한다.

외부 데이터 소스(프로바이더)로부터 버전 정보와 시험 데이터를 가져와
로컬 JSON 파일 기반 모델에 추가/갱신/비활성화하는 기능을 제공한다.
exam_no 기반 태스크 분리: std_list_cache.json의 데이터를 참조하여
(doc_id, exam_no) 조합별로 독립 태스크를 생성한다.
"""

from app.features.schedule.models import version, task, schedule_block
from app.features.schedule.providers.base import NoChangesError
from app.config import OfpidSettings


def load_std_list_cache():
    """std_list 로컬 캐시를 읽어 반환한다. 없으면 []."""
    from app.features.schedule.models.std_list import load_cache
    return load_cache()


def _task_blocks(task_id):
    """task_id에 연결된 스케줄 블록 목록을 반환한다."""
    return [b for b in schedule_block.get_all() if b.get('task_id') == task_id]


def _scheduled_identifier_ids(task_dict):
    """해당 task에서 이미 스케줄 블록에 배치된 식별자 ID 집합을 반환한다.

    identifier_ids=None인 블록은 task 전체가 배치된 것으로 간주한다.
    """
    identifiers = [
        i.get('id') for i in task_dict.get('identifiers', [])
        if isinstance(i, dict) and i.get('id')
    ]
    scheduled = set()
    for block in _task_blocks(task_dict['id']):
        block_ids = block.get('identifier_ids')
        if block_ids is None:
            scheduled.update(identifiers)
        else:
            scheduled.update(block_ids)
    return scheduled


def _identifier_ids(task_dict):
    """태스크에 포함된 식별자 ID 목록을 반환한다."""
    return [
        i.get('id') if isinstance(i, dict) else i
        for i in task_dict.get('identifiers', [])
        if (i.get('id') if isinstance(i, dict) else i)
    ]


def _block_identifier_ids(task_dict, block, task_blocks):
    """현재 태스크 상태 기준으로 블록이 실제 커버하는 식별자 ID를 반환한다."""
    block_ids = block.get('identifier_ids')
    if block_ids is not None:
        return list(block_ids)

    explicit_ids = set()
    for other in task_blocks:
        if other.get('id') == block.get('id'):
            continue
        other_ids = other.get('identifier_ids')
        if other_ids:
            explicit_ids.update(other_ids)
    return [iid for iid in _identifier_ids(task_dict) if iid not in explicit_ids]


def _freeze_full_blocks_before_identifier_merge(existing):
    """동기화 전 전체 블록(None)을 기존 식별자 목록으로 고정한다.

    identifier_ids=None 블록은 "현재 태스크의 모든 식별자"를 뜻한다. 동기화로
    새 식별자가 추가되면 기존 블록에 새 식별자가 자동 포함되므로, 새 항목이
    큐로 남지 않는다. 동기화 직전의 실제 커버 범위를 명시 리스트로 저장해
    기존 일정은 그대로 두고 신규 식별자만 미배치 상태로 남긴다.
    """
    blocks = _task_blocks(existing['id'])
    for block in blocks:
        if block.get('identifier_ids') is not None:
            continue
        schedule_block.update(
            block['id'],
            identifier_ids=_block_identifier_ids(existing, block, blocks),
        )


def _merge_preserving_scheduled_removed(existing, incoming, warnings):
    """동기화에서 삭제된 식별자 중 이미 배치된 항목은 보존한다."""
    incoming_ids = {
        i.get('id') for i in incoming
        if isinstance(i, dict) and i.get('id')
    }
    scheduled_ids = _scheduled_identifier_ids(existing)
    merged = list(incoming)

    for old in existing.get('identifiers', []):
        if not isinstance(old, dict):
            continue
        old_id = old.get('id')
        if not old_id or old_id in incoming_ids:
            continue
        if old_id in scheduled_ids:
            merged.append(old)
            warnings.append(
                f"{existing.get('doc_name', '')} / {old_id}: "
                "이미 스케줄 블록에 배치되어 동기화 삭제를 건너뜀"
            )

    return merged


class SyncService:
    """외부 프로바이더와의 데이터 동기화를 수행하는 서비스 클래스."""

    @staticmethod
    def sync_versions(provider):
        """프로바이더로부터 버전 정보를 동기화한다."""
        external = provider.get_versions()
        external_ids = {v['id'] for v in external}
        existing = {v['id']: v for v in version.get_all()}
        added = updated = deactivated = 0

        for ext in external:
            if ext['id'] in existing:
                version.update(ext['id'], name=ext['name'],
                               description=ext.get('description', ''),
                               is_active=True)
                updated += 1
            else:
                version.create(name=ext['name'],
                               description=ext.get('description', ''),
                               id=ext['id'])
                added += 1

        for vid, v in existing.items():
            if vid not in external_ids and v.get('is_active', True):
                version.patch(vid, is_active=False)
                deactivated += 1

        return {'added': added, 'updated': updated, 'deactivated': deactivated}

    @staticmethod
    def sync_test_data(provider, version_id=None):
        """프로바이더로부터 시험 데이터를 동기화한다.

        std_list_cache.json의 exam_no 정보를 참조하여
        (doc_id, exam_no) 조합별로 태스크를 생성·갱신한다.
        캐시가 비어 있으면 exam_no=None 태스크 1개로 기존 방식대로 동작한다.

        Args:
            provider: BaseProvider 인스턴스.
            version_id: 특정 버전 ID로 제한. None이면 전체.

        Returns:
            dict: {'added': int, 'updated': int, 'deleted': int,
                   'cancelled': int, 'warnings': list}
        """
        try:
            if version_id:
                external = provider.get_test_data(version_id)
            else:
                external = provider.get_test_data_all()
        except NoChangesError as exc:
            return {'skipped': True, 'reason': 'no_change', 'updated_at': str(exc)}

        # exam_no 맵 구성: test_info → {exam_no, ...}
        # 항목에 이미 'exam_no' 키가 있으면(dyn_ready 형식) 이 맵은 사용하지 않는다.
        exam_no_map = {}
        for row in load_std_list_cache():
            ti = row.get('test_info', '')
            en = row.get('exam_no')
            if ti and en is not None:
                exam_no_map.setdefault(ti, set()).add(en)

        synced_combos = set()  # {(doc_id, exam_no)} 이번 sync에서 처리한 조합
        added = updated = deleted = 0
        warnings = []

        for item in external:
            try:
                doc_id = int(item.get('doc_id'))
            except (TypeError, ValueError):
                warnings.append(f"잘못된 doc_id, 건너뜀: {item}")
                continue

            doc_name = item.get('doc_name') or item.get('section_name', '')
            identifiers = item.get('identifiers', [])
            ver = (item.get('version_id')
                   or OfpidSettings.get_current_ofp_id()
                   or '')

            # dyn_ready 형식: item에 exam_no가 직접 포함 → 바로 사용
            if 'exam_no' in item:
                combos_to_sync = [(item['exam_no'], identifiers)]
            else:
                # 구 형식: std_list 캐시에서 exam_no 조회
                doc_exam_nos = set()
                for ident in identifiers:
                    ident_id = ident.get('id', '') if isinstance(ident, dict) else ident
                    doc_exam_nos.update(exam_no_map.get(ident_id, set()))

                if not doc_exam_nos:
                    combos_to_sync = [(None, identifiers)]
                else:
                    combos_to_sync = []
                    for exam_no in sorted(doc_exam_nos):
                        filtered = [
                            i for i in identifiers
                            if isinstance(i, dict)
                            and exam_no in exam_no_map.get(i.get('id', ''), set())
                        ]
                        combos_to_sync.append((exam_no, filtered))

            for exam_no, idents in combos_to_sync:
                est_minutes = sum(
                    i.get('estimated_minutes', 0)
                    for i in idents
                    if isinstance(i, dict)
                )
                synced_combos.add((doc_id, exam_no))

                existing = task.get_by_doc_and_exam(doc_id, exam_no)
                if existing:
                    _freeze_full_blocks_before_identifier_merge(existing)
                    idents = _merge_preserving_scheduled_removed(
                        existing, idents, warnings,
                    )
                    est_minutes = sum(
                        i.get('estimated_minutes', 0)
                        for i in idents
                        if isinstance(i, dict)
                    )
                    task.patch(existing['id'],
                               identifiers=idents,
                               estimated_minutes=est_minutes,
                               doc_name=doc_name,
                               version_id=ver)
                    updated += 1
                else:
                    task.create(
                        doc_id=doc_id,
                        exam_no=exam_no,
                        version_id=ver,
                        assignee_names=[],
                        location_id='',
                        doc_name=doc_name,
                        identifiers=idents,
                        estimated_minutes=est_minutes,
                    )
                    added += 1

        # 이번 sync 결과에 없는 (doc_id, exam_no) 조합은 삭제한다.
        # 단, 이미 스케줄 블록에 배치된 task는 삭제하지 않고 경고만 반환한다.
        for t in task.get_all():
            did = t.get('doc_id')
            if did is None:
                continue
            combo = (did, t.get('exam_no'))
            if combo not in synced_combos:
                if _task_blocks(t['id']):
                    warnings.append(
                        f"{t.get('doc_name', '')}: 이미 스케줄 블록에 배치되어 "
                        "동기화 삭제를 건너뜀"
                    )
                    continue
                task.delete(t['id'])
                deleted += 1

        return {'added': added, 'updated': updated,
                'deleted': deleted, 'cancelled': deleted,
                'warnings': warnings}
