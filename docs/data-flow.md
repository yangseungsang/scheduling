# 데이터 흐름 문서

이 문서는 화면, API, 서비스, 저장소 사이에서 데이터가 어떻게 이동하고 사용되는지 설명한다.

## 1. 전체 흐름

```text
외부 데이터 또는 로컬 JSON
  -> Provider
  -> SyncService
  -> tasks.json
  -> schedule_blocks.json
  -> execution 화면
  -> executions.json
  -> 외부 완료 시간 전송(선택)
```

브라우저는 직접 JSON 파일을 읽지 않는다. 모든 읽기/쓰기는 Flask API를 통한다.

```text
Browser JavaScript
  -> Flask route
  -> Procedure service 또는 feature service
  -> service/helper
  -> repository
  -> store
  -> JSON file
```

## 2. 저장 파일

| 파일 | 소유 기능 | 주요 용도 |
| --- | --- | --- |
| `app/features/schedule/data/tasks.json` | Schedule | 시험 절차, 문서, 차수, 식별자 목록 |
| `app/features/schedule/data/schedule_blocks.json` | Schedule | 캘린더에 배치된 블록 |
| `app/features/schedule/data/users.json` | Schedule | 담당자 이름, 색상, 역할 |
| `app/features/schedule/data/locations.json` | Schedule | 장소 이름, 색상, 설명 |
| `app/features/schedule/data/settings.json` | Schedule | 근무 시간, 휴식 시간, 슬롯 설정 |
| `app/features/schedule/data/versions.json` | Schedule | 동기화 대상 버전 |
| `app/features/schedule/data/std_list_cache.json` | Schedule | 차수별 식별자 캐시 |
| `app/features/execution/data/executions.json` | Execution | 식별자별 실행 상태와 결과 |

Schedule 데이터는 `app.features.schedule.store`를 통해 읽고 쓴다.
Execution 데이터는 `app.features.execution.store`를 통해 읽고 쓴다.
Schedule과 Execution을 함께 조합해야 하는 조회는 `app.domains.procedure.service`를 기준으로 한다.

## 3. 동기화 데이터 가져오기

동기화는 외부 시스템이나 로컬 JSON에서 시험 절차를 가져와 `tasks.json`으로 병합한다.

```text
POST /api/sync/test-data
  -> routes/sync.py
  -> providers.get_provider()
  -> SyncService.sync_test_data()
  -> task repository
  -> tasks.json
```

Provider별 입력은 다음과 같다.

| Provider | 가져오는 위치 | 사용 방식 |
| --- | --- | --- |
| `json_file` | `procedures.json`, `versions.json` | 개발/로컬 데이터 |
| `rest_api` | `API_BASE_URL`의 API | 외부 REST 시스템 |
| `dyn_ready` | `DYN_READY_URL/dyn_ready/std-list/grouped` | dyn_ready 표준 목록 |

동기화 결과는 task 단위로 저장된다.

```json
{
  "id": "t_...",
  "doc_id": 1001,
  "version_id": "ofp_001",
  "exam_no": 1,
  "doc_name": "시험 절차서",
  "assignee_names": [],
  "location_id": "",
  "identifiers": [
    {
      "id": "TC-001",
      "name": "기능 시험",
      "estimated_minutes": 60,
      "owners": ["작성자"]
    }
  ],
  "estimated_minutes": 60,
  "remaining_minutes": 60
}
```

이미 캘린더에 배치된 식별자가 동기화 데이터에서 사라지면 삭제하지 않고 보존한다.
기존 전체 블록이 있는 task에 새 식별자가 추가되면 기존 블록은 당시 식별자 목록으로 고정되고, 새 식별자는 큐에 남는다.

## 4. 스케줄 화면에서 데이터 쓰기

사용자가 큐의 task 또는 식별자를 캘린더로 드래그하면 프론트엔드는 블록 생성 API를 호출한다.

```text
POST /schedule/api/blocks
Content-Type: application/json
```

요청 예:

```json
{
  "task_id": "t_1234",
  "date": "2026-03-10",
  "start_time": "09:00",
  "end_time": "11:00",
  "assignee_names": ["홍길동"],
  "location_id": "loc_1234",
  "identifier_ids": ["TC-001", "TC-002"]
}
```

처리 흐름:

