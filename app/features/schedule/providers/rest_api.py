import os
import requests
from app.features.schedule.providers.base import BaseProvider


class RestApiProvider(BaseProvider):

    def __init__(self):
        self.base_url = os.environ.get('API_BASE_URL', '').rstrip('/')
        self.api_key = os.environ.get('API_KEY', '')
        self.headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}

    def get_versions(self):
        resp = requests.get(f'{self.base_url}/versions', headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def get_test_data(self, version_id):
        resp = requests.get(f'{self.base_url}/procedures/{version_id}', headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def get_test_data_all(self):
        resp = requests.get(f'{self.base_url}/procedures', headers=self.headers)
        resp.raise_for_status()
        return resp.json()
