from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class AuthorityStatus:

    ACTIVE = "active"

    REVOKED = "revoked"



class AgentAuthority(BaseModel):

    authority_id: str = Field(
        default_factory=lambda:
        str(uuid4())
    )

    agent_id: str

    permission: str

    environment: str

    scope: str

    approval_required: bool = False

    status: str = (
        AuthorityStatus.ACTIVE
    )

    created_at: datetime = Field(
        default_factory=lambda:
        datetime.now(timezone.utc)
    )
