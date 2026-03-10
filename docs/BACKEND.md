# Backend 아키텍처 문서

## 1. 개요

Flask + Jinja2 기반 **서버 사이드 렌더링(SSR)** 애플리케이션.

> **SSR이란?** 브라우저가 요청할 때마다 서버에서 HTML을 완성하여 보내주는 방식.
> React/Vue 같은 SPA(Single Page Application)는 클라이언트에서 JS로 화면을 그리지만,
> 이 프로젝트는 서버(Jinja2 템플릿)에서 HTML을 렌더링한 뒤 브라우저에 전달한다.
> 빌드 도구 없이 간단하게 동작하며, JS는 드래그앤드롭 등 인터랙션에만 사용된다.

데이터베이스 없이 JSON 파일로 데이터를 관리하며, **Repository 패턴**으로 데이터 접근을 추상화한다.

> **Repository 패턴이란?** 데이터 저장소(여기선 JSON 파일)에 대한 읽기/쓰기를
> 전용 모듈(Repository)로 분리하는 설계 패턴이다.
> Route 코드에서 `json_store.read_json('tasks.json')`을 직접 호출하는 대신
> `task_repo.get_all()`처럼 의미 있는 메서드로 접근한다.
> **장점:** 저장 방식이 바뀌어도(예: JSON → DB) Route 코드는 수정할 필요 없다.

> **인증 없음:** 이 앱에는 로그인/인증이 없다. 누구나 모든 데이터를 조회·수정·삭제할 수 있다.

