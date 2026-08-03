import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from af_core.delivery.artifact_publisher import (
    ArtifactDeliveryPublisher,
    DeliveryArtifactPublicationError,
    PUBLICATION_MEDIA_TYPE,
)
from af_core.storage import (
    ArtifactIntegrityError,
    ArtifactPolicyError,
    LocalContentAddressedArtifactStore,
)


def delivery_files(
    root: Path,
) -> tuple[Path, Path, Path]:
    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest = root / "delivery-manifest.json"
    audit = root / "delivery-audit.json"
    report = root / "delivery-report.txt"

    manifest.write_text(
        json.dumps(
            {
                "delivery_id": "delivery-a",
                "run_id": "run-a",
                "project_id": "project-a",
                "decision": "complete",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    audit.write_text(
        json.dumps(
            {
                "run_id": "run-a",
                "events": [],
            }
        ),
        encoding="utf-8",
    )

    report.write_text(
        "AF-Core final delivery\n",
        encoding="utf-8",
    )

    return manifest, audit, report


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


def test_publish_paths_stores_delivery_and_receipt(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "store"
    )
    publisher = ArtifactDeliveryPublisher(
        store
    )

    manifest, audit, report = delivery_files(
        tmp_path / "delivery"
    )

    published = publisher.publish_paths(
        manifest_path=manifest,
        audit_path=audit,
        report_path=report,
    )

    assert published.bundle.delivery_id == (
        "delivery-a"
    )
    assert published.bundle.run_id == "run-a"
    assert published.bundle.project_id == (
        "project-a"
    )

    assert (
        published.publication_reference.media_type
        == PUBLICATION_MEDIA_TYPE
    )

    assert store.exists(
        published.publication_reference.artifact_id
    )

    for reference in (
        published.bundle.references()
    ):
        assert store.verify(
            reference.artifact_id
        ) == reference


def test_publish_materialized_adapter(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "store"
    )
    publisher = ArtifactDeliveryPublisher(
        store
    )

    manifest, audit, report = delivery_files(
        tmp_path / "delivery"
    )

    materialized = SimpleNamespace(
        manifest_path=manifest,
        audit_path=audit,
        report_path=report,
    )

    published = publisher.publish_materialized(
        materialized
    )

    assert published.bundle.delivery_id == (
        "delivery-a"
    )


def test_publication_recovers_after_store_restart(
    tmp_path: Path,
) -> None:
    root = tmp_path / "store"
    manifest, audit, report = delivery_files(
        tmp_path / "delivery"
    )

    first = LocalContentAddressedArtifactStore(
        root
    )
    published = ArtifactDeliveryPublisher(
        first
    ).publish_paths(
        manifest_path=manifest,
        audit_path=audit,
        report_path=report,
    )

    second = LocalContentAddressedArtifactStore(
        root
    )

    restored = ArtifactDeliveryPublisher(
        second
    ).load(
        published.publication_reference.artifact_id
    )

    assert restored == published


def test_verify_checks_receipt_and_all_artifacts(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "store"
    )
    publisher = ArtifactDeliveryPublisher(
        store
    )

    manifest, audit, report = delivery_files(
        tmp_path / "delivery"
    )

    published = publisher.publish_paths(
        manifest_path=manifest,
        audit_path=audit,
        report_path=report,
    )

    assert publisher.verify(
        published
    ) == published


def test_invalid_manifest_json_is_rejected(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "store"
    )
    publisher = ArtifactDeliveryPublisher(
        store
    )

    manifest, audit, report = delivery_files(
        tmp_path / "delivery"
    )

    manifest.write_text(
        "{invalid-json",
        encoding="utf-8",
    )

    with pytest.raises(
        DeliveryArtifactPublicationError,
        match="not valid JSON",
    ):
        publisher.publish_paths(
            manifest_path=manifest,
            audit_path=audit,
            report_path=report,
        )


def test_missing_manifest_identity_is_rejected(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "store"
    )
    publisher = ArtifactDeliveryPublisher(
        store
    )

    manifest, audit, report = delivery_files(
        tmp_path / "delivery"
    )

    manifest.write_text(
        json.dumps(
            {
                "delivery_id": "delivery-a",
                "run_id": "run-a",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        DeliveryArtifactPublicationError,
        match="project_id",
    ):
        publisher.publish_paths(
            manifest_path=manifest,
            audit_path=audit,
            report_path=report,
        )


def test_missing_delivery_file_is_rejected(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "store"
    )
    publisher = ArtifactDeliveryPublisher(
        store
    )

    manifest, audit, report = delivery_files(
        tmp_path / "delivery"
    )
    report.unlink()

    with pytest.raises(
        DeliveryArtifactPublicationError,
        match="does not exist",
    ):
        publisher.publish_paths(
            manifest_path=manifest,
            audit_path=audit,
            report_path=report,
        )


def test_symlink_delivery_file_is_rejected(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "store"
    )
    publisher = ArtifactDeliveryPublisher(
        store
    )

    manifest, audit, report = delivery_files(
        tmp_path / "delivery"
    )

    external = tmp_path / "external-report.txt"
    external.write_text(
        "external",
        encoding="utf-8",
    )

    report.unlink()
    report.symlink_to(external)

    with pytest.raises(
        ArtifactPolicyError,
        match="symlink",
    ):
        publisher.publish_paths(
            manifest_path=manifest,
            audit_path=audit,
            report_path=report,
        )


def test_tampered_delivery_artifact_is_detected(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "store"
    )
    publisher = ArtifactDeliveryPublisher(
        store
    )

    manifest, audit, report = delivery_files(
        tmp_path / "delivery"
    )

    published = publisher.publish_paths(
        manifest_path=manifest,
        audit_path=audit,
        report_path=report,
    )

    report_reference = (
        published.bundle.report
    )

    object_path(
        store,
        report_reference.sha256,
    ).write_bytes(
        b"tampered-report"
    )

    with pytest.raises(
        ArtifactIntegrityError,
        match="mismatch",
    ):
        publisher.load(
            published
            .publication_reference
            .artifact_id
        )


def test_tampered_publication_receipt_is_detected(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "store"
    )
    publisher = ArtifactDeliveryPublisher(
        store
    )

    manifest, audit, report = delivery_files(
        tmp_path / "delivery"
    )

    published = publisher.publish_paths(
        manifest_path=manifest,
        audit_path=audit,
        report_path=report,
    )

    publication_reference = (
        published.publication_reference
    )

    object_path(
        store,
        publication_reference.sha256,
    ).write_bytes(
        b"tampered-publication"
    )

    with pytest.raises(
        ArtifactIntegrityError,
        match="mismatch",
    ):
        publisher.load(
            publication_reference.artifact_id
        )


def test_non_publication_artifact_is_rejected(
    tmp_path: Path,
) -> None:
    store = LocalContentAddressedArtifactStore(
        tmp_path / "store"
    )

    reference = store.put_bytes(
        b'{"not":"a publication"}',
        media_type="application/json",
    )

    with pytest.raises(
        DeliveryArtifactPublicationError,
        match="not a delivery publication",
    ):
        ArtifactDeliveryPublisher(
            store
        ).load(
            reference.artifact_id
        )
