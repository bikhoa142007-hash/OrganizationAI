"""Map pg_dump/docker diagnostic text to a small, non-sensitive code set."""

from __future__ import annotations

import argparse
import re
import sys


def classify_diagnostic(text: str, *, exit_code: int, archive_ready: bool) -> str:
    """Return an allowlisted diagnostic code; never return source text."""
    if exit_code == 0:
        if not archive_ready:
            return "ARCHIVE_MISSING_OR_EMPTY"
        return "STDERR_PRESENT_NONFATAL" if text.strip() else "NONE"

    message = re.sub(r"\s+", " ", text.casefold())

    if any(
        marker in message
        for marker in (
            "invalid mount config",
            "mounts denied",
            "bind source path does not exist",
            "bind source path must be",
            "not shared from the host",
        )
    ):
        return "DOCKER_BIND_MOUNT_FAILED"

    if any(
        marker in message
        for marker in (
            "cannot connect to the docker daemon",
            "error during connect",
            "is the docker daemon running",
        )
    ):
        return "DOCKER_ENGINE_FAILED"

    if any(
        marker in message
        for marker in (
            "permission denied for table",
            "permission denied for sequence",
            "permission denied for schema",
            "permission denied for relation",
            "permission denied for database",
            "permission denied for function",
            "permission denied for type",
            "must be owner of",
            "insufficient privilege",
        )
    ):
        return "DATABASE_PRIVILEGE_FAILED"

    output_file_open_failed = "could not open output file" in message
    output_file_permission_denied = any(
        marker in message
        for marker in (
            "permission denied",
            "access is denied",
            "operation not permitted",
            "read-only file system",
        )
    )
    if output_file_open_failed and output_file_permission_denied:
        return "BACKUP_PATH_PERMISSION_FAILED"
    if output_file_open_failed:
        return "BACKUP_PATH_OPEN_FAILED_REDACTED"

    if any(
        marker in message
        for marker in ("permission denied", "access is denied", "operation not permitted")
    ):
        return "PERMISSION_DENIED_UNCLASSIFIED"

    if any(
        marker in message
        for marker in (
            "unrecognized option",
            "unknown option",
            "invalid option",
            "option requires an argument",
        )
    ):
        return "PG_DUMP_OPTION_ERROR"

    if any(
        marker in message
        for marker in (
            "password authentication failed",
            "authentication failed",
            "no password supplied",
            "password is required",
        )
    ):
        return "DATABASE_AUTHENTICATION_FAILED"

    if any(
        marker in message
        for marker in (
            "no space left on device",
            "not enough space",
            "disk is full",
        )
    ):
        return "BACKUP_STORAGE_FAILED"

    if any(
        marker in message
        for marker in (
            "server version mismatch",
            "server version:",
            "pg_dump version:",
        )
    ):
        return "PG_DUMP_VERSION_MISMATCH"

    if any(
        marker in message
        for marker in (
            "error response from daemon",
            "docker: error",
            "docker: unknown command",
        )
    ):
        return "DOCKER_CLI_ERROR_REDACTED"

    if any(
        marker in message
        for marker in (
            "could not connect to server",
            "connection refused",
            "connection timed out",
            "could not translate host name",
            "no route to host",
            "ssl error",
            "ssl syscall",
            "certificate verify failed",
            "timeout expired",
        )
    ):
        return "DATABASE_CONNECTION_FAILED"

    # Docker reserves 125-127 for its own runner/command startup failures.
    if exit_code in (125, 126, 127):
        return "DOCKER_RUN_START_OR_COMMAND_FAILED"
    if not message:
        return "ERROR_OUTPUT_UNAVAILABLE"
    if "pg_dump:" in message:
        return "PG_DUMP_ERROR_REDACTED"
    if "docker:" in message:
        return "DOCKER_CLI_ERROR_REDACTED"
    return "DOCKER_RUN_OR_CONTAINER_ERROR_REDACTED"


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--archive-ready", action="store_true")
    arguments = parser.parse_args()
    diagnostic = sys.stdin.read()
    print(
        classify_diagnostic(
            diagnostic,
            exit_code=arguments.exit_code,
            archive_ready=arguments.archive_ready,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
