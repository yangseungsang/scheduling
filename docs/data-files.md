# Data Files

이 문서는 `app/features/**/data` 아래 JSON 데이터 파일의 역할과 주요 키를 정리한다. 파일은 UTF-8 JSON으로 저장되며, `settings.json`을 제외한 현재 영속 데이터는 대부분 배열 형태다.

## 디렉터리 개요

| 경로 | 용도 |
| --- | --- |
| `app/features/schedule/data/` | 스케줄링 화면과 관리자 기능에서 사용하는 기준 데이터, 시험 태스크, 배치 블록, 동기화 캐시를 저장한다. |
| `app/features/execution/data/` | 시험 실행 화면의 실행 상태, 타이머 구간, 결과 카운트, 코멘트를 저장한다. |

## 파일별 요약

| 파일 | 형태 | 설명 |
| --- | --- | --- |
| `schedule/data/tasks.json` | 배열 | 스케줄링 대상이 되는 시험 문서/절차 단위 데이터다. 각 항목은 문서, 시험 식별자 목록, 담당자, 장소, 예상 시간을 가진다. |
| `schedule/data/schedule_blocks.json` | 배열 | 캘린더에 실제 배치된 블록 데이터다. 날짜, 시간, 장소, 담당자, 포함 식별자를 저장한다. |
| `schedule/data/users.json` | 배열 | 시험 담당자 또는 사용자 기준 정보다. 이름, 역할, 표시 색상을 저장한다. |
| `schedule/data/locations.json` | 배열 | 시험 장소 기준 정보다. 장소명, 색상, 설명을 저장한다. |
| `schedule/data/versions.json` | 배열 | 외부 OFP 또는 스케줄 버전 기준 정보다. 동기화 대상 버전과 활성 여부를 저장한다. |
| `schedule/data/settings.json` | 객체 | 근무 시간, 점심 시간, 그리드 간격, 표시 옵션 같은 전역 설정이다. |
| `schedule/data/procedures.json` | 배열 | 외부 시험 절차 원본 또는 `json_file` provider의 입력 데이터다. 동기화 시 `tasks.json`의 소스가 된다. |
| `schedule/data/std_list_cache.json` | 배열 | MySQL `std_list`에서 가져온 `test_info`와 `exam_no` 매핑 캐시다. 재시험 차수별 task 분리에 사용된다. |
| `execution/data/executions.json` | 배열 | 시험 실행 레코드다. 식별자별 실행 상태, 타이머 segments, 수행자, 결과 카운트, 완료 시각을 저장한다. |
| `execution/data/executions.json.bak` | 배열 | `executions.json` 쓰기 전에 생성되는 백업 파일이다. 현재 git 추적 대상은 아니지만 로컬 data 폴더에 생길 수 있다. |
| `schedule/data/dyn_ready_meta.json` | 객체 | `dyn_ready` provider 사용 시 생성되는 메타 캐시다. 현재 기본 파일 목록에는 없을 수 있다. |

## 공통 규칙

| 항목 | 설명 |
| --- | --- |
| `id` 접두사 | `tasks`: `t_`, `schedule_blocks`: `sb_`, `users`: `u_`, `locations`: `loc_`, `versions`: `v_`, `executions`: `ex_`를 사용한다. 일부 외부 동기화 데이터는 외부 ID를 그대로 쓸 수 있다. |
| 시간 형식 | 날짜는 `YYYY-MM-DD`, 시각은 `HH:MM`, datetime은 ISO 문자열(`YYYY-MM-DDTHH:MM:SS`)을 사용한다. |
| 담당자 참조 | 스케줄 데이터는 user id가 아니라 `users.json`의 `name` 값을 `assignee_names`나 `owners`에 저장한다. |
| 장소 참조 | `location_id`는 `locations.json`의 `id`를 참조한다. |
| 실행 상태 | 일반적인 시험 진행 상태는 `tasks.json`에 저장하지 않고 `executions.json`을 기준으로 동적으로 계산한다. |

## `tasks.json`

스케줄링 대상 시험 문서 또는 절차다. 하나의 task 안에 여러 시험 식별자(`identifiers`)가 들어간다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | task 고유 ID. 보통 `t_` 접두사를 가진다. |
| `doc_id` | number/string | 외부 문서 또는 절차 ID. 동기화 시 문서 매칭에 사용된다. |
| `version_id` | string | `versions.json`의 `id` 또는 외부 OFP ID. 없으면 빈 문자열일 수 있다. |
| `exam_no` | number/null | 재시험 또는 시험 차수. 없으면 `null` 또는 필드 없음으로 취급한다. |
| `assignee_names` | string[] | 시험 담당자 이름 목록. `users.json.name`과 매칭된다. |
| `location_id` | string | 기본 시험 장소 ID. `locations.json.id`를 참조한다. |
| `doc_name` | string | 문서 또는 시험 절차 이름. |
| `identifiers` | object[] | task에 포함된 시험 식별자 목록. 세부 키는 아래 표를 참고한다. |
| `estimated_minutes` | number | task 전체 예상 소요 시간. 보통 `identifiers[].estimated_minutes` 합계다. |
| `remaining_minutes` | number | 아직 캘린더에 배치되지 않은 잔여 예상 시간. |
| `memo` | string | task 메모. |
| `created_at` | string | task 생성 시각 ISO 문자열. |
| `status` | string | 예외적으로 외부에서 삭제된 task를 `cancelled`로 표시할 때만 의미가 있다. 일반 진행 상태에는 사용하지 않는다. |

