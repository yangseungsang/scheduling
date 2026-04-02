# Backend 아키텍처 문서

## 1. 개요

Flask + Jinja2 기반 **서버 사이드 렌더링(SSR)** 애플리케이션.

> **SSR이란?** 브라우저가 요청할 때마다 서버에서 HTML을 완성하여 보내주는 방식.
> React/Vue 같은 SPA(Single Page Application)는 클라이언트에서 JS로 화면을 그리지만,
> 이 프로젝트는 서버(Jinja2 템플릿)에서 HTML을 렌더링한 뒤 브라우저에 전달한다.
> 빌드 도구 없이 간단하게 동작하며, JS는 드래그앤드롭 등 인터랙션에만 사용된다.

데이터베이스 없이 JSON 파일로 데이터를 관리하며, **Model 계층**으로 데이터 접근을 추상화한다.

> **Model 계층이란?** 데이터 저장소(여기선 JSON 파일)에 대한 읽기/쓰기를
> 전용 모듈(Model)로 분리하는 설계 패턴이다.
> Route 코드에서 `store.read_json('tasks.json')`을 직접 호출하는 대신
> `task.get_all()`처럼 의미 있는 메서드로 접근한다.
> **장점:** 저장 방식이 바뀌어도(예: JSON → DB) Route 코드는 수정할 필요 없다.

> **인증 없음:** 이 앱에는 로그인/인증이 없다. 누구나 모든 데이터를 조회·수정·삭제할 수 있다.

```
요청 흐름 (두 가지 패턴):

1) 단순 CRUD (대부분의 요청):
   Browser → Blueprint (Route) → Model → JSON File

2) 복잡한 비즈니스 로직 (자동 스케줄링):
   Browser → Blueprint (Route) → Service (scheduler.py)
                                      ↓
                                 Model → JSON File

응답:
   Route → Jinja2 Template → HTML 응답 (페이지 렌더링)
   Route → JSON 응답 (API 호출)
```

---

## 2. 앱 초기화

### 처음 실행하는 방법

```bash
cd scheduling
python3 -m venv venv              # 가상환경 생성
source venv/bin/activate           # 가상환경 활성화
pip install -r requirements.txt    # 의존성 설치
python3 run.py                     # 서버 실행 (http://localhost:5001)
```

### `schedule/__init__.py` — `create_app()`

| 단계 | 설명 |
|------|------|
| 1 | Flask 인스턴스 생성, 인라인 Config 로드 (`SECRET_KEY`, `DATA_DIR`) |
| 2 | `SEND_FILE_MAX_AGE_DEFAULT = 0` — 브라우저 캐시 비활성화 (개발 편의용. CSS/JS 수정 시 즉시 반영) |
| 3 | `data/` 디렉토리 자동 생성 (없으면) |
| 4 | Jinja2 전역 함수 등록: `enumerate`, `cache_bust` |
| 5 | CORS 헤더 추가 (`Access-Control-Allow-Origin: *`) |
| 6 | Blueprint 3개 등록 (`register_routes(app)` 호출) |
| 7 | 루트 `/` → `/schedule/` 리다이렉트 |

**`cache_bust`란?** 서버 기동 시각의 타임스탬프 값. 템플릿에서 `<script src="drag_drop.js?v={{ cache_bust }}">`처럼 사용하여, 서버를 재시작할 때마다 브라우저가 캐시된 이전 JS/CSS가 아닌 최신 파일을 로드하게 한다.

**Blueprint 등록:**

| Blueprint | URL Prefix | 역할 |
|-----------|-----------|------|
| `schedule_bp` | `/schedule` | 캘린더 뷰 + 블록 CRUD |
| `tasks_bp` | `/tasks` | 시험 항목 CRUD |
| `admin_bp` | `/admin` | 설정/사용자/장소/버전 관리 |

### `run.py`
```python
app = create_app()
app.run(host='0.0.0.0', port=5001, debug=True)
```
> macOS AirPlay가 5000 포트를 점유하므로 5001 사용.

---

## 3. 데이터 저장 계층

### `schedule/store.py` — JSON I/O + 파일 잠금

| 함수 | 설명 |
|------|------|
| `generate_id(prefix)` | `"{prefix}{uuid4().hex[:8]}"` 형식 ID 생성 (예: `t_a1b2c3d4`) |
| `_get_path(filename)` | `current_app.config['DATA_DIR'] + filename`으로 전체 경로 반환. **주의:** Flask 앱 컨텍스트 안에서만 동작한다. |
| `read_json(filename)` | portalocker 읽기 잠금 → JSON 파싱 → 반환 |
| `write_json(filename, data)` | `.bak` 백업 생성 → portalocker 쓰기 잠금 → JSON 저장 |

