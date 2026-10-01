import os

import pytest

from sonic_config_version.audit import AuditLog
from sonic_config_version.errors import CommandError, LockError, ValidationError
from sonic_config_version.locking import FileLock
from sonic_config_version.process import CommandRunner, sanitized_environment
from sonic_config_version.repository.git_runner import validate_revision


@pytest.mark.parametrize("revision", ["--help", "HEAD..main", "HEAD@{1}", "x y", ""])
def test_unsafe_revisions_are_rejected(revision):
    with pytest.raises(ValidationError):
        validate_revision(revision)


def test_operation_lock_is_nonblocking(tmp_path):
    path = str(tmp_path / "operation.lock")
    with FileLock(path):
        with pytest.raises(LockError):
            with FileLock(path):
                pass


def test_audit_redacts_sensitive_fields(tmp_path):
    path = str(tmp_path / "audit" / "audit.jsonl")
    audit = AuditLog(path)
    audit.append("commit", "success", password="bad", nested={"community": "private", "safe": "ok"})
    event = audit.read(1)[0]
    assert event["details"]["password"] == "<redacted>"
    assert event["details"]["nested"]["community"] == "<redacted>"
    assert event["details"]["nested"]["safe"] == "ok"
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_command_runner_enforces_timeout_and_output_bounds():
    with pytest.raises(CommandError, match="timed out"):
        CommandRunner(timeout=0.05).run(["/usr/bin/python3", "-c", "import time; time.sleep(1)"])
    with pytest.raises(CommandError, match="output exceeded"):
        CommandRunner(max_output=10).run(["/usr/bin/python3", "-c", "print('x' * 100)"])


def test_git_global_and_system_configuration_are_disabled():
    environment = sanitized_environment("/service-home")
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
