# 데이터 파일 기술 문서

이 프로젝트는 DB 없이 JSON 파일을 영속 저장소로 사용한다. 스케줄 데이터와 실행 데이터는 서로 다른 디렉터리에 저장된다.

## 1. 읽는 순서

1. `app/__init__.py`가 데이터 디렉터리를 Flask config에 저장한다.
2. 스케줄 모델은 `current_app.config['DATA_DIR']` 아래 파일을 사용한다.
3. 실행 모델은 `current_app.config['EXECUTION_DATA_DIR']` 아래 파일을 사용한다.
4. `read_json()`은 파일이 없거나 비어 있으면 기본값을 반환한다.
5. `write_json()`은 기존 파일을 `.bak`으로 백업한 뒤 저장한다.

## 2. 디렉터리

| 경로 | 설명 |
| --- | --- |
| `app/features/schedule/data/` | task, block, 기준정보, 설정, provider 입력/캐시 |
| `app/features/execution/data/` | 실행 상태, 타이머 구간, 결과 카운트 |

## 3. 파일 목록

| 파일 | 형태 | 설명 |
| --- | --- | --- |
| `schedule/data/tasks.json` | array | 시험 문서/절차 단위 task |
| `schedule/data/schedule_blocks.json` | array | 캘린더에 배치된 일정 블록 |
| `schedule/data/users.json` | array | 시험 담당자 기준 정보 |
| `schedule/data/locations.json` | array | 시험 장소 기준 정보 |
| `schedule/data/versions.json` | array | OFP/스케줄 버전 기준 정보 |
| `schedule/data/settings.json` | object | 근무 시간, 휴식, 그리드, 표시 설정 |
| `schedule/data/procedures.json` | array | `json_file` provider의 시험 절차 입력 |
| `schedule/data/std_list_cache.json` | array | MySQL `std_list`에서 가져온 `test_info`/`exam_no` 캐시 |
| `schedule/data/dyn_ready_meta.json` | object | `dyn_ready` provider의 변경 감지 메타 캐시. 런타임에 생성될 수 있음 |
| `execution/data/executions.json` | array | 식별자별 실행 레코드 |
| `*.json.bak` | 원본과 동일 | 쓰기 전 자동 백업. 로컬 운영 중 생성될 수 있음 |

## 4. 공통 규칙

| 항목 | 규칙 |
| --- | --- |
| 문자 인코딩 | UTF-8 |
| JSON 저장 | `ensure_ascii=False`, `indent=2` |
| 날짜 | `YYYY-MM-DD` |
| 시각 | `HH:MM` |
| 일시 | ISO 문자열. 예: `2026-05-13T09:00:00` |
| ID 접두사 | task `t_`, block `sb_`, user `u_`, location `loc_`, version `v_`, execution `ex_` |
| 담당자 참조 | user id가 아니라 `users.json[].name` 문자열을 저장 |
| 장소 참조 | `locations.json[].id`를 저장 |
| 일반 진행 상태 | task가 아니라 execution 레코드에서 계산 |

## 5. `tasks.json`

시험 문서 또는 절차 단위 데이터다. 하나의 task는 여러 시험 식별자(`identifiers`)를 가진다.

```json
{
  "id": "t_a1b2c3d4",
  "doc_id": 1001,
  "version_id": "v_001",
  "exam_no": 2,
  "assignee_names": ["홍길동"],
  "location_id": "loc_001",
  "doc_name": "SW 시험 절차서",
  "identifiers": [
    {
      "id": "TC-001",
      "name": "기능 시험",
      "owners": ["김작성"],
      "estimated_minutes": 60,
      "total_count": 12
    }
  ],
  "estimated_minutes": 60,
  "remaining_minutes": 60,
  "memo": "",
  "created_at": "2026-05-13T09:00:00"
}
```

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | task 고유 ID |
| `doc_id` | number/string | 외부 문서 ID. 동기화 매칭 키 |
| `version_id` | string | `versions.json.id` 또는 외부 OFP ID |
| `exam_no` | number/null | 시험 차수. 같은 식별자라도 차수가 다르면 별도 task로 허용 |
| `assignee_names` | string[] | 시험 수행 담당자 이름 |
| `location_id` | string | 기본 시험 장소 ID |
| `doc_name` | string | 문서/절차 표시명 |
| `identifiers` | object[] | 시험 식별자 목록 |
| `estimated_minutes` | number | 식별자 예상 시간 합 |
| `remaining_minutes` | number | 아직 큐에 남아 있는 예상 시간 |
| `memo` | string | 메모 |
| `created_at` | string | 생성 시각 |
| `status` | string | 예외 필드. 외부 삭제/취소 시 `cancelled`로만 사용 |

