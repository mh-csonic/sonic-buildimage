import json
import os

from sonic_config_version.adapters.base import SonicAdapter
from sonic_config_version.constants import (
    COMMAND_TIMEOUT_SECONDS,
    CONFIG_CLI_PATH,
    MAX_COMMAND_OUTPUT_BYTES,
    NATIVE_CHECKPOINT_DIR,
    SONIC_CFGGEN_PATH,
    STARTUP_CONFIG_PATH,
)
from sonic_config_version.errors import CapabilityError, ValidationError
from sonic_config_version.process import CommandRunner
from sonic_config_version.snapshot.normalizer import read_json_file


class CommunitySonicAdapter(SonicAdapter):
    def __init__(
        self,
        config_path=CONFIG_CLI_PATH,
        cfggen_path=SONIC_CFGGEN_PATH,
        startup_path=STARTUP_CONFIG_PATH,
        checkpoint_dir=NATIVE_CHECKPOINT_DIR,
        runner=None,
    ):
        self.config_path = config_path
        self.cfggen_path = cfggen_path
        self.startup_path = startup_path
        self.checkpoint_dir = checkpoint_dir
        self.runner = runner or CommandRunner(
            timeout=COMMAND_TIMEOUT_SECONDS,
            max_output=MAX_COMMAND_OUTPUT_BYTES,
        )

    def _config(self, *arguments):
        _, stdout, _ = self.runner.run([self.config_path] + list(arguments))
        return stdout

    def export_running(self):
        _, stdout, _ = self.runner.run([self.cfggen_path, "-d", "--print-data"])
        try:
            return json.loads(stdout)
        except ValueError as exc:
            raise ValidationError("sonic-cfggen returned invalid JSON: {}".format(exc))

    def read_startup(self):
        return json.loads(read_json_file(self.startup_path).decode("utf-8"))

    def system_info(self):
        try:
            from sonic_py_common import device_info, multi_asic

            version = device_info.get_sonic_version_info() or {}
            release = (
                version.get("build_version")
                or version.get("sonic_version")
                or version.get("release")
                or version.get("build_version_base")
            )
            return {
                "platform": device_info.get_platform(),
                "hwsku": device_info.get_hwsku(),
                "sonic_release": release,
                "asic_count": multi_asic.get_num_asics(),
            }
        except Exception as exc:
            raise CapabilityError("cannot determine SONiC platform information: {}".format(exc))

    def create_checkpoint(self, name):
        self._config("checkpoint", name)

    def checkpoint_path(self, name):
        if not name.startswith("sonicgit-") or not name.replace("-", "").isalnum():
            raise ValidationError("invalid checkpoint name")
        return os.path.join(self.checkpoint_dir, name + ".cp.json")

    def read_checkpoint(self, name):
        return json.loads(read_json_file(self.checkpoint_path(name)).decode("utf-8"))

    def delete_checkpoint(self, name):
        self._config("delete-checkpoint", name)

    def rollback_checkpoint(self, name):
        self._config("rollback", name)

    def validate_candidate(self, path):
        self._config("replace", "--dry-run", path)

    def apply_candidate(self, path):
        self._config("replace", path)

    def save_startup(self):
        self._config("save", "-y")

    def capabilities(self):
        commands = {
            "git": "/usr/bin/git",
            "config": self.config_path,
            "sonic_cfggen": self.cfggen_path,
        }
        available = {name: os.path.isfile(path) and os.access(path, os.X_OK) for name, path in commands.items()}
        native = {name: False for name in ("export", "replace", "checkpoint", "rollback", "delete-checkpoint", "save")}
        try:
            code, output, error = self.runner.run([self.config_path, "--help"], check=False)
            help_text = output + "\n" + error
            if code == 0:
                for name in ("replace", "checkpoint", "rollback", "delete-checkpoint", "save"):
                    native[name] = name in help_text
        except Exception:
            pass
        try:
            self.export_running()
            native["export"] = True
        except Exception:
            pass
        return {"paths": commands, "available": available, "native_commands": native}
