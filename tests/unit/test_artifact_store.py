import hashlib
from pathlib import Path

import pytest

from af_core.storage import (
    ArtifactPolicyError,
    ArtifactReference,
    ArtifactStore,
    LocalContentAddressedArtifactStore,
)


def artifact_id(
    digest: str,
) -> str:
    return f"sha256:{digest}"


def object_path(
    store: LocalContentAddressedArtifactStore,
    digest: str,
) -> Path:
    return (
        store.root
        / "objects"
        / "sha256"
        / digest[:2]
        / digest
    )


def metadata_path(
    store: LocalContentAddressedArtifactStore,
    digest: str,
) -> Path:
    return (
        store.root
        / "metadata"
        / "sha256"
        / digest[:2]
        / f"{digest}.json"
    )


def test_artifact_reference_rejects_digest_mismatch():
    with pytest.raises(
        ValueError,
        match="must match",
    ):
        ArtifactReference(
            artifact_id=artifact_id("a" * 64),
            sha256="b" * 64,
            size_bytes=1,
            created_at="2026-08-04T00:00:00+00:00",
        )


def test_store_satisfies_artifact_store_protocol(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )

    assert isinstance(store, ArtifactStore)


def test_put_bytes_round_trip_is_content_addressed(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )
    content = b"AF-Core artifact content"
    digest = hashlib.sha256(content).hexdigest()

    reference = store.put_bytes(content)

    assert reference.sha256 == digest
    assert reference.artifact_id == artifact_id(
        digest
    )
    assert reference.size_bytes == len(content)
    assert store.exists(reference.artifact_id)
    assert (
        store.read_bytes(reference.artifact_id)
        == content
    )
    assert (
        store.verify(reference.artifact_id)
        == reference
    )


def test_duplicate_content_is_deduplicated(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )
    content = b"same immutable content"

    first = store.put_bytes(
        content,
        media_type="text/plain",
        original_name="first.txt",
        metadata={
            "owner": "first",
        },
    )

    second = store.put_bytes(
        content,
        media_type="application/json",
        original_name="second.json",
        metadata={
            "owner": "second",
        },
    )

    assert second == first
    assert second.media_type == "text/plain"
    assert second.original_name == "first.txt"
    assert second.metadata == {
        "owner": "first",
    }


def test_metadata_and_filename_are_preserved(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )

    reference = store.put_bytes(
        b'{"status":"ready"}',
        media_type="application/json",
        original_name="manifest.json",
        metadata={
            "project_id": "project-a",
            "run_id": "run-a",
        },
    )

    restored = store.get(
        reference.artifact_id
    )

    assert restored.media_type == (
        "application/json"
    )
    assert restored.original_name == (
        "manifest.json"
    )
    assert dict(restored.metadata) == {
        "project_id": "project-a",
        "run_id": "run-a",
    }


def test_put_file_round_trip_streams_content(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )
    source = tmp_path / "large.bin"
    content = b"artifact-block-" * 100_000

    source.write_bytes(content)

    reference = store.put_file(
        source,
        media_type="application/octet-stream",
    )

    assert reference.original_name == "large.bin"
    assert reference.size_bytes == len(content)
    assert (
        store.read_bytes(reference.artifact_id)
        == content
    )


def test_empty_artifact_round_trip(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )

    reference = store.put_bytes(b"")

    assert reference.size_bytes == 0
    assert store.read_bytes(
        reference.artifact_id
    ) == b""


def test_oversized_bytes_are_rejected(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts",
        maximum_size_bytes=4,
    )

    with pytest.raises(
        ArtifactPolicyError,
        match="maximum size",
    ):
        store.put_bytes(b"12345")


def test_oversized_file_is_rejected(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts",
        maximum_size_bytes=4,
    )
    source = tmp_path / "oversized.bin"
    source.write_bytes(b"12345")

    with pytest.raises(
        ArtifactPolicyError,
        match="maximum size",
    ):
        store.put_file(source)


def test_source_symlink_is_rejected(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )
    source = tmp_path / "source.bin"
    link = tmp_path / "source-link.bin"

    source.write_bytes(b"source")
    link.symlink_to(source)

    with pytest.raises(
        ArtifactPolicyError,
        match="symlink",
    ):
        store.put_file(link)


