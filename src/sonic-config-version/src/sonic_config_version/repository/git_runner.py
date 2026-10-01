import os
import re

from sonic_config_version.constants import GIT_PATH, GIT_TIMEOUT_SECONDS, MAX_COMMAND_OUTPUT_BYTES
from sonic_config_version.errors import ValidationError
from sonic_config_version.process import CommandRunner


REVISION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@{}~^/+-]{0,127}$")


def validate_revision(revision):
    if not isinstance(revision, str) or not REVISION_PATTERN.fullmatch(revision):
        raise ValidationError("invalid Git revision syntax")
    if revision.startswith("-") or ".." in revision or "@{" in revision:
        raise ValidationError("unsafe Git revision syntax")
    return revision


class GitRunner:
    def __init__(self, repository, base_dir, git_path=GIT_PATH):
        self.repository = repository
        self.git_path = git_path
        self.command_runner = CommandRunner(
            timeout=GIT_TIMEOUT_SECONDS,
            max_output=MAX_COMMAND_OUTPUT_BYTES,
            home=base_dir,
        )

    def run(self, *arguments, check=True, input_text=None):
        argv = [
            self.git_path,
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "credential.helper=",
            "-C",
            self.repository,
        ] + list(arguments)
        _, stdout, stderr = self.command_runner.run(argv, check=check, input_text=input_text)
        return stdout, stderr

    def version(self):
        _, stdout, _ = self.command_runner.run([self.git_path, "--version"])
        return stdout.strip()

    def exists(self):
        return os.path.isfile(os.path.join(self.repository, ".git", "HEAD"))
