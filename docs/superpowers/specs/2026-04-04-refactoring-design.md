# Scheduling App Refactoring Design

## Context
기능 추가가 반복되면서 코드 중복, 거대한 단일 파일, 테스트 부족 문제가 누적됨.
전체 리팩토링으로 가독성, 유지보수성, 안정성을 개선한다.

## Scope
백엔드(Python) + 프론트엔드(JS/CSS) 전체. 드래그앤드롭 동작은 특히 주의.

---

## 1. 백엔드: 모델 BaseRepository 추출

### 현재 문제
5개 모델(user, location, version, task, schedule_block)이 동일한 CRUD 코드를 복붙.

### 설계
`schedule/models/base.py`에 공통 클래스 추출:

```python
class BaseRepository:
    FILENAME = ''
    ID_PREFIX = ''

    @classmethod
    def get_all(cls): ...
    @classmethod
    def get_by_id(cls, item_id): ...
    @classmethod
    def create(cls, data): ...
    @classmethod
    def update(cls, item_id, **kwargs): ...
    @classmethod
    def patch(cls, item_id, **kwargs): ...
    @classmethod
    def delete(cls, item_id): ...
```

각 모델은 상속 후 고유 로직만 추가:
```python
class TaskRepository(BaseRepository):
    FILENAME = 'tasks.json'
    ID_PREFIX = 't_'

    @classmethod
    def get_by_version(cls, version_id): ...
    @classmethod
    def validate_unique_identifiers(cls, test_list, exclude_task_id=None): ...
```

### 파일 변경
- 신규: `schedule/models/base.py`
- 수정: `schedule/models/user.py`, `location.py`, `version.py`, `task.py`, `schedule_block.py`

---

## 2. 백엔드: calendar.py 분리

### 현재 문제
736줄 단일 파일. 뷰 3개 + API 3개가 90% 동일 setup 코드.

### 설계
`schedule/routes/calendar.py`를 역할별로 분리:

- `schedule/routes/calendar_views.py` — day/week/month 뷰 렌더링
- `schedule/routes/calendar_api.py` — 블록 CRUD API
- `schedule/routes/calendar_helpers.py` — `_prepare_view_context()`, `_sync_task_remaining_hours()` 등 공통 함수

공통 뷰 컨텍스트:
```python
def _prepare_view_context(date_range, version_id=None):
    """Build maps, fetch blocks, enrich, get queue — used by all views."""
    sttngs = settings.get()
    users_map, tasks_map, locations_map = build_maps()
    blocks = schedule_block.get_by_date_range(*date_range)
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = enrich_blocks(blocks, users_map, tasks_map, locations_map,
                             sttngs.get('block_color_by', 'assignee'))
    queue = get_queue_tasks(users_map, locations_map, version_id)
    return sttngs, enriched, queue, locations_map
```

### 라우트 등록
`schedule/routes/__init__.py`에서 통합 등록.

---

## 3. 프론트엔드: drag_drop.js 모듈 분할

### 현재 문제
1,483줄 단일 IIFE. 모든 기능이 한 파일에 혼재.

### 설계 (드래그앤드롭 동작 보존 최우선)
파일 분할하되 **전역 상태와 이벤트 흐름은 유지**:

```
schedule/static/js/
├── schedule-app.js      ← 진입점 (DOMContentLoaded, 전역상태)
├── utils.js             ← api(), time helpers, showToast
├── modals.js            ← showConfirmModal, showRemainingAlert, openMemoModal
├── drag-core.js         ← startDrag(), findTarget(), ghost, highlight
├── block-move.js        ← initBlockMove(), initMonthBlockMove()
├── block-resize.js      ← initResize()
├── queue-drag.js        ← initQueueDrag(), identifier picker
├── context-menu.js      ← initContextMenu(), split picker
├── block-detail.js      ← showTaskDetailPopup(), initBlockDetail()
├── schedule-features.js ← weekend toggle, shift, simple block, queue search
```

**핵심 원칙:**
- 각 모듈은 `window.ScheduleApp` 네임스페이스에 등록
- `drag-core.js`의 `startDrag()`는 다른 모듈에서 `ScheduleApp.startDrag()`로 호출
- 이벤트 바인딩 순서는 기존과 동일하게 `schedule-app.js`에서 관리
- **IIFE 패턴 유지** — 모듈 번들러 없이 스크립트 태그 순서로 로드

### 로드 순서
```html
<script src="js/utils.js"></script>
<script src="js/modals.js"></script>
<script src="js/drag-core.js"></script>
<script src="js/block-move.js"></script>
<script src="js/block-resize.js"></script>
<script src="js/queue-drag.js"></script>
<script src="js/context-menu.js"></script>
<script src="js/block-detail.js"></script>
<script src="js/schedule-features.js"></script>
<script src="js/schedule-app.js"></script>
```

### 테스트 전략
분할 전후로 수동 테스트 체크리스트:
- [ ] 큐→시간표 드래그 (단일/분할)
- [ ] 블록 이동 (같은날/다른날/큐복귀)
- [ ] 블록 리사이즈 (늘리기/줄이기/경고팝업)
- [ ] 우클릭 메뉴 (상태변경/분리/삭제)
- [ ] 더블클릭 상세팝업
- [ ] 주말토글, 일정이동

---

## 4. CSS 정리

### 설계
- CSS 변수로 색상 토큰화 (`:root { --color-text: #1e293b; ... }`)
- 중복 규칙 제거 (`.queue-card-hours`, `.queue-card-id` 중복)
- 미사용 드래프트 관련 스타일 정리

---

## 5. 데이터 정리

### 미사용 필드 제거
- `tasks.json`: `procedure_owner` → hidden 유지하되 UI 노출 없음 (이미 완료)
- `schedule_blocks.json`: `origin` 필드 — 사용처 없음, 제거
- `schedule_blocks.json`: `is_draft` — 자동스케줄링 제거됨, 제거

### 마이그레이션
기존 데이터에서 불필요 필드 strip하는 스크립트 추가.

---

## 6. 테스트 보강

### 추가할 테스트

**calendar API 테스트 (최우선):**
- 블록 생성 (일반/간단블록)
- 블록 이동, 리사이즈
- 블록 분리 (split API)
- 일정 이동 (shift API)
- 큐 복귀 시 장소 초기화
- 겹침 감지 (overlap)
- 식별자 이동 (_remove_identifiers_from_other_blocks)

**enrichment 테스트:**
- enrich_blocks: 분할 블록, 간단 블록, 삭제된 task
- get_queue_tasks: 버전 필터, completed 제외, 잔여시간 계산

**통합 테스트:**
- task 생성 → 블록 배치 → 리사이즈 → 큐 복귀 → 재배치 시나리오

---

## 구현 순서

1. **테스트 먼저** — 현재 동작을 테스트로 고정
2. **백엔드 모델** — BaseRepository 추출
3. **백엔드 라우트** — calendar.py 분리
4. **데이터 정리** — 미사용 필드 제거
5. **CSS 정리** — 변수화, 중복 제거
6. **JS 분할** — 가장 마지막 (테스트로 검증하며 진행)

---

## 검증

- `pytest tests/ -v` 전체 통과
- 수동 체크리스트로 드래그앤드롭 검증
- 서버 구동 후 주요 페이지 렌더링 확인
