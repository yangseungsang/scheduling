# 시험 실행(Execution) 페이지 설계 v2

## 1. 개요

시간표에서 관리자가 편성한 일정을 바탕으로, 시험자가 실제 시험을 수행하며
**식별자 단위로 시작/결과/특이사항을 기록**하는 별도 페이지.

- **관리자**: `/schedule` — 시간표 편성
- **시험자**: `/execution` — 시험 실행 및 결과 입력

기존 schedule 코드는 변경하지 않는다. execution에서 schedule 모델을 읽기 + block_status patch만 수행.

---

## 2. 폴더 구조

```
app/
  features/
    schedule/                          # 기존 (변경 없음)
    execution/                         # 신규
      __init__.py                      # register_blueprints(app)
      store.py                         # 자체 data/ 경로 read_json/write_json
      data/
        executions.json                # 실행 기록 데이터
      models/
        __init__.py
        execution.py                   # ExecutionRepository
      routes/
        __init__.py
        execution_views.py             # Blueprint /execution (HTML)
        execution_api.py               # REST API
  templates/
    execution/
      base.html                        # 시험자 전용 레이아웃
      day.html                         # 일별 시험 실행 페이지
  static/
    execution/
      css/style.css
      js/execution-app.js
```

### 의존성

```
execution → schedule (단방향)
  - 읽기: schedule.models.task, schedule.models.schedule_block, schedule.models.user, schedule.models.location
  - 쓰기: schedule.models.schedule_block.patch(block_id, block_status=...) — 상태 동기화만
```

---

## 3. 데이터 모델

### 3.1 executions.json

```json
[
  {
    "id": "ex_a1b2c3d4",
    "block_id": "sb_7db79de1",
    "task_id": "t_003",
    "doc_name": "항법 연산",
    "identifier_id": "TC-010",
    "tester_name": "박준혁",
    "status": "completed",
    "started_at": "2026-04-07T09:05",
    "completed_at": "2026-04-07T09:58",
    "pass_count": 3,
    "fail_count": 1,
    "comment": "센서 3번 포트 접촉 불량 확인",
    "action": "포트 교체 후 재시험 예정"
  }
]
```

### 3.2 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| id | string | 고유 ID (ex_ 접두사) |
| block_id | string | 연결된 스케줄 블록 ID |
| task_id | string | 연결된 태스크 ID |
| doc_name | string | 문서명 |
| identifier_id | string | 시험 식별자 ID (TC-001 등) |
| tester_name | string | 시험 수행자 이름 |
| status | string | pending / in_progress / completed |
| started_at | string\|null | 시험 시작 시각 (시험 시작 시 기록) |
| completed_at | string\|null | 시험 완료 시각 (결과 입력 시 기록) |
| pass_count | int | PASS 건수 (기본 0) |
| fail_count | int | FAIL 건수 (기본 0) |
| comment | string | 특이사항 (시험 중/후 수정 가능) |
| action | string | 조치사항 (시험 중/후 수정 가능) |

### 3.3 상태 흐름

```
pending ──[시험 시작]──→ in_progress ──[결과 입력]──→ completed
                              │
                              └──[시작 취소]──→ pending
```

---

## 4. 시간표 연동 (block_status 동기화)

실행 상태 변경 시 해당 블록의 `block_status`를 자동 갱신:

| 블록 내 식별자 상태 | block_status |
|---------------------|-------------|
| 전부 pending | pending |
| 하나라도 in_progress | in_progress |
| 전부 completed | completed |

구현: execution API 핸들러에서 상태 변경 후 `_sync_block_status(block_id)` 호출.
이 함수는 해당 block_id의 모든 execution을 조회 → 위 규칙 적용 → `schedule_block.patch(block_id, block_status=...)`.

---

## 5. API 설계

### 5.1 페이지 라우트

| Method | URL | 설명 |
|--------|-----|------|
| GET | /execution/ | 오늘 날짜 실행 페이지 |
| GET | /execution/?date=2026-04-07 | 특정 날짜 실행 페이지 |

### 5.2 REST API

| Method | URL | 설명 | 요청 | 응답 |
|--------|-----|------|------|------|
| GET | /execution/api/day?date= | 당일 실행 현황 | query: date | {blocks, summary} |
| POST | /execution/api/start | 시험 시작 | {block_id, task_id, doc_name, identifier_id, tester_name} | execution (201) |
| POST | /execution/api/complete | 결과 입력 | {execution_id, pass_count, fail_count} | execution |
| PUT | /execution/api/\<id\>/comment | 특이사항/조치 수정 | {comment, action} | execution |
| POST | /execution/api/cancel | 시작 취소 | {execution_id} | execution |

### 5.3 GET /execution/api/day 응답 구조

