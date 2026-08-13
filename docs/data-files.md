# 데이터 파일

애플리케이션 데이터는 `app/data/`의 역할별 JSON 문서에 저장한다.

| 파일 | domain 타입 | 내용 |
| --- | --- | --- |
| `test_plan.json` | `TestPlan` | 시험 사이클 버전, procedure, 일정 블록 |
| `test_executions.json` | `Executions` | 시험 항목별 실행 상태와 결과 |
| `settings.json` | `AppSettings` | 근무 시간과 화면 설정 |

`test_plan.json`의 최상위 `version_id`는 현재 전체 시험 사이클의
버전이다. procedure나 실행 기록마다 반복 저장하지 않는다. feature 코드는 JSON
파일을 직접 읽거나 쓰지 않고 repository가 domain 타입으로 변환해 반환한다.

각 JSON 파일은 잠금 안에서 최신 데이터를 읽고 수정한 뒤 원자적으로 교체한다.
계획 변경은 `test_plan.json`만, 실행 상태 변경은 `test_executions.json`만 쓴다.
빈 문자열, 빈 배열, `false`, `0`인 선택 필드는 파일에
쓰지 않고 domain 타입이 읽을 때 기본값으로 복원한다.

장소는 별도 기준 정보가 아니다. `TestProcedure.location_name`과
`ScheduleBlock.location_name`에 이름을 직접 저장하며, 필터 목록은 이 값들에서 계산한다.
외부 입력은 DynReady API에서 동기화하므로 feature 내부 데이터 폴더나 캐시 파일은 없다.

실행 기록은 별도 `id`를 만들지 않는다. 계획에서 이미 유일한
`procedure_id`와 `test_item_id` 조합을 실행 기록의 키로 사용한다.

## 초기화

`POST /admin/api/project-reset`은 procedures, schedule, executions를 비운다.
애플리케이션 설정은 유지한다.

`POST /api/sync/reset-and-sync`은 같은 영역을 비운 뒤 DynReady 데이터를 다시 가져온다.
