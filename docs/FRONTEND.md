# Frontend 기술 문서

이 프로젝트의 프론트엔드는 Jinja2 서버 렌더링, Bootstrap 5, 바닐라 JavaScript로 구성된다. 번들러는 없으며 스케줄 화면은 `window.ScheduleApp` 네임스페이스에 기능을 등록한다.

## 1. 화면 진입 흐름

1. 사용자가 `/schedule/week`, `/schedule/`, `/schedule/month` 중 하나에 접속한다.
2. Flask 라우트가 Jinja2 템플릿에 task, block, location, setting 데이터를 넣어 렌더링한다.
3. 템플릿의 `{% block scripts %}`가 `window.SCHEDULE_BREAKS`, `window.GRID_INTERVAL` 같은 화면별 설정을 먼저 주입한다.
4. 공통 JS 모듈들이 순서대로 로드된다.
5. `schedule-app.js`가 `DOMContentLoaded`에서 각 기능 초기화 함수를 호출한다.
6. 사용자의 드래그, 리사이즈, 팝업 저장은 `/schedule/api/*`로 전송되고 성공 시 화면을 갱신한다.

## 2. 템플릿 구조

```text
app/templates/
├── layouts/base.html
├── schedule/
│   ├── base.html
│   ├── views/day.html
│   ├── views/week.html
│   ├── views/month.html
│   ├── views/_task_queue.html
│   ├── views/_location_filter.html
│   ├── views/_version_selector.html
│   ├── tasks/list.html
│   ├── tasks/detail.html
│   ├── tasks/form.html
│   └── admin/*.html
└── execution/
    ├── base.html
    ├── index.html
    ├── day.html
    └── detail.html
```

스케줄 템플릿은 `schedule/base.html`을 기준으로 Bootstrap, vendor 파일, schedule CSS/JS를 로드한다. 현재 등록된 실행 목록(`/execution/`)은 `layouts/base.html`을 상속하고, 실행 상세(`/execution/<identifier_id>`)는 `execution/base.html`을 상속한다. `execution/day.html`과 `routes/execution_views.py`는 현재 URL 맵에 등록되지 않은 legacy 일간 실행 화면이다.

## 3. Schedule JS 모듈 로드 순서

`app/static/schedule/js/` 모듈은 의존 순서가 있다.

```text
utils.js
modals.js
drag-core.js
block-move.js
block-resize.js
queue-drag.js
context-menu.js
block-detail.js
schedule-features.js
schedule-app.js
```

각 파일은 아래 패턴으로 기능을 등록한다.

```javascript
window.ScheduleApp = window.ScheduleApp || {};
(function(App) {
  App.someFeature = someFeature;
})(window.ScheduleApp);
```

새 기능을 추가할 때는 먼저 `utils.js`의 공통 함수/API 래퍼를 재사용할 수 있는지 확인하고, 초기화 함수는 마지막에 `schedule-app.js`에서 호출한다.

## 4. Schedule 모듈 역할

| 파일 | 역할 |
| --- | --- |
| `utils.js` | 시간 계산, API 호출, 토스트, 읽기 전용 판별, 공통 상수 |
| `modals.js` | 확인/메모 모달 |
| `drag-core.js` | 드래그 시작, 고스트, 드롭 타깃 탐색, 컬럼 가이드 |
| `block-move.js` | 시간표 블록 이동, 월간 블록 이동, 큐 복귀 |
| `block-resize.js` | 블록 상/하 리사이즈와 축소 확인 |
| `queue-drag.js` | 큐 task 드래그, 식별자 선택 피커, 블록 생성 |
| `context-menu.js` | 우클릭 메뉴, 상태 변경, 잠금, 분리, 삭제 |
| `block-detail.js` | 더블클릭 상세 팝업, 식별자 배치 상태, 메모 저장 |
| `schedule-features.js` | 주말 토글, 일정 이동, 단순 블록용 큐 task 생성, 큐 검색/그룹, hover 강조, 월간 더보기 |
| `schedule-app.js` | 페이지별 초기화 진입점 |

## 5. 드래그앤드롭 흐름

### 5.1 큐에서 시간표로 배치

1. 사용자가 `.queue-task-item`을 누른다.
2. `queue-drag.js`가 task의 식별자 목록과 기존 배치 상태를 확인한다.
3. 식별자가 여러 개이면 선택 피커를 연다.
4. 드래그 고스트는 `drag-core.js`가 만든다.
5. 드롭 위치는 날짜, 장소, 시작 시각으로 변환된다.
6. `POST /schedule/api/blocks` 요청을 보낸다.
7. 백엔드는 이미 다른 블록에 있던 식별자를 필요하면 제거한다.
8. 성공하면 화면을 다시 로드해 큐와 블록을 최신 상태로 맞춘다.

### 5.2 기존 블록 이동

1. 사용자가 `.schedule-block`을 드래그한다.
2. 잠긴 블록이면 이동하지 않는다.
3. 드롭 대상이 큐이면 `DELETE /schedule/api/blocks/<id>?restore=1`을 호출한다.
4. 드롭 대상이 시간표이면 `PUT /schedule/api/blocks/<id>`로 날짜/시간/장소를 갱신한다.
5. 월간 뷰에서는 날짜 변경 중심으로 동작한다.

### 5.3 블록 리사이즈

1. 사용자가 리사이즈 핸들을 드래그한다.
2. 높이는 슬롯 단위로 스냅된다.
3. 축소 시 확인 모달을 띄운다.
4. `PUT /schedule/api/blocks/<id>`에 `resize: true`를 포함해 보낸다.
5. 리사이즈는 실제 투입 시간 조정이므로 큐 잔여 시간 복원으로 처리하지 않는다.

