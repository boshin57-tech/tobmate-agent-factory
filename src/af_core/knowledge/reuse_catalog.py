from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class ReuseAssetType:

    CODE = "code"

    ENGINE = "engine"

    AGENT = "agent"

    WORKFLOW = "workflow"

    ARCHITECTURE = "architecture"

    SMART_CONTRACT = "smart_contract"

    UI_COMPONENT = "ui_component"


class ReusableAsset(BaseModel):

    asset_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    name: str

    asset_type: str

    description: str

    source_project: str

    version: str = "1.0"

    reuse_count: int = 0

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )


class ReuseCatalogEngine:
    """
    Catalog of reusable project assets.
    """


    def __init__(self) -> None:

        self._assets: list[
            ReusableAsset
        ] = []


    def register(
        self,
        asset: ReusableAsset,
    ) -> ReusableAsset:

        self._assets.append(
            asset
        )

        return asset


    def get(
        self,
        asset_id: str,
    ) -> ReusableAsset | None:

        for asset in self._assets:

            if asset.asset_id == asset_id:
                return asset

        return None


    def find_by_type(
        self,
        asset_type: str,
    ) -> tuple[
        ReusableAsset,
        ...
    ]:

        return tuple(
            asset
            for asset
            in self._assets
            if asset.asset_type
            == asset_type
        )


    def search(
        self,
        keyword: str,
    ) -> tuple[
        ReusableAsset,
        ...
    ]:

        keyword = keyword.lower()

        return tuple(
            asset
            for asset
            in self._assets
            if keyword
            in (
                asset.name
                +
                asset.description
            ).lower()
        )


    def record_reuse(
        self,
        asset_id: str,
    ) -> None:

        asset = self.get(
            asset_id
        )

        if asset:

            asset.reuse_count += 1


    def all_assets(
        self,
    ) -> tuple[
        ReusableAsset,
        ...
    ]:

        return tuple(
            self._assets
        )


    @property
    def count(
        self,
    ) -> int:

        return len(
            self._assets
        )