```
요청 흐름 (두 가지 패턴):

1) 단순 CRUD (대부분의 요청):
   Browser → Blueprint (Route) → Repository → JSON File

2) 복잡한 비즈니스 로직 (자동 스케줄링):
   Browser → Blueprint (Route) → Service (scheduler.py)
                                      ↓
                                 Repository → JSON File

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

### `config.py`
```python
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    DATA_DIR = os.path.join(BASE_DIR, 'data')   # JSON 파일 저장 경로
```

### `app/__init__.py` — `create_app()`

| 단계 | 설명 |
|------|------|
| 1 | Flask 인스턴스 생성, Config 로드 |
| 2 | `SEND_FILE_MAX_AGE_DEFAULT = 0` — 브라우저 캐시 비활성화 (개발 편의용. CSS/JS 수정 시 즉시 반영) |
| 3 | `data/` 디렉토리 자동 생성 (없으면) |
| 4 | Jinja2 전역 함수 등록: `enumerate`, `cache_bust` |
| 5 | CORS 헤더 추가 (`Access-Control-Allow-Origin: *`) |
| 6 | Blueprint 3개 등록 (아래 참조) |
| 7 | 루트 `/` → `/schedule/` 리다이렉트 |

**`cache_bust`란?** 서버 기동 시각의 타임스탬프 값. 템플릿에서 `<script src="drag_drop.js?v={{ cache_bust }}">`처럼 사용하여, 서버를 재시작할 때마다 브라우저가 캐시된 이전 JS/CSS가 아닌 최신 파일을 로드하게 한다.

**CORS가 필요한 이유:** 같은 서버에서 렌더링하므로 엄밀히 CORS가 필수는 아니지만, 외부 도구(Postman, 다른 프론트엔드)에서 API를 호출할 때를 대비한 설정이다.

**Blueprint 등록:**

| Blueprint | URL Prefix | 역할 |
|-----------|-----------|------|
| `schedule_bp` | `/schedule` | 캘린더 뷰 + 블록 CRUD |
| `tasks_bp` | `/tasks` | 업무 CRUD |
| `admin_bp` | `/admin` | 설정/사용자/카테고리 관리 |

### `run.py`
```python
app = create_app()
app.run(host='0.0.0.0', port=5001, debug=True)
```
> macOS AirPlay가 5000 포트를 점유하므로 5001 사용.

---

## 3. 데이터 저장 계층

### `app/json_store.py` — JSON I/O + 파일 잠금

| 함수 | 설명 |
|------|------|
| `generate_id(prefix)` | `"{prefix}{uuid4().hex[:8]}"` 형식 ID 생성 (예: `t_a1b2c3d4`) |
| `_get_path(filename)` | `current_app.config['DATA_DIR'] + filename`으로 전체 경로 반환. **주의:** Flask 앱 컨텍스트 안에서만 동작한다. 스크립트에서 직접 호출하면 에러 발생. |
| `read_json(filename)` | portalocker 읽기 잠금 → JSON 파싱 → 반환 |
| `write_json(filename, data)` | `.bak` 백업 생성 → portalocker 쓰기 잠금 → JSON 저장 |

> **파일 잠금(portalocker)이란?**
> 웹 서버는 여러 요청을 동시에 처리한다. 만약 두 요청이 같은 JSON 파일을
> 동시에 읽고 쓰면 데이터가 깨질 수 있다.
> `portalocker`는 OS 수준의 파일 잠금을 제공하여 한 번에 하나의 프로세스만
> 파일을 수정할 수 있게 한다 (5초 타임아웃).
>
> - **읽기 잠금** (`'r'` 모드): 여러 프로세스가 동시에 읽을 수 있지만, 쓰기를 차단
> - **쓰기 잠금** (`'w'` 모드): 다른 모든 접근을 차단하고 단독으로 쓰기

> **`.bak` 백업이란?**
> `write_json` 호출 시 기존 파일을 `tasks.json.bak`으로 복사한 뒤 새 내용을 쓴다.
> 쓰기 도중 오류가 발생하면 `.bak` 파일에서 수동으로 복구할 수 있다.
> (자동 복구 로직은 없음 — 관리자가 직접 `.bak` 파일을 원본으로 복원해야 한다.)

> **트랜잭션 부재 주의:**
> JSON 파일 기반이므로 여러 파일을 수정하는 작업(예: 블록 삭제 후 task remaining_hours 갱신)
> 도중 에러가 나면 한쪽만 수정되어 데이터 불일치가 생길 수 있다. DB의 트랜잭션 같은 원자성 보장이 없다.

**핵심 설계:**
- `ensure_ascii=False`로 한글 직접 저장
- 빈 파일은 `[]` 반환 (settings는 `{}`)
- 매 호출마다 파일 전체를 읽고 쓴다 (데이터가 수천 건 이상이면 성능 저하 가능)

### 데이터 파일 구조

```
data/
├── users.json            ← 팀원 목록
├── tasks.json            ← 업무 목록
├── categories.json       ← 카테고리 목록
├── schedule_blocks.json  ← 스케줄 블록
└── settings.json         ← 시스템 설정
```

**ID 접두사 규칙:**

| 접두사 | 엔티티 | 예시 |
|--------|--------|------|
| `u_` | User | `u_3f8a1b2c` |
| `t_` | Task | `t_7e4d9c0a` |
| `c_` | Category | `c_1a2b3c4d` |
| `sb_` | Schedule Block | `sb_5f6e7d8c` |

---

## 4. Repository 계층

각 Repository는 단일 JSON 파일에 대한 CRUD를 제공한다.

> **`update` vs `patch` 용어 주의:**
> - `user_repo.update()`, `category_repo.update()` — **전체 갱신.** 모든 필드를 인자로 받아 덮어쓴다.
> - `task_repo.patch()` — **부분 갱신.** 전달된 kwargs 필드만 수정. **화이트리스트 없음** — 어떤 필드든 수정 가능.
> - `schedule_repo.update()` — **부분 갱신처럼 동작.** kwargs로 전달된 필드만 수정하되, **화이트리스트**(`ALLOWED_FIELDS`)로 허용 필드를 제한한다.
>
> 같은 `update`라는 이름이지만 repo마다 동작이 다르므로 주의.

### 4.1 `user_repo.py` → `users.json`

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

### 4.2 `category_repo.py` → `categories.json`

```json
{ "id": "c_xxx", "name": "프론트엔드", "color": "#E74C3C" }
```

| 메서드 | 설명 |
|--------|------|
| `get_all()` / `get_by_id()` / `create()` / `update()` / `delete()` | 기본 CRUD |

### 4.3 `task_repo.py` → `tasks.json`

```json
{
  "id": "t_xxx",
  "title": "로그인 기능 구현",
  "description": "OAuth2 로그인 연동",
  "assignee_id": "u_xxx",
  "category_id": "c_xxx",
  "priority": "high",           // high | medium | low
  "estimated_hours": 8.0,
  "remaining_hours": 5.5,       // 아직 스케줄되지 않은 시간
  "deadline": "2026-03-15",
  "status": "in_progress",      // waiting | in_progress | completed
  "created_at": "2026-03-01T09:00:00"
}
```

| 메서드 | 설명 |
|--------|------|
| `get_all()` | 전체 업무 목록 |
| `get_by_id(task_id)` | ID로 조회 |
| `create(title, description, assignee_id, ...)` | 생성. `status='waiting'`, `remaining_hours=estimated_hours`로 초기화 |
| `update(task_id, title, ...)` | **전체** 필드 갱신 — 모든 인자 필요 |
| `patch(task_id, **kwargs)` | **부분** 갱신 — 전달된 필드만 수정 (화이트리스트 없음) |
| `delete(task_id)` | 삭제 |

### 4.4 `schedule_repo.py` → `schedule_blocks.json`

```json
{
  "id": "sb_xxx",
  "task_id": "t_xxx",
  "assignee_id": "u_xxx",
  "date": "2026-03-15",
  "start_time": "09:00",
  "end_time": "12:00",
  "is_draft": false,         // true=초안(자동 배치), false=확정
  "is_locked": false,        // true=잠금(이동/삭제 방지)
  "origin": "manual",        // "manual"(수동) | "auto"(자동 스케줄링)
  "block_status": "pending", // pending | in_progress | completed | cancelled
  "memo": ""
}
```

**`block_status` 값의 의미:**

| 값 | 한국어 | 설명 |
|----|--------|------|
| `pending` | 시작 전 | 아직 작업을 시작하지 않은 상태 (기본값) |
| `in_progress` | 진행 중 | 현재 작업 중 |
| `completed` | 완료 | 작업 완료 |
| `cancelled` | 불가 | 해당 시간에 작업 불가능 (회의, 외출 등으로 취소) |

| 메서드 | 설명 |
|--------|------|
| `get_all()` | 전체 블록 |
| `get_by_id(block_id)` | ID로 조회 |
| `get_by_date(date_str)` | 특정 날짜의 블록 |
| `get_by_date_range(start, end)` | 날짜 범위 블록 (inclusive) |
| `get_by_assignee(assignee_id)` | 담당자별 블록 |
| `create(task_id, assignee_id, date, start_time, end_time, ...)` | 생성 (기본값: `is_draft=False`, `origin='manual'`, `block_status='pending'`) |
| `update(block_id, **kwargs)` | 부분 갱신 — **화이트리스트 필드만 허용** (아래 참조) |
| `delete(block_id)` | 삭제 |
| `delete_drafts()` | 모든 초안 블록 삭제 |
| `approve_drafts()` | 모든 초안의 `is_draft`를 `False`로 변경 |

**Repository 레벨 update 허용 필드 (ALLOWED_FIELDS):**
`date`, `start_time`, `end_time`, `is_draft`, `is_locked`, `block_status`, `task_id`, `assignee_id`, `origin`, `memo`

> **이중 필터링 주의:**
> Route (`PUT /api/blocks/<id>`)에서도 별도의 `allowed` 세트로 한 번 더 필터링한다:
> `{'date', 'start_time', 'end_time', 'is_draft', 'is_locked', 'block_status'}`
> 즉 API로는 `task_id`, `assignee_id`, `origin`, `memo`를 변경할 수 **없다**.
> (`memo`는 전용 엔드포인트 `PUT /api/blocks/<id>/memo`를 사용)

### 4.5 `settings_repo.py` → `settings.json`

```json
{
  "work_start": "09:00",
  "work_end": "18:00",
  "lunch_start": "12:00",
  "lunch_end": "13:00",
  "breaks": [
    { "start": "09:45", "end": "10:00" },
    { "start": "14:45", "end": "15:00" }
  ],
  "grid_interval_minutes": 15,
  "max_schedule_days": 14,
  "block_color_by": "assignee"  // "assignee" | "category"
}
```

| 메서드 | 설명 |
|--------|------|
| `get()` | 설정 반환 (파일 없으면 위 기본값) |
| `update(data)` | 현재 설정에 `data` 병합 후 저장 |

---

## 5. Blueprint 라우팅

### 5.1 Schedule Blueprint (`/schedule`)

#### 페이지 렌더링

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/schedule/` | GET | 일간 뷰 (`day.html`) |
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
| `/schedule/api/blocks/<id>` | PUT | 200 | 블록 수정 (이동, 리사이즈) |
| `/schedule/api/blocks/<id>` | DELETE | 200 | 블록 삭제 (항상 remaining_hours 재계산) |
| `/schedule/api/blocks/<id>/lock` | PUT | 200 | 잠금 토글 |
| `/schedule/api/blocks/<id>/status` | PUT | 200 | 상태 변경 |
| `/schedule/api/blocks/<id>/memo` | PUT | 200 | 메모 수정 |

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
   프론트엔드에서 보낸 end_time과 실제 저장된 값이 다를 수 있다.

