# 데이터 아키텍처 상세 구현 스펙

이 문서는 `docs/data-architecture-redesign.md`를 실제 코드로 옮긴 현재 구현 규칙이다.
기본 JSON 운용은 유지하면서 compact snapshot, compact ORM, 외부 read API, 그리고 주요 화면 쓰기 경로의 DB-native 모드를 함께 제공한다.

## 1. 구현 범위

현재 구현은 다음을 포함한다.

1. 내부 ID 규칙과 compact JSON schema
2. 기존 JSON -> compact snapshot 변환 모듈
3. compact snapshot 파일/ORM repository
4. 외부 read-only API
5. schedule block, task catalog, execution run의 compact ORM 직접 쓰기
6. 일/주/月 schedule 화면, task 화면, execution 화면의 compact ORM read adapter
7. 기준정보/settings compact ORM 직접 쓰기
8. sync test-data의 compact catalog 직접 쓰기

## 2. 내부 ID 규칙

내부 ID는 저장소가 JSON이든 DB든 동일하게 사용한다.

| 엔티티 | prefix | 생성 기준 |
| --- | --- | --- |
| document | `doc_` | `version_id`, `doc_id` |
| test item | `ti_` | `document_id`, `external_test_id` |
| exam attempt | `ea_` | `test_item_id`, `exam_no` |
| schedule block | `blk_` | legacy block id |
| schedule block item | `bi_` | `block_id`, `exam_attempt_id` |
| execution run | `run_` | legacy execution id |

ID는 deterministic hash로 만든다.
같은 legacy 입력을 여러 번 변환해도 같은 ID가 나와야 한다.

## 3. Compact JSON schema

### 3.1 `catalog.json`

```json
{
  "schema_version": "1.0",
  "documents": [],
  "test_items": [],
  "exam_attempts": [],
  "sync": {
    "provider": "",
    "updated_at": "",
    "data_hash": ""
  },
  "migration": {
    "warnings": []
  }
}
```

`documents[]`:

| 필드 | 설명 |
| --- | --- |
| `id` | 내부 document ID |
| `legacy_task_ids` | 이 문서로부터 생성된 기존 task ID 목록 |
| `external_doc_id` | 기존 `task.doc_id` |
| `version_id` | 기존 `task.version_id` |
| `doc_name` | 문서명 |
| `is_active` | 기본 `true` |

`test_items[]`:

| 필드 | 설명 |
| --- | --- |
| `id` | 내부 test item ID |
| `document_id` | 상위 문서 ID |
| `external_test_id` | 기존 식별자 ID |
| `name` | 시험 항목명 |
| `estimated_minutes` | 예상 시간 |
| `total_count` | 전체 건수 |
| `owner_names` | 작성자 목록 |
| `is_active` | 기본 `true` |

`exam_attempts[]`:

| 필드 | 설명 |
| --- | --- |
| `id` | 내부 attempt ID |
| `test_item_id` | 상위 test item ID |
| `exam_no` | 시험 차수 |
| `legacy_task_id` | 기존 task ID |
| `legacy_identifier_id` | 기존 식별자 ID |
| `default_location_id` | 기존 task 기본 장소 |
| `default_assignee_names` | 기존 task 담당자 |
| `memo` | task 메모 |
| `state` | `active` 또는 `cancelled` |

### 3.2 `schedule.json`

```json
{
  "schema_version": "1.0",
  "blocks": [],
  "block_items": [],
  "migration": {
    "warnings": []
  }
}
```

`blocks[]`:

| 필드 | 설명 |
| --- | --- |
| `id` | 내부 block ID |
| `legacy_block_id` | 기존 block ID |
| `date`, `start_time`, `end_time` | 배치 시간 |
| `location_id` | 장소 |
| `assignee_names` | 담당자 |
| `kind` | `test` 또는 `simple` |
| `title` | 단순 일정 제목 |
| `memo` | block 메모 |
| `is_locked` | 잠금 여부 |
| `manual_status` | 기존 `block_status`가 `cancelled`일 때만 `cancelled`, 그 외 빈 문자열 |
| `overflow_minutes` | 초과 시간 |

`block_items[]`:

| 필드 | 설명 |
| --- | --- |
| `id` | 내부 block item ID |
| `block_id` | 내부 block ID |
| `exam_attempt_id` | 내부 attempt ID |
| `sort_order` | block 안 순서 |

### 3.3 `executions.json`

```json
{
  "schema_version": "1.0",
  "runs": [],
  "migration": {
    "warnings": []
  }
}
```

`runs[]`:

| 필드 | 설명 |
| --- | --- |
| `id` | 내부 run ID |
| `legacy_execution_id` | 기존 execution ID |
| `exam_attempt_id` | 내부 attempt ID |
| `status` | `pending`, `in_progress`, `paused`, `completed` |
| `segments` | 기존 segment 배열 |
| `total_count`, `fail_count`, `block_count`, `pass_count` | 결과 카운트 |
| `comment` | 코멘트 |
| `performer_name` | 수행자 |
| `created_at`, `completed_at` | 시각 |
| `elapsed_seconds_snapshot`, `elapsed_mins_snapshot` | 기존 경과 시간 스냅샷 |

