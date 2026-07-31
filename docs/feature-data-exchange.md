# Feature Data Exchange

Schedule과 execution 데이터는 여러 feature가 함께 사용한다. 새 feature는 JSON 파일을 직접 읽지 말고 `data_exchange` 서비스를 통해 read-only snapshot을 사용한다.

## 내부 Python 사용

```python
from app.features.data_exchange.service import feature_snapshot

snapshot = feature_snapshot()
tasks = snapshot['schedule']['tasks']
executions = snapshot['execution']['executions']
```

필요한 영역만 읽을 수도 있다.

```python
from app.features.data_exchange.service import schedule_snapshot, execution_snapshot
```

## HTTP API

외부 클라이언트 또는 분리된 feature 화면은 다음 read-only API를 사용한다.

| Endpoint | 설명 |
| --- | --- |
| `/features/api/schedule` | tasks, schedule_blocks, users, locations, versions |
| `/features/api/execution` | executions |
| `/features/api/snapshot` | schedule과 execution 통합 snapshot |

쓰기 작업은 기존 schedule/execution API를 사용한다. `data_exchange` API는 feature 간 참조와 조회 전용 경로다.