2. **블록 이동(PUT, resize가 아닌 경우) 시 근무시간 보존:** 이동 시 서버가 원래 블록의 실제 근무시간(work minutes)을 계산한 뒤, 새 위치에서 동일한 근무시간이 나오도록 end_time을 재조정한다.

3. **겹침 감지:** 같은 담당자의 같은 날짜에 시간이 겹치면 `409 Conflict`를 반환한다.

#### 핵심 헬퍼 함수

| 함수 | 설명 |
|------|------|
| `_build_maps()` | users/tasks/categories를 `{id: obj}` dict로 변환 |
| `_enrich_blocks(blocks, ...)` | 블록에 표시용 필드 추가 (아래 예시 참조) |
| `_get_queue_tasks(...)` | 미배치 잔여시간이 있는 업무 목록 (큐 사이드바용) |
| `_check_overlap(...)` | 같은 담당자의 시간 겹침 검증. 겹치면 **겹치는 블록 객체** 반환, 아니면 `None` |
| `_compute_overlap_layout(blocks)` | 겹치는 블록의 열 배치 계산 (아래 설명 참조) |
| `_sync_task_remaining_hours(task_id)` | `remaining = estimated - 전체 블록 시간 합계` 재계산 |

**`_enrich_blocks` 결과 예시:**
```json
{
  "id": "sb_xxx",
  "task_id": "t_xxx",
  "task_title": "로그인 구현",      // ← 추가됨
  "assignee_name": "홍길동",        // ← 추가됨
  "category_name": "프론트엔드",    // ← 추가됨
  "color": "#4A90D9",               // ← 추가됨 (block_color_by 설정에 따라 담당자 또는 카테고리 색상)
  "date": "2026-03-15",
  "start_time": "09:00",
  "end_time": "12:00"
}
```