### `identifiers[]`

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 시험 식별자 ID |
| `name` | string | 시험 항목명 |
| `owners` | string[] | 작성자/개발자 이름 |
| `estimated_minutes` | number | 식별자 예상 소요 시간 |
| `total_count` | number | 전체 시험 케이스 수 후보 |
| `test_count` | number | 전체 건수 후보 |
| `case_count` | number | 전체 건수 후보 |
| `count` | number | 전체 건수 후보 |

Execution API는 전체 건수를 `total_count -> test_count -> case_count -> count` 순서로 읽고, 없으면 0으로 둔다.

## 6. `schedule_blocks.json`

캘린더에 실제 배치된 일정 블록이다.

```json
{
  "id": "sb_a1b2c3d4",
  "task_id": "t_a1b2c3d4",
  "assignee_names": ["홍길동"],
  "location_id": "loc_001",
  "date": "2026-05-13",
  "start_time": "09:00",
  "end_time": "10:00",
  "is_locked": false,
  "block_status": "pending",
  "memo": "",
  "identifier_ids": ["TC-001"],
  "title": "",
  "is_simple": false,
  "overflow_minutes": 0
}
```

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 블록 고유 ID |
| `task_id` | string/null | 연결 task. 단순 블록이면 없을 수 있음 |
| `assignee_names` | string[] | 블록 담당자 이름 |
| `location_id` | string | 배치 장소 ID |
| `date` | string | 배치 날짜 |
| `start_time` | string | 시작 시각 |
| `end_time` | string | 종료 시각 |
| `is_locked` | boolean | 이동/리사이즈 제한 여부 |
| `block_status` | string | `pending`, `in_progress`, `completed`, `cancelled` |
| `memo` | string | 블록 메모 |
| `identifier_ids` | string[]/null | 포함 식별자. `null`이면 task 전체 식별자 포함 |
| `title` | string | 단순 블록 제목 |
| `is_simple` | boolean | 시험 외 단순 일정 여부 |
| `overflow_minutes` | number | 업무 시간 초과로 다음 근무일에 이어지는 분량 |

## 7. 기준 정보 파일

### `users.json`

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 사용자 ID |
| `name` | string | 담당자 이름. task/block이 이 값을 참조 |
| `role` | string | 역할 |
| `color` | string | UI 표시 색상 |

### `locations.json`

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 장소 ID |
| `name` | string | 장소명 |
| `color` | string | UI 표시 색상 |
| `description` | string | 설명 |

### `versions.json`

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 버전/OFP ID |
| `name` | string | 버전명 |
| `description` | string | 설명 |
| `is_active` | boolean | 활성 여부 |
| `created_at` | string | 생성 시각 |

활성 버전은 `OfpidSettings.get_current_ofp_id()`에서 조회한다.

## 8. `settings.json`

전역 설정 단일 객체다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `work_start` | string | 시간표 표시 시작 |
| `work_end` | string | 시간표 표시 종료 |
| `actual_work_start` | string | 실제 업무 시작. 자동 배치 기준 |
| `actual_work_end` | string | 실제 업무 종료. 초과 판단 기준 |
| `lunch_start` | string | 점심 시작 |
| `lunch_end` | string | 점심 종료 |
| `breaks` | object[] | 추가 휴식 시간 목록 |
| `grid_interval_minutes` | number | 시간표 격자 간격 |
| `max_schedule_days` | number | 자동 배치에서 고려할 최대 일수 |
| `block_color_by` | string | 블록 색상 기준 |

