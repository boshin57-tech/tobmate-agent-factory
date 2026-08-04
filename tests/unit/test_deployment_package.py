from __future__ import annotations

import json
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from af_core.production.deployment_models import (
    DeploymentFileKind,
    DeploymentPackagePlan,
    DeploymentPolicyError,
    ReleaseIdentity,
    ReleasePackageInput,
)
from af_core.production.deployment_package import (
    DeploymentPackageService,
)


RELEASE_ID = (
    "release-"
    "00112233445566778899aabbccddeeff"
)

NOW = datetime(
    2026,
    8,
    4,
    7,
    0,
    tzinfo=timezone.utc,
)


def make_identity(
    *,
    release_id: str = RELEASE_ID,
) -> ReleaseIdentity:
    return ReleaseIdentity(
        release_id=release_id,
        application_name=(
            "tobmate-agent-factory"
        ),
        version="1.1.0",
        git_commit="e3b0f1b",
    )


def make_sources(
    root: Path,
) -> tuple[Path, Path]:
    wheel = root / "package.whl"
    runbook = root / "RUNBOOK.md"

    wheel.write_bytes(
        b"deterministic-wheel"
    )
    runbook.write_text(
        "# Release Runbook\n",
        encoding="utf-8",
    )

    return wheel, runbook


def make_plan(
    *,
    destination_root: Path,
    wheel: Path,
    runbook: Path,
    activate: bool = False,
) -> DeploymentPackagePlan:
    return DeploymentPackagePlan(
        destination_root=destination_root,
        identity=make_identity(),
        files=(
            ReleasePackageInput(
                source_path=wheel,
                relative_path=(
                    "packages/package.whl"
                ),
                kind=(
                    DeploymentFileKind.WHEEL
                ),
            ),
            ReleasePackageInput(
                source_path=runbook,
                relative_path=(
                    "docs/RUNBOOK.md"
                ),
                kind=(
                    DeploymentFileKind.RUNBOOK
                ),
            ),
        ),
        python_requires=">=3.11",
        activate=activate,
    )


def test_release_identity_validates_and_normalizes() -> None:
    identity = ReleaseIdentity(
        release_id=RELEASE_ID.upper(),
        application_name=(
            "TOBMATE-AGENT-FACTORY"
        ),
        version="1.1.0",
        git_commit="E3B0F1B",
    )

    assert identity.release_id == RELEASE_ID
    assert (
        identity.application_name
        == "tobmate-agent-factory"
    )
    assert identity.git_commit == "e3b0f1b"


def test_release_identity_rejects_invalid_values() -> None:
    with pytest.raises(
        ValidationError
    ):
        ReleaseIdentity(
            release_id="release-invalid",
            application_name="Invalid Name",
            version="latest",
            git_commit="not-a-commit",
        )


