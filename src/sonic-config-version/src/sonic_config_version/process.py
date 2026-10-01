import os
import selectors
import subprocess
import time

from sonic_config_version.constants import COMMAND_TIMEOUT_SECONDS, MAX_COMMAND_OUTPUT_BYTES
from sonic_config_version.errors import CommandError


SAFE_PATH = "/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin"


def _private_umask():
    os.umask(0o077)


def sanitized_environment(home="/"):
    return {
        "PATH": SAFE_PATH,
        "HOME": home,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


class CommandRunner:
    def __init__(self, timeout=COMMAND_TIMEOUT_SECONDS, max_output=MAX_COMMAND_OUTPUT_BYTES, home="/"):
        self.timeout = timeout
        self.max_output = max_output
        self.home = home

    def run(self, argv, check=True, input_text=None):
        if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(item, str) for item in argv):
            raise CommandError("command must be a non-empty argument vector")
        try:
            process = subprocess.Popen(
                list(argv),
                stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=sanitized_environment(self.home),
                shell=False,
                preexec_fn=_private_umask,
            )
        except OSError as exc:
            raise CommandError("cannot execute {}: {}".format(argv[0], exc))

        if input_text is not None:
            if not isinstance(input_text, str) or len(input_text.encode("utf-8")) > self.max_output:
                process.kill()
                process.wait()
                raise CommandError("command input must be bounded UTF-8 text")
            try:
                process.stdin.write(input_text.encode("utf-8"))
                process.stdin.close()
            except BrokenPipeError:
                pass

        output = {"stdout": bytearray(), "stderr": bytearray()}
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        deadline = time.monotonic() + self.timeout
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    process.kill()
                    process.wait()
                    raise CommandError("command timed out after {} seconds: {}".format(self.timeout, argv[0]))
                events = selector.select(min(remaining, 0.25))
                if not events and process.poll() is not None:
                    events = [(key, selectors.EVENT_READ) for key in list(selector.get_map().values())]
                for key, _ in events:
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buffer = output[key.data]
                    buffer.extend(chunk)
                    if len(buffer) > self.max_output:
                        process.kill()
                        process.wait()
                        raise CommandError("command output exceeded {} bytes".format(self.max_output))
            returncode = process.wait()
        finally:
            selector.close()
            if process.poll() is None:
                process.kill()
                process.wait()

        stdout = bytes(output["stdout"]).decode("utf-8", "replace")
        stderr = bytes(output["stderr"]).decode("utf-8", "replace")
        if check and returncode:
            detail = stderr.strip() or stdout.strip() or "no diagnostic output"
            if len(detail) > 4096:
                detail = detail[:4096] + "...<truncated>"
            raise CommandError("{} failed with exit {}: {}".format(argv[0], returncode, detail))
        return returncode, stdout, stderr