> **파일 잠금(portalocker)이란?**
> 웹 서버는 여러 요청을 동시에 처리한다. 만약 두 요청이 같은 JSON 파일을
> 동시에 읽고 쓰면 데이터가 깨질 수 있다.
> `portalocker`는 OS 수준의 파일 잠금을 제공하여 한 번에 하나의 프로세스만
> 파일을 수정할 수 있게 한다 (5초 타임아웃).

> **`.bak` 백업이란?**
> `write_json` 호출 시 기존 파일을 `tasks.json.bak`으로 복사한 뒤 새 내용을 쓴다.
> 쓰기 도중 오류가 발생하면 `.bak` 파일에서 수동으로 복구할 수 있다.

**핵심 설계:**
- `ensure_ascii=False`로 한글 직접 저장
- 빈 파일은 `[]` 반환 (settings는 `{}`)
- 매 호출마다 파일 전체를 읽고 쓴다 (데이터가 수천 건 이상이면 성능 저하 가능)

### 데이터 파일 구조

```
data/
├── users.json            ← 팀원 목록
├── locations.json        ← 시험 장소 목록
├── versions.json         ← 소프트웨어 버전 목록
├── tasks.json            ← 시험 항목 목록
├── schedule_blocks.json  ← 스케줄 블록
├── settings.json         ← 시스템 설정
└── procedures.json       ← 절차서 정보 (mock 데이터)
```

**ID 접두사 규칙:**

| 접두사 | 엔티티 | 예시 |
|--------|--------|------|
| `u_` | User | `u_3f8a1b2c` |
| `loc_` | Location | `loc_00000001` |
| `v_` | Version | `v_00000001` |
| `t_` | Task | `t_7e4d9c0a` |
| `sb_` | Schedule Block | `sb_5f6e7d8c` |

---

## 4. Model 계층

각 Model은 단일 JSON 파일에 대한 CRUD를 제공한다. (기존 Repository 패턴에서 `schedule/models/`로 이전)

> **`update` vs `patch` 용어 주의:**
> - `user.update()`, `location.update()` — **전체 갱신.** 모든 필드를 인자로 받아 덮어쓴다.
> - `task.patch()` — **부분 갱신.** 전달된 kwargs 필드만 수정. **화이트리스트 없음** — 어떤 필드든 수정 가능.
> - `schedule_block.update()` — **부분 갱신처럼 동작.** kwargs로 전달된 필드만 수정하되, **화이트리스트**(`ALLOWED_FIELDS`)로 허용 필드를 제한한다.

### 4.1 `user.py` → `users.json`

```json
{ "id": "u_xxx", "name": "홍길동", "role": "개발자", "color": "#4A90D9" }
```

| 메서드 | 설명 |
|--------|------|
| `get_all()` | 전체 사용자 목록 |
| `get_by_id(user_id)` | ID로 조회 |
| `create(name, role, color)` | 생성 (자동 ID) |
| `update(user_id, name, role, color)` | 전체 필드 수정 |
| `delete(user_id)` | 삭제 |

### 4.2 `location.py` → `locations.json`

```json
{ "id": "loc_xxx", "name": "시험실 A", "color": "#E74C3C", "description": "1층 좌측" }
```

| 메서드 | 설명 |
|--------|------|
| `get_all()` / `get_by_id()` / `create(name, color, description)` / `update()` / `delete()` | 기본 CRUD |

### 4.3 `version.py` → `versions.json`

```json
{ "id": "v_xxx", "name": "v2.1.0", "description": "2차 통합 시험", "is_active": true, "created_at": "2026-03-28T09:00:00" }
```

| 메서드 | 설명 |
|--------|------|
| `get_all()` | 전체 버전 목록 |
| `get_active()` | 활성 버전만 반환 |
| `get_by_id()` | ID로 조회 |
| `create(name, description)` | 생성 (is_active=True, created_at 자동) |
| `update(version_id, name, description, is_active)` | 수정 |
| `delete(version_id)` | 삭제 |

### 4.4 `task.py` → `tasks.json`

