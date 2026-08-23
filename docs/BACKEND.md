# Backend 개발 가이드

이 문서는 Flask 백엔드의 폴더별 책임, 주요 객체, HTTP 요청 흐름과 저장 규칙을 설명한다. 시스템 전체 그림은 `docs/architecture.md`, JSON schema는 `docs/data-files.md`를 참고한다.

## 1. 계층별 역할

```text
HTTP request
  -> routes: 입력 파싱, status code, HTML/JSON response
  -> services: 업무 규칙과 workflow
  -> domain: 불변 데이터와 직렬화 규칙
  -> repositories: 잠금, read-modify-write, JSON file
```

조회 중 여러 영역을 결합해야 하면 다음 흐름을 사용한다.

```text
repository
  -> typed domain objects
  -> presentation/read model
  -> template or API response dict
```

## 2. Flask 애플리케이션

### `app/__init__.py`

`create_app()`은 애플리케이션의 composition root다.

1. Flask 객체와 template/static 경로 생성
2. 환경 변수 기반 설정 적용
3. JSON 데이터 디렉터리와 기본 파일 초기화
4. Jinja 전역 `cache_bust` 등록
5. CORS 응답 헤더 추가
6. schedule/execution blueprint 등록
7. 루트 URL을 주간 캘린더로 연결

Feature의 `register_blueprints()`는 domain import 시 route가 따라오는 순환 의존을 방지하기 위해 route를 함수 내부에서 지연 import한다.

## 3. 공통 Domain

### `app/domain/common/`

특정 feature가 소유하지 않는 최소한의 기능만 둔다.

| 항목 | 역할 |
| --- | --- |
| `SCHEMA_VERSION` | 설정 JSON의 기본 schema 버전 |
| `stable_id(prefix, *parts)` | 외부 business key로부터 재현 가능한 내부 ID 생성 |

`stable_id()`는 같은 `document_id + test_round`가 다시 동기화돼도 동일 procedure를 갱신하도록 한다.

## 4. Schedule Feature

### 4.1 Domain

경로: `app/features/schedule/domain/`

| 타입 | 책임 |
| --- | --- |
| `TestItem` | 시험 항목 ID, 이름, 예상 시간, 총 건수, 담당자 |
| `TestProcedure` | 외부 문서/차수와 그 안의 시험 항목 collection |
| `ScheduleBlock` | 날짜, 시작/종료, 장소, 담당자, 포함 시험 항목 |
| `Schedule` | schedule block collection |
| `TestPlan` | 버전, procedure와 schedule block을 묶는 저장 aggregate |
| `AppSettings` | 근무/점심/휴식/그리드/색상 설정 |

Domain 타입은 `@dataclass(frozen=True)`다. 변경은 기존 객체를 직접 수정하지 않고 `dataclasses.replace()`로 새 객체를 만들어 repository update callback에서 반환한다.

```python
repository.update_test_procedures(lambda procedures: tuple(
    replace(item, memo='수정됨') if item.id == target_id
    else item
    for item in procedures
))
```

### 4.2 Integrations

경로: `app/features/schedule/integrations/dyn_ready.py`

`DynReadyClient`는 `DYN_READY_URL/dyn_ready/std-list/grouped`를 호출한다. `_transform()`은 외부 응답을 내부 service 입력 형식으로 정규화한다.

| 외부 필드 | 내부 필드 |
| --- | --- |
| `doc_id` | `document_id` |
| `doc_name` | `document_name` |
| `exam_no` | `test_round` |
| `test_id` | test item `id` |
| `func_name` | test item `name` |
| `pf_num` | `total_count` |
| `owner` | `owners` |

HTTP 응답 원본은 저장하거나 다른 계층으로 노출하지 않는다.

### 4.3 Services

#### `test_procedures.py`

- procedure 생성, 수정, 삭제
- 같은 시험 차수에서 시험 항목 ID 중복 방지
- 화면/API용 dict 변환
- 배치된 block 시간을 차감한 `remaining_minutes` 계산
- procedure 삭제 시 연관 block과 execution도 함께 제거

#### `blocks.py`

- 필수 필드와 시간 범위 검증
- 같은 날짜/장소의 block 충돌 검사
- 잠긴 block 수정 방지
- procedure 시험 항목의 중복 배치 해제
- block 이동, 상태, 메모, lock 변경
- 선택 시험 항목 분할과 큐 복귀
- 특정 날짜 이후 block 일괄 이동

#### `_block_commands.py`

`ScheduleBlockService`가 검증을 마친 뒤 호출하는 저수준 command다. 최신 plan을 잠금 안에서 읽고 immutable block collection을 교체한다. 외부 route가 직접 사용하지 않는 내부 모듈이다.

#### `time.py`

- HH:MM과 minute 변환
- 점심 및 휴식 구간 계산
- 실제 작업 시간 계산
- break를 건너뛴 종료 시각 계산
- 화면 time slot 생성

#### `sync.py`