def test_create_publishes_deterministic_manifest(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    wheel, runbook = make_sources(
        source_root
    )

    destination = tmp_path / "deployment"

    service = DeploymentPackageService(
        clock=lambda: NOW
    )

    result = service.create(
        make_plan(
            destination_root=destination,
            wheel=wheel,
            runbook=runbook,
        )
    )

    assert result.release_dir.is_dir()
    assert result.manifest.file_count == 2
    assert (
        result.manifest.identity.release_id
        == RELEASE_ID
    )

    paths = tuple(
        record.relative_path
        for record in result.manifest.files
    )

    assert paths == (
        "payload/docs/RUNBOOK.md",
        "payload/packages/package.whl",
    )

    payload = json.loads(
        result.manifest_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload["file_count"] == 2
    assert (
        payload["identity"]["release_id"]
        == RELEASE_ID
    )


def test_create_applies_restrictive_permissions(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    wheel, runbook = make_sources(
        source_root
    )

    result = DeploymentPackageService(
        clock=lambda: NOW
    ).create(
        make_plan(
            destination_root=(
                tmp_path / "deployment"
            ),
            wheel=wheel,
            runbook=runbook,
        )
    )

    manifest_mode = stat.S_IMODE(
        result.manifest_path.stat().st_mode
    )
    payload_mode = stat.S_IMODE(
        (
            result.release_dir
            / "payload"
            / "packages"
            / "package.whl"
        ).stat().st_mode
    )
    release_mode = stat.S_IMODE(
        result.release_dir.stat().st_mode
    )

    assert manifest_mode == 0o640
    assert payload_mode == 0o640
    assert release_mode == 0o750


def test_create_atomically_activates_release(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    wheel, runbook = make_sources(
        source_root
    )

    result = DeploymentPackageService(
        clock=lambda: NOW
    ).create(
        make_plan(
            destination_root=(
                tmp_path / "deployment"
            ),
            wheel=wheel,
            runbook=runbook,
            activate=True,
        )
    )

    assert (
        result.current_pointer_path
        is not None
    )
    assert (
        result.current_pointer_path
        .read_text(encoding="ascii")
        .strip()
        == RELEASE_ID
    )
    assert not (
        result.current_pointer_path
        .is_symlink()
    )

from af_core.production.deployment_models import (
    DeploymentIntegrityError,
)


def test_verify_accepts_complete_release(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    wheel, runbook = make_sources(
        source_root
    )

    service = DeploymentPackageService(
        clock=lambda: NOW
    )

    result = service.create(
        make_plan(
            destination_root=(
                tmp_path / "deployment"
            ),
            wheel=wheel,
            runbook=runbook,
        )
    )

    verified = service.verify(
        result.release_dir
    )

    assert (
        verified.identity.release_id
        == RELEASE_ID
    )
    assert verified.file_count == 2


def test_verify_rejects_tampered_payload(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    wheel, runbook = make_sources(
        source_root
    )

    service = DeploymentPackageService(
        clock=lambda: NOW
    )

    result = service.create(
        make_plan(
            destination_root=(
                tmp_path / "deployment"
            ),
            wheel=wheel,
            runbook=runbook,
        )
    )

    payload = (
        result.release_dir
        / "payload"
        / "packages"
        / "package.whl"
    )

    payload.write_bytes(
        b"tampered-wheel"
    )

    with pytest.raises(
        DeploymentIntegrityError,
        match="checksum|size",
    ):
        service.verify(
            result.release_dir
        )


def test_verify_rejects_tampered_manifest(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    wheel, runbook = make_sources(
        source_root
    )

    service = DeploymentPackageService(
        clock=lambda: NOW
    )

    result = service.create(
        make_plan(
            destination_root=(
                tmp_path / "deployment"
            ),
            wheel=wheel,
            runbook=runbook,
        )
    )

    result.manifest_path.write_text(
        '{"tampered":true}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        DeploymentIntegrityError,
        match="checksum mismatch",
    ):
        service.load_manifest(
            result.release_dir
        )


def test_create_rejects_duplicate_release(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    wheel, runbook = make_sources(
        source_root
    )

    service = DeploymentPackageService(
        clock=lambda: NOW
    )

    plan = make_plan(
        destination_root=(
            tmp_path / "deployment"
        ),
        wheel=wheel,
        runbook=runbook,
    )

    service.create(plan)

    with pytest.raises(
        DeploymentPolicyError,
        match="release already exists",
    ):
        service.create(plan)


def test_create_rejects_duplicate_relative_paths(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    wheel, runbook = make_sources(
        source_root
    )

    plan = DeploymentPackagePlan(
        destination_root=(
            tmp_path / "deployment"
        ),
        identity=make_identity(),
        files=(
            ReleasePackageInput(
                source_path=wheel,
                relative_path=(
                    "packages/shared.bin"
                ),
                kind=(
                    DeploymentFileKind.WHEEL
                ),
            ),
            ReleasePackageInput(
                source_path=runbook,
                relative_path=(
                    "packages/shared.bin"
                ),
                kind=(
                    DeploymentFileKind.RUNBOOK
                ),
            ),
        ),
    )

    with pytest.raises(
        DeploymentPolicyError,
        match="must be unique",
    ):
        DeploymentPackageService(
            clock=lambda: NOW
        ).create(plan)

def test_create_rejects_traversal_path(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    wheel, _ = make_sources(
        source_root
    )

    plan = DeploymentPackagePlan(
        destination_root=(
            tmp_path / "deployment"
        ),
        identity=make_identity(),
        files=(
            ReleasePackageInput(
                source_path=wheel,
                relative_path=(
                    "../escaped.whl"
                ),
                kind=(
                    DeploymentFileKind.WHEEL
                ),
            ),
        ),
    )

    with pytest.raises(
        DeploymentPolicyError,
        match="invalid deployment relative path",
    ):
        DeploymentPackageService(
            clock=lambda: NOW
        ).create(plan)


def test_create_rejects_symlink_source(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    wheel, _ = make_sources(
        source_root
    )

    symlink = (
        source_root / "linked-package.whl"
    )
    symlink.symlink_to(wheel)

    plan = DeploymentPackagePlan(
        destination_root=(
            tmp_path / "deployment"
        ),
        identity=make_identity(),
        files=(
            ReleasePackageInput(
                source_path=symlink,
                relative_path=(
                    "packages/package.whl"
                ),
                kind=(
                    DeploymentFileKind.WHEEL
                ),
            ),
        ),
    )

    with pytest.raises(
        DeploymentPolicyError,
        match="symlink",
    ):
        DeploymentPackageService(
            clock=lambda: NOW
        ).create(plan)


def test_create_rejects_source_inside_destination(
    tmp_path: Path,
) -> None:
    destination = (
        tmp_path / "deployment"
    )
    destination.mkdir()

    source = (
        destination / "package.whl"
    )
    source.write_bytes(
        b"unsafe-overlap"
    )

    plan = DeploymentPackagePlan(
        destination_root=destination,
        identity=make_identity(),
        files=(
            ReleasePackageInput(
                source_path=source,
                relative_path=(
                    "packages/package.whl"
                ),
                kind=(
                    DeploymentFileKind.WHEEL
                ),
            ),
        ),
    )

    with pytest.raises(
        DeploymentPolicyError,
        match="inside the destination root",
    ):
        DeploymentPackageService(
            clock=lambda: NOW
        ).create(plan)


def test_verify_rejects_extra_payload_file(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    wheel, runbook = make_sources(
        source_root
    )

    service = DeploymentPackageService(
        clock=lambda: NOW
    )

    result = service.create(
        make_plan(
            destination_root=(
                tmp_path / "deployment"
            ),
            wheel=wheel,
            runbook=runbook,
        )
    )

    unexpected = (
        result.release_dir
        / "payload"
        / "unexpected.txt"
    )
    unexpected.write_text(
        "unexpected",
        encoding="utf-8",
    )

    with pytest.raises(
        DeploymentIntegrityError,
        match="inventory mismatch",
    ):
        service.verify(
            result.release_dir
        )


def test_executable_mode_is_recorded_and_verified(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()

    script = (
        source_root / "start-service"
    )
    script.write_text(
        "#!/bin/sh\nexit 0\n",
        encoding="utf-8",
    )

    service = DeploymentPackageService(
        clock=lambda: NOW
    )

    result = service.create(
        DeploymentPackagePlan(
            destination_root=(
                tmp_path / "deployment"
            ),
            identity=make_identity(),
            files=(
                ReleasePackageInput(
                    source_path=script,
                    relative_path=(
                        "bin/start-service"
                    ),
                    kind=(
                        DeploymentFileKind.OTHER
                    ),
                    executable=True,
                ),
            ),
        )
    )

    deployed_script = (
        result.release_dir
        / "payload"
        / "bin"
        / "start-service"
    )

    assert stat.S_IMODE(
        deployed_script.stat().st_mode
    ) == 0o750

    assert (
        result.manifest.files[0].executable
        is True
    )

    service.verify(
        result.release_dir
    )

    deployed_script.chmod(0o640)

    with pytest.raises(
        DeploymentIntegrityError,
        match="execution mode mismatch",
    ):
        service.verify(
            result.release_dir
        )
