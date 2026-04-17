# 시험실행 페이지 설계 (Issue #35 반영)

## 1. 개요

기존 날짜별 뷰 스펙(`2026-04-13-execution-page-design.md`)을 대체하는 새 설계.
GitHub Issue #35 요구사항 반영.

- URL: `/execution/`
- 역할: 시험자가 식별자 단위로 시험을 수행하고 결과를 기록하는 페이지
- 기존 스케줄(`/schedule/`)과 별도 feature로 분리

---

## 2. 폴더 구조

```
app/
  features/
    execution/
      __init__.py            ← register_blueprints(app) 진입점
      store.py               ← 독립 데이터 저장소 (EXECUTION_DATA_DIR 사용)
      data/
        executions.json      ← 실행 기록 데이터
      models/
        __init__.py
        execution.py         ← ExecutionRepository
      routes/
        __init__.py
        views.py             ← GET /execution/ (HTML 페이지)
        api.py               ← REST API
  templates/
    execution/
      index.html             ← 시험실행 메인 페이지
  static/
    execution/
      js/
        execution-app.js     ← 타이머, 모달, 리스트 렌더링
```

---

## 3. 데이터 모델

### executions.json

```json
[
  {
    "id": "ex_a1b2c3d4",
    "identifier_id": "TC-001",
    "task_id": "t_001",
    "status": "pending",
    "segments": [
      { "start": "2026-04-17T09:05:00", "end": "2026-04-17T12:00:00" },
      { "start": "2026-04-17T13:00:00", "end": null }
    ],
    "total_count": 5,
    "fail_count": 1,
    "pass_count": 4,
    "created_at": "2026-04-17T09:05:00",
    "completed_at": null
  }
]
```

### 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 고유 ID (`ex_` 접두사) |
| `identifier_id` | string | 시험 식별자 ID (TC-001 등) |
| `task_id` | string | 연결된 태스크 ID |
| `status` | string | `pending` / `in_progress` / `paused` / `completed` |
| `segments` | array | 실제 시험 시간 구간 목록. `end: null`이면 현재 진행 중 |
| `total_count` | int | 외부 API에서 가져온 총 시험 항목 수 (임시 mock) |
| `fail_count` | int | 사용자 직접 입력한 FAIL 수 |
| `pass_count` | int | `total_count - fail_count` 자동 계산 |
| `created_at` | string | 생성(시험시작) 시각 (ISO 8601) |
| `completed_at` | string\|null | 시험완료 시각 |

### 상태 흐름

```
pending ──[시험시작]──→ in_progress ──[일시정지]──→ paused
                              │                        │
                              │◄──────[재시작]─────────┘
                              │
                              └──[시험완료]──→ completed ──[재시험]──→ pending
```

- 식별자 하나당 execution 레코드 하나 유지
- 재시험 시 segments/fail_count/pass_count 초기화

---

## 4. API 설계

