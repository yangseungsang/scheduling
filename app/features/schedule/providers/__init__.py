"""데이터 프로바이더 팩토리 모듈.

환경 변수(PROVIDER_TYPE)에 따라 적절한 데이터 프로바이더 인스턴스를
생성하여 반환한다. 기본값은 'json_file'(로컬 JSON 파일 기반).
"""

import os
from app.features.schedule.providers.json_file import JsonFileProvider


def get_provider():
    """설정된 프로바이더 타입에 따라 프로바이더 인스턴스를 생성한다.

    환경 변수 PROVIDER_TYPE으로 프로바이더 종류를 지정할 수 있다.
    미설정 시 기본값 'json_file'(JsonFileProvider)을 사용한다.

    Returns:
        BaseProvider: 프로바이더 인스턴스.

    Raises:
        ValueError: 알 수 없는 프로바이더 타입이 지정된 경우.
    """
    provider_type = os.environ.get('PROVIDER_TYPE', 'json_file')
    if provider_type == 'json_file':
        return JsonFileProvider()
    if provider_type == 'rest_api':
        from app.features.schedule.providers.rest_api import RestApiProvider
        return RestApiProvider()
    raise ValueError(f'Unknown provider type: {provider_type}')
