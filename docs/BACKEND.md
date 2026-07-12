# Backend 기술 문서

이 문서는 Flask 백엔드의 구조, 데이터 접근 방식, API, 동기화 흐름을 단계별로 설명한다.

## 1. 전체 흐름

1. `run.py`가 `app.create_app()`을 호출한다.
2. `app/__init__.py`가 Flask 앱을 만들고 `DATA_DIR`, `EXECUTION_DATA_DIR`, `SECRET_KEY`를 설정한다.
3. `app.features.schedule.register_blueprints(app)`가 스케줄 관련 블루프린트를 등록한다.
4. `app.features.execution.register_blueprints(app)`가 실행 관련 블루프린트를 등록한다.
5. 브라우저 요청은 Jinja2 페이지 라우트 또는 JSON API 라우트로 들어온다.
6. 라우트는 모델/서비스/헬퍼를 호출하고, 모델은 JSON 파일 저장소를 읽고 쓴다.

루트 URL `/`은 `/schedule/week`로 리다이렉트된다.

## 2. 애플리케이션 설정

| 항목 | 위치 | 설명 |
| --- | --- | --- |
| `SECRET_KEY` | `app/__init__.py` | Flask 세션 키. 환경 변수 없으면 `dev-secret-key`. 운영 환경에서는 반드시 교체한다. |
| `DATA_DIR` | `app/__init__.py` | 스케줄 데이터 경로. 기본값은 `app/features/schedule/data`. |
| `EXECUTION_DATA_DIR` | `app/__init__.py` | 실행 데이터 경로. 기본값은 `app/features/execution/data`. |
| `SEND_FILE_MAX_AGE_DEFAULT` | `app/__init__.py` | 개발 편의를 위해 정적 파일 캐시를 끈다. |
| `cache_bust` | Jinja 전역 | 서버 시작 시각. 정적 파일 URL 캐시 무효화에 사용한다. |

모든 응답에는 개발 편의를 위한 CORS 헤더가 추가된다.

## 3. 블루프린트

| 블루프린트 | prefix | 파일 | 역할 |
| --- | --- | --- | --- |
| `schedule` | `/schedule` | `calendar_views.py`, `calendar_api.py` | 일/주/월 캘린더 페이지와 블록 API |
| `tasks` | `/tasks` | `tasks.py` | 시험 항목 페이지와 task API |
| `admin` | `/admin` | `admin.py` | 설정, 사용자, 장소 페이지와 기준정보 JSON API. 버전은 현재 JSON API만 등록 |
| `sync` | `/api/sync` | `sync.py` | 외부/로컬 데이터 동기화 |
| `execution` | `/execution` | `views.py` | 실행 목록/상세 페이지 |
| `execution_api` | `/execution/api` | `api.py` | 실행 타이머와 결과 API |

## 4. 저장소 계층

### 4.1 공통 JSON 저장

스케줄 도메인은 `app/features/schedule/store.py`, 실행 도메인은 `app/features/execution/store.py`를 사용한다.

1. `_get_path(filename)`이 Flask config의 데이터 디렉터리와 파일명을 합친다.
2. `read_json(filename)`은 파일이 없거나 비어 있으면 기본값을 반환한다.
3. `write_json(filename, data)`는 기존 파일을 `.bak`으로 복사한 뒤 JSON을 저장한다.
4. 읽기/쓰기는 `portalocker.Lock(..., timeout=5)`로 보호된다.

`settings.json`만 객체(dict)이며, 나머지 영속 데이터 파일은 배열(list)이다.

### 4.2 BaseRepository

`app/features/schedule/models/base.py`의 `BaseRepository`는 JSON 배열 파일에 대한 공통 CRUD를 제공한다.

| 메서드 | 설명 |
| --- | --- |
| `get_all()` | 전체 배열 반환 |
| `get_by_id(item_id)` | `id`가 일치하는 단일 항목 반환 |
| `create(data)` | ID가 없으면 `ID_PREFIX`로 생성 후 저장 |
| `patch(item_id, **kwargs)` | 허용 필드만 부분 수정 |
| `delete(item_id)` | ID 기준 삭제 |
| `filter_by(**kwargs)` | 모든 조건이 일치하는 항목 필터 |

## 5. 스케줄 모델