`breaks[]` 항목은 `{ "start": "10:00", "end": "10:15" }` 형식이다.

## 9. Provider 입력/캐시

### `procedures.json`

`PROVIDER_TYPE=json_file`일 때 동기화 입력으로 사용한다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `version_id` | string | 연결할 버전/OFP ID |
| `doc_id` | number/string | 문서 ID |
| `doc_name` | string | 문서명 |
| `section_name` | string | 하위 호환용 절차명 |
| `exam_no` | number/null | 선택. 있으면 차수별 task 생성에 직접 사용 |
| `identifiers` | object[] | 시험 식별자 목록 |
| `test_list` | object[] | 하위 호환 키. `identifiers`가 없을 때 사용 |

### `std_list_cache.json`

`POST /api/sync/std-list`가 MySQL `std_list`에서 읽어 저장한다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `test_info` | string | 시험 식별자 ID |
| `exam_no` | number | 시험 차수 |

동기화 시 provider 데이터에 `exam_no`가 직접 없으면 이 파일로 식별자를 차수별로 나눈다.

### `dyn_ready_meta.json`

`PROVIDER_TYPE=dyn_ready` 사용 시 생성될 수 있다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `updated_at` | string | 외부 응답 최종 갱신 시각 |
| `data_hash` | string | 응답 `data`의 SHA-256 해시 |

`updated_at`이 바뀌지 않아도 데이터가 삭제/수정된 경우를 감지하기 위해 해시를 함께 저장한다.

## 10. `executions.json`

식별자별 실행 상태와 결과를 저장한다.

```json
{
  "id": "ex_a1b2c3d4",
  "identifier_id": "TC-001",
  "task_id": "t_a1b2c3d4",
  "exam_no": 2,
  "status": "in_progress",
  "segments": [
    {"start": "2026-05-13T09:00:00", "end": null}
  ],
  "total_count": 12,
  "fail_count": 0,
  "block_count": 0,
  "pass_count": 0,
  "comment": "",
  "performer": "홍길동",
  "created_at": "2026-05-13T09:00:00",
  "completed_at": null,
  "elapsed_seconds": 0,
  "elapsed_mins": 0
}
```

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 실행 레코드 ID |
| `identifier_id` | string | 시험 식별자 ID |
| `task_id` | string | 상위 task ID |
| `exam_no` | number/null | task의 시험 차수 |
| `status` | string | `in_progress`, `paused`, `completed`. 레코드가 없으면 UI에서 pending |
| `segments` | object[] | 타이머가 실제로 동작한 구간 |
| `total_count` | number | 전체 시험 건수 |
| `fail_count` | number | 실패 건수 |
| `block_count` | number | 블록/보류 건수 |
| `pass_count` | number | 통과 건수 |
| `comment` | string | 코멘트 |
| `performer` | string | 실제 수행자 |
| `created_at` | string | 생성 시각 |
| `completed_at` | string/null | 완료 시각 |
| `elapsed_seconds` | number | 저장된 경과 시간 스냅샷 |
| `elapsed_mins` | number | 저장된 경과 분 스냅샷 |
| `action_status` | string | 선택 필드 |
| `action_input` | string/object | 선택 필드 |

### `segments[]`

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `start` | string | 구간 시작 시각 |
| `end` | string/null | 구간 종료 시각. 진행 중이면 `null` |

응답 시 경과 시간은 저장된 `elapsed_seconds`보다 `segments` 기반 재계산 값을 우선 사용한다.

## 11. 데이터 수정 시 확인할 것

1. task의 `identifiers[].id` 중복 검사는 같은 `exam_no` 안에서만 한다.
2. block의 `identifier_ids=null`은 전체 식별자 포함이라는 뜻이다.
3. task 상태를 직접 저장하지 말고 execution 상태로 계산한다.
4. 담당자는 ID가 아니라 이름 문자열로 연결된다.
5. 저장소 쓰기는 `.bak` 파일을 만들 수 있으므로 운영/배포 스크립트에서 백업 파일 추적 여부를 분리한다.