```text
calendar_api.api_create_block()
  -> blocks.create_block()
  -> 필수값 검사
  -> task 기본 담당자/장소 보정
  -> 휴식 시간 반영
  -> 담당자/장소 겹침 검사
  -> 근무 종료 초과분 계산
  -> schedule_block.create()
  -> schedule_blocks.json
  -> sync_task_remaining_minutes()
  -> tasks.json
```

응답 예:

```json
{
  "id": "sb_1234",
  "task_id": "t_1234",
  "date": "2026-03-10",
  "start_time": "09:00",
  "end_time": "11:00",
  "location_id": "loc_1234",
  "identifier_ids": ["TC-001", "TC-002"],
  "block_status": "pending",
  "is_locked": false
}
```

근무 종료를 넘으면 다음 근무일 블록이 자동 생성되고 응답에 `continuations`가 붙는다.

```json
{
  "id": "sb_1234",
  "date": "2026-03-10",
  "end_time": "16:30",
  "continuation": {
    "id": "sb_5678",
    "date": "2026-03-11",
    "start_time": "08:30",
    "end_time": "10:00"
  },
  "continuations": [
    {
      "id": "sb_5678",
      "date": "2026-03-11",
      "start_time": "08:30",
      "end_time": "10:00"
    }
  ]
}
```

## 5. 스케줄 화면에서 데이터 읽기

일간/주간/월간 화면은 API 응답을 받아 캘린더 블록과 큐를 그린다.

```text
GET /schedule/api/day
GET /schedule/api/week
GET /schedule/api/month
```

서버는 다음 데이터를 조합한다.

```text
tasks.json
schedule_blocks.json
users.json
locations.json
settings.json
executions.json
  -> enrich_blocks()
  -> get_queue_tasks()
  -> 화면 표시용 JSON
```

큐는 `tasks.json`만 보고 만들지 않는다. `schedule_blocks.json`을 함께 확인해서 아직 배치되지 않은 식별자만 계산한다.

중요 규칙:

1. `identifier_ids=null`인 블록은 해당 task의 모든 현재 식별자를 포함하는 전체 블록이다.
2. `identifier_ids=["TC-001"]`인 블록은 지정된 식별자만 포함한다.
3. 전체 블록이 동기화 중 명시적 식별자 목록으로 고정되면, 새로 추가된 식별자는 큐에 남는다.
4. 모든 식별자가 execution 기준 `completed`이면 큐에서 제외한다.

## 6. 블록 수정과 삭제

블록 이동/리사이즈는 PUT 요청으로 처리한다.

```text
PUT /schedule/api/blocks/<block_id>
```

요청 예:

```json
{
  "date": "2026-03-11",
  "start_time": "13:00",
  "end_time": "15:00",
  "location_id": "loc_5678"
}
```

처리 흐름:

```text
calendar_api.api_update_block()
  -> blocks.update_block()
  -> 기존 블록 조회
  -> 이동/리사이즈 규칙 적용
  -> 겹침 검사
  -> 초과분 continuation 생성
  -> schedule_blocks.json 갱신
  -> task.remaining_minutes 갱신
```

블록 삭제는 DELETE 요청으로 처리한다.

```text
DELETE /schedule/api/blocks/<block_id>
DELETE /schedule/api/blocks/<block_id>?restore=1
DELETE /schedule/api/blocks/<block_id>?restore=task
```

| 옵션 | 동작 |
| --- | --- |
| 없음 | 해당 블록 하나만 삭제 |
| `restore=1` | 해당 블록 하나를 삭제하고 task 장소를 비움 |
| `restore=task` 또는 `restore=all` | 같은 task의 모든 블록을 삭제하고 task 장소를 비움 |

## 7. 실행 화면에서 데이터 읽기

실행 목록은 스케줄에 배치된 식별자와 실행 결과를 합쳐 보여준다.

```text
GET /execution/api/list
```

서버는 다음 데이터를 조합한다.

```text
tasks.json
schedule_blocks.json
locations.json
executions.json
  -> app.domains.procedure.service.execution_items()
  -> execution item list
```

응답 항목 예:

```json
{
  "identifier_id": "TC-001",
  "identifier_name": "기능 시험",
  "task_id": "t_1234",
  "doc_name": "시험 절차서",
  "display_name": "시험 절차서",
  "assignee_names": ["홍길동"],
  "location_id": "loc_1234",
  "location_name": "시험실 A",
  "scheduled_date": "2026-03-10",
  "total_count": 10,
  "execution": {
    "id": "ex_1234",
    "status": "in_progress",
    "elapsed_seconds": 120,
    "fail_count": 0,
    "block_count": 0,
    "pass_count": 0,
    "performer": "홍길동",
    "completed_at": null
  }
}
```