### 5.2 Tasks Blueprint (`/tasks`)

#### 페이지 렌더링

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/tasks/` | GET | 업무 목록 (필터링: status, assignee, priority, category) |
| `/tasks/new` | GET/POST | 업무 생성 |
| `/tasks/<id>` | GET | 업무 상세 |
| `/tasks/<id>/edit` | GET/POST | 업무 수정 |
| `/tasks/<id>/delete` | POST | 업무 삭제 |

#### API

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/tasks/api/list` | GET | 업무 목록 JSON (필터 지원) |
| `/tasks/api/<id>` | GET | 업무 상세 JSON |
| `/tasks/api/create` | POST | 업무 생성 |
| `/tasks/api/<id>/update` | PUT | 업무 수정 |
| `/tasks/api/<id>/delete` | DELETE | 업무 삭제 |

### 5.3 Admin Blueprint (`/admin`)

#### 페이지 렌더링

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/admin/settings` | GET/POST | 설정 폼 (시간은 15분 단위로 스냅) |
| `/admin/users` | GET | 사용자 목록 |
| `/admin/users/new` | GET/POST | 사용자 생성 |
| `/admin/users/<id>/edit` | GET/POST | 사용자 수정 |
| `/admin/users/<id>/delete` | POST | 사용자 삭제 |
| `/admin/categories` | GET | 카테고리 목록 |
| `/admin/categories/new` | GET/POST | 카테고리 생성 |
| `/admin/categories/<id>/edit` | GET/POST | 카테고리 수정 |
| `/admin/categories/<id>/delete` | POST | 카테고리 삭제 |

#### API

설정, 사용자, 카테고리 각각 REST API 제공 (`/admin/api/settings`, `/admin/api/users`, `/admin/api/categories`).

---

## 6. 스케줄링 알고리즘 (`app/services/scheduler.py`)

### 6.1 자동 스케줄링: `generate_draft_schedule()`

```
1. 미완료 업무 조회 (status != 'completed' AND remaining_hours > 0)
2. 정렬: 마감일 오름차순 → 우선순위(high > medium > low)
3. 기존 초안 블록 전부 삭제 (clean slate — 아래 설명 참조)
4. 확정 블록 전부 조회 (이미 점유된 시간대 참조)
5. 각 업무에 대해:
   a. hours_needed = remaining_hours - (이미 확정된 블록의 근무시간 합)
   b. 오늘부터 max_schedule_days(14일)까지 순회:
      - 해당 날짜에서 담당자의 빈 시간대(slot) 계산
      - 빈 시간대에 블록 생성 (is_draft=True, origin='auto')
      - hours_needed가 0이 되면 다음 업무로
   c. 14일 안에 배치 못하면 unplaced 목록에 추가
