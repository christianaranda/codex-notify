#!/usr/bin/env python3
"""Create the Codex Notify Pushover credential env file."""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import sys
import tempfile


DEFAULT_ENV_PATH = Path.home() / ".codex" / "codex-notify" / ".pushover.env"


def validate_secret(name: str, value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{name} cannot be empty")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{name} cannot contain newlines")
    return value


def render_env_file(user_key: str, app_token: str) -> str:
    return (
        f"PUSHOVER_USER_KEY={validate_secret('PUSHOVER_USER_KEY', user_key)}\n"
        f"PUSHOVER_APP_TOKEN={validate_secret('PUSHOVER_APP_TOKEN', app_token)}\n"
    )


def write_env_file(path: Path, user_key: str, app_token: str, *, force: bool) -> None:
    path = path.expanduser()
    if path.exists() and not force:
        raise FileExistsError(
            f"{path} already exists. Re-run with --force to replace it."
        )

    content = render_env_file(user_key, app_token)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass

    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as temp_file:
            temp_name = temp_file.name
            os.chmod(temp_name, 0o600)
            temp_file.write(content)
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def prompt_credentials() -> tuple[str, str]:
    print("Enter Pushover credentials. Input is hidden and stays local.")
    user_key = getpass.getpass("Pushover user key: ")
    app_token = getpass.getpass("Pushover app token: ")
    return (
        validate_secret("PUSHOVER_USER_KEY", user_key),
        validate_secret("PUSHOVER_APP_TOKEN", app_token),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set up Codex Notify Pushover credentials."
    )
    parser.add_argument(
        "--path",
        default=str(DEFAULT_ENV_PATH),
        help=f"Credential env-file path. Default: {DEFAULT_ENV_PATH}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing credential env file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        user_key, app_token = prompt_credentials()
        path = Path(args.path).expanduser()
        write_env_file(path, user_key, app_token, force=args.force)
        print(f"Saved Codex Notify credentials to {path}")
        print("Next: run the README dry-run and sample notification checks.")
        return 0
    except (FileExistsError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
