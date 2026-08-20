# 시스템 아키텍처

이 문서는 현재 코드 기준으로 애플리케이션이 어떻게 시작되고, 각 폴더가 어떤 책임을 가지며, 요청과 데이터가 어떤 순서로 이동하는지 설명한다.

## 1. 시스템 개요

이 애플리케이션은 외부 DynReady에서 시험 절차를 가져와 캘린더에 배치하고, 시험 항목별 실제 실행 시간과 결과를 기록하는 Flask 기반 내부 도구다.

핵심 기능은 두 feature로 구분한다.

| Feature | 소유하는 기능과 데이터 |
| --- | --- |
| `schedule` | 시험 절차, 일정 블록, 근무 시간 설정, 외부 동기화, 내보내기 |
| `execution` | 시험 실행 상태, 타이머, 수행자, 코멘트, pass/fail/block 결과 |

두 feature가 공통 화면을 만들 때는 서로의 route를 호출하지 않는다. Repository에서 각 domain 데이터를 읽은 뒤 application read model에서 조합한다.

```text
DynReady
   |
   v
schedule/integrations -> schedule/services -> Schedule Domain
                                               |
                                               v
                                      JsonDomainRepository
                                               |
                      +------------------------+------------------------+
                      |                        |                        |
                test_plan.json       test_executions.json        settings.json
                      |                        |
                      +------------+-----------+
                                   v
                        read model / presentation
                                   |
                      +------------+------------+
                      |                         |
                 Schedule UI               Execution UI
```

## 2. 설계 원칙

### 2.1 Feature가 자신의 domain을 소유한다

`TestProcedure`, `ScheduleBlock`, `AppSettings`는 schedule feature가 소유하고, `ExecutionRun`은 execution feature가 소유한다. 최상위 `app/domain/`에는 특정 feature에 속하지 않는 ID 생성과 공통 상수만 둔다.

### 2.2 외부 데이터 형식을 내부 모델로 사용하지 않는다

DynReady 응답의 `doc_id`, `exam_no`, `test_id` 같은 필드는 integration 계층에서 `document_id`, `test_round`, `id`로 변환한다. 외부 API 변경은 integration에 머물고 내부 서비스와 domain은 정규화된 모델만 사용한다.

### 2.3 Route는 HTTP, Service는 업무 규칙을 담당한다

Route는 입력 파싱, 상태 코드, JSON/HTML 응답 변환을 담당한다. 일정 충돌, 시험 항목 분할, 동기화 병합, 상태 전이 같은 규칙은 service나 repository class에 둔다.

### 2.4 파일 I/O는 Repository에 집중한다

Feature 코드는 `app/data/*.json`을 직접 열지 않는다. `JsonDomainRepository`가 JSON과 domain 객체 사이의 변환, 파일 잠금, 원자적 교체를 담당한다.

### 2.5 화면용 데이터는 별도 read model에서 만든다

저장 모델을 템플릿이나 API 형식으로 그대로 노출하지 않는다. `presentation.py`, `listing.py`, `app/services/read_models.py`가 일정과 실행 데이터를 조합해 화면 전용 필드를 만든다.

## 3. 디렉터리 구조와 책임

```text
app/
├── __init__.py                         # Flask app factory와 blueprint 등록
├── data/                               # 기본 JSON 영속 데이터
├── domain/
│   └── common/                         # feature 독립 공통 상수와 stable ID
├── repositories/
│   ├── json_domain.py                  # JSON 저장, 잠금, domain 변환
│   └── test_operations.py              # schedule/execution 결합 저장 모델
├── services/
│   └── read_models.py                  # feature 간 공통 조회 모델
├── features/
│   ├── schedule/
│   │   ├── domain/                     # procedure, schedule, settings 모델
│   │   ├── integrations/               # DynReady 외부 API 어댑터
│   │   ├── routes/                     # 캘린더, 절차, 설정, 동기화 HTTP
│   │   └── services/                   # 일정 및 동기화 업무 규칙
│   └── execution/
│       ├── domain/                     # 실행 기록 모델
│       ├── routes/                     # 실행 화면 및 실행 API
│       ├── services/                   # 실행 목록 read model
│       ├── repository.py               # 실행 상태 전이
│       └── storage.py                  # dict와 typed 실행 모델 변환
├── templates/                          # Jinja2 서버 렌더링 템플릿
└── static/
    ├── schedule/                       # 캘린더 CSS/JavaScript
    └── execution/                      # 실행 화면 CSS/JavaScript

scripts/                                # 시드와 운영 보조 스크립트
tests/                                  # pytest 회귀 및 통합 테스트
docs/                                   # 제품·구조·프론트엔드·데이터 문서
```

### `app/domain/common/`

