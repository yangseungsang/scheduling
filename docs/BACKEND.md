# Backend 아키텍처 문서

## 1. 개요

Flask + Jinja2 기반 SSR 애플리케이션. JSON 파일 저장, portalocker 파일 잠금. Blueprint 4개.

---

## 2. 모델 (schedule/models/)

### BaseRepository (base.py)
모든 모델의 공통 CRUD 패턴:
- `get_all()`, `get_by_id()`, `create(data)`, `patch(item_id, **kwargs)`, `delete()`, `filter_by(**kwargs)`
- `FILENAME`, `ID_PREFIX`, `ALLOWED_FIELDS` 클래스 변수로 설정

### Task (task.py)
```
파일: tasks.json, 접두사: t_
필드: id, doc_id(int), version_id, assignee_names(이름 배열), location_id,
      doc_name, identifiers, estimated_minutes, remaining_minutes,
      status, memo, created_at, is_simple
identifiers 항목: {id, name, estimated_minutes, owners: []}
고유 메서드: get_by_doc_id, validate_unique_identifiers, compute_estimated_minutes
```

### ScheduleBlock (schedule_block.py)
```
파일: schedule_blocks.json, 접두사: sb_
필드: id, task_id, assignee_names(이름 배열), location_id,
      date, start_time, end_time, is_locked, block_status,
      memo, identifier_ids, title, is_simple, overflow_minutes
고유 메서드: get_by_date, get_by_date_range,
            get_by_assignee, get_by_location_and_date
```

### 기타
- **User** (users.json, `u_`): name, role, color
- **Location** (locations.json, `loc_`): name, color, description
- **Version** (versions.json, `v_`): name, description, is_active, `get_active()`
- **Settings** (settings.json): `get()`, `update(data)`

---

## 3. 라우트 (schedule/routes/)

### calendar_views.py — 뷰 렌더링
| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/schedule/` | 일간 뷰 (5분 그리드) |
| GET | `/schedule/week` | 주간 뷰 (장소별 서브컬럼, 초기 진입) |
| GET | `/schedule/month` | 월간 뷰 (평일만) |
| GET | `/schedule/api/day\|week\|month` | JSON 데이터 |

### calendar_api.py — 블록 API
| 메서드 | URL | 설명 |
|--------|-----|------|
| POST | `/schedule/api/blocks` | 블록 생성 (종료시간 초과 시 다음 근무일 자동 넘김) |
| PUT | `/schedule/api/blocks/<id>` | 이동/리사이즈 (`resize:true` 시 사용자 입력 그대로 적용) |
| DELETE | `/schedule/api/blocks/<id>` | 삭제 (`?restore=1` → 잔여시간 복원) |
| PUT | `/schedule/api/blocks/<id>/lock` | 잠금 토글 |
| PUT | `/schedule/api/blocks/<id>/status` | 상태 변경 |
| PUT | `/schedule/api/blocks/<id>/memo` | 메모 수정 |
| POST | `/schedule/api/simple-blocks` | 간단 블록 생성 (task 자동 생성) |
| GET | `/schedule/api/blocks/by-task/<tid>` | 태스크별 블록 조회 |
| POST | `/schedule/api/blocks/shift` | 일정 이동 (주말 건너뛰기) |
| POST | `/schedule/api/blocks/<id>/split` | 블록 분리 |
| POST | `/schedule/api/blocks/<id>/return-identifiers` | 일부 식별자 큐 복귀 |
| GET | `/schedule/api/export` | CSV/Excel 내보내기 (버전 정보 포함) |

### calendar_helpers.py — 공통 함수
- `sync_task_remaining_minutes(task_id)` — est=identifiers 합, remaining=est-scheduled
- `remove_identifiers_from_other_blocks()` — 식별자 이동 시 기존 블록에서 제거/삭제
- `sync_task_status(task_id)` — 블록 상태 → 태스크 상태 연동
- `DAY_NAMES` — ['월', '화', '수', '목', '금'] (평일만)

### tasks.py
| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/tasks/` | 목록 (상태/담당자/장소/문서명 필터) |
| GET/POST | `/tasks/new` | 생성 |
| GET | `/tasks/<id>` | 상세 |
| GET/POST | `/tasks/<id>/edit` | 수정 |
| POST | `/tasks/<id>/delete` | 삭제 |
| GET | `/tasks/api/list\|<id>` | API 조회 |
| POST | `/tasks/api/create` | API 생성 |
| PUT | `/tasks/api/<id>/update` | API 수정 |
| DELETE | `/tasks/api/<id>/delete` | API 삭제 |
| GET | `/tasks/api/check-identifier` | 식별자 중복 검사 |
| GET | `/tasks/api/procedure/<int:doc_id>` | 문서 조회 |