| 모델 | 파일 | 데이터 파일 | ID 접두사 | 핵심 필드/메서드 |
| --- | --- | --- | --- | --- |
| `TaskRepository` | `task.py` | `tasks.json` | `t_` | `doc_id`, `exam_no`, `identifiers`, `remaining_minutes`, `get_by_doc_and_exam()` |
| `ScheduleBlockRepository` | `schedule_block.py` | `schedule_blocks.json` | `sb_` | `task_id`, `date`, `start_time`, `end_time`, `identifier_ids`, `block_status` |
| `UserRepository` | `user.py` | `users.json` | `u_` | `name`, `role`, `color` |
| `LocationRepository` | `location.py` | `locations.json` | `loc_` | `name`, `color`, `description` |
| `VersionRepository` | `version.py` | `versions.json` | `v_` | `is_active`, `get_active()` |
| `SettingsRepository` | `settings.py` | `settings.json` | 없음 | 전역 설정 단일 객체 |

`TaskRepository.create()`는 일반 진행 상태를 저장하지 않는다. 진행 상태는 `executions.json`의 실행 레코드로 계산한다. `status='cancelled'`는 외부 동기화에서 삭제/취소된 task를 표시할 때만 예외적으로 사용한다.

`ScheduleBlockRepository.block_status`는 저장 필드지만, 화면 렌더링 시 일반 블록은 execution 상태로 다시 계산된다. 저장된 `cancelled`만 수동 상태로 우선 보존된다.

`SettingsRepository.block_color_by`는 `assignee`, `location`, `status`를 지원한다.

## 6. 실행 모델

`app/features/execution/models/execution.py`의 `ExecutionRepository`가 식별자별 실행 상태를 관리한다.

상태 흐름:

```text
pending(레코드 없음 또는 pending 레코드) -> in_progress -> paused -> in_progress -> completed
```

핵심 규칙:

1. 실행 레코드는 `(identifier_id, task_id)` 조합으로 조회한다.
2. 같은 식별자가 여러 시험 차수(`exam_no`)나 task에 존재할 수 있으므로 `identifier_id`만으로는 충분하지 않다.
3. 타이머 시간은 `segments[]`의 구간 합으로 계산한다.
4. `pause()`는 열린 segment의 `end`를 닫는다.
5. `resume()`은 새 열린 segment를 추가한다.
6. `complete()`은 열린 segment만 닫고, `pass_count = total_count - fail_count - block_count`로 계산한다.
7. 완료 후 `API_BASE_URL`이 있으면 `/update_test_time`으로 소요 시간을 비동기 전송한다.
8. `/pending-comment`와 `/reset`은 `pending` 상태 execution 레코드를 저장할 수 있다.

## 7. 주요 API

### 7.1 캘린더 페이지/API

| Method | URL | 설명 |
| --- | --- | --- |
| `GET` | `/schedule/` | 일간 뷰 |
| `GET` | `/schedule/week` | 주간 뷰 |
| `GET` | `/schedule/month` | 월간 뷰 |
| `GET` | `/schedule/api/day` | 일간 JSON |
| `GET` | `/schedule/api/week` | 주간 JSON |
| `GET` | `/schedule/api/month` | 월간 JSON |

### 7.2 블록 API

| Method | URL | 설명 |
| --- | --- | --- |
| `POST` | `/schedule/api/blocks` | 큐 항목을 시간표에 배치 |
| `PUT` | `/schedule/api/blocks/<block_id>` | 이동/리사이즈/날짜 변경 |
| `DELETE` | `/schedule/api/blocks/<block_id>` | 블록 삭제. `?restore=1`이면 큐 복귀 |
| `PUT` | `/schedule/api/blocks/<block_id>/lock` | 잠금 토글 |
| `PUT` | `/schedule/api/blocks/<block_id>/status` | 상태 변경 |
| `PUT` | `/schedule/api/blocks/<block_id>/memo` | 메모 저장 |
| `POST` | `/schedule/api/simple-blocks` | 시험 외 단순 블록용 큐 task 생성 |
| `GET` | `/schedule/api/blocks/by-task/<task_id>` | task에 연결된 블록 조회 |
| `POST` | `/schedule/api/blocks/shift` | 특정 날짜 이후 일정 밀기/당기기 |
| `POST` | `/schedule/api/blocks/<block_id>/split` | 블록 식별자 분리 |
| `POST` | `/schedule/api/blocks/<block_id>/return-identifiers` | 일부 식별자를 큐로 복귀 |
| `GET` | `/schedule/api/export` | CSV/XLSX 내보내기 |

### 7.3 Task API