```json
{
  "id": "t_xxx",
  "procedure_id": "STP-001",
  "version_id": "v_xxx",
  "assignee_ids": ["u_xxx1", "u_xxx2"],
  "location_id": "loc_xxx",
  "section_name": "통신 시험",
  "procedure_owner": "김철수",
  "test_list": ["TC-001", "TC-002", "TC-003"],
  "estimated_hours": 2.0,
  "remaining_hours": 1.5,
  "status": "waiting",
  "memo": "",
  "created_at": "2026-03-28T09:50:00"
}
```

| 메서드 | 설명 |
|--------|------|
| `get_all()` | 전체 시험 항목 목록 |
| `get_by_id(task_id)` | ID로 조회 |
| `get_by_version(version_id)` | 버전별 조회 |
| `create(procedure_id, version_id, assignee_ids, ...)` | 생성. `status='waiting'`, `remaining_hours=estimated_hours`로 초기화 |
| `update(task_id, procedure_id, ...)` | **전체** 필드 갱신 — 모든 인자 필요 |
| `patch(task_id, **kwargs)` | **부분** 갱신 — 전달된 필드만 수정 (화이트리스트 없음) |
| `delete(task_id)` | 삭제 |

### 4.5 `schedule_block.py` → `schedule_blocks.json`

```json
{
  "id": "sb_xxx",
  "task_id": "t_xxx",
  "assignee_ids": ["u_xxx1", "u_xxx2"],
  "location_id": "loc_xxx",
  "version_id": "v_xxx",
  "date": "2026-03-15",
  "start_time": "09:00",
  "end_time": "12:00",
  "is_draft": false,
  "is_locked": false,
  "origin": "manual",
  "block_status": "pending",
  "memo": ""
}
```

**`block_status` 값의 의미:**

| 값 | 한국어 | 설명 |
|----|--------|------|
| `pending` | 시작 전 | 아직 작업을 시작하지 않은 상태 (기본값) |
| `in_progress` | 진행 중 | 현재 작업 중 |
| `completed` | 완료 | 작업 완료 |
| `cancelled` | 불가 | 해당 시간에 작업 불가능 |

| 메서드 | 설명 |
|--------|------|
| `get_all()` | 전체 블록 |
| `get_by_id(block_id)` | ID로 조회 |
| `get_by_date(date_str)` | 특정 날짜의 블록 |
| `get_by_date_range(start, end)` | 날짜 범위 블록 (inclusive) |
| `get_by_version(version_id)` | 버전별 블록 |
| `get_by_assignee(assignee_id)` | 담당자별 블록 |
| `get_by_location_and_date(location_id, date_str)` | 특정 장소+날짜의 블록 |
| `create(task_id, assignee_ids, location_id, version_id, date, start_time, end_time, ...)` | 생성 (기본값: `is_draft=False`, `origin='manual'`, `block_status='pending'`) |
| `update(block_id, **kwargs)` | 부분 갱신 — **화이트리스트 필드만 허용** (아래 참조) |
| `delete(block_id)` | 삭제 |
| `delete_drafts()` | 모든 초안 블록 삭제 |
| `approve_drafts()` | 모든 초안의 `is_draft`를 `False`로 변경 |

**Model 레벨 update 허용 필드 (ALLOWED_FIELDS):**
`date`, `start_time`, `end_time`, `is_draft`, `is_locked`, `block_status`, `task_id`, `assignee_ids`, `location_id`, `version_id`, `origin`, `memo`

> **이중 필터링 주의:**
> Route (`PUT /api/blocks/<id>`)에서도 별도의 `allowed` 세트로 한 번 더 필터링한다:
> `{'date', 'start_time', 'end_time', 'is_draft', 'is_locked', 'block_status', 'location_id'}`
> 즉 API로는 `task_id`, `assignee_ids`, `version_id`, `origin`, `memo`를 변경할 수 **없다**.
> (`memo`는 전용 엔드포인트 `PUT /api/blocks/<id>/memo`를 사용)

### 4.6 `settings.py` → `settings.json`

```json
{
  "work_start": "08:00",
  "work_end": "17:00",
  "actual_work_start": "08:30",
  "actual_work_end": "16:30",
  "lunch_start": "12:00",
  "lunch_end": "13:00",
  "breaks": [
    { "start": "09:45", "end": "10:00" },
    { "start": "14:45", "end": "15:00" }
  ],
  "grid_interval_minutes": 15,
  "max_schedule_days": 14,
  "block_color_by": "assignee"
}
```