### `tasks.json`의 `identifiers[]`

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 시험 식별자 ID. 예: `TC-001`. |
| `name` | string | 시험 항목명. |
| `owners` | string[] | 식별자 작성자 또는 담당자 이름 목록. |
| `estimated_minutes` | number | 해당 식별자 단위 예상 소요 시간. |
| `total_count` | number | 선택 필드. execution 결과의 전체 시험 케이스 수로 사용할 수 있다. |
| `test_count` | number | 선택 필드. `total_count`가 없을 때 전체 건수 후보로 사용될 수 있다. |
| `case_count` | number | 선택 필드. `total_count`, `test_count`가 없을 때 전체 건수 후보로 사용될 수 있다. |
| `count` | number | 선택 필드. 다른 카운트 필드가 없을 때 전체 건수 후보로 사용될 수 있다. |

## `schedule_blocks.json`

캘린더에 배치된 일정 블록이다. task 전체 또는 task 안의 일부 식별자만 포함할 수 있다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 블록 고유 ID. `sb_` 접두사를 가진다. |
| `task_id` | string/null | 연결된 task ID. 단순 블록이면 `null`일 수 있다. |
| `assignee_names` | string[] | 이 블록에 배정된 담당자 이름 목록. |
| `location_id` | string | 블록이 배치된 장소 ID. `locations.json.id`를 참조한다. |
| `date` | string | 배치 날짜. `YYYY-MM-DD`. |
| `start_time` | string | 시작 시각. `HH:MM`. |
| `end_time` | string | 종료 시각. `HH:MM`. |
| `is_locked` | boolean | 잠금 여부. 잠긴 블록은 UI에서 이동/리사이즈를 제한한다. |
| `block_status` | string | 블록 상태. 일반적으로 `pending`, `in_progress`, `completed`, `cancelled` 중 하나다. |
| `memo` | string | 블록 메모. |
| `identifier_ids` | string[]/null | 이 블록에 포함된 식별자 ID 목록. `null`이면 task의 전체 식별자를 포함하는 블록으로 본다. |
| `title` | string | 단순 블록 제목. `is_simple=true`일 때 사용한다. |
| `is_simple` | boolean | task 없이 제목만 가지는 단순 일정 여부. |
| `overflow_minutes` | number | 업무 시간 초과 등으로 다음 날에 이어진 시간(분). |

## `users.json`

사용자 또는 시험 담당자 기준 정보다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 사용자 고유 ID. `u_` 접두사를 가진다. |
| `name` | string | 사용자 이름. `tasks.assignee_names`, `schedule_blocks.assignee_names`, `identifiers.owners`가 이 값을 참조한다. |
| `role` | string | 역할 또는 직무명. |
| `color` | string | UI 표시 색상. HEX 색상 문자열을 사용한다. |

## `locations.json`

시험 장소 기준 정보다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 장소 고유 ID. `loc_` 접두사를 가진다. |
| `name` | string | 장소 이름. 예: `STE1`. |
| `color` | string | UI 표시 색상. HEX 색상 문자열을 사용한다. |
| `description` | string | 장소 설명. |

## `versions.json`

스케줄 버전 또는 외부 OFP 버전 기준 정보다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 버전 ID. 내부 생성 시 `v_` 접두사를 사용하고, 외부 동기화 시 외부 ID를 그대로 저장할 수 있다. |
| `name` | string | 버전 이름. |
| `description` | string | 버전 설명. |
| `is_active` | boolean | 활성 여부. 필드가 없으면 활성으로 간주한다. |
| `created_at` | string | 생성 시각 ISO 문자열. |

## `settings.json`