6. 반환: { placed: [블록 목록], unplaced: [업무 목록] }
```

> **왜 clean slate(전부 삭제 후 재생성)?**
> 증분 방식(기존 초안을 유지하고 부족한 것만 추가)은 이전 초안의 위치가 최적이 아닐 수 있고,
> 업무 우선순위 변경 시 전체 재배치가 필요하다. 매번 깨끗하게 다시 배치하는 것이 단순하고 정확하다.

> **5-a 단계 상세:**
> `remaining_hours`는 "아직 스케줄되지 않은 총 시간"이지만, 이미 **확정된** 블록이
> 일부 시간을 차지하고 있을 수 있다. 스케줄러는 확정 블록의 **실제 근무시간**(휴식 제외)을
> 계산하여 빼므로, `hours_needed`는 "추가로 초안을 배치해야 할 시간"이 된다.

### 6.2 빈 시간대 계산: `_get_available_work_slots()`

```
입력: date, assignee_id, existing_blocks, settings
출력: [(start_time, end_time, work_hours), ...]

1. 해당 날짜 + 담당자의 기존 블록에서 점유 시간대 추출
2. 근무시간(09:00~18:00)에서 점유 시간대를 제외한 빈 구간 계산
3. 각 빈 구간에서 실제 근무시간 계산 (휴식 시간 차감)
4. work_hours > 0인 슬롯만 반환
```

**중요:** 슬롯은 휴식시간으로 분할되지 않는다.
이유: 하나의 업무 블록이 점심시간을 걸쳐서 배치될 수 있기 때문이다.
예를 들어 11:00~14:00 블록은 점심(12:00~13:00)을 포함하지만 실제 근무시간은 2시간이다.
슬롯을 휴식 기준으로 나누면 이런 배치가 불가능해진다.

**구체적 예시:** 09:00~18:00 근무, 12:00~13:00 점심, 이미 10:00~11:00에 블록이 있는 경우:

```
점유 시간대: [10:00~11:00]
전체 근무: 09:00~18:00