> **`work_start/end` vs `actual_work_start/end`:**
> `work_start/end`는 캘린더 **표시 범위** (08:00~17:00).
> `actual_work_start/end`는 자동 스케줄링의 **실제 배치 범위** (08:30~16:30).

| 메서드 | 설명 |
|--------|------|
| `get()` | 설정 반환 (파일 없으면 기본값) |
| `update(data)` | 현재 설정에 `data` 병합 후 저장 |

---

## 5. Blueprint 라우팅

### 5.1 Schedule Blueprint (`/schedule`)

#### 페이지 렌더링

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/schedule/` | GET | 일간 뷰 (`day.html`) — 장소별 컬럼 레이아웃 |
| `/schedule/week` | GET | 주간 뷰 (`week.html`) |
| `/schedule/month` | GET | 월간 뷰 (`month.html`) |

#### 데이터 API

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/schedule/api/day?date=YYYY-MM-DD` | GET | 일간 데이터 JSON |
| `/schedule/api/week?date=YYYY-MM-DD` | GET | 주간 데이터 JSON |
| `/schedule/api/month?date=YYYY-MM-DD` | GET | 월간 데이터 JSON |

#### 블록 CRUD API

| 라우트 | 메서드 | 응답 코드 | 설명 |
|--------|--------|-----------|------|
| `/schedule/api/blocks` | POST | 201 | 블록 생성 |
| `/schedule/api/blocks/<id>` | PUT | 200 | 블록 수정 (이동, 리사이즈, 소요시간 변경) |
| `/schedule/api/blocks/<id>` | DELETE | 200 | 블록 삭제 (항상 remaining_hours 재계산) |
| `/schedule/api/blocks/<id>/lock` | PUT | 200 | 잠금 토글 |
| `/schedule/api/blocks/<id>/status` | PUT | 200 | 상태 변경 (태스크 상태 자동 연동) |
| `/schedule/api/blocks/<id>/memo` | PUT | 200 | 메모 수정 |

**블록 수정 (`PUT /schedule/api/blocks/<id>`) 특수 파라미터:**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `resize` | bool | `true`이면 리사이즈 모드 — task의 estimated_hours를 총 스케줄 시간으로 재계산 |
| `duration_minutes` | int | 상세 팝업에서 소요시간 변경 시 사용 — start_time 기준으로 end_time을 재계산 (휴식시간 고려) |

#### 초안 API

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/schedule/api/draft/generate` | POST | 자동 스케줄링 실행 |
| `/schedule/api/draft/approve` | POST | 초안 전체 확정 |
| `/schedule/api/draft/discard` | POST | 초안 전체 폐기 |

#### 내보내기 API

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/schedule/api/export?start_date=...&end_date=...&format=csv\|xlsx` | GET | CSV/Excel 다운로드 |

#### 블록 생성 시 중요한 서버 동작

1. **`adjust_end_for_breaks` 호출:** 블록 생성 시 서버가 end_time을 자동 조정한다. 휴식시간에 걸치는 블록은 실제 근무시간을 보존하기 위해 end_time이 뒤로 밀린다.
   ```
   예: start_time=11:00, end_time=13:00 (2시간)으로 생성 요청
   → 12:00~13:00 점심이 포함되므로
   → 실제 저장: start_time=11:00, end_time=14:00 (총 3시간 중 근무 2시간)
   ```

2. **블록 이동(PUT, resize가 아닌 경우) 시 근무시간 보존:** 이동 시 서버가 원래 블록의 실제 근무시간(work minutes)을 계산한 뒤, 새 위치에서 동일한 근무시간이 나오도록 end_time을 재조정한다.

3. **소요시간 변경(PUT, duration_minutes) 시:** 상세 팝업에서 소요시간을 변경하면 start_time을 기준으로 duration_minutes만큼의 실제 근무시간이 되는 end_time을 계산한다.

4. **겹침 감지:** 같은 장소(location)의 같은 날짜에 시간이 겹치면 `409 Conflict`를 반환한다.

5. **블록 상태 → 태스크 연동:** `PUT /api/blocks/<id>/status`로 블록 상태를 변경하면 `_sync_task_status()`가 호출되어 해당 태스크의 모든 확정 블록 상태를 확인한 뒤 태스크 상태를 자동 갱신한다.
   - 모든 블록 `completed` → 태스크 `completed`
   - 일부 `in_progress` 또는 일부만 `completed` → 태스크 `in_progress`
   - 그 외 → 기존 상태 유지