전역 스케줄 표시 및 근무 시간 설정이다. 배열이 아니라 단일 객체다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `work_start` | string | 시간표 표시 시작 시각. |
| `work_end` | string | 시간표 표시 종료 시각. |
| `actual_work_start` | string | 실제 업무 시작 시각. 자동 배치나 근무 시간 계산에 사용한다. |
| `actual_work_end` | string | 실제 업무 종료 시각. |
| `lunch_start` | string | 점심 시작 시각. |
| `lunch_end` | string | 점심 종료 시각. |
| `breaks` | object[] | 정규 휴식 시간 목록. 각 항목은 `start`, `end`를 가진다. |
| `grid_interval_minutes` | number | 캘린더 격자 간격(분). |
| `max_schedule_days` | number | 자동 배치 또는 스케줄 표시에서 고려할 최대 일수. |
| `block_color_by` | string | 블록 색상 기준. 현재 `assignee`, `location`, `status` 계열 값이 사용된다. |

### `settings.json`의 `breaks[]`

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `start` | string | 휴식 시작 시각. |
| `end` | string | 휴식 종료 시각. |

## `procedures.json`

외부 시험 절차 원본 데이터다. `PROVIDER_TYPE=json_file`일 때 동기화 provider가 이 파일을 읽어 `tasks.json`으로 반영한다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `version_id` | string | 연결할 버전 또는 OFP ID. |
| `doc_id` | number/string | 문서 ID. |
| `doc_name` | string | 문서 또는 절차 이름. |
| `exam_no` | number/null | 선택 필드. 절차 자체가 특정 차수에 속할 때 사용된다. |
| `identifiers` | object[] | 절차에 포함된 시험 식별자 목록. 구조는 `tasks.json`의 `identifiers[]`와 유사하다. |

## `std_list_cache.json`

MySQL `std_list` 테이블에서 읽은 시험 식별자와 차수 매핑 캐시다. 비어 있으면 기존 방식대로 `exam_no=null` task 1개로 동기화한다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `test_info` | string | 시험 식별자 ID. 예: `TC-001`. |
| `exam_no` | number | 해당 식별자가 속한 시험 차수. |

## `executions.json`

시험 실행 상태와 결과를 저장한다. 스케줄 데이터에는 실행 결과를 다시 쓰지 않고, 실행 화면과 상태 계산에서 이 파일을 참조한다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | 실행 레코드 ID. `ex_` 접두사를 가진다. |
| `identifier_id` | string | 실행 대상 시험 식별자 ID. |
| `task_id` | string | 실행 대상 식별자가 속한 task ID. 같은 식별자가 여러 차수나 문서에 있어도 task 기준으로 분리한다. |
| `exam_no` | number/null | 실행 대상 task의 시험 차수. |
| `status` | string | 실행 상태. `pending`, `in_progress`, `paused`, `completed` 중 하나다. |
| `segments` | object[] | 실제 타이머가 동작한 시간 구간 목록. 자세한 구조는 아래 표를 참고한다. |
| `total_count` | number | 전체 시험 케이스 수. |
| `fail_count` | number | 실패 건수. |
| `block_count` | number | 블록 또는 보류 건수. |
| `pass_count` | number | 통과 건수. 완료 시 `max(0, total_count - fail_count - block_count)`로 계산된다. |
| `comment` | string | 실행 코멘트. 시작 전 pending 코멘트도 이 필드에 저장될 수 있다. |
| `performer` | string | 실제 시험 수행자 이름. |
| `created_at` | string | 실행 레코드 생성 시각 ISO 문자열. |
| `completed_at` | string/null | 완료 시각 ISO 문자열. 완료 전이면 `null`. |
| `elapsed_seconds` | number | 저장된 경과 시간 스냅샷(초). 응답 시에는 `segments` 기반으로 재계산될 수 있다. |
| `elapsed_mins` | number | 저장된 경과 시간 스냅샷(분, 올림). |
| `action_status` | string | 선택 필드. 실행 중 별도 액션 상태를 저장할 때 사용한다. |
| `action_input` | string/object | 선택 필드. 액션 관련 입력값을 저장할 때 사용한다. |

### `executions.json`의 `segments[]`

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `start` | string | 구간 시작 시각 ISO 문자열. |
| `end` | string/null | 구간 종료 시각 ISO 문자열. 진행 중인 마지막 구간이면 `null`. |

## `executions.json.bak`

`execution/store.py`가 `executions.json`을 쓰기 전에 기존 파일을 복사해 만드는 백업이다. 저장소 추적 대상은 아니며, 로컬 운영 중 생성될 수 있다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| 전체 구조 | array | 원본 `executions.json`과 동일한 실행 레코드 배열이다. |

## `dyn_ready_meta.json`

`DYN_READY_URL` 기반 provider가 외부 `/dyn_ready/std-list/grouped` 응답을 동기화할 때 생성할 수 있는 메타 파일이다.

| 키 | 타입 | 설명 |
| --- | --- | --- |
| `updated_at` | string | 외부 응답의 최종 갱신 시각. |
| `data_hash` | string | 외부 응답 `data` 배열을 안정적으로 직렬화한 SHA-256 해시. `updated_at`이 바뀌지 않는 삭제/수정도 감지하기 위해 사용한다. |
