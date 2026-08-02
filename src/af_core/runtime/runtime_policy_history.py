"""Hash-linked runtime policy decision history."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from af_core.runtime.runtime_policy_models import RuntimePolicyResult


GENESIS_HASH = "0" * 64


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RuntimePolicyHistoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_id: str = Field(
        default_factory=lambda: str(uuid4())
    )
    sequence: int = Field(ge=1)
    previous_hash: str
    record_hash: str
    result: RuntimePolicyResult
    recorded_at: datetime = Field(default_factory=utc_now)


class RuntimePolicyHistoryVerification(BaseModel):
    model_config = ConfigDict(frozen=True)

    valid: bool
    record_count: int
    invalid_sequence: int | None = None
    reason: str = ""


class RuntimePolicyHistory:
    def __init__(self) -> None:
        self._records: list[
            RuntimePolicyHistoryRecord
        ] = []
        self._lock = RLock()

    def append(
        self,
        result: RuntimePolicyResult,
    ) -> RuntimePolicyHistoryRecord:
        with self._lock:
            sequence = len(self._records) + 1
            previous_hash = (
                self._records[-1].record_hash
                if self._records
                else GENESIS_HASH
            )
            recorded_at = utc_now()

            record_hash = self._calculate_hash(
                sequence=sequence,
                previous_hash=previous_hash,
                result=result,
                recorded_at=recorded_at,
            )

            record = RuntimePolicyHistoryRecord(
                sequence=sequence,
                previous_hash=previous_hash,
                record_hash=record_hash,
                result=result,
                recorded_at=recorded_at,
            )

            self._records.append(record)
            return record

    def list_records(
        self,
    ) -> tuple[RuntimePolicyHistoryRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def query(
        self,
        *,
        request_id: str | None = None,
        subject_id: str | None = None,
    ) -> tuple[RuntimePolicyHistoryRecord, ...]:
        with self._lock:
            records = tuple(self._records)

        return tuple(
            record
            for record in records
            if (
                request_id is None
                or record.result.request_id == request_id
            )
            and (
                subject_id is None
                or record.result.subject_id == subject_id
            )
        )

    def verify_chain(
        self,
    ) -> RuntimePolicyHistoryVerification:
        with self._lock:
            records = tuple(self._records)

        previous_hash = GENESIS_HASH

        for record in records:
            if record.previous_hash != previous_hash:
                return RuntimePolicyHistoryVerification(
                    valid=False,
                    record_count=len(records),
                    invalid_sequence=record.sequence,
                    reason="Previous hash mismatch",
                )

            expected_hash = self._calculate_hash(
                sequence=record.sequence,
                previous_hash=record.previous_hash,
                result=record.result,
                recorded_at=record.recorded_at,
            )

            if expected_hash != record.record_hash:
                return RuntimePolicyHistoryVerification(
                    valid=False,
                    record_count=len(records),
                    invalid_sequence=record.sequence,
                    reason="Record hash mismatch",
                )

            previous_hash = record.record_hash

        return RuntimePolicyHistoryVerification(
            valid=True,
            record_count=len(records),
        )

    @staticmethod
    def _calculate_hash(
        *,
        sequence: int,
        previous_hash: str,
        result: RuntimePolicyResult,
        recorded_at: datetime,
    ) -> str:
        payload = {
            "sequence": sequence,
            "previous_hash": previous_hash,
            "result": result.model_dump(mode="json"),
            "recorded_at": recorded_at.isoformat(),
        }

        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return hashlib.sha256(canonical).hexdigest()