```json
{
  "date": "2026-04-07",
  "blocks": [
    {
      "block_id": "sb_7db79de1",
      "task_id": "t_003",
      "doc_name": "항법 연산",
      "start_time": "09:00",
      "end_time": "11:06",
      "location_name": "STE2",
      "assignee_names": ["박준혁", "최수연"],
      "identifiers": [
        {
          "id": "TC-010",
          "name": "항법 데이터 입력 시험",
          "estimated_minutes": 53,
          "owners": ["박준혁"],
          "execution": {
            "id": "ex_a1b2c3d4",
            "status": "completed",
            "started_at": "2026-04-07T09:05",
            "completed_at": "2026-04-07T09:58",
            "pass_count": 3,
            "fail_count": 1,
            "tester_name": "박준혁",
            "comment": "센서 3번 포트 접촉 불량",
            "action": "포트 교체 후 재시험"
          }
        },
        {
          "id": "TC-011",
          "name": "연산 정확도 검증",
          "estimated_minutes": 47,
          "owners": ["박준혁"],
          "execution": null
        }
      ]
    }
  ],
  "summary": {
    "total": 8,
    "pending": 3,
    "in_progress": 1,
    "completed": 4,
    "total_pass": 12,
    "total_fail": 2
  }
}
```

---

## 6. 페이지 UI

### 6.1 레이아웃

시험자 전용 base.html (관리자 toolbar 불필요).

```
┌──────────────────────────────────────────┐
│  시험 실행          ◀ 2026-04-07 ▶       │
├──────────────────────────────────────────┤
│  요약: 전체 8 | 완료 4 | 진행 1 | 대기 3 │
│  PASS 12 / FAIL 2                        │
│  [============================........]  │
├──────────────────────────────────────────┤
│                                          │
│  09:00-11:06  항법 연산  @ STE2          │
│  담당: 박준혁, 최수연                      │
│  ┌────────────────────────────────────┐  │
│  │ TC-010  항법 데이터 입력  53분       │  │
│  │ ✅ PASS 3 / FAIL 1  (09:05~09:58) │  │
│  │ 특이사항: [___________________]    │  │
│  │ 조치사항: [___________________]    │  │
│  │                        [저장]      │  │
│  ├────────────────────────────────────┤  │
│  │ TC-011  연산 정확도 검증  47분       │  │
│  │ 🔵 진행중  (10:02~)                │  │
│  │ PASS [__] FAIL [__]               │  │
│  │ 특이사항: [___________________]    │  │
│  │ 조치사항: [___________________]    │  │
│  │              [결과 저장]            │  │
│  ├────────────────────────────────────┤  │
│  │ TC-012  항법 오류 처리  34분         │  │
│  │ ○ 미시험     [시험 시작]            │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

### 6.2 식별자별 상태 및 액션

| 상태 | 표시 | 액션 |
|------|------|------|
| pending | ○ 미시험 | [시험 시작] |
| in_progress | 🔵 진행중 (HH:MM~) | PASS/FAIL 입력 + 특이사항/조치사항 + [결과 저장] [시작 취소] |
| completed | ✅ PASS N / FAIL M (HH:MM~HH:MM) | 특이사항/조치사항 수정 + [저장] |

### 6.3 요약 바

```
전체 8건 | 완료 4 | 진행중 1 | 대기 3 | PASS 12 / FAIL 2
[============================............]  62.5%
```

---

## 7. 앱 등록

### 7.1 execution/__init__.py

```python
from app.features.execution.routes import register_execution_routes

def register_blueprints(app):
    register_execution_routes(app)
```

### 7.2 app/__init__.py 수정 (유일한 기존 파일 수정)

```python
from app.features.execution import register_blueprints as register_execution
register_execution(app)
```

### 7.3 store.py

execution 자체 data 경로 사용 (schedule의 DATA_DIR과 독립):

```python
EXECUTION_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
```

---

## 8. ExecutionRepository 메서드

```python
class ExecutionRepository:
    FILENAME = 'executions.json'
    ID_PREFIX = 'ex_'

    def get_by_block(cls, block_id): ...
    def get_by_identifier(cls, identifier_id): ...
    def start(cls, block_id, task_id, doc_name, identifier_id, tester_name): ...
    def complete(cls, execution_id, pass_count, fail_count): ...
    def update_comment(cls, execution_id, comment, action): ...
    def cancel(cls, execution_id): ...
```

---

## 9. 구현 순서

1. execution feature 폴더 구조 + store.py + ExecutionRepository
2. execution REST API (start/complete/cancel/comment/day)
3. block_status 동기화 로직 (_sync_block_status)
4. 시험자 전용 base.html + day.html 템플릿
5. 프론트엔드 JS (시작/결과입력/특이사항 저장/요약)
6. app/__init__.py에 Blueprint 등록
7. 테스트 작성
