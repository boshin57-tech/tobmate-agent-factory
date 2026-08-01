from __future__ import annotations

import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()

    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)

    return digest.hexdigest()


class PatchPackageManifest(BaseModel):
    package_id: str = Field(
        default_factory=lambda: f"pkg_{uuid4().hex}"
    )
    project_id: str
    run_id: str
    base_revision: str
    branch: str
    patch_sha256: str
    patch_size_bytes: int
    changed_files: list[str] = Field(default_factory=list)
    delivery_manifest_sha256: str
    created_at: datetime = Field(default_factory=utc_now)


class PatchPackageService:
    def create(
        self,
        *,
        output_path: str | Path,
        project_id: str,
        run_id: str,
        base_revision: str,
        branch: str,
        diff_text: str,
        changed_files: list[str],
        delivery_manifest_path: str | Path,
    ) -> PatchPackageManifest:
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        delivery_manifest = Path(
            delivery_manifest_path
        ).expanduser().resolve()

        if not delivery_manifest.is_file():
            raise FileNotFoundError(
                f"Delivery manifest not found: {delivery_manifest}"
            )

        patch_bytes = diff_text.encode("utf-8")

        manifest = PatchPackageManifest(
            project_id=project_id,
            run_id=run_id,
            base_revision=base_revision,
            branch=branch,
            patch_sha256=sha256_bytes(patch_bytes),
            patch_size_bytes=len(patch_bytes),
            changed_files=sorted(set(changed_files)),
            delivery_manifest_sha256=sha256_file(
                delivery_manifest
            ),
        )

        temporary_dir = output.parent / (
            f".{output.name}.{manifest.package_id}.tmp"
        )
        temporary_dir.mkdir(parents=True, exist_ok=False)

        try:
            patch_path = temporary_dir / "changes.patch"
            package_manifest_path = (
                temporary_dir / "package-manifest.json"
            )
            copied_delivery_manifest = (
                temporary_dir / "delivery-manifest.json"
            )

            patch_path.write_bytes(patch_bytes)
            package_manifest_path.write_text(
                json.dumps(
                    manifest.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            copied_delivery_manifest.write_bytes(
                delivery_manifest.read_bytes()
            )

            temporary_archive = output.with_suffix(
                output.suffix + ".tmp"
            )

            with tarfile.open(
                temporary_archive,
                mode="w:gz",
            ) as archive:
                archive.add(
                    patch_path,
                    arcname="changes.patch",
                )
                archive.add(
                    package_manifest_path,
                    arcname="package-manifest.json",
                )
                archive.add(
                    copied_delivery_manifest,
                    arcname="delivery-manifest.json",
                )

            temporary_archive.replace(output)
        finally:
            for child in temporary_dir.iterdir():
                child.unlink()
            temporary_dir.rmdir()

        return manifest

    def verify(
        self,
        package_path: str | Path,
    ) -> bool:
        package = Path(package_path).expanduser().resolve()

        if not package.is_file():
            return False

        try:
            with tarfile.open(package, mode="r:gz") as archive:
                names = set(archive.getnames())

                required = {
                    "changes.patch",
                    "package-manifest.json",
                    "delivery-manifest.json",
                }

                if names != required:
                    return False

                patch_member = archive.extractfile(
                    "changes.patch"
                )
                manifest_member = archive.extractfile(
                    "package-manifest.json"
                )
                delivery_member = archive.extractfile(
                    "delivery-manifest.json"
                )

                if (
                    patch_member is None
                    or manifest_member is None
                    or delivery_member is None
                ):
                    return False

                patch_bytes = patch_member.read()
                manifest = PatchPackageManifest.model_validate_json(
                    manifest_member.read()
                )
                delivery_bytes = delivery_member.read()

                if len(patch_bytes) != manifest.patch_size_bytes:
                    return False

                if (
                    sha256_bytes(patch_bytes)
                    != manifest.patch_sha256
                ):
                    return False

                if (
                    sha256_bytes(delivery_bytes)
                    != manifest.delivery_manifest_sha256
                ):
                    return False

                return True
        except (
            tarfile.TarError,
            OSError,
            ValueError,
        ):
            return False
