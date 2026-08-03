"""Publish materialized deliveries into durable artifact storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
)

from af_core.storage.artifact_models import (
    ArtifactReference,
    ArtifactStore,
)


PUBLICATION_MEDIA_TYPE = (
    "application/vnd.tobmate.af-core."
    "delivery-publication+json"
)


class DeliveryArtifactPublicationError(RuntimeError):
    """Raised when delivery publication or recovery is invalid."""


class DeliveryArtifactBundle(BaseModel):
    """Immutable references for one materialized delivery."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    delivery_id: str
    run_id: str
    project_id: str
    created_at: str
    manifest: ArtifactReference
    audit: ArtifactReference
    report: ArtifactReference

    def references(
        self,
    ) -> tuple[ArtifactReference, ...]:
        return (
            self.manifest,
            self.audit,
            self.report,
        )


class PublishedDelivery(BaseModel):
    """Publication receipt and its immutable artifact bundle."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    publication_reference: ArtifactReference
    bundle: DeliveryArtifactBundle


class ArtifactDeliveryPublisher:
    """Bridge materialized delivery files to an ArtifactStore."""

    def __init__(
        self,
        store: ArtifactStore,
    ) -> None:
        self.store = store

    def publish_materialized(
        self,
        materialized: object,
    ) -> PublishedDelivery:
        """Publish a ProjectDeliveryMaterializer result."""

        manifest_path = self._find_path(
            materialized,
            role="manifest",
        )
        audit_path = self._find_path(
            materialized,
            role="audit",
        )
        report_path = self._find_path(
            materialized,
            role="report",
        )

        return self.publish_paths(
            manifest_path=manifest_path,
            audit_path=audit_path,
            report_path=report_path,
        )

    def publish_paths(
        self,
        *,
        manifest_path: str | Path,
        audit_path: str | Path,
        report_path: str | Path,
    ) -> PublishedDelivery:
        """Publish final delivery files and a recovery receipt."""

        manifest = Path(
            manifest_path
        ).expanduser()
        audit = Path(
            audit_path
        ).expanduser()
        report = Path(
            report_path
        ).expanduser()

        self._require_file(
            manifest,
            role="manifest",
        )
        self._require_file(
            audit,
            role="audit",
        )
        self._require_file(
            report,
            role="report",
        )

        identity = self._manifest_identity(
            manifest.read_bytes()
        )

        common_metadata = {
            "delivery_id": identity["delivery_id"],
            "run_id": identity["run_id"],
            "project_id": identity["project_id"],
        }

        manifest_reference = self.store.put_file(
            str(manifest),
            media_type="application/json",
            original_name=manifest.name,
            metadata={
                **common_metadata,
                "delivery_role": "manifest",
            },
        )

        audit_reference = self.store.put_file(
            str(audit),
            media_type="application/json",
            original_name=audit.name,
            metadata={
                **common_metadata,
                "delivery_role": "audit",
            },
        )

        report_reference = self.store.put_file(
            str(report),
            media_type="text/plain",
            original_name=report.name,
            metadata={
                **common_metadata,
                "delivery_role": "report",
            },
        )

        bundle = DeliveryArtifactBundle(
            delivery_id=identity["delivery_id"],
            run_id=identity["run_id"],
            project_id=identity["project_id"],
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),
            manifest=manifest_reference,
            audit=audit_reference,
            report=report_reference,
        )

        publication_payload = self._canonical_payload(
            bundle
        )

        publication_reference = self.store.put_bytes(
            publication_payload,
            media_type=PUBLICATION_MEDIA_TYPE,
            original_name="delivery-publication.json",
            metadata=common_metadata,
        )

        return PublishedDelivery(
            publication_reference=publication_reference,
            bundle=bundle,
        )

    def load(
        self,
        publication_id: str,
    ) -> PublishedDelivery:
        """Recover and verify a published delivery by receipt ID."""

        publication_reference = self.store.verify(
            publication_id
        )

        if (
            publication_reference.media_type
            != PUBLICATION_MEDIA_TYPE
        ):
            raise DeliveryArtifactPublicationError(
                "artifact is not a delivery publication"
            )

        try:
            bundle = (
                DeliveryArtifactBundle
                .model_validate_json(
                    self.store.read_bytes(
                        publication_id
                    )
                )
            )
        except (
            ValidationError,
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            raise DeliveryArtifactPublicationError(
                "delivery publication payload is invalid"
            ) from exc

        for expected in bundle.references():
            actual = self.store.verify(
                expected.artifact_id
            )

            if actual != expected:
                raise DeliveryArtifactPublicationError(
                    "delivery artifact reference mismatch: "
                    f"{expected.artifact_id}"
                )

        manifest_identity = self._manifest_identity(
            self.store.read_bytes(
                bundle.manifest.artifact_id
            )
        )

        expected_identity = {
            "delivery_id": bundle.delivery_id,
            "run_id": bundle.run_id,
            "project_id": bundle.project_id,
        }

        if manifest_identity != expected_identity:
            raise DeliveryArtifactPublicationError(
                "delivery manifest identity mismatch"
            )

        return PublishedDelivery(
            publication_reference=publication_reference,
            bundle=bundle,
        )

    def verify(
        self,
        publication: PublishedDelivery,
    ) -> PublishedDelivery:
        """Verify receipt, manifest identity and all artifacts."""

        restored = self.load(
            publication.publication_reference.artifact_id
        )

        if restored != publication:
            raise DeliveryArtifactPublicationError(
                "delivery publication receipt mismatch"
            )

        return restored

    @staticmethod
    def _canonical_payload(
        bundle: DeliveryArtifactBundle,
    ) -> bytes:
        return json.dumps(
            bundle.model_dump(
                mode="json"
            ),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _manifest_identity(
        payload: bytes,
    ) -> dict[str, str]:
        try:
            decoded: Any = json.loads(
                payload.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise DeliveryArtifactPublicationError(
                "delivery manifest is not valid JSON"
            ) from exc

        if not isinstance(decoded, dict):
            raise DeliveryArtifactPublicationError(
                "delivery manifest must be a JSON object"
            )

        identity: dict[str, str] = {}

        for field in (
            "delivery_id",
            "run_id",
            "project_id",
        ):
            value = decoded.get(field)

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise DeliveryArtifactPublicationError(
                    "delivery manifest is missing "
                    f"a valid {field}"
                )

            identity[field] = value.strip()

        return identity

    @staticmethod
    def _require_file(
        path: Path,
        *,
        role: str,
    ) -> None:
        if not path.is_file():
            raise DeliveryArtifactPublicationError(
                f"delivery {role} file does not exist: "
                f"{path}"
            )

    @staticmethod
    def _find_path(
        materialized: object,
        *,
        role: str,
    ) -> Path:
        preferred = f"{role}_path"

        if hasattr(
            materialized,
            preferred,
        ):
            return Path(
                getattr(
                    materialized,
                    preferred,
                )
            )

        candidates: list[tuple[str, Path]] = []

        for name in dir(materialized):
            if (
                role not in name.lower()
                or not name.lower().endswith("_path")
            ):
                continue

            try:
                value = getattr(
                    materialized,
                    name,
                )
            except Exception:
                continue

            if isinstance(
                value,
                (str, Path),
            ):
                candidates.append(
                    (name, Path(value))
                )

        if len(candidates) == 1:
            return candidates[0][1]

        raise DeliveryArtifactPublicationError(
            "materialized delivery does not expose "
            f"an unambiguous {role} path"
        )
