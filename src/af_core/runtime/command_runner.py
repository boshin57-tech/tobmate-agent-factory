from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from af_core.production import (
    ProductionSettings,
    SecretReference,
    is_sensitive_key,
    redact_text,
    sanitized_environment,
    validate_environment_key,
)


class CommandPolicyError(RuntimeError):
    """Raised when a command violates runtime policy."""


class CommandExecutionError(RuntimeError):
    """Raised when command execution itself fails."""


class CommandResult(BaseModel):
    command: list[str]
    cwd: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    changed_files: list[str] = Field(default_factory=list)


class CommandPolicy:
    DEFAULT_ALLOWED_EXECUTABLES = {
        "python",
        "python3",
        "pytest",
        "git",
        "cargo",
        "sui",
        "npm",
        "node",
        "go",
        "bash",
        "sh",
    }

    FORBIDDEN_ARGUMENTS = {
        "--force",
        "-f",
    }

    FORBIDDEN_GIT_SUBCOMMANDS = {
        "push",
        "clean",
        "reset",
        "checkout",
        "switch",
        "merge",
        "rebase",
        "commit",
        "tag",
        "remote",
        "config",
    }

    def __init__(
        self,
        *,
        allowed_executables: set[str] | None = None,
    ) -> None:
        self.allowed_executables = (
            set(allowed_executables)
            if allowed_executables is not None
            else set(self.DEFAULT_ALLOWED_EXECUTABLES)
        )

    def validate(
        self,
        command: Sequence[str],
    ) -> list[str]:
        normalized = [str(item) for item in command]

        if not normalized:
            raise CommandPolicyError("Command cannot be empty")

        executable = Path(normalized[0]).name

        if executable not in self.allowed_executables:
            raise CommandPolicyError(
                f"Executable is not allowed: {executable}"
            )

        if any(
            argument in self.FORBIDDEN_ARGUMENTS
            for argument in normalized[1:]
        ):
            raise CommandPolicyError(
                "Force arguments are not allowed"
            )

        if executable == "git" and len(normalized) >= 2:
            subcommand = normalized[1]

            if subcommand in self.FORBIDDEN_GIT_SUBCOMMANDS:
                raise CommandPolicyError(
                    f"Git subcommand is not allowed: {subcommand}"
                )

        if executable in {"bash", "sh"}:
            self._validate_shell(normalized)

        return normalized

    def _validate_shell(self, command: list[str]) -> None:
        if len(command) < 3 or command[1] != "-c":
            raise CommandPolicyError(
                "Shell commands must use 'sh -c' or 'bash -c'"
            )

        script = command[2]

        forbidden_tokens = {
            "sudo",
            "rm -rf",
            "mkfs",
            "shutdown",
            "reboot",
            "curl ",
            "wget ",
            "ssh ",
            "scp ",
            "nc ",
            "netcat",
            "> /etc/",
            "/dev/sd",
        }

        lowered = script.lower()

        for token in forbidden_tokens:
            if token in lowered:
                raise CommandPolicyError(
                    f"Forbidden shell content detected: {token}"
                )