- `SCHEMA_VERSION`: 설정 JSON schema 기본 버전
- `stable_id()`: 외부 business key로부터 결정적 내부 ID 생성
- 특정 feature의 모델이나 Flask 객체를 import하지 않는다.

### `app/features/schedule/domain/`

- `procedures.py`: `TestItem`, `TestProcedure`
- `scheduling.py`: `ScheduleBlock`, `Schedule`
- `plan.py`: procedure와 schedule을 한 문서로 묶는 `TestPlan`
- `settings.py`: 근무 시간, 휴식, 그리드 설정을 담는 `AppSettings`
- 모든 타입은 불변 dataclass이며 `from_dict()`와 `to_dict()`가 JSON 경계를 담당한다.

### `app/features/execution/domain/`

- `ExecutionRun`: `(procedure_id, test_item_id)`로 식별되는 실행 기록
- `Executions`: 여러 실행 기록의 collection
- `elapsed_seconds`: 저장된 누적 시간과 현재 진행 구간을 합산하는 계산 속성

### `app/repositories/`

- `JsonDomainRepository`는 세 JSON 파일의 유일한 저수준 접근점이다.
- `portalocker`로 동일 데이터 디렉터리의 `.data.lock`을 획득한다.
- 쓰기는 같은 디렉터리에 임시 파일을 완성한 뒤 `os.replace()`로 교체한다.
- `TestOperations`는 `TestPlan`과 `Executions`를 잠금 안에서 함께 읽거나 변경할 때만 사용한다.

### `app/features/schedule/services/`

| 파일 | 책임 |
| --- | --- |
| `test_procedures.py` | procedure CRUD, 중복 시험 항목 검증, 남은 시간 계산 |
| `_block_commands.py` | 잠금 안의 단일 schedule block 변경 명령 |
| `blocks.py` | 충돌 검사, 이동, 분할, 큐 복귀, 일괄 날짜 이동 |
| `time.py` | 근무/점심/휴식 시간을 반영한 시간 계산 |
| `sync.py` | 외부 procedure 병합과 삭제 경고 처리 |
| `presentation.py` | 일/주/월 화면과 큐에 필요한 view model 생성 |
| `export.py` | CSV/XLSX 직렬화 |
| `settings.py` | 설정 조회와 부분 업데이트 |

### `app/features/execution/`

| 파일 | 책임 |
| --- | --- |
| `repository.py` | pending, in_progress, paused, completed 상태 전이와 결과 변경 |
| `storage.py` | 기존 dict 기반 API와 typed `ExecutionRun` 사이 변환 |
| `services/listing.py` | plan과 execution을 조합해 목록/상세 응답 생성 |
| `routes/views.py` | 실행 목록과 상세 HTML 렌더링 |
| `routes/api.py` | 시작, 일시정지, 재개, 완료, 코멘트, 수행자 API |

### `app/templates/`와 `app/static/`

Jinja2가 초기 화면 골격과 서버 계산 데이터를 렌더링한다. 이후 JavaScript가 drag, resize, modal, filter를 처리하고 API 명령을 보낸다. 저장 성공 후에는 서버 데이터를 다시 읽어 화면과 영속 상태가 어긋나지 않게 한다.

## 4. 애플리케이션 시작 흐름

1. `create_app()`이 Flask 인스턴스를 만든다.
2. `SECRET_KEY`, `DOMAIN_DATA_DIR`과 정적 파일 캐시 설정을 적용한다.
3. `JsonDomainRepository.initialize()`가 누락된 JSON 파일을 기본 domain 값으로 생성한다.
4. schedule blueprint를 등록한다.
5. execution blueprint를 등록한다.
6. `/` 요청은 `/schedule/week`로 이동한다.

Feature package의 `register_blueprints()`는 route를 지연 import한다. 따라서 repository가 feature domain 모델을 import해도 Flask route 초기화가 연쇄적으로 발생하지 않는다.

## 5. 주요 요청 흐름

### 5.1 DynReady 동기화

```text
POST /api/sync/test-data
 -> schedule/routes/sync.py
 -> DynReadyClient.get_test_data_all()
 -> integrations/dyn_ready.py에서 외부 필드 정규화
 -> SyncService.sync_test_data()
 -> TestProcedureService create/update
 -> JsonDomainRepository.update_plan()
 -> test_plan.json
```

이미 일정에 배치된 시험 항목이 외부 응답에서 사라진 경우 즉시 제거하지 않고 기존 항목을 보존하며 경고를 반환한다.

### 5.2 캘린더 조회

```text
GET /schedule/week
 -> calendar_views.py
 -> repository.load_operations()
 -> presentation.build_ui_blocks()
 -> presentation.build_queue_procedures()
 -> week.html 렌더링
```

