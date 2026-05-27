"""데이터 프로바이더 팩토리 모듈.

환경 변수(PROVIDER_TYPE)에 따라 적절한 데이터 프로바이더 인스턴스를
생성하여 반환한다. 기본값은 'json_file'(로컬 JSON 파일 기반).

지원 프로바이더:
    - json_file (기본): 로컬 data/*.json 파일에서 데이터를 읽는다.
    - rest_api: 외부 REST API 서버에서 데이터를 가져온다.
              API_BASE_URL 환경 변수가 설정되지 않으면 json_file로 자동 폴백.
    - dyn_ready: 자체 /dyn_ready/std-list/grouped 엔드포인트에서 데이터를 가져온다.
              DYN_READY_URL 환경 변수로 베이스 URL을 지정한다(기본: http://127.0.0.1:5000).

사용 예:
    # 기본 (json_file)
    provider = get_provider()

    # REST API 사용 시
    # $ export PROVIDER_TYPE=rest_api
    # $ export API_BASE_URL=http://api.example.com
"""

import os
from app.features.schedule.providers.json_file import JsonFileProvider


def get_provider():
    """설정된 프로바이더 타입에 따라 프로바이더 인스턴스를 생성한다.

    환경 변수 PROVIDER_TYPE으로 프로바이더 종류를 지정할 수 있다.
    미설정 시 기본값 'json_file'(JsonFileProvider)을 사용한다.

    rest_api 타입을 지정했더라도 API_BASE_URL이 없으면 json_file로 폴백한다.
    이는 개발 환경에서 외부 API 서버 없이 동작할 수 있도록 하기 위함이다.

    Returns:
        BaseProvider: 프로바이더 인스턴스.

    Raises:
        ValueError: 알 수 없는 프로바이더 타입이 지정된 경우.
    """
    provider_type = os.environ.get('PROVIDER_TYPE', 'json_file')
    if provider_type == 'json_file':
        return JsonFileProvider()
    if provider_type == 'rest_api':
        api_base_url = os.environ.get('API_BASE_URL', '').strip()
        if not api_base_url:
            # API_BASE_URL 미설정 시 json_file로 자동 폴백 (개발 환경 호환)
            return JsonFileProvider()
        from app.features.schedule.providers.rest_api import RestApiProvider
        return RestApiProvider()
    if provider_type == 'dyn_ready':
        from app.features.schedule.providers.dyn_ready import DynReadyProvider
        return DynReadyProvider()
    raise ValueError(f'Unknown provider type: {provider_type}')