| Method | URL | 설명 |
| --- | --- | --- |
| `GET` | `/tasks/` | task 목록 페이지 |
| `GET/POST` | `/tasks/new` | task 생성 폼 |
| `GET` | `/tasks/<task_id>` | task 상세 |
| `GET/POST` | `/tasks/<task_id>/edit` | task 수정 |
| `POST` | `/tasks/<task_id>/delete` | task 삭제 |
| `GET` | `/tasks/api/list` | task 목록 JSON |
| `GET` | `/tasks/api/<task_id>` | task 단건 JSON |
| `POST` | `/tasks/api/create` | task 생성 API |
| `PUT` | `/tasks/api/<task_id>/update` | task 수정 API |
| `DELETE` | `/tasks/api/<task_id>/delete` | task 삭제 API |
| `GET` | `/tasks/api/procedure/<doc_id>` | 절차 원본 조회 |
| `GET` | `/tasks/api/check-identifier` | 식별자 중복 검사 |

### 7.4 Admin API

| Method | URL | 설명 |
| --- | --- | --- |
| `GET/POST` | `/admin/settings` | 설정 페이지/폼 저장 |
| `GET` | `/admin/users`, `/admin/locations` | 사용자/장소 목록 |
| `GET/POST` | `/admin/users/new`, `/admin/locations/new` | 사용자/장소 생성 |
| `GET/POST` | `/admin/users/<id>/edit`, `/admin/locations/<id>/edit` | 사용자/장소 수정 |
| `POST` | `/admin/users/<id>/delete`, `/admin/locations/<id>/delete` | 사용자/장소 삭제 |
| `GET/PUT` | `/admin/api/settings` | 설정 조회/수정 |
| `GET/POST` | `/admin/api/users`, `/admin/api/locations`, `/admin/api/versions` | 기준 데이터 조회/생성 |
| `PUT/DELETE` | `/admin/api/users/<id>`, `/admin/api/locations/<id>`, `/admin/api/versions/<id>` | 기준 데이터 수정/삭제 |
| `POST` | `/admin/api/project-reset` | 프로젝트 데이터 초기화 |

### 7.5 Sync API

| Method | URL | 설명 |
| --- | --- | --- |
| `POST` | `/api/sync/versions` | provider의 버전 목록 동기화 |
| `POST` | `/api/sync/test-data` | provider의 시험 데이터 동기화 |
| `POST` | `/api/sync/reset-and-sync` | 기존 동기화 데이터 초기화 후 재동기화 |
| `GET` | `/api/sync/status` | 동기화 상태 조회 |
| `POST` | `/api/sync/std-list` | MySQL `std_list`를 `std_list_cache.json`으로 저장 |

### 7.6 Execution API

| Method | URL | 설명 |
| --- | --- | --- |
| `GET` | `/execution/` | 실행 목록 페이지 |
| `GET` | `/execution/<identifier_id>?task_id=<task_id>` | 실행 상세 페이지. `task_id`로 재시험/동일 식별자를 구분 |
| `GET` | `/execution/api/list` | 실행 항목 목록 JSON. 기본은 전체 task 식별자, `date`/`location` 쿼리는 배치 block 기준 필터 |
| `GET` | `/execution/api/item/<identifier_id>?task_id=<task_id>` | 실행 항목 단건 JSON. `task_id` 선택 지원 |
| `GET` | `/execution/api/total-count/<identifier_id>?task_id=<task_id>` | 식별자의 전체 시험 건수. `task_id` 선택 지원 |
| `GET` | `/execution/api/whoami` | 세션 수행자 조회 |
| `POST` | `/execution/api/login` | 세션 수행자 저장 |
| `POST` | `/execution/api/start` | 실행 시작 또는 재시작 |
| `POST` | `/execution/api/pause` | 일시정지 |
| `POST` | `/execution/api/resume` | 재개 |
| `POST` | `/execution/api/complete` | 완료 처리 |
| `PUT` | `/execution/api/pending-comment` | 실행 전 코멘트 저장 |
| `PUT` | `/execution/api/comment` | 실행 레코드 코멘트 저장 |
| `PUT` | `/execution/api/performer` | 수행자 저장 |
| `PATCH` | `/execution/api/timing/<identifier_id>` | 외부/수동 소요 시간 반영. 선택적으로 `doc_name`, `identifier_name` 검증. 해당 식별자의 `estimated_minutes`와 task 합계를 갱신 |
| `POST` | `/execution/api/reset` | 실행 레코드 초기화 |

## 8. 동기화 흐름