#### 핵심 헬퍼 함수

| 함수 | 위치 | 설명 |
|------|------|------|
| `build_maps()` | `helpers/enrichment.py` | users/tasks/locations를 `{id: obj}` dict로 변환 |
| `enrich_blocks(blocks, ...)` | `helpers/enrichment.py` | 블록에 표시용 필드 추가 (procedure_id, assignee_name, location_name, color 등) |
| `get_queue_tasks(...)` | `helpers/enrichment.py` | 미배치 잔여시간이 있는 업무 목록 (큐 사이드바용) |
| `check_overlap(...)` | `helpers/overlap.py` | 같은 장소의 시간 겹침 검증. 겹치면 **겹치는 블록 객체** 반환, 아니면 `None` |
| `compute_overlap_layout(blocks)` | `helpers/overlap.py` | 겹치는 블록의 열 배치 계산 |

**`enrich_blocks` 결과 예시:**
```json
{
  "id": "sb_xxx",
  "task_id": "t_xxx",
  "procedure_id": "STP-001",
  "section_name": "통신 시험",
  "assignee_name": "홍길동, 김영희",
  "location_name": "시험실 A",
  "color": "#4A90D9",
  "date": "2026-03-15",
  "start_time": "09:00",
  "end_time": "12:00"
}
```

### 5.2 Tasks Blueprint (`/tasks`)

#### 페이지 렌더링

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/tasks/` | GET | 시험 항목 목록 (필터링: status, version, location, assignee, procedure) + 배치 상태 표시 |
| `/tasks/new` | GET/POST | 시험 항목 생성 |
| `/tasks/<id>` | GET | 시험 항목 상세 |
| `/tasks/<id>/edit` | GET/POST | 시험 항목 수정 |
| `/tasks/<id>/delete` | POST | 시험 항목 삭제 |

#### API

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/tasks/api/list` | GET | 시험 항목 목록 JSON (version 필터 지원) |
| `/tasks/api/<id>` | GET | 시험 항목 상세 JSON (enriched: assignee_names, location_name, version_name 포함) |
| `/tasks/api/create` | POST | 시험 항목 생성 |
| `/tasks/api/<id>/update` | PUT | 시험 항목 수정 |
| `/tasks/api/<id>/delete` | DELETE | 시험 항목 삭제 |
| `/tasks/api/procedure/<procedure_id>` | GET | 절차서 정보 조회 (외부 API 또는 mock) |

### 5.3 Admin Blueprint (`/admin`)

#### 페이지 렌더링

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/admin/settings` | GET/POST | 설정 폼 |
| `/admin/users` | GET | 사용자 목록 |
| `/admin/users/new` | GET/POST | 사용자 생성 |
| `/admin/users/<id>/edit` | GET/POST | 사용자 수정 |
| `/admin/users/<id>/delete` | POST | 사용자 삭제 |
| `/admin/locations` | GET | 장소 목록 |
| `/admin/locations/new` | GET/POST | 장소 생성 |
| `/admin/locations/<id>/edit` | GET/POST | 장소 수정 |
| `/admin/locations/<id>/delete` | POST | 장소 삭제 |
| `/admin/versions` | GET | 버전 목록 |
| `/admin/versions/new` | GET/POST | 버전 생성 |
| `/admin/versions/<id>/edit` | GET/POST | 버전 수정 |
| `/admin/versions/<id>/delete` | POST | 버전 삭제 |

#### API

설정, 사용자, 장소, 버전 각각 REST API 제공:
- `/admin/api/settings` (GET, PUT)
- `/admin/api/users` (GET, POST), `/admin/api/users/<id>` (PUT, DELETE)
- `/admin/api/locations` (GET, POST), `/admin/api/locations/<id>` (PUT, DELETE)
- `/admin/api/versions` (GET, POST), `/admin/api/versions/<id>` (PUT, DELETE)

---

## 6. 스케줄링 알고리즘 (`schedule/services/scheduler.py`)

### 6.1 자동 스케줄링: `generate_draft_schedule()`

```
1. 미완료 업무 조회 (status != 'completed' AND remaining_hours > 0)
2. 정렬: 절차서ID 순
3. 기존 초안 블록 전부 삭제 (clean slate)
4. 확정 블록 전부 조회 (이미 점유된 시간대 참조)
5. 전체 장소 목록 로드 (장소 자동 배정용)
6. 각 업무에 대해:
   a. hours_needed = remaining_hours - (이미 확정된 블록의 근무시간 합)
   b. 장소 후보 결정:
      - 태스크에 location_id 있음 → 해당 장소만 후보
      - 태스크에 location_id 없음 → 등록된 모든 장소가 후보
   c. 오늘부터 max_schedule_days(14일)까지 순회:
      - _find_best_slot()으로 후보 장소별 가장 빠른 빈 시간대 탐색
      - 가장 빠른 시간에 배치 가능한 장소를 선택하여 블록 생성 (is_draft=True, origin='auto')
      - hours_needed가 0이 되면 다음 업무로
   d. 14일 안에 배치 못하면 unplaced 목록에 추가
