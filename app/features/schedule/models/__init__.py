"""
모델 패키지 초기화 모듈.

각 도메인별 모델 모듈을 임포트하여 패키지 수준에서 접근 가능하게 한다.
이를 통해 `from app.features.schedule.models import task` 등으로 사용할 수 있다.
"""

from app.features.schedule.models import location, schedule_block, settings, task, user, version