### 4.1 페이지 라우트

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/execution/` | 시험실행 메인 페이지 |

### 4.2 REST API

| Method | URL | 요청 body | 설명 |
|--------|-----|-----------|------|
| GET | `/execution/api/list` | query: `date`, `location` | 식별자 목록 + 실행 상태 조인 |
| GET | `/execution/api/total-count/<identifier_id>` | — | 외부 총 시험 개수 (임시 mock) |
| POST | `/execution/api/start` | `{identifier_id, task_id}` | 시험시작: segment 추가, status→in_progress |
| POST | `/execution/api/pause` | `{execution_id}` | 일시정지: 현재 segment end 기록 |
| POST | `/execution/api/resume` | `{execution_id}` | 재시작: 새 segment 시작 |
| POST | `/execution/api/complete` | `{execution_id, fail_count}` | 시험완료: 최종 저장 |
| POST | `/execution/api/reset` | `{execution_id}` | 재시험: pending으로 초기화 |

### 4.3 GET /execution/api/list 응답 구조

```json
[
  {
    "identifier_id": "TC-001",
    "identifier_name": "시스템 전원 투입 시험",
    "task_id": "t_001",
    "doc_name": "시스템 초기화",
    "location_id": "loc_abc",
    "location_name": "STE1",
    "scheduled_date": "2026-04-18",
    "execution": {
      "id": "ex_a1b2c3d4",
      "status": "in_progress",
      "elapsed_seconds": 2843,
      "total_count": 8,
      "fail_count": 2,
      "pass_count": 6
    }
  }
]
```

`execution`이 `null`이면 아직 시험 시작 전(pending).  
`elapsed_seconds`는 서버에서 segments 합산 계산.

---

## 5. UI 구조

### 5.1 메인 리스트

```
┌─────────────────────────────────────────────────────┐
│  시험 실행                                           │
│  [날짜 필터 ▼]  [장소 필터 ▼]                       │
├──────┬──────────────────┬──────┬──────┬──────┬──────┤
│ TC   │ 식별자명         │ 문서 │ 장소 │ 날짜 │ 상태 │
├──────┼──────────────────┼──────┼──────┼──────┼──────┤
│TC-001│ 시스템 전원 투입  │초기화│ STE1 │ 4/18 │ ○대기│
│TC-002│ 초기화 절차 검증  │초기화│ STE1 │ 4/18 │🔵진행│
│TC-003│ 통신 링크 설정   │통신  │ STE2 │ 4/19 │✅완료│
└──────┴──────────────────┴──────┴──────┴──────┴──────┘
```

- 더블클릭으로 해당 식별자의 입력 모달 오픈
- 상태 배지: 대기(○), 진행중(🔵+경과시간), 일시정지(⏸), 완료(✅)
- 필터는 URL query string으로 유지 (`?date=2026-04-18&location=loc_abc`)

### 5.2 더블클릭 모달

**대기 상태:**
```
┌─ TC-001 시스템 전원 투입 시험 ──────────────┐
│                                               │
│              [시험시작]                       │
└───────────────────────────────────────────────┘
```

**진행중 상태:**
```
┌─ TC-002 초기화 절차 검증 ────────────────────┐
│                                               │
│  ⏱  00:47:23   [일시정지]                    │
│                                               │
│  총 시험: 8건                                 │
│  FAIL: [  2  ]  →  PASS: 6  (자동계산)       │
│                                               │
│  [재시험]              [시험완료]             │
└───────────────────────────────────────────────┘
```

**일시정지 상태:**
```
┌─ TC-002 초기화 절차 검증 ────────────────────┐
│                                               │
│  ⏸  00:47:23   [재시작]                      │
│                                               │
│  총 시험: 8건                                 │
│  FAIL: [  2  ]  →  PASS: 6  (자동계산)       │
│                                               │
│  [재시험]              [시험완료]             │
└───────────────────────────────────────────────┘
```

**완료 상태:**
```
┌─ TC-003 통신 링크 설정 ──────────────────────┐
│                                               │
│  ✅ 완료  총 1:23:45                          │
│  PASS: 6  FAIL: 2  (총 8건)                  │
│                                               │
│  [재시험]                          [닫기]     │
└───────────────────────────────────────────────┘
```

---

## 6. 앱 등록

### app/__init__.py 수정

```python
from app.features.schedule import register_blueprints as register_schedule
register_schedule(app)

from app.features.execution import register_blueprints as register_execution
register_execution(app)
```

### execution store.py

schedule의 `DATA_DIR`을 사용하지 않고 독립 경로 사용:

```python
EXECUTION_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
```

---

## 7. 외부 API (총 시험 개수) Mock

현재는 `identifier_id`에 상관없이 고정값(예: 10) 반환.
추후 실제 외부 API URL로 교체:

```python
def get_total_count(identifier_id: str) -> int:
    # TODO: 실제 외부 API 연동
    return 10
```

---

## 8. 제외 사항 (Issue #35)

- exec-summary 섹션 없음
- 조치사항(action items) 입력 없음
- 날짜별 그룹화 없음 (전체 플랫 리스트)