`presentation.py`는 procedure, block, execution 상태를 조합해 색상, 상태, 분할 수, 잔여 시간 같은 화면 전용 필드를 추가한다.

### 5.3 일정 블록 생성과 변경

```text
JavaScript drag/drop
 -> /schedule/api/blocks
 -> calendar_api.py
 -> ScheduleBlockService
 -> ScheduleCommandService
 -> JsonDomainRepository.update_plan/update_schedule
 -> test_plan.json
```

상위 service는 필수값, 잠금, 장소/시간 충돌, 시험 항목 소유권을 검증한다. `_block_commands.py`는 검증이 끝난 변경을 최신 plan에 적용한다.

### 5.4 실행 상태 변경

```text
POST /execution/api/start|pause|resume|complete
 -> execution/routes/api.py
 -> ExecutionRepository
 -> ExecutionStorage
 -> JsonDomainRepository.update_executions()
 -> test_executions.json
```

실행 레코드는 별도 ID 없이 `(procedure_id, test_item_id)`가 키다. 완료 시 `pass_count = total_count - fail_count - block_count`로 계산하며 음수가 되지 않게 제한한다.

### 5.5 내보내기

```text
GET /schedule/api/export
 -> plan + executions 조회
 -> presentation.build_export_blocks()
 -> export.export_csv() 또는 export.export_xlsx()
 -> 다운로드 응답
```

내보내기는 저장 모델을 직접 직렬화하지 않고 일정, 시험 항목, 실행 상태가 결합된 export row를 사용한다.

### 5.6 프로젝트 초기화

`POST /admin/api/project-reset`은 procedure, schedule, execution을 비우지만 `settings.json`은 유지한다. `POST /api/sync/reset-and-sync`은 같은 데이터를 비운 뒤 DynReady에서 다시 동기화한다.

## 6. 데이터와 트랜잭션 경계

| 파일 | 소유 모델 | 주요 변경 주체 |
| --- | --- | --- |
| `test_plan.json` | `TestPlan` | schedule services, sync |
| `test_executions.json` | `Executions` | execution repository |
| `settings.json` | `AppSettings` | schedule settings service |

한 영역만 변경할 때는 해당 파일만 다시 쓴다. procedure 삭제처럼 schedule과 execution을 동시에 정리해야 할 때는 `update_operations()`가 공유 잠금 안에서 최신 데이터를 읽고 두 파일을 연속 교체한다.

파일 교체는 원자적이지만 여러 파일을 하나의 파일시스템 트랜잭션으로 묶지는 않는다. 프로세스가 두 번째 파일 교체 전에 비정상 종료하면 부분 반영 가능성이 있으므로, 향후 강한 다중 문서 원자성이 필요하면 단일 DB나 journal 도입을 고려한다.

## 7. 의존 방향

```text
routes
  -> feature services / feature repository
      -> feature domain
      -> JsonDomainRepository
          -> feature domains
          -> shared domain utilities

integrations
  -> 외부 HTTP API
  -> schedule service가 이해하는 정규화 데이터

presentation/read_models
  -> schedule domain + execution domain
  -> template/API 전용 dict
```

금지하는 의존은 다음과 같다.

- domain에서 Flask, route, template, 파일 경로 import
- schedule route에서 execution route 호출 또는 그 반대
- feature service에서 JSON 파일 직접 `open()`
- DynReady 응답 필드명을 domain 전체에 전파

## 8. 설정과 실행

| 환경 변수 | 설명 | 기본값 |
| --- | --- | --- |
| `DOMAIN_DATA_DIR` | JSON 데이터 디렉터리 | `app/data` |
| `SECRET_KEY` | Flask session key | 개발용 문자열 |
| `DYN_READY_URL` | DynReady base URL | `http://127.0.0.1:5000` |
| `API_BASE_URL` | 완료 시간 통지 API의 base URL | 미설정 시 전송하지 않음 |
| `API_KEY` | 완료 시간 통지 Bearer token | 없음 |

개발 실행과 테스트:

```bash
pip install -r requirements.txt
python3 run.py
python -m pytest -q
```

기본 개발 URL은 `http://localhost:5001`이다.

## 9. 변경 시 확인 순서

1. 변경 데이터의 소유 feature를 결정한다.
2. domain 필드와 JSON 호환성을 먼저 확인한다.
3. 업무 규칙은 service/repository class에 추가한다.
4. route는 입력 검증과 응답 변환만 담당하게 유지한다.
5. 화면 전용 계산은 presentation/read model에 둔다.
6. 저장 변경은 잠금 안의 read-modify-write로 구현한다.
7. unit test와 route/integration test를 함께 추가한다.
8. `docs/BACKEND.md`, `docs/FRONTEND.md`, `docs/data-files.md` 중 영향을 받는 문서를 갱신한다.
