"""SQL tables for durable autonomous project execution runs."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
)


project_run_metadata = MetaData()


project_run_snapshots = Table(
    "project_run_snapshots",
    project_run_metadata,
    Column(
        "run_id",
        String(255),
        primary_key=True,
    ),
    Column(
        "project_id",
        String(255),
        nullable=False,
    ),
    Column(
        "status",
        String(64),
        nullable=False,
    ),
    Column(
        "version",
        Integer,
        nullable=False,
    ),
    Column(
        "created_at",
        Float,
        nullable=False,
    ),
    Column(
        "updated_at",
        Float,
        nullable=False,
    ),
    Column(
        "state_payload",
        Text,
        nullable=False,
    ),
)

Index(
    "ix_project_run_snapshots_project_id",
    project_run_snapshots.c.project_id,
)

Index(
    "ix_project_run_snapshots_status",
    project_run_snapshots.c.status,
)


project_run_events = Table(
    "project_run_events",
    project_run_metadata,
    Column(
        "run_id",
        String(255),
        ForeignKey(
            "project_run_snapshots.run_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    ),
    Column(
        "sequence",
        Integer,
        nullable=False,
    ),
    Column(
        "kind",
        String(64),
        nullable=False,
    ),
    Column(
        "occurred_at",
        Float,
        nullable=False,
    ),
    Column(
        "task_id",
        String(255),
        nullable=True,
    ),
    Column(
        "detail_payload",
        Text,
        nullable=False,
    ),
    PrimaryKeyConstraint(
        "run_id",
        "sequence",
        name="pk_project_run_events",
    ),
)

Index(
    "ix_project_run_events_run_time",
    project_run_events.c.run_id,
    project_run_events.c.occurred_at,
)
