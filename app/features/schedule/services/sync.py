"""동기화 서비스 — 외부 프로바이더 데이터를 로컬 모델에 병합한다.

외부 데이터 소스(프로바이더)로부터 버전 정보와 시험 데이터를 가져와
로컬 JSON 파일 기반 모델에 추가/갱신/비활성화하는 기능을 제공한다.
"""

from app.features.schedule.models import version, task


class SyncService:
    """외부 프로바이더와의 데이터 동기화를 수행하는 서비스 클래스.

    정적 메서드로 구성되어 인스턴스 생성 없이 사용 가능하다.
    """

    @staticmethod
    def sync_versions(provider):
        """프로바이더로부터 버전 정보를 동기화한다.

        외부에 존재하는 버전은 추가 또는 갱신하고,
        외부에 더 이상 없는 버전은 비활성화(is_active=False) 처리한다.

        Args:
            provider: BaseProvider 인터페이스를 구현한 프로바이더 인스턴스.

        Returns:
            dict: {'added': int, 'updated': int, 'deactivated': int}
                동기화 결과 통계.
        """
        external = provider.get_versions()
        external_ids = {v['id'] for v in external}
        existing = {v['id']: v for v in version.get_all()}
        added = updated = deactivated = 0

        for ext in external:
            if ext['id'] in existing:
                # 기존 버전: 이름·설명 갱신 및 활성화
                version.update(ext['id'], name=ext['name'],
                               description=ext.get('description', ''),
                               is_active=True)
                updated += 1
            else:
                # 신규 버전: 생성
                version.create(name=ext['name'],
                               description=ext.get('description', ''),
                               id=ext['id'])
                added += 1

        # 외부에 없는 기존 활성 버전은 비활성화
        for vid, v in existing.items():
            if vid not in external_ids and v.get('is_active', True):
                version.patch(vid, is_active=False)
                deactivated += 1

        return {'added': added, 'updated': updated, 'deactivated': deactivated}

    @staticmethod
    def sync_test_data(provider, version_id=None):
        """프로바이더로부터 시험 데이터를 동기화한다.

        외부 데이터의 doc_id를 키로 사용하여 태스크를 매칭하고,
        식별자(identifiers)와 예상 시간을 갱신한다.
        외부에서 사라진 태스크는 'cancelled' 상태로 변경한다.

        Args:
            provider: BaseProvider 인터페이스를 구현한 프로바이더 인스턴스.
            version_id: 특정 버전 ID로 제한. None이면 전체 버전 대상.

        Returns:
            dict: {'added': int, 'updated': int, 'cancelled': int, 'warnings': list}
                동기화 결과 통계 및 경고 메시지 목록.
        """
        if version_id:
            external = provider.get_test_data(version_id)
        else:
            external = provider.get_test_data_all()

        external_doc_ids = set()  # 외부에 존재하는 doc_id 집합
        added = updated = cancelled = 0
        warnings = []

        for item in external:
            try:
                doc_id = int(item.get('doc_id'))
            except (TypeError, ValueError):
                warnings.append(f"잘못된 doc_id, 건너뜀: {item}")
                continue
            external_doc_ids.add(doc_id)

            doc_name = item.get('doc_name') or item.get('section_name', '')
            identifiers = item.get('identifiers', [])
            # 각 식별자의 예상 시간을 합산하여 태스크 전체 예상 시간 계산
            est_minutes = sum(i.get('estimated_minutes', 0) for i in identifiers)

            existing = task.get_by_doc_id(doc_id)
            if existing:
                # 기존 태스크 갱신: 식별자 목록, 예상 시간, 문서명
                task.patch(existing['id'],
                           identifiers=identifiers,
                           estimated_minutes=est_minutes,
                           doc_name=doc_name,
                           version_id=item.get('version_id', existing.get('version_id', '')))
                updated += 1
            else:
                # 신규 태스크 생성
                task.create(
                    doc_id=doc_id,
                    version_id=item.get('version_id', ''),
                    assignee_names=[],
                    location_id='',
                    doc_name=doc_name,
                    identifiers=identifiers,
                    estimated_minutes=est_minutes,
                )
                added += 1

        # 외부에서 사라진 태스크를 취소 처리
        for t in task.get_all():
            did = t.get('doc_id')
            if (did is not None
                    and did not in external_doc_ids
                    and t.get('status') != 'cancelled'):
                task.patch(t['id'], status='cancelled')
                cancelled += 1

        return {'added': added, 'updated': updated,
                'cancelled': cancelled, 'warnings': warnings}
