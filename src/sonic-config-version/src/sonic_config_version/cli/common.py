import json
import os

import click

from sonic_config_version.errors import SonicGitError
from sonic_config_version.manager import SonicGitManager


def require_root(purpose="SonicGit modifying operations"):
    if os.geteuid() != 0:
        error = click.ClickException("root privileges are required for {}".format(purpose))
        error.exit_code = 2
        raise error


def manager():
    return SonicGitManager()


def emit(value):
    if isinstance(value, str):
        click.echo(value)
    else:
        click.echo(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def run(action):
    try:
        emit(action())
    except SonicGitError as exc:
        error = click.ClickException("{}: {}".format(exc.code, exc))
        error.exit_code = int(exc.code[2:])
        raise error
    except Exception as exc:
        error = click.ClickException("SG999: {}".format(exc))
        error.exit_code = 70
        raise error