### 3.4 `resources.json`

```json
{
  "schema_version": "1.0",
  "users": [],
  "locations": [],
  "versions": []
}
```

기준정보는 1차 구현에서 기존 구조를 그대로 복사한다.

### 3.5 `settings.json`

기존 `settings.json`을 복사하되 `schema_version`과 `provider_cache`를 추가할 수 있다.

## 4. 변환 규칙

### 4.1 task -> catalog

1. 같은 `(version_id, doc_id)`는 하나의 document가 된다.
2. 같은 document 안의 같은 `identifier.id`는 하나의 test item이 된다.
3. 각 `(test_item, exam_no)`는 하나의 exam attempt가 된다.
4. 기존 task의 `status='cancelled'`는 attempt `state='cancelled'`로 옮긴다.
5. `remaining_minutes`는 저장하지 않는다.

### 4.2 block -> schedule

1. 모든 기존 block은 새 block이 된다.
2. `is_simple=true` 또는 `task_id`가 없으면 `kind='simple'`이고 block item은 만들지 않는다.
3. `identifier_ids=null`이면 해당 task의 모든 identifier attempt를 block item으로 만든다.
4. `identifier_ids`가 배열이면 해당 식별자 attempt만 block item으로 만든다.
5. 연결할 attempt를 찾지 못하면 block은 유지하고 warning을 남긴다.
6. 기존 `block_status='cancelled'`만 `manual_status='cancelled'`로 옮긴다.

### 4.3 execution -> executions

1. `(task_id, identifier_id)`로 exam attempt를 찾는다.
2. 찾으면 execution run으로 변환한다.
3. 찾지 못하면 run은 만들지 않고 warning을 남긴다.
4. `segments`는 JSON 구현에서는 run 안에 nested로 둔다.

## 5. 외부 제공 규칙

외부 시스템이 가져갈 데이터는 compact 저장 파일을 그대로 읽게 하지 않는다.
외부에는 `/api/external/v1/*` 또는 `exports/*` snapshot을 제공한다.

1차 구현에서는 CLI와 read-only API가 같은 변환 결과를 사용한다.

| 경로 | 역할 |
| --- | --- |
| `app/services/compact_migration.py` | legacy in-memory 데이터 -> compact snapshot 변환 |
| `app/services/compact_snapshot_files.py` | legacy JSON 파일 읽기와 compact snapshot 파일 쓰기 |
| `app/services/read_models.py` | compact snapshot 기반 조회/내보내기 row 생성 |
| `app/db/models.py` | compact domain SQLAlchemy ORM table mapping |
| `app/db/repository.py` | compact snapshot ORM repository |
| `app/repositories/compact_snapshot.py` | snapshot source 선택 factory (`json`/`orm`) |
| `app/repositories/orm_file_storage.py` | 기존 파일 모양 payload를 ORM에 저장하는 전환용 storage |
| `app/services/compact_snapshot_storage.py` | storage adapter payload -> compact snapshot 변환 |
| `app/services/compact_orm_sync.py` | ORM storage payload -> compact ORM 테이블 동기화 |
| `app/services/compact_consistency.py` | ORM storage payload와 compact ORM snapshot 정합성 검사 |
| `app/services/compact_schedule_commands.py` | compact ORM schedule block command service |
| `app/features/schedule/services/compact_blocks.py` | 기존 schedule block API payload와 compact ORM command 사이의 호환 계층 |
| `app/features/schedule/services/compact_tasks.py` | task API/sync payload와 compact catalog ORM command 사이의 호환 계층 |
| `app/features/schedule/repositories.py` | schedule model storage adapter (`json`/`orm`) |
| `app/features/execution/repositories.py` | execution record storage adapter (`json`/`orm`) |
| `scripts/build_compact_snapshot.py` | `exports/compact-snapshot/*.json` 생성 CLI |
| `scripts/migrate_legacy_to_db.py` | legacy JSON -> compact ORM DB 적재 CLI |
| `scripts/migrate_legacy_storage_to_orm.py` | legacy JSON storage -> ORM storage payload 적재 CLI |
| `scripts/check_compact_consistency.py` | ORM storage와 compact ORM 정합성 검사 CLI |
| `scripts/compact_schedule_block.py` | compact ORM schedule block 직접 쓰기 CLI |
| `app/features/external_data/routes.py` | `/api/external/v1/*` read-only API |

현재 제공 API:

| API | 설명 |
| --- | --- |
| `GET /api/external/v1/snapshot` | 전체 compact snapshot |
| `GET /api/external/v1/catalog` | catalog만 조회 |
| `GET /api/external/v1/schedule?start_date=...&end_date=...` | 기간별 schedule, block item, export row |
| `GET /api/external/v1/executions?date=...&location=...` | 실행 목록 read model |
| `GET /api/external/v1/metadata` | schema version, 생성 시각, count, sync 정보 |

외부 API의 데이터 원본은 설정으로 선택한다.

| 설정 | 값 | 설명 |
| --- | --- | --- |
| `EXTERNAL_DATA_SOURCE` | `json` | 기본값. legacy JSON 파일에서 compact snapshot을 즉시 생성 |
| `EXTERNAL_DATA_SOURCE` | `orm` | `DATABASE_URL`의 ORM DB에서 compact snapshot 조회 |
| `DATABASE_URL` | SQLAlchemy URL | 기본값은 `sqlite:///app/data/scheduling.sqlite3` |
| `SCHEDULE_STORAGE` | `json`, `orm`, `compact_orm` | schedule 쓰기 저장소. `compact_orm`은 schedule block 핵심 API부터 compact ORM 테이블에 직접 기록 |
| `EXECUTION_STORAGE` | `json`, `orm`, `compact_orm` | execution record CRUD 저장소. `compact_orm`은 `execution_runs`에 직접 기록 |
| `SYNC_COMPACT_ON_ORM_STORAGE_WRITE` | `1` 또는 `0` | ORM storage 저장 후 compact ORM 자동 갱신 여부 |

DB 적재 예시:

```bash
python3 scripts/migrate_legacy_to_db.py --database-url sqlite:///app/data/scheduling.sqlite3 --drop-existing
EXTERNAL_DATA_SOURCE=orm python3 run.py
```

기존 화면의 쓰기 경로를 ORM storage로 검증할 때:

```bash
python3 scripts/migrate_legacy_storage_to_orm.py --database-url sqlite:///app/data/scheduling.sqlite3
SCHEDULE_STORAGE=orm EXECUTION_STORAGE=orm EXTERNAL_DATA_SOURCE=orm python3 run.py
```

`migrate_legacy_storage_to_orm.py`는 `storage_payloads` 적재 후 compact ORM 테이블도 한 번 갱신한다. 실행 중에는 `SYNC_COMPACT_ON_ORM_STORAGE_WRITE=1`이 기본값이라 ORM storage 저장마다 compact ORM snapshot이 갱신된다.

`SCHEDULE_STORAGE=compact_orm`은 `storage_payloads`를 거치지 않고 정규화된 compact ORM 테이블(`schedule_blocks`, `block_items`)에 직접 기록한다. 현재 연결된 화면 경로는 schedule 일/주/月 HTML 뷰, `/schedule/api/day`, `/schedule/api/week`, `/schedule/api/month`, `/schedule/api/export`, `/schedule/api/blocks`의 생성, 수정, 삭제, `/lock`, `/status`, `/memo`, `/by-task`, `/shift`, `/split`, `/return-identifiers`다. 실행 목록 화면과 `/execution/api/list`, `/execution/api/item`, `/execution/api/total-count`도 compact snapshot을 읽는다. 기존 화면 API와 호환되도록 서비스 계층에서 legacy `task_id`/`identifier_ids`를 compact `exam_attempt_id`로 변환하고, 응답에는 기존 `block_status` 이름을 유지한다.

admin 기준정보(`users`, `locations`, `versions`)와 `settings`는 `SCHEDULE_STORAGE=compact_orm`에서 compact ORM resource/settings 테이블에 직접 쓴다. task 목록/상세는 compact catalog에서 legacy 화면 형태로 읽기 projection을 제공한다. task 생성/수정/삭제와 sync test-data 쓰기는 compact catalog command가 `source_documents`, `test_items`, `exam_attempts`를 직접 갱신한다.

자동 갱신은 가능한 범위에서 부분 교체를 사용한다. 독립 리소스(`users`, `locations`, `versions`)와 `settings`는 compact ORM 테이블을 직접 갱신하고, 관계 재계산이 필요한 `tasks`, `schedule_blocks`, `executions`만 관련 섹션을 재생성한다.

정합성 점검:

```bash
python3 scripts/check_compact_consistency.py --database-url sqlite:///app/data/scheduling.sqlite3
```

DB-native schedule block 쓰기 검증:

```bash
python3 scripts/compact_schedule_block.py --database-url sqlite:///app/data/scheduling.sqlite3 create \
  --date 2026-08-01 --start-time 09:00 --end-time 09:30 --attempt-id ea_xxx
```

DB-native execution 쓰기는 다음 설정으로 사용한다.

```bash
SCHEDULE_STORAGE=compact_orm EXECUTION_STORAGE=compact_orm EXTERNAL_DATA_SOURCE=orm python3 run.py
```

이 모드에서 실행 시작, 일시정지, 재개, 완료, 코멘트, 수행자, 초기화는 compact ORM `execution_runs` 테이블에 직접 반영된다.
