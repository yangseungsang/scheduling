# 시험 실행(Execution) 페이지 설계

## 1. 개요

시간표(schedule) 페이지에서 관리자가 편성한 일정을 바탕으로,
시험자가 실제 시험을 수행하며 **식별자 단위로 시작/결과를 기록**하는 별도 페이지.

- **관리자**: `/schedule` — 시간표 편성
- **시험자**: `/execution` — 시험 실행 및 결과 입력

같은 앱 내 별도 feature 폴더로 분리하며, 권한 시스템은 추후 추가한다.

---

## 2. 폴더 구조

```
app/
  features/
    schedule/                          ← 기존 (관리자 시간표)
    execution/                         ← 신규 (시험 실행)
      __init__.py                      ← register_blueprints(app) 진입점
      store.py                         ← (옵션) 자체 store 또는 schedule.store 재사용
      data/
        executions.json                ← 실행 기록 데이터
      models/
        __init__.py
        execution.py                   ← ExecutionRepository (BaseRepository 상속)
      routes/
        __init__.py
        execution_views.py             ← HTML 페이지 라우트 (Blueprint: /execution)
        execution_api.py               ← REST API 라우트
      helpers/
        __init__.py
        (필요시 추가)
  templates/
    execution/                         ← 시험 실행 전용 템플릿
      base.html                        ← 시험자 전용 레이아웃 (schedule/base.html과 별도)
      day.html                         ← 일별 시험 실행 페이지
  static/
    execution/                         ← 시험 실행 전용 정적 파일
      css/
        style.css
      js/
        execution-app.js
```

### 의존성 방향

```
execution → schedule (단방향 읽기 전용)
```

```python
# execution 코드에서 schedule 데이터 접근
from app.features.schedule.models import task, schedule_block
from app.features.schedule.models import user, location
```

execution은 schedule의 **모델(읽기)**만 import한다.
schedule은 execution을 전혀 알지 못한다.

---

## 3. 데이터 모델

### 3.1 executions.json

```json
[
  {
    "id": "ex_a1b2c3d4",
    "block_id": "sb_7db79de1",
    "task_id": "t_003",
    "identifier_id": "TC-010",
    "tester_name": "박준혁",
    "status": "completed",
    "started_at": "2026-04-07T09:05:23",
    "completed_at": "2026-04-07T09:58:10",
    "actual_minutes": 53,
    "result": "pass",
    "notes": ""
  }
]
```

### 3.2 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 고유 ID (`ex_` 접두사) |
| `block_id` | string | 연결된 스케줄 블록 ID |
| `task_id` | string | 연결된 태스크 ID |
| `identifier_id` | string | 시험 식별자 ID (TC-001 등) |
| `tester_name` | string | 시험 수행자 이름 |
| `status` | string | `pending` / `in_progress` / `completed` |
| `started_at` | string\|null | 시험 시작 시각 (ISO 8601) |
| `completed_at` | string\|null | 시험 완료 시각 (ISO 8601) |
| `actual_minutes` | int\|null | 실제 소요 시간 (분) — completed_at - started_at 자동 계산 |
| `result` | string\|null | `pass` / `fail` / `conditional` (status=completed일 때만) |
| `notes` | string | 비고/메모 |

### 3.3 상태 흐름

```
pending ──[시험 시작]──→ in_progress ──[결과 입력]──→ completed
                              │
                              └──[시험 시작 취소]──→ pending
```

### 3.4 ExecutionRepository

```python
class ExecutionRepository(BaseRepository):
    FILENAME = 'executions.json'
    ID_PREFIX = 'ex_'

    @classmethod
    def get_by_block(cls, block_id):
        """블록 ID로 해당 블록의 모든 실행 기록 조회"""

    @classmethod
    def get_by_identifier(cls, identifier_id):
        """식별자 ID로 실행 기록 조회"""

    @classmethod
    def get_by_date(cls, date_str):
        """날짜 기준으로 해당일 블록들의 실행 기록 조회"""

    @classmethod
    def start(cls, block_id, task_id, identifier_id, tester_name):
        """시험 시작: status=in_progress, started_at=now 기록"""

    @classmethod
    def complete(cls, execution_id, result, notes=''):
        """결과 입력: status=completed, completed_at=now, actual_minutes 자동 계산"""

    @classmethod
    def cancel_start(cls, execution_id):
        """시작 취소: status=pending으로 복원"""
```

**store.py 처리:**
- `app/features/schedule/store.py`의 `read_json`/`write_json`은 `current_app.config['DATA_DIR']`을 사용
- execution의 데이터 파일은 **자체 data 폴더**(`app/features/execution/data/`)에 저장
- 방법: `EXECUTION_DATA_DIR`을 별도 config로 등록하거나, ExecutionRepository에서 store 함수를 오버라이드

```python
# app/features/execution/store.py
import os, json, portalocker

EXECUTION_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

def read_json(filename):
    path = os.path.join(EXECUTION_DATA_DIR, filename)
    # ... (schedule/store.py와 동일한 패턴)

def write_json(filename, data):
    path = os.path.join(EXECUTION_DATA_DIR, filename)
    # ... (schedule/store.py와 동일한 패턴)
```

---

## 4. API 설계