7. 반환: { placed: [블록 목록], unplaced: [업무 목록] }
```

> **왜 clean slate(전부 삭제 후 재생성)?**
> 증분 방식은 이전 초안의 위치가 최적이 아닐 수 있고,
> 우선순위 변경 시 전체 재배치가 필요하다. 매번 깨끗하게 다시 배치하는 것이 단순하고 정확하다.

### 6.2 당일 완료 제약

시험은 한번 시작하면 같은 날 끝나야 한다. 하루 가용 시간을 초과하는 시험은 배치하지 않고 unplaced로 보고한다.

### 6.3 장소 자동 배정

태스크에 `location_id`가 없으면 등록된 모든 장소를 후보로 하여, 각 날짜에서 가장 빠른 시간에 배치 가능한 장소를 자동 선택한다. `_find_best_slot()`이 후보 장소별로 `_find_slot_for_task()`를 호출하여 가장 이른 시작 시간의 슬롯을 반환한다.

### 6.4 겹침 방지

- **장소 충돌 방지:** 같은 장소+시간에 2개 시험 불가
- 스케줄러는 장소 기준으로 빈 시간대를 계산

---

## 7. 시간 유틸리티

### `schedule/helpers/time_utils.py`

| 함수 | 설명 |
|------|------|
| `time_to_minutes(t)` | "HH:MM" → 분 (예: "09:30" → 570) |
| `minutes_to_time(m)` | 분 → "HH:MM" (예: 570 → "09:30") |
| `get_break_periods(settings)` | 점심 + 추가 휴식을 `[(start_min, end_min)]` 튜플 리스트로 반환 |
| `adjust_end_for_breaks(start, end, settings)` | 휴식 시간만큼 end_time을 뒤로 밀어 실제 근무시간 보존 |
| `work_minutes_in_range(start, end, settings)` | 구간 내 실제 근무 **분** 계산 (휴식 차감) |
| `generate_time_slots(settings)` | 근무시간을 grid_interval 단위로 분할한 시간 목록 |
| `is_break_slot(time_str, settings)` | 해당 시각이 휴식 시간인지 판별 |

**`adjust_end_for_breaks` 예시:**
```
입력: start="11:00", end="13:00", 점심=12:00~13:00
원래 의도: 2시간 근무
하지만 11:00~13:00 사이에 점심 1시간이 포함됨
→ 실제 근무시간을 보존하기 위해 end를 1시간 뒤로 밀음
출력: "14:00" (11:00~14:00 = 3시간 중 점심 제외 2시간 근무)
```

### `schedule/services/scheduler.py` 내부 함수

| 함수 | 설명 |
|------|------|
| `_work_hours_in_range(start, end, settings)` | 실제 근무 **시간** (float) 반환 |
| `_compute_end_for_work_hours(start, hours, settings)` | 지정 근무시간이 되는 종료시각 계산 |
| `_find_best_slot(date, task, hours, candidate_locs, blocks, settings)` | 후보 장소별 가장 빠른 빈 슬롯 탐색 → `(start, end, location_id)` 또는 `None` |
| `_find_slot_for_task(date, task, hours, blocks, settings, location_id=None)` | 특정 장소(또는 태스크 기본 장소)의 빈 슬롯 탐색 |

---

## 8. 서비스 계층

### `schedule/services/scheduler.py` — 자동 스케줄링

위 6절 참조.

### `schedule/services/procedure.py` — 절차서 조회

외부 시스템의 절차서 정보를 조회하는 서비스. 현재는 `procedures.json` 파일에서 mock 데이터를 반환하며, 추후 외부 API 연동 예정.

### `schedule/services/export.py` — 내보내기

스케줄 블록을 CSV 또는 Excel 형식으로 내보내는 서비스.