class RestrictedCommandRunner:
    LEGACY_ALLOWED_ENVIRONMENT_KEYS = {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "CARGO_HOME",
        "RUSTUP_HOME",
        "TMPDIR",
    }

    def __init__(
        self,
        workspace_path: str | Path,
        *,
        policy: CommandPolicy | None = None,
        settings: ProductionSettings | None = None,
        environment_source: Mapping[str, str] | None = None,
    ) -> None:
        self.workspace = Path(
            workspace_path
        ).expanduser().resolve()

        if not self.workspace.is_dir():
            raise ValueError(
                f"Workspace does not exist: {self.workspace}"
            )

        self.policy = policy or CommandPolicy()
        self.settings = settings
        self._environment_source = dict(
            os.environ
            if environment_source is None
            else environment_source
        )

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: str | Path | None = None,
        timeout: int | None = None,
        environment: Mapping[str, str] | None = None,
        secret_environment: Mapping[
            str,
            SecretReference,
        ] | None = None,
    ) -> CommandResult:
        normalized = self.policy.validate(command)
        execution_cwd = self._resolve_cwd(cwd)

        before = await self._git_status()

        env, known_secrets = self._safe_environment(
            environment,
            secret_environment,
        )

        effective_timeout = (
            timeout
            if timeout is not None
            else (
                self.settings.command_timeout_seconds
                if self.settings is not None
                else 60
            )
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *normalized,
                cwd=str(execution_cwd),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=effective_timeout,
            )

            timed_out = False
        except asyncio.TimeoutError:
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()
            timed_out = True

        after = await self._git_status()

        changed_files = sorted(after - before)

        stdout = redact_text(
            stdout_bytes.decode(
                "utf-8",
                errors="replace",
            ),
            known_secrets=known_secrets,
        )

        stderr = redact_text(
            stderr_bytes.decode(
                "utf-8",
                errors="replace",
            ),
            known_secrets=known_secrets,
        )

        return CommandResult(
            command=[
                redact_text(
                    item,
                    known_secrets=known_secrets,
                )
                for item in normalized
            ],
            cwd=str(execution_cwd),
            returncode=(
                process.returncode
                if not timed_out
                else -1
            ),
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            changed_files=changed_files,
        )

    def _resolve_cwd(
        self,
        cwd: str | Path | None,
    ) -> Path:
        target = (
            self.workspace
            if cwd is None
            else Path(cwd).expanduser().resolve()
        )

        if target != self.workspace and self.workspace not in target.parents:
            raise CommandPolicyError(
                "Command working directory is outside workspace"
            )

        if not target.is_dir():
            raise CommandPolicyError(
                f"Command directory does not exist: {target}"
            )

        return target

    def _safe_environment(
        self,
        extra: Mapping[str, str] | None,
        secret_environment: Mapping[
            str,
            SecretReference,
        ] | None,
    ) -> tuple[dict[str, str], tuple[str, ...]]:
        if self.settings is None:
            allowed_keys = set(
                self.LEGACY_ALLOWED_ENVIRONMENT_KEYS
            )
            secret_keys: set[str] = set()
        else:
            allowed_keys = set(
                self.settings.allowed_environment_keys
            )
            secret_keys = set(
                self.settings.secret_environment_keys
            )

        environment = sanitized_environment(
            self._environment_source,
            allowed_keys=tuple(allowed_keys),
            secret_keys=tuple(secret_keys),
        )

        for key, value in (extra or {}).items():
            normalized = validate_environment_key(key)

            if (
                normalized in secret_keys
                or is_sensitive_key(normalized)
            ):
                raise CommandPolicyError(
                    "Secret environment variable must use "
                    f"SecretReference: {normalized}"
                )

            if normalized not in allowed_keys:
                raise CommandPolicyError(
                    "Environment variable is not allowed: "
                    f"{normalized}"
                )

            environment[normalized] = str(value)

        known_secrets: list[str] = []

        for key, reference in (
            secret_environment or {}
        ).items():
            normalized = validate_environment_key(key)

            if (
                self.settings is not None
                and normalized not in secret_keys
            ):
                raise CommandPolicyError(
                    "Secret environment variable is not "
                    f"declared: {normalized}"
                )

            value = reference.resolve(
                self._environment_source
            )

            if value is not None:
                environment[normalized] = value
                known_secrets.append(value)

        return environment, tuple(known_secrets)

    async def _git_status(self) -> set[str]:
        git_dir = self.workspace / ".git"

        if not git_dir.exists():
            return set()

        process = await asyncio.create_subprocess_exec(
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            cwd=str(self.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _stderr = await process.communicate()

        if process.returncode != 0:
            return set()

        lines = stdout.decode(
            "utf-8",
            errors="replace",
        ).splitlines()

        return {
            line[3:].strip()
            for line in lines
            if len(line) >= 4
        }