def test_store_root_symlink_is_rejected(
    tmp_path: Path,
) -> None:
    real_root = tmp_path / "real-root"
    linked_root = tmp_path / "linked-root"

    real_root.mkdir()
    linked_root.symlink_to(
        real_root,
        target_is_directory=True,
    )

    with pytest.raises(
        ArtifactPolicyError,
        match="root must not be a symlink",
    ):
        LocalContentAddressedArtifactStore(
            linked_root
        )


def test_invalid_and_missing_ids_are_rejected(
    tmp_path: Path,
) -> None:
    from af_core.storage import (
        ArtifactNotFoundError,
    )

    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )

    assert store.exists("invalid") is False

    with pytest.raises(
        ArtifactPolicyError,
        match="sha256",
    ):
        store.read_bytes("../../etc/passwd")

    with pytest.raises(
        ArtifactNotFoundError,
        match="not found",
    ):
        store.get(
            artifact_id("0" * 64)
        )


def test_tampered_object_is_detected(
    tmp_path: Path,
) -> None:
    from af_core.storage import (
        ArtifactIntegrityError,
    )

    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )

    reference = store.put_bytes(
        b"original content"
    )

    path = object_path(
        store,
        reference.sha256,
    )

    path.write_bytes(b"tampered content")

    with pytest.raises(
        ArtifactIntegrityError,
        match="mismatch",
    ):
        store.verify(reference.artifact_id)


def test_tampered_metadata_is_detected(
    tmp_path: Path,
) -> None:
    from af_core.storage import (
        ArtifactIntegrityError,
    )

    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )

    reference = store.put_bytes(
        b"metadata integrity"
    )

    path = metadata_path(
        store,
        reference.sha256,
    )

    path.write_text(
        '{"artifact_id":"invalid"}',
        encoding="utf-8",
    )

    with pytest.raises(
        ArtifactIntegrityError,
        match="metadata is invalid",
    ):
        store.get(reference.artifact_id)


def test_object_symlink_is_rejected(
    tmp_path: Path,
) -> None:
    from af_core.storage import (
        ArtifactIntegrityError,
    )

    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )

    reference = store.put_bytes(
        b"object symlink protection"
    )

    external = tmp_path / "external-object"
    external.write_bytes(
        b"object symlink protection"
    )

    path = object_path(
        store,
        reference.sha256,
    )
    path.unlink()
    path.symlink_to(external)

    with pytest.raises(
        ArtifactIntegrityError,
        match="symlink",
    ):
        store.verify(reference.artifact_id)


def test_metadata_symlink_is_rejected(
    tmp_path: Path,
) -> None:
    from af_core.storage import (
        ArtifactIntegrityError,
    )

    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )

    reference = store.put_bytes(
        b"metadata symlink protection"
    )

    path = metadata_path(
        store,
        reference.sha256,
    )

    external = tmp_path / "external-metadata.json"
    external.write_bytes(path.read_bytes())

    path.unlink()
    path.symlink_to(external)

    with pytest.raises(
        ArtifactIntegrityError,
        match="symlink",
    ):
        store.get(reference.artifact_id)


def test_layout_permissions_and_temp_cleanup(
    tmp_path: Path,
) -> None:
    import stat

    store = LocalContentAddressedArtifactStore(
        tmp_path / "artifacts"
    )
    source = tmp_path / "package.bin"
    source.write_bytes(b"durable package")

    reference = store.put_file(source)

    stored_object = object_path(
        store,
        reference.sha256,
    )
    stored_metadata = metadata_path(
        store,
        reference.sha256,
    )

    assert stored_object.is_file()
    assert stored_metadata.is_file()

    assert stat.S_IMODE(
        stored_object.stat().st_mode
    ) == 0o640

    assert stat.S_IMODE(
        stored_metadata.stat().st_mode
    ) == 0o640

    assert list(
        (store.root / "temporary").iterdir()
    ) == []

    assert not tuple(
        store.root.rglob("*.tmp")
    )


def test_reference_rejects_unsafe_name_and_media_type():
    digest = "a" * 64

    with pytest.raises(
        ValueError,
        match="plain filename",
    ):
        ArtifactReference(
            artifact_id=artifact_id(digest),
            sha256=digest,
            size_bytes=1,
            original_name="../secret.txt",
            created_at="2026-08-04T00:00:00+00:00",
        )

    with pytest.raises(
        ValueError,
        match="valid MIME type",
    ):
        ArtifactReference(
            artifact_id=artifact_id(digest),
            sha256=digest,
            size_bytes=1,
            media_type="text/plain\ninvalid",
            created_at="2026-08-04T00:00:00+00:00",
        )