### 4.1 페이지 라우트

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/execution/` | 오늘 날짜 시험 실행 페이지 (리다이렉트) |
| GET | `/execution/?date=2026-04-07` | 특정 날짜 시험 실행 페이지 |

### 4.2 REST API

| Method | URL | 설명 | 요청 | 응답 |
|--------|-----|------|------|------|
| GET | `/execution/api/day?date=` | 당일 실행 현황 조회 | query: date | `{blocks, executions}` |
| POST | `/execution/api/start` | 시험 시작 | `{block_id, task_id, identifier_id, tester_name}` | execution 객체 (201) |
| POST | `/execution/api/complete` | 결과 입력 | `{execution_id, result, notes}` | execution 객체 |
| POST | `/execution/api/cancel` | 시작 취소 | `{execution_id}` | execution 객체 |
| GET | `/execution/api/summary?date=` | 당일 요약 (통과/실패/미시험 건수) | query: date | `{total, passed, failed, ...}` |

### 4.3 GET /execution/api/day 응답 구조

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
            "result": "pass",
            "started_at": "...",
            "completed_at": "...",
            "actual_minutes": 52,
            "tester_name": "박준혁",
            "notes": ""
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
    "passed": 3,
    "failed": 1,
    "conditional": 0
  }
}
```

각 식별자에 `execution` 필드를 조인하여 반환한다.
`execution`이 `null`이면 아직 시험 시작 전(pending) 상태.

---

## 5. 페이지 UI 구조

### 5.1 레이아웃

시험자 전용 `base.html`을 별도로 만든다 (관리자 toolbar 불필요).

```
┌──────────────────────────────────────────┐
│  시험 실행          ◀ 2026-04-07 ▶  요약 │  ← 상단 헤더
├──────────────────────────────────────────┤
│                                          │
│  09:00-11:06  항법 연산  @ STE2          │  ← 블록 카드
│  담당: 박준혁, 최수연                      │
│  ┌────────────────────────────────────┐  │
│  │ TC-010  항법 데이터 입력  53분       │  │  ← 식별자 행
│  │ 작성자: 박준혁                       │  │
│  │ ✅ 통과  52분  (09:05~09:57)       │  │
│  ├────────────────────────────────────┤  │
│  │ TC-011  연산 정확도 검증  47분       │  │
│  │ 작성자: 박준혁                       │  │
│  │ 🔵 진행중  (10:02~)                │  │
│  │              [결과 입력]            │  │
│  ├────────────────────────────────────┤  │
│  │ TC-012  항법 오류 처리  34분         │  │
│  │ 작성자: 최수연                       │  │
│  │ ○ 미시험     [시험 시작]            │  │
│  └────────────────────────────────────┘  │
│                                          │
│  14:40-15:18  통신 기능  @ STE1          │  ← 다음 블록 카드
│  ...                                     │
└──────────────────────────────────────────┘
```

### 5.2 식별자별 상태 표시 및 액션

| 상태 | 표시 | 버튼 |
|------|------|------|
| 미시험 (execution 없음) | `○ 미시험` | `[시험 시작]` |
| 진행중 (`in_progress`) | `🔵 진행중 (10:02~)` | `[결과 입력]` `[시작 취소]` |
| 통과 (`pass`) | `✅ 통과 52분 (09:05~09:57)` | (편집 가능 여부 TBD) |
| 실패 (`fail`) | `❌ 실패 48분 (09:05~09:53)` | (편집 가능 여부 TBD) |
| 조건부 (`conditional`) | `⚠️ 조건부 50분` | (편집 가능 여부 TBD) |

### 5.3 결과 입력 UI

`[결과 입력]` 클릭 시 인라인 또는 모달로:

```
┌─ 결과 입력: TC-011 ──────────────┐
│                                   │
│  판정:  ◉ 통과  ○ 실패  ○ 조건부 │
│                                   │
│  비고:  [________________]        │
│                                   │
│         [취소]  [저장]            │
└───────────────────────────────────┘
```

소요시간은 `started_at` ~ 현재시각으로 **자동 계산**하여 저장.

### 5.4 요약 바

페이지 상단 또는 하단에 당일 진행 현황 요약:

```
전체 8건 | 통과 3 | 실패 1 | 진행중 1 | 미시험 3
[=============================............]  62.5%
```

---

## 6. 앱 등록

### 6.1 execution __init__.py

```python
# app/features/execution/__init__.py
from app.features.execution.routes import register_execution_routes

def register_blueprints(app):
    register_execution_routes(app)
```

### 6.2 app/__init__.py 수정

```python
def create_app():
    ...
    from app.features.schedule import register_blueprints as register_schedule
    register_schedule(app)

    from app.features.execution import register_blueprints as register_execution
    register_execution(app)
    ...
```

### 6.3 DATA_DIR 처리

execution 데이터는 `app/features/execution/data/` 에 저장한다.
schedule의 `DATA_DIR` config를 공유하지 않고, execution 자체 경로를 사용:

```python
# app/features/execution/store.py
EXECUTION_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
```

이렇게 하면 schedule 쪽을 건드리지 않고 독립적으로 동작한다.

---

## 7. 향후 확장 고려사항

### 7.1 권한 시스템 (추후)

- 관리자: `/schedule`, `/admin` 접근 가능
- 시험자: `/execution` 접근 가능
- 로그인 시 역할(role) 기반으로 네비게이션/접근 제어

### 7.2 스케줄 ↔ 실행 연동 (추후)

- 실행 결과를 스케줄 페이지에서도 조회 (읽기 전용)
- 블록 상태(`block_status`)를 실행 결과에 따라 자동 갱신

### 7.3 리포트/통계 (추후)

- 일별/주별 시험 진척률
- 식별자별 pass/fail 이력
- 예상 시간 vs 실제 시간 비교

### 7.4 첨부파일 (추후)

- 시험 결과 스크린샷, 로그 파일 등 첨부
- `uploads/` 디렉토리 기반 파일 저장

---

## 8. 구현 순서 (예정)

1. execution feature 폴더 구조 생성
2. store.py + ExecutionRepository 모델 구현
3. REST API 라우트 구현 (start/complete/cancel/day)
4. 시험자 전용 base.html + day.html 템플릿
5. 프론트엔드 JS (시작/결과입력/요약)
6. 테스트 작성
