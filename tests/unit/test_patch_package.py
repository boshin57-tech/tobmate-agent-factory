from pathlib import Path
import io
import json
import tarfile

from af_core.delivery.patch_package import (
    PatchPackageService,
)


def create_delivery_manifest(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "delivery_id": "delivery-1",
                "project_id": "project-1",
                "run_id": "run-1",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_patch_package_create_and_verify(
    tmp_path: Path,
) -> None:
    delivery_manifest = create_delivery_manifest(
        tmp_path / "manifest.json"
    )
    output = tmp_path / "patch-package.tar.gz"

    service = PatchPackageService()

    manifest = service.create(
        output_path=output,
        project_id="project-1",
        run_id="run-1",
        base_revision="abc123",
        branch="af/project-1/run-1",
        diff_text=(
            "diff --git a/app.py b/app.py\n"
            "+VALUE = 2\n"
        ),
        changed_files=[
            "app.py",
            "app.py",
        ],
        delivery_manifest_path=delivery_manifest,
    )

    assert output.is_file()
    assert manifest.changed_files == ["app.py"]
    assert service.verify(output)

    with tarfile.open(output, "r:gz") as archive:
        assert set(archive.getnames()) == {
            "changes.patch",
            "package-manifest.json",
            "delivery-manifest.json",
        }


def test_patch_package_detects_tampered_patch(
    tmp_path: Path,
) -> None:
    delivery_manifest = create_delivery_manifest(
        tmp_path / "manifest.json"
    )
    original = tmp_path / "original.tar.gz"
    tampered = tmp_path / "tampered.tar.gz"

    service = PatchPackageService()

    service.create(
        output_path=original,
        project_id="project-1",
        run_id="run-1",
        base_revision="abc123",
        branch="af/project-1/run-1",
        diff_text="+VALUE = 2\n",
        changed_files=["app.py"],
        delivery_manifest_path=delivery_manifest,
    )

    with tarfile.open(original, "r:gz") as source:
        package_manifest = source.extractfile(
            "package-manifest.json"
        ).read()
        delivery_bytes = source.extractfile(
            "delivery-manifest.json"
        ).read()

    with tarfile.open(tampered, "w:gz") as archive:
        for name, data in {
            "changes.patch": b"tampered",
            "package-manifest.json": package_manifest,
            "delivery-manifest.json": delivery_bytes,
        }.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(
                info,
                io.BytesIO(data),
            )

    assert not service.verify(tampered)


def test_patch_package_requires_delivery_manifest(
    tmp_path: Path,
) -> None:
    service = PatchPackageService()

    try:
        service.create(
            output_path=tmp_path / "package.tar.gz",
            project_id="project-1",
            run_id="run-1",
            base_revision="abc123",
            branch="af/project-1/run-1",
            diff_text="+VALUE = 2\n",
            changed_files=["app.py"],
            delivery_manifest_path=(
                tmp_path / "missing.json"
            ),
        )
    except FileNotFoundError:
        pass
    else:
        raise AssertionError(
            "Missing delivery manifest was accepted"
        )