동기화 결과를 기존 procedure와 `document_id + test_round`로 매칭한다. 외부에서 사라진 항목이 이미 schedule에 있으면 제거하지 않고 보존 경고를 만든다.

#### `presentation.py`

Domain을 schedule 화면용 dict로 변환한다.

- execution 상태가 반영된 block 상태
- 담당자/장소/상태 기반 색상
- 분할 block의 시험 항목 개수
- 큐의 미배치 시험 항목과 잔여 시간
- 월간 달력 주차와 겹침 layout

#### `export.py`

presentation에서 만든 enriched block을 CSV 또는 XLSX bytes로 변환한다. XLSX는 `openpyxl`을 우선 사용하고 사용할 수 없는 경우 표준 라이브러리 기반 writer를 사용한다.

#### `settings.py`

`settings.json`을 dict로 반환하고 전달된 필드만 기존 설정에 병합한다.

### 4.4 Routes

#### 캘린더 HTML/API

| Method | URL | 담당 |
| --- | --- | --- |
| GET | `/schedule/` | 일간 화면 |
| GET | `/schedule/week` | 주간 화면 |
| GET | `/schedule/month` | 월간 화면 |
| GET | `/schedule/api/day` | 일간 JSON |
| GET | `/schedule/api/week` | 주간 JSON |
| GET | `/schedule/api/month` | 월간 JSON |
| POST | `/schedule/api/blocks` | 시험 block 생성 |
| PUT | `/schedule/api/blocks/<id>` | block 이동/크기 변경 |
| DELETE | `/schedule/api/blocks/<id>` | block 삭제 또는 큐 복귀 |
| PUT | `/schedule/api/blocks/<id>/lock` | 잠금 토글 |
| PUT | `/schedule/api/blocks/<id>/status` | 수동 상태 변경 |
| PUT | `/schedule/api/blocks/<id>/memo` | 메모 변경 |
| POST | `/schedule/api/simple-blocks` | 시험 외 단순 일정 생성 |
| POST | `/schedule/api/blocks/shift` | 날짜 기준 일괄 이동 |
| POST | `/schedule/api/blocks/<id>/split` | 선택 항목 분리 |
| POST | `/schedule/api/blocks/<id>/return-test_items` | 일부 항목 큐 복귀 |
| GET | `/schedule/api/export` | CSV/XLSX 다운로드 |

#### Procedure

| Method | URL | 담당 |
| --- | --- | --- |
| GET | `/procedures/` | 목록 화면 |
| GET/POST | `/procedures/new` | 생성 폼 |
| GET | `/procedures/<id>` | 상세 화면 |
| GET/POST | `/procedures/<id>/edit` | 수정 폼 |
| POST | `/procedures/<id>/delete` | HTML workflow 삭제 |
| GET | `/procedures/api/list` | 목록 JSON |
| GET | `/procedures/api/<id>` | 상세 JSON |
| POST | `/procedures/api/create` | 생성 API |
| PUT | `/procedures/api/<id>/update` | 수정 API |
| DELETE | `/procedures/api/<id>/delete` | 삭제 API |
| GET | `/procedures/api/check-test-item` | 시험 항목 중복 확인 |

#### 설정과 동기화

| Method | URL | 담당 |
| --- | --- | --- |
| GET/POST | `/admin/settings` | 설정 화면 |
| GET/PUT | `/admin/api/settings` | 설정 API |
| POST | `/admin/api/project-reset` | 계획/실행 초기화 |
| POST | `/api/sync/test-data` | DynReady 병합 |
| POST | `/api/sync/reset-and-sync` | 초기화 후 재동기화 |
| GET | `/api/sync/status` | 현재 procedure 개수 |

## 5. Execution Feature

### 5.1 Domain

경로: `app/features/execution/domain/`

`ExecutionRun`은 다음 상태를 가진다.

```text
pending -> in_progress -> paused -> in_progress -> completed
```

주요 시간 필드:

- `started_at`: 최초 또는 재시작 시각
- `ended_at`: 완료 시각
- `active_started_at`: 현재 진행 구간 시작 시각
- `actual_seconds`: 종료된 진행 구간의 누적 시간
- `elapsed_seconds`: 저장 누적 시간과 현재 진행 구간을 합친 계산값

### 5.2 Storage와 Repository

`storage.py`는 기존 API가 사용하는 dict와 typed domain 객체 사이를 변환한다. `repository.py`는 storage 위에서 실행 상태 전이를 제공한다.

```text
ExecutionRepository
  -> ExecutionStorage
  -> JsonDomainRepository.update_executions()
  -> test_executions.json
```

`ExecutionRepository`는 다음 규칙을 보장한다.

- 키는 `procedure_id + test_item_id`
- 재시작은 기존 기록을 초기화
- pause 시 현재 구간을 누적 시간에 반영
- resume 시 새 active 구간 시작
- complete 시 pass/fail/block 계산과 종료 시각 저장
- 아직 시작하지 않은 항목에도 pending comment 저장 가능