빈 구간 계산:
  1) 09:00~10:00 → 휴식 없음 → work_hours = 1.0h
  2) 11:00~18:00 → 점심 1시간 차감 → work_hours = 6.0h

반환: [("09:00", "10:00", 1.0), ("11:00", "18:00", 6.0)]
```

### 6.3 근무시간 계산: `_work_hours_in_range()`

```
입력: start_time, end_time, settings
출력: 실제 근무시간 (float, hours)

계산: 전체 구간 - (점심 겹침 + 각 휴식 겹침) = 실제 근무 분

예시: 11:00~15:00
  전체 = 240분
  점심(12:00~13:00) 겹침 = 60분
  오후 휴식(14:45~15:00) 겹침 = 15분
  실제 근무 = 240 - 60 - 15 = 165분 = 2.75시간
```

### 6.4 종료시각 계산: `_compute_end_for_work_hours()`

```
입력: start_time, work_hours, settings
출력: end_time (15분 스냅)

알고리즘: 시작 시각부터 전진하며 휴식시간을 건너뛰어
          정확히 work_hours만큼의 실제 근무시간이 되는 종료시각 계산

예시: 09:00 시작, 4시간 근무
  09:00-09:45 (45분 근무)
  (09:45-10:00 휴식 건너뜀)
  10:00-12:00 (120분 근무)
  (12:00-13:00 점심 건너뜀)
  13:00-14:00 (60분 근무) → 여기까지 225분 = 3.75시간
  14:00-14:15 (15분 근무) → 240분 = 4시간
  → 종료시각: 14:15
```

### 6.5 초안 확정: `approve_drafts()`

```
1. 모든 초안 블록 조회 (is_draft=True)
2. is_draft = False로 변경 (확정)
3. 각 업무별로 초안 블록의 근무시간 합산 (_work_hours_in_range 사용, 휴식 제외)
4. task.remaining_hours -= 합산 시간
5. remaining_hours ≤ 0이면 task.status = 'completed'
```

> **참고:** `waiting` 상태의 업무에 블록이 확정되어도 `in_progress`로 자동 변경되지 않는다.
> 기존 상태가 유지된다 (코드: `new_status = 'completed' if new_remaining <= 0 else task['status']`).

### 6.6 초안 폐기: `discard_drafts()`

모든 초안 블록 삭제.

---

## 7. 시간 유틸리티

> **주의: 시간 관련 유틸리티가 두 곳에 존재한다.**
>
> | 위치 | 사용처 | 반환 단위 |
> |------|--------|----------|
> | `app/utils/time_utils.py` | routes.py | **분** (정수) |
> | `app/services/scheduler.py` 내부 함수 | scheduler.py 자체 | **시간** (float) |
>
> 예를 들어:
> - `time_utils.work_minutes_in_range()` → **분** 반환 (예: 120)
> - `scheduler._work_hours_in_range()` → **시간** 반환 (예: 2.0)
>
> 두 모듈의 함수 이름과 시그니처가 비슷하지만 반환값이 다르므로 혼동하지 않도록 주의.

### `app/utils/time_utils.py`

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

### `app/services/scheduler.py` 내부 함수

| 함수 | 설명 |
|------|------|
| `_parse_time(time_str)` | "HH:MM" → datetime 객체 |
| `_format_time(dt)` | datetime → "HH:MM" |
| `_get_break_periods(settings)` | `[("12:00", "13:00"), ...]` **문자열** 튜플 반환 |
| `_work_hours_in_range(start, end, settings)` | 실제 근무 **시간** (float) 반환 |
| `_compute_end_for_work_hours(start, hours, settings)` | 지정 근무시간이 되는 종료시각 계산 |

---

## 8. remaining_hours 동기화 흐름

```
[블록 생성/수정/삭제]
       ↓
  _sync_task_remaining_hours(task_id)
       ↓
  1. task = task_repo.get_by_id(task_id)
  2. blocks = 해당 task의 모든 블록 조회
  3. total_scheduled = 각 블록의 (end_time - start_time) 합계
  4. remaining = estimated_hours - total_scheduled
  5. task_repo.patch(task_id, remaining_hours=remaining)
