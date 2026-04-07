"""외부 데이터 프로바이더 추상 베이스 클래스 모듈.

모든 외부 데이터 소스 프로바이더가 구현해야 할 인터페이스를 정의한다.
새로운 프로바이더(예: REST API, 데이터베이스 등)를 추가하려면
이 클래스를 상속하여 추상 메서드를 구현하면 된다.
"""

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """외부 데이터 프로바이더의 추상 베이스 클래스.

    버전 정보와 시험 데이터를 제공하는 인터페이스를 정의한다.
    모든 프로바이더는 이 클래스를 상속하고 아래 메서드를 구현해야 한다.
    """

    @abstractmethod
    def get_versions(self):
        """외부 소스에서 버전 목록을 가져온다.

        Returns:
            list: 버전 딕셔너리 목록.
                각 항목은 {'id': str, 'name': str, 'description': str} 형태.
        """

    @abstractmethod
    def get_test_data(self, version_id):
        """특정 버전의 시험 데이터를 가져온다.

        Args:
            version_id: 조회할 버전 ID.

        Returns:
            list: 시험 데이터 딕셔너리 목록.
                각 항목은 {'section_name': str, 'version_id': str,
                'identifiers': [{'id': str, 'estimated_minutes': int,
                'owners': list}]} 형태.
        """

    @abstractmethod
    def get_test_data_all(self):
        """모든 버전의 시험 데이터를 가져온다.

        Returns:
            list: 전체 시험 데이터 딕셔너리 목록 (get_test_data와 동일 형태).
        """
