from abc import ABC, abstractmethod


class SonicAdapter(ABC):
    @abstractmethod
    def export_running(self):
        raise NotImplementedError

    @abstractmethod
    def read_startup(self):
        raise NotImplementedError

    @abstractmethod
    def system_info(self):
        raise NotImplementedError

    @abstractmethod
    def create_checkpoint(self, name):
        raise NotImplementedError

    @abstractmethod
    def read_checkpoint(self, name):
        raise NotImplementedError

    @abstractmethod
    def delete_checkpoint(self, name):
        raise NotImplementedError

    @abstractmethod
    def rollback_checkpoint(self, name):
        raise NotImplementedError

    @abstractmethod
    def validate_candidate(self, path):
        raise NotImplementedError

    @abstractmethod
    def apply_candidate(self, path):
        raise NotImplementedError

    @abstractmethod
    def save_startup(self):
        raise NotImplementedError

    @abstractmethod
    def capabilities(self):
        raise NotImplementedError
