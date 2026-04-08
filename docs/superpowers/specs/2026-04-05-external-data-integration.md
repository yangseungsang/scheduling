# 외부 데이터 통합 설계

## Context
시험 데이터(식별자, 작성자), 소프트웨어 버전은 외부 시스템이 원본이다. 이 앱은 일정 배치만 담당한다. 연동 방식은 미정이므로, 어떤 방식이든 붙일 수 있는 Provider 추상화를 도입한다.

## 데이터 소유권

| 데이터 | 소유자 | 이 앱에서 | 비고 |
|--------|--------|----------|------|
| 버전 | **외부** | 읽기 전용 | 동기화로 가져옴 |
| 시험식별자/작성자 | **외부** | 읽기 전용 | test_list, owners |
| 장절명 | **외부** | 읽기 전용 | section_name |
| 팀원 | 이 앱 | CRUD | assignee_ids |
| 장소 | 이 앱 | CRUD | location_id |
| 일정 블록 | 이 앱 | CRUD | schedule_blocks |
| 설정 | 이 앱 | CRUD | settings |

## 1. Provider 인터페이스

### schedule/providers/base.py
```python
class BaseProvider(ABC):
    @abstractmethod
    def get_versions(self) -> list[dict]:
        """[{"id": "VER-001", "name": "v1.0.0", "description": "..."}]"""

    @abstractmethod
    def get_test_data(self, version_id: str) -> list[dict]:
        """버전별 시험 데이터 반환"""

    @abstractmethod
    def get_test_data_all(self) -> list[dict]:
        """전체 시험 데이터 반환"""
```

### 반환 형식
```json
// get_test_data()
[{
    "section_name": "3.1 시스템 초기화",
    "version_id": "VER-001",
    "identifiers": [
        {"id": "TC-001", "estimated_hours": 0.783, "owners": ["김민수"]}
    ]
}]
```

### 구현체
- **JsonFileProvider** (schedule/providers/json_file.py) — 현재 동작 호환, 기본값
- 향후: RestApiProvider, FileImportProvider 등 추가 가능

### 설정
```python
# schedule/__init__.py
PROVIDER_TYPE = os.environ.get('PROVIDER_TYPE', 'json_file')
```

## 2. 동기화 서비스

### schedule/services/sync.py

**SyncService.sync_versions(provider):**
- Provider에서 버전 목록 가져옴
- 새 버전 → 추가 (외부 ID 그대로 사용)
- 기존 버전 → 이름/설명 업데이트
- 삭제된 버전 → is_active=False (삭제하지 않음)

**SyncService.sync_test_data(provider, version_id=None):**
- Provider에서 시험 데이터 가져옴
- 매칭 기준: section_name + version_id 조합
- 새 장절 → task 생성 (source='external')
- 기존 장절 → 식별자/작성자 업데이트 (이 앱이 추가한 assignee_ids, location_id, 일정은 보존)
- 삭제된 장절 → status='cancelled' (삭제하지 않음, 배치된 블록 보존)

**충돌 규칙:**
- 이미 배치된 블록이 있는 task의 식별자가 변경되면 → 블록 유지, 경고 반환
- 외부 데이터는 절대 삭제 안 함 (비활성화/취소만)

### 동기화 API (schedule/routes/sync.py)
```
POST /api/sync/versions     — Provider에서 버전 동기화
POST /api/sync/test-data    — Provider에서 시험 데이터 동기화
GET  /api/sync/status       — 마지막 동기화 시간, 변경 요약
```

## 3. 모델 변경

### version.py
- `create()` — id 파라미터 추가 (외부 ID 허용, 없으면 자동 생성)

### task.py
- `source` 필드 추가: `'external'` (동기화로 생성) / `'local'` (수동 생성)
- `external_key` 필드 추가: `section_name + '::' + version_id` (매칭 키)

### schedule_block.py, user.py, location.py, settings.py
- **변경 없음**

## 4. UI 변경

### 버전 관리 (admin/versions.html)
- 직접 생성/삭제 비활성화 → "동기화" 버튼으로 대체
- 수동 생성은 유지하되 로컬 전용으로 표시

### 시험항목 폼 (tasks/form.html)
- source=='external'인 task → 장절명, 식별자 테이블, 작성자 필드 읽기 전용
- assignee_ids, location_id, memo는 편집 가능 (이 앱 소유 필드)

### 시험항목 목록 (tasks/list.html)
- 외부 원본 항목에 "외부" 뱃지 표시

## 5. 변경하지 않는 범위 (사이드이펙트 방지)

- schedule_block 모델 및 calendar API — 블록 CRUD 로직 불변
- JS 모듈 10개 — 드래그앤드롭, 리사이즈, 팝업 로직 불변
- enrichment.py — 데이터 가공 로직 불변
- overlap.py, time_utils.py — 헬퍼 불변
- CSS — 스타일 불변

## 6. 새 파일 목록

| 파일 | 역할 |
|------|------|
| schedule/providers/__init__.py | 패키지 + get_provider() 팩토리 |
| schedule/providers/base.py | BaseProvider ABC |
| schedule/providers/json_file.py | JsonFileProvider |
| schedule/services/sync.py | SyncService |
| schedule/routes/sync.py | 동기화 API 라우트 |
| tests/test_providers.py | Provider 테스트 |
| tests/test_sync.py | 동기화 서비스 테스트 |

## 7. 데이터 마이그레이션

기존 tasks.json에 `source`, `external_key` 필드 추가:
- 기존 task → source='local', external_key=''
- 동기화 후 → source='external', external_key='section_name::version_id'

기존 versions.json:
- 기존 v_xxx ID 유지 (하위 호환)
- 새로 동기화된 버전은 외부 ID 그대로 사용

## 8. 테스트 전략

- **test_providers.py**: JsonFileProvider 읽기 동작
- **test_sync.py**: 버전 동기화 (추가/업데이트/비활성화), 시험 데이터 동기화 (추가/업데이트/취소), 충돌 감지 (배치된 블록 있는 task 변경)
- **기존 149개 테스트**: 모두 통과 필수 (사이드이펙트 없음 확인)