`scheduled_date`는 계획일이고, `execution.completed_at`은 실제 수행 완료 시각이다.

## 8. 실행 데이터 쓰기

실행 시작, 일시정지, 재개, 완료는 `executions.json`에 기록된다.

```text
POST /execution/api/start
POST /execution/api/pause
POST /execution/api/resume
POST /execution/api/complete
POST /execution/api/reset
PUT  /execution/api/comment
PUT  /execution/api/performer
```

시작 요청 예:

```json
{
  "identifier_id": "TC-001",
  "task_id": "t_1234"
}
```

완료 요청 예:

```json
{
  "execution_id": "ex_1234",
  "fail_count": 1,
  "block_count": 0
}
```

Execution은 `segments[]`로 실제 동작 시간을 기록한다.

```json
{
  "id": "ex_1234",
  "identifier_id": "TC-001",
  "task_id": "t_1234",
  "status": "completed",
  "segments": [
    {
      "start": "2026-03-10T09:00:00",
      "end": "2026-03-10T09:30:00"
    }
  ],
  "total_count": 10,
  "fail_count": 1,
  "block_count": 0,
  "pass_count": 9,
  "performer": "홍길동",
  "completed_at": "2026-03-10T09:30:00"
}
```

완료 후 `API_BASE_URL`이 설정되어 있으면 외부 `/update_test_time`으로 소요 시간을 비동기 전송한다.

## 9. Feature Data Exchange API

다른 기능이나 외부 클라이언트가 스케줄/실행 데이터를 읽어야 할 때는 read-only API를 사용한다.

```text
GET /features/api/schedule
GET /features/api/execution
GET /features/api/snapshot
```

이 API는 JSON 파일 원본과 Procedure item 스냅샷을 함께 반환한다.
기능 간 공유에 필요한 조합 데이터는 `procedure_items`를 우선 사용한다.

사용 기준:

1. 화면 표시나 내부 기능 조합은 기존 schedule/execution API를 사용한다.
2. 다른 기능이 스케줄과 실행 데이터를 함께 가져가야 하면 `/features/api/snapshot`을 사용한다.
3. 쓰기는 지원하지 않는다. 데이터 변경은 각 도메인의 전용 API를 통해 한다.

## 9.1 Procedure Service

`app.domains.procedure.service`는 Schedule과 Execution이 공유하는 조회 경계다.

주요 함수:

| 함수 | 용도 |
| --- | --- |
| `execution_items(date_filter, location_filter)` | 실행 목록용 task, block, location, execution 조합 |
| `find_execution_item(identifier_id, task_id)` | 실행 상세 item 조회 |
| `total_count(identifier_id, task_id)` | 식별자의 전체 시험 건수 조회 |
| `execution_status_map()` | Schedule 블록/큐 상태 계산용 실행 상태 맵 |
| `update_identifier_elapsed()` | 외부 timing 입력으로 식별자 예상 시간 갱신 |

이 계층 덕분에 Execution API는 Schedule repository 조합을 직접 알 필요가 없고,
Schedule enrichment도 Execution repository를 직접 읽지 않는다.

## 10. 저장소 잠금과 쓰기 규칙

Schedule repository의 기본 `create`, `patch`, `delete`는 `transact_json()`을 사용한다.

```text
BaseRepository.create/patch/delete
  -> store.transact_json(filename, callback)
  -> portalocker.Lock
  -> read
  -> modify
  -> write
```

이 구조는 같은 파일의 read-modify-write를 하나의 lock 안에서 처리한다.
따라서 같은 JSON 파일을 동시에 수정할 때, 읽은 뒤 다른 요청이 먼저 써서 변경이 덮이는 위험을 줄인다.

주의할 점:

1. 파일 하나 단위의 원자성만 보장한다.
2. 여러 파일을 함께 바꾸는 작업은 아직 완전한 트랜잭션이 아니다.
3. 예를 들어 블록 생성 후 task 잔여 시간을 갱신하는 흐름은 `schedule_blocks.json`과 `tasks.json`을 순서대로 갱신한다.