```

> **주의: 휴식시간 포함 여부의 불일치**
>
> `_sync_task_remaining_hours`는 `time_to_minutes(end) - time_to_minutes(start)`로 계산하므로
> **휴식시간을 포함한 전체 시간**을 사용한다.
> 반면 `approve_drafts`는 `_work_hours_in_range`로 **휴식시간을 제외한 실제 근무시간**을 사용한다.
>
> 즉 같은 `remaining_hours` 필드를 서로 다른 기준으로 계산하는 곳이 공존한다.
> 이것은 잠재적 데이터 불일치의 원인이 될 수 있다.

**동기화 실행 조건:**

| 상황 | 동기화 여부 | 이유 |
|------|------------|------|
| 블록 생성 (`POST /api/blocks`) | O | 새 블록 시간만큼 remaining 감소 |
| 블록 리사이즈 (`PUT`, `resize=true`) | O | 블록 크기가 변경되었으므로 재계산 |
| 블록 이동 (`PUT`, resize 아님) | X | 이동은 근무시간이 보존되므로 변경 불필요 |
| 블록 삭제 (`DELETE`) | O | 항상 재계산 |

---

## 9. 겹침 감지 및 레이아웃

### 겹침 감지 (`_check_overlap`)

```python
def _check_overlap(assignee_id, date_str, start_time, end_time, exclude_block_id=None):
    # 같은 담당자 + 같은 날짜의 블록 중
    # 시간이 겹치는 블록이 있으면 해당 블록 객체를 반환 (None이면 겹침 없음)
    # exclude_block_id: 자기 자신은 제외 (수정 시)
```

겹침이 감지되면 `409 Conflict` 응답:
```json
{ "error": "해당 시간에 이미 다른 업무가 배치되어 있습니다." }
```

### 겹침 레이아웃 (`_compute_overlap_layout`)

같은 시간대에 여러 블록이 있을 때, 나란히 표시하기 위한 열 배치 계산:

```
입력: 같은 날짜의 블록 리스트
출력: 각 블록에 col_index, col_total 추가

예시: 3개 블록이 09:00~11:00에 겹치는 경우

정렬 후 열 배치:
  블록A (09:00~10:30) → col_index=0
  블록B (09:00~11:00) → col_index=1  (0열은 A가 사용 중)
  블록C (09:30~10:00) → col_index=2  (0,1열 모두 사용 중)

  모두 같은 겹침 그룹 → col_total = 3

프론트엔드 렌더링:
  블록A: width=33.3%, left=0%
  블록B: width=33.3%, left=33.3%
  블록C: width=33.3%, left=66.6%
```

---

## 10. 내보내기 기능

`GET /schedule/api/export?start_date=...&end_date=...&format=csv|xlsx`

- CSV: `csv.writer`로 직접 생성
- XLSX: `openpyxl` 라이브러리 사용. **`openpyxl`이 설치되지 않은 경우 자동으로 CSV 폴백.**
- 컬럼: 날짜, 시간, 담당자, 업무명, 카테고리, 상태, 메모
- 블록을 날짜+시간 순으로 정렬하여 출력

---

## 11. 에러 처리

API 응답 형식:
```json
// 성공 (블록 생성)
{ "ok": true, "block": {...} }

// 실패
{ "error": "해당 시간에 이미 다른 업무가 배치되어 있습니다." }
```

> **에러 메시지는 하드코딩된 한국어.** 다국어(i18n) 미지원.

HTTP 상태 코드:

| 코드 | 의미 | 사용처 |
|------|------|--------|
| `200` | 성공 | 조회, 수정, 삭제 |
| `201` | 생성 성공 | 블록 생성 (`POST /api/blocks`) |
| `400` | 유효성 검증 실패 | 필수 필드 누락, 잘못된 시간 형식 |
| `404` | 없음 | 블록/업무 ID가 존재하지 않을 때 |
| `409` | 충돌 | 같은 담당자의 시간 겹침 |