1. `sync.py` 라우트가 `get_provider()`로 provider를 선택한다.
2. `PROVIDER_TYPE` 기본값은 `json_file`이다.
3. `rest_api`는 `API_BASE_URL`이 없으면 `json_file`로 폴백한다.
4. `dyn_ready`는 `DYN_READY_URL`의 `/dyn_ready/std-list/grouped`를 호출한다.
5. `SyncService.sync_test_data()`는 외부 데이터를 `(doc_id, exam_no)` 단위로 task에 병합한다.
6. provider 항목에 `exam_no`가 있으면 그 값을 우선 사용하고, 없으면 `std_list_cache.json`의 `test_info -> exam_no` 매핑으로 재시험 task를 분리한다.
7. 이미 스케줄 블록에 배치된 식별자가 외부 데이터에서 사라진 경우 삭제하지 않고 경고를 반환한다.
8. 이번 동기화에 없는 task는 삭제한다. 단, 이미 블록이 있으면 삭제하지 않고 경고만 남긴다.
9. `dyn_ready` provider는 `updated_at`과 응답 데이터 해시가 모두 같으면 `skipped: true`를 반환한다.

## 9. 시간/잔여 시간 규칙

| 동작 | 결과 |
| --- | --- |
| 큐에서 블록 생성 | `remaining_minutes` 재계산 |
| 블록 이동 | 날짜/시간만 변경, 잔여 시간은 연결 상태 기준 재계산 |
| 블록 리사이즈 | 실제 배정 시간 변경으로 보고 `remaining_minutes`를 직접 늘리지 않는다 |
| 블록 삭제 + `restore=1` | 해당 식별자/시간을 큐에 다시 노출 |
| 식별자 분리 | 남은 식별자만 큐에 표시 |
| 업무 종료 초과 | 다음 근무일로 초과분을 자동 배치한다 |

## 10. 개발 확인 순서

1. 의존성 설치: `pip install -r requirements.txt`
2. 서버 실행: `python3 run.py`
3. 브라우저 확인: `http://localhost:5001`
4. 테스트 실행: `pytest`

현재 저장소에는 ruff 설정 파일이 없다. 포맷터를 사용할 경우 먼저 설정을 추가한다.

## 11. 향후 구조 원칙

장기 구조 개편은 `docs/data-architecture-redesign.md`를 기준으로 한다.

핵심 원칙:

1. route는 요청/응답만 담당하고 업무 규칙은 service에 둔다.
2. service는 repository 인터페이스만 사용한다.
3. JSON 파일 구조와 DB 테이블 구조는 repository 구현체 내부에 숨긴다.
4. 화면과 외부 연동은 저장 원본이 아니라 read model/API를 사용한다.
5. 외부에서 데이터를 가져갈 때는 data 파일을 직접 계약으로 삼지 않고 `/api/external/v1/*` 또는 `exports/*` snapshot을 제공한다.

현재 구현된 구조 개편의 첫 단위:

| 영역 | 모듈 |
| --- | --- |
| compact snapshot 변환 | `app/services/compact_migration.py` |
| legacy JSON 파일 adapter | `app/services/compact_snapshot_files.py` |
| compact read model | `app/services/read_models.py` |
| compact ORM models | `app/db/models.py` |
| compact ORM repository | `app/db/repository.py` |
| compact snapshot repository factory | `app/repositories/compact_snapshot.py` |
| schedule storage adapter | `app/features/schedule/repositories.py` |
| execution storage adapter | `app/features/execution/repositories.py` |
| compact schedule command service | `app/services/compact_schedule_commands.py` |
| schedule block API 호환 서비스 | `app/features/schedule/services/compact_blocks.py` |
| schedule compact read adapter | `app/features/schedule/services/compact_read.py` |
| compact task catalog command service | `app/features/schedule/services/compact_tasks.py` |
| 외부 read-only API | `app/features/external_data/routes.py` |
| 실행 목록 view model | `app/features/execution/services/listing.py` |

외부 API는 기본적으로 legacy JSON에서 compact snapshot을 생성한다. `EXTERNAL_DATA_SOURCE=orm`으로 실행하면 `DATABASE_URL`에 지정된 SQLAlchemy DB에서 snapshot을 읽는다. 기존 JSON 데이터를 DB에 적재할 때는 `scripts/migrate_legacy_to_db.py`를 사용한다.

저장소 선택 설정:

| 설정 | 기본값 | 현재 지원 | 역할 |
| --- | --- | --- | --- |
| `EXTERNAL_DATA_SOURCE` | `json` | `json`, `orm` | 외부 API snapshot 조회 원본 |
| `SCHEDULE_STORAGE` | `json` | `json`, `orm`, `compact_orm` | schedule 쓰기 storage |
| `EXECUTION_STORAGE` | `json` | `json`, `orm`, `compact_orm` | execution record CRUD storage |
| `SYNC_COMPACT_ON_ORM_STORAGE_WRITE` | `1` | `1`, `0` | ORM storage 저장 후 compact ORM snapshot 자동 갱신 |
| `DATABASE_URL` | SQLite | SQLAlchemy URL | ORM snapshot DB 연결 |

