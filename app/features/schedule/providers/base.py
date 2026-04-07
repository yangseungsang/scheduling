from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Abstract base for external data providers."""

    @abstractmethod
    def get_versions(self):
        """Return list of version dicts: [{id, name, description}]"""

    @abstractmethod
    def get_test_data(self, version_id):
        """Return test data for a version: [{section_name, version_id, identifiers: [{id, estimated_minutes, owners}]}]"""

    @abstractmethod
    def get_test_data_all(self):
        """Return all test data across all versions."""