### admin.py
- 팀원/장소/설정 CRUD (폼 + REST API)
- 버전 관리 (API만: POST/PUT/DELETE `/admin/api/versions`)

### sync.py
- 외부 프로바이더 동기화 (doc_id 기반 매칭)
- 리셋+재동기화

---

## 4. 헬퍼 (schedule/helpers/)

### enrichment.py
- `build_maps()` — users_map(이름 키), tasks_map, locations_map
- `enrich_blocks()` — 블록에 task/user/location 정보 결합
  - 분할 블록: 해당 식별자 시간만 estimated_minutes로
  - `is_split`, `block_identifier_count`, `total_identifier_count` 계산
  - `split_status`: `'partial'`(나머지 큐에 있음) / `'split'`(전체 배치됨)
- `get_queue_tasks()` — 큐 항목 (담당자→제목 순 정렬)
  - 분할 안 된 블록 있으면 → 큐 미표시 (리사이즈 = 실제 시간 변경)
  - 분할 블록만 있으면 → 미배치 식별자 시간을 remaining으로
- `build_month_weeks()` — 월간 달력 (평일 5일만)

### time_utils.py
- `work_minutes_in_range()` — 휴식 제외 실 작업 시간
- `adjust_end_for_breaks()` — 휴식 건너뛰기 종료 시간 계산
- `generate_time_slots()` — actual_work_start~actual_work_end 슬롯 생성
- `is_break_slot()` — 점심/휴식 판별

### overlap.py
- `check_overlap()` — 장소+시간 충돌 감지
- `compute_overlap_layout()` — 겹치는 블록의 열 배치 계산

---

## 5. 시간 관리 규칙

| 동작 | estimated_minutes | remaining_minutes | 큐 |
|------|------------------|-------------------|-----|
| 리사이즈 | 불변 | 불변 | 블록 있으면 미표시 |
| 이동 | 불변 | 재계산 | 재계산 |
| 큐 복귀 | 불변 | 재계산 | 표시 |
| 분할 배치 | 불변 | - | 미배치 식별자만 |
| 종료시간 초과 | 불변 | 재계산 | 다음 근무일 자동 넘김 |

### 다음 근무일 자동 넘김
- 블록 생성/이동/리사이즈 시 actual_work_end 초과 감지
- 초과분(순수 작업 시간)을 다음 근무일(주말 건너뜀) work_start부터 자동 배치
- 겹침으로 배치 실패 시 초과분은 줄어듦 (overflow_minutes=0 리셋)

---

## 6. 서비스 (schedule/services/)

- **export.py**: CSV/Excel 내보내기 (버전 정보, 분리 블록 N/M 표시)
- **procedure.py**: 문서 조회 (doc_id 기반, procedures.json)
- **sync.py**: 외부 프로바이더 동기화 (doc_id 기반 매칭)

## 7. 데이터 저장 (store.py)

- `read_json()` / `write_json()` — portalocker 파일 잠금, .bak 백업
- `generate_id(prefix)` — UUID 기반

## 8. 프론트엔드 주요 기능

- **드래그 고스트 그리드 스냅**: 슬롯 경계 맞춤 + 휴식 시간 포함 높이 자동 확장
- **다중 선택**: Ctrl+클릭 토글, Shift+클릭 범위 선택, Esc 해제
- **큐 다중 드래그**: 선택 후 드래그 → 순차 배치
- **블록 다중 이동**: 선택 후 드래그 → 종료시간 초과 시 다음날 자동 전환
- **식별자 체크박스**: 상세 팝업에서 전체 선택/해제 + 분리/큐 복귀 버튼
- **큐 그룹화**: 담당자별 그룹 토글 (localStorage 유지)
- **장소 필터**: 일간/주간 뷰에서 컬럼 자체 숨김
