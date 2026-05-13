class OfpidSettings:
    """현재 운용 버전(OFP ID) 설정을 관리한다."""

    @classmethod
    def get_current_ofp_id(cls):
        """활성화된 버전의 ID를 반환한다.

        versions.json 에서 is_active=True 인 첫 번째 버전의 id를 반환한다.
        활성 버전이 없으면 None.
        """
        from app.features.schedule.models import version
        versions = version.get_all()
        active = next((v for v in versions if v.get('is_active')), None)
        return active['id'] if active else None
