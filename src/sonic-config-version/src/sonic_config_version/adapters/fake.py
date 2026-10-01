import copy
import json

from sonic_config_version.adapters.base import SonicAdapter


class FakeSonicAdapter(SonicAdapter):
    """In-memory adapter used by orchestration and contract tests."""

    def __init__(self, running=None, startup=None, info=None):
        self.running = copy.deepcopy(running or {})
        self.startup = copy.deepcopy(startup if startup is not None else self.running)
        self.info = info or {
            "platform": "x86_64-kvm_x86_64-r0",
            "hwsku": "Force10-S6000",
            "sonic_release": "test",
            "asic_count": 1,
        }
        self.checkpoints = {}
        self.calls = []
        self.fail_on = None

    def _call(self, name):
        self.calls.append(name)
        if self.fail_on == name:
            raise RuntimeError("injected {} failure".format(name))

    def export_running(self):
        self._call("export_running")
        return copy.deepcopy(self.running)

    def read_startup(self):
        self._call("read_startup")
        return copy.deepcopy(self.startup)

    def system_info(self):
        return copy.deepcopy(self.info)

    def create_checkpoint(self, name):
        self._call("create_checkpoint")
        self.checkpoints[name] = copy.deepcopy(self.running)

    def read_checkpoint(self, name):
        self._call("read_checkpoint")
        return copy.deepcopy(self.checkpoints[name])

    def delete_checkpoint(self, name):
        self._call("delete_checkpoint")
        self.checkpoints.pop(name, None)

    def rollback_checkpoint(self, name):
        self._call("rollback_checkpoint")
        self.running = copy.deepcopy(self.checkpoints[name])

    @staticmethod
    def _read(path):
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)

    def validate_candidate(self, path):
        self._call("validate_candidate")
        self._read(path)

    def apply_candidate(self, path):
        self._call("apply_candidate")
        self.running = self._read(path)

    def save_startup(self):
        self._call("save_startup")
        self.startup = copy.deepcopy(self.running)

    def capabilities(self):
        return {
            "paths": {"git": "/usr/bin/git", "config": "fake", "sonic_cfggen": "fake"},
            "available": {"git": True, "config": True, "sonic_cfggen": True},
            "native_commands": {
                "export": True,
                "replace": True,
                "checkpoint": True,
                "rollback": True,
                "delete-checkpoint": True,
                "save": True,
            },
        }
