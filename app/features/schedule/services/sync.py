"""동기화 서비스 — 외부 프로바이더 데이터를 로컬 모델에 병합한다.

외부 데이터 소스(프로바이더)로부터 버전 정보와 시험 데이터를 가져와
로컬 JSON 파일 기반 모델에 추가/갱신/비활성화하는 기능을 제공한다.
exam_no 기반 태스크 분리: std_list_cache.json의 데이터를 참조하여
(doc_id, exam_no) 조합별로 독립 태스크를 생성한다.
"""

from app.features.schedule.models import version, task
from app.features.schedule.providers.base import NoChangesError
from app.config import OfpidSettings


def load_std_list_cache():
    """std_list 로컬 캐시를 읽어 반환한다. 없으면 []."""
    from app.features.schedule.models.std_list import load_cache
    return load_cache()


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
            dict: {'added': int, 'updated': int, 'cancelled': int, 'warnings': list}
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
        added = updated = cancelled = 0
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

        # 이번 sync 결과에 없는 (doc_id, exam_no) 조합을 취소 처리
        for t in task.get_all():
            did = t.get('doc_id')
            if did is None:
                continue
            combo = (did, t.get('exam_no'))
            if combo not in synced_combos and t.get('status') != 'cancelled':
                task.patch(t['id'], status='cancelled')
                cancelled += 1

        return {'added': added, 'updated': updated,
                'cancelled': cancelled, 'warnings': warnings}
