import os
from app.features.schedule.providers.json_file import JsonFileProvider


def get_provider():
    """Factory: return the configured data provider."""
    provider_type = os.environ.get('PROVIDER_TYPE', 'json_file')
    if provider_type == 'json_file':
        return JsonFileProvider()
    raise ValueError(f'Unknown provider type: {provider_type}')