### 5.3 Listing Service

`services/listing.py`는 plan과 executions를 함께 읽어 화면용 실행 항목을 만든다. 날짜, 장소, 상태, procedure 필터는 저장 모델이 아니라 이 read model에 적용된다.

### 5.4 Routes

| Method | URL | 담당 |
| --- | --- | --- |
| GET | `/execution/` | 실행 목록 화면 |
| GET | `/execution/<test_item_id>?procedure_id=...` | 실행 상세 화면 |
| GET | `/execution/api/list` | 필터 가능한 실행 목록 |
| GET | `/execution/api/item/<test_item_id>` | 실행 상세 JSON |
| GET | `/execution/api/total-count/<test_item_id>` | 총 시험 건수 |
| POST | `/execution/api/start` | 시작/재시작 |
| POST | `/execution/api/pause` | 일시정지 |
| POST | `/execution/api/resume` | 재개 |
| POST | `/execution/api/complete` | 완료 |
| PUT | `/execution/api/pending-comment` | 시작 전 코멘트 |
| PUT | `/execution/api/comment` | 코멘트 변경 |
| PUT | `/execution/api/performer` | 수행자 변경 |
| PATCH | `/execution/api/timing/<test_item_id>` | 시간 직접 보정 |
| POST | `/execution/api/reset` | pending으로 초기화 |
| GET/POST | `/execution/api/whoami`, `/login` | session 수행자 확인/설정 |

완료 후 `API_BASE_URL`이 설정돼 있으면 daemon thread가 `/update_test_time`에 실제 소요 시간을 전송한다. 실패는 로그만 남기고 이미 저장된 완료 결과를 되돌리지 않는다.

## 6. Repository 상세

### 파일별 책임

| 메서드 그룹 | 대상 파일 |
| --- | --- |
| `load_plan`, `update_plan`, `update_schedule` | `test_plan.json` |
| `load_executions`, `update_executions` | `test_executions.json` |
| `load_settings`, `replace_settings` | `settings.json` |
| `load_operations`, `update_operations` | plan과 executions 결합 |

### 안전한 변경 방식

```python
repository.update_plan(lambda current: replace(
    current,
    schedule_blocks=current.schedule_blocks + (new_block,),
))
```

Update callback은 잠금을 획득한 뒤 읽은 최신 객체를 입력으로 받는다. callback 밖에서 먼저 읽고 나중에 `replace_*`로 저장하면 다른 요청의 변경을 덮어쓸 수 있으므로, 동시 변경 가능성이 있는 workflow에서는 `update_*`를 사용한다.

### 쓰기 과정

1. 데이터 디렉터리 생성
2. `.data.lock` 획득
3. 최신 JSON 읽기 및 domain 변환
4. callback으로 새 불변 객체 생성
5. 같은 디렉터리에 임시 JSON 완성
6. flush와 `fsync`
7. `os.replace()`로 대상 파일 교체
8. 잠금 해제

## 7. Read Model

`app/services/read_models.py`는 schedule과 execution 양쪽에서 사용할 수 있는 순수 조합 함수다.

| 함수 | 결과 |
| --- | --- |
| `build_execution_list_items()` | procedure 시험 항목과 실행 상태 결합 |
| `build_unscheduled_attempts()` | 아직 배치되지 않았고 완료되지 않은 항목 |
| `build_schedule_export_rows()` | 일정과 실행 결과를 포함한 export row |

이 모듈은 Flask나 파일 시스템을 알지 않는다. 입력으로 받은 domain 객체만 조합한다.

## 8. 오류 처리

- 업무 검증 오류는 `ScheduleBlockError`, `TestProcedureError`에 HTTP status code를 담는다.
- Route는 이 예외를 JSON 오류 응답 또는 flash 메시지로 변환한다.
- 외부 DynReady HTTP 오류는 sync route에서 실패 응답으로 변환한다.
- 외부 timing 알림 실패는 warning 로그만 남긴다.
- Repository 파일 잠금은 최대 10초 대기하고 실패 시 예외를 호출자에게 전달한다.

## 9. 테스트 구조

| 테스트 | 범위 |
| --- | --- |
| `test_domain_types.py` | domain 직렬화와 계산 속성 |
| `test_json_repository.py` | 잠금, 파일 분리, 원자적 변경, route 통합 |
| `test_routes_*.py` | Flask HTML/API 요청 |
| `test_calendar_api.py` | block command와 검증 |
| `test_execution*.py` | 상태 전이와 실행 read model |
| `test_sync.py`, `test_dyn_ready.py` | 외부 응답 변환과 병합 |
| `test_schedule_time.py` | 휴식/근무 시간 계산 |

`tests/conftest.py`는 각 테스트가 실제 `app/data`를 수정하지 않도록 `tmp_path/domain_data`를 `DOMAIN_DATA_DIR`로 설정한다.

전체 회귀 테스트:

```bash
python -m pytest -q
```