`SCHEDULE_STORAGE=orm`, `EXECUTION_STORAGE=orm`은 전환용 `storage_payloads` 테이블에 기존 파일 모양의 payload를 저장한다. 이는 기존 화면의 쓰기 경로를 DB 위에서 검증하기 위한 중간 단계다. 정규화된 장기 모델은 compact ORM 테이블(`source_documents`, `test_items`, `exam_attempts`, `schedule_blocks`, `block_items`, `execution_runs`)이 담당한다.

`SCHEDULE_STORAGE=compact_orm`은 schedule block API의 생성, 수정, 삭제, 잠금, 상태, 메모 저장, task별 조회, 일괄 이동, 식별자 분리/복귀를 compact ORM 테이블에 직접 기록한다. 일/주/月 HTML 뷰와 `/schedule/api/day`, `/schedule/api/week`, `/schedule/api/month`, `/schedule/api/export`도 compact ORM snapshot에서 read model을 구성한다. 이 모드는 legacy 파일 모양 payload를 갱신하지 않으며, 서비스 계층에서 legacy `task_id`/`identifier_ids`를 compact `exam_attempt_id`로 변환한다.

실행 목록 화면과 `/execution/api/list`, `/execution/api/item`, `/execution/api/total-count`는 `SCHEDULE_STORAGE=compact_orm`일 때 compact ORM snapshot을 읽는다. `EXECUTION_STORAGE=compact_orm`이면 실행 시작, 일시정지, 재개, 완료, 코멘트, 수행자, 초기화도 compact ORM `execution_runs` 테이블에 직접 저장한다.

`SCHEDULE_STORAGE=compact_orm`의 schedule storage adapter는 admin 기준정보(`users`, `locations`, `versions`)와 `settings` 쓰기를 compact ORM resource/settings 테이블에 직접 반영한다. task 목록/상세는 compact catalog에서 legacy 화면 형태로 읽고, task 생성/수정/삭제와 sync test-data 쓰기는 compact catalog command가 `source_documents`, `test_items`, `exam_attempts`를 직접 갱신한다.

`SYNC_COMPACT_ON_ORM_STORAGE_WRITE=1`이면 ORM storage 저장 후 `storage_payloads`를 compact snapshot으로 변환해 compact ORM 테이블도 같이 갱신한다. 따라서 `EXTERNAL_DATA_SOURCE=orm` 외부 API가 화면 쓰기 결과를 따라갈 수 있다.

동기화는 파일 성격에 따라 범위를 줄인다.

| 저장 파일 | compact ORM 반영 |
| --- | --- |
| `users.json`, `locations.json`, `versions.json` | `resource_records` 직접 교체 |
| `settings.json` | `app_settings` 직접 교체 |
| `tasks.json` | catalog, schedule, executions 섹션 교체 |
| `schedule_blocks.json` | schedule 섹션 교체 |
| `executions.json` | executions 섹션 교체 |
| `procedures.json` | compact snapshot에 포함되지 않으므로 no-op |

현재 JSON storage를 ORM storage payload와 compact ORM 테이블로 적재할 때는 다음 명령을 사용한다.

```bash
python3 scripts/migrate_legacy_storage_to_orm.py --database-url sqlite:///app/data/scheduling.sqlite3
SCHEDULE_STORAGE=orm EXECUTION_STORAGE=orm EXTERNAL_DATA_SOURCE=orm python3 run.py
```

ORM storage와 compact ORM snapshot의 정합성은 다음 명령으로 확인한다.

```bash
python3 scripts/check_compact_consistency.py --database-url sqlite:///app/data/scheduling.sqlite3
```

DB-native schedule block command도 제공한다. 이 명령은 `storage_payloads`를 거치지 않고 compact ORM `schedule_blocks`, `block_items`에 직접 쓴다.

```bash
python3 scripts/compact_schedule_block.py --database-url sqlite:///app/data/scheduling.sqlite3 create \
  --date 2026-08-01 --start-time 09:00 --end-time 09:30 --attempt-id ea_xxx
python3 scripts/compact_schedule_block.py --database-url sqlite:///app/data/scheduling.sqlite3 delete blk_xxx
```

이 command와 같은 쓰기 경로가 `SCHEDULE_STORAGE=compact_orm`의 schedule block 핵심 API에도 연결되어 있다.