## 6. 큐 표시 규칙

큐는 `views/_task_queue.html`에서 렌더링된다.

| 상황 | 큐 표시 |
| --- | --- |
| 블록이 하나도 없는 task | 전체 task 표시 |
| `identifier_ids=null`인 전체 블록이 있는 task | 큐에서 숨김 |
| 일부 식별자만 배치된 task | 미배치 식별자 시간만 표시 |
| 단순 블록 | 제목과 시간 중심으로 표시 |

큐 그룹화 상태와 장소 필터 상태는 `localStorage`에 저장해 새로고침 후에도 유지한다.

## 7. 장소 필터

`views/_location_filter.html`이 일간/주간 화면에서 사용된다.

1. 전체 모드에서는 모든 장소 컬럼을 표시한다.
2. 개별 장소를 누르면 전체 모드를 해제하고 해당 장소만 토글한다.
3. 모든 개별 장소가 꺼지면 자동으로 전체 모드가 된다.
4. 필터된 장소는 드롭 가이드에서도 제외된다.
5. 선택 상태는 `localStorage`에 저장된다.

## 8. 블록 상세/상태 표시

더블클릭 상세 팝업은 task의 전체 식별자를 보여준다.

| 표시 | 의미 |
| --- | --- |
| 굵은 식별자 | 현재 블록에 포함됨 |
| 흐린 식별자 + 타 블록 라벨 | 다른 블록에 포함됨 |
| `N/M` 뱃지 | 전체 식별자 중 이 블록이 포함한 수 |
| 빨간 분할 뱃지 | 일부 식별자가 아직 큐에 남아 있음 |
| 진행/완료/불가 색상 | execution 상태 기반 표시. 저장된 `cancelled` 블록은 수동 상태로 유지 |

## 9. Execution 화면

실행 화면은 `app/static/execution/js/`와 `app/static/execution/css/style.css`를 사용한다.

| 파일 | 역할 |
| --- | --- |
| `execution-app.js` | 실행 목록 화면, 날짜/장소/검색 필터, 열 표시 설정, 정렬, 바코드 상세 이동 |
| `execution-detail.js` | 식별자 상세 실행 화면 |

실행 화면은 `/execution/api/list`로 task 식별자 전체를 읽고, 날짜/장소 필터를 선택하면 배치된 block 기준으로 좁힌다. 목록 API는 화면용 view model 필드인 `execution_status`, `execution_comment`, `performer_name`, `result_counts`, `status_order`를 함께 내려준다. 프론트엔드는 이 값을 렌더링하고, nested `execution` 객체는 상세 이동 호환 데이터로만 취급한다. 동일 식별자가 여러 task에 있을 수 있으므로 상세 이동과 API 호출에는 `task_id`를 함께 사용한다. 타이머 버튼은 `/execution/api/start`, `/pause`, `/resume`, `/complete`를 호출한다.

목록 테이블의 열 표시 설정은 `localStorage.execColVis`에 저장된다. 스케줄 편집/읽기 모드는 `localStorage.scheduleMode`, 큐 그룹/장소 필터 상태도 `localStorage`를 사용한다.

## 10. CSS 구조

| 경로 | 설명 |
| --- | --- |
| `app/static/schedule/css/style.css` | 스케줄 화면, 큐, 캘린더, 모달, 필터 스타일 |
| `app/static/execution/css/style.css` | 실행 화면 스타일 |
| `app/static/schedule/vendor/bootstrap.min.css` | 로컬 Bootstrap |
| `app/static/schedule/vendor/bootstrap-icons.css` | 로컬 Bootstrap Icons |

디자인 토큰은 CSS 변수로 관리한다. 새 색상/간격이 필요하면 먼저 기존 변수를 재사용하고, 반복되는 값만 새 변수로 추가한다.

## 11. UI 책임 원칙

프론트엔드는 preview와 render를 담당한다. 업무 규칙과 최종 저장 결과는 백엔드 service/API가 담당한다.

프론트엔드가 가져도 되는 책임:

1. 드래그 중 좌표, 고스트, hover, drop target preview
2. 모달, 선택 피커, 토스트, 필터, 정렬, 열 표시 설정
3. localStorage 기반 개인 화면 상태
4. 서버가 준 view model 렌더링
5. 입력값 수집과 API command 전송

프론트엔드에서 줄여야 하는 책임:

1. 큐에 남은 식별자/수행 대상 계산
2. `identifier_ids=null` 같은 데이터 특수 규칙 해석
3. block 분할/복귀 규칙
4. 휴식 시간 제외 작업 시간 계산
5. 업무 종료 초과와 다음 근무일 자동 배치
6. block 충돌 검사
7. execution 상태와 결과 카운트 계산
8. 재시험 차수 구분과 외부 동기화 병합 규칙

프론트엔드가 preview 계산을 하더라도 저장 후에는 항상 백엔드 응답을 다시 렌더링한다.

## 12. 프론트엔드 변경 절차

1. 수정하려는 화면의 템플릿을 먼저 확인한다.
2. 해당 화면에서 로드되는 JS 모듈과 초기화 함수를 찾는다.
3. 서버에서 내려오는 데이터 속성(`data-*`)과 API 응답 구조를 확인한다.
4. UI 조작은 가능하면 기존 공통 모달, 토스트, API 래퍼를 사용한다.
5. 일간/주간/월간 중 같은 기능이 모두 필요한지 확인한다.
6. 업무 규칙이 필요하면 프론트에 새로 구현하지 말고 백엔드 service/API로 옮길 수 있는지 먼저 확인한다.
7. 드래그/리사이즈 변경은 잠금, 장소 필터, 휴식 시간, 업무 종료 초과 규칙을 함께 검증한다.
