from __future__ import annotations

from pydantic import BaseModel, Field

from .knowledge_models import (
    KnowledgeRecord,
    KnowledgeQuery,
)

from .knowledge_registry import (
    KnowledgeRegistryEngine,
)

from .pattern_library import (
    PatternLibraryEngine,
    PatternRecord,
)

from .reuse_catalog import (
    ReuseCatalogEngine,
    ReusableAsset,
)


class SelectionRequest(BaseModel):

    keyword: str

    knowledge_type: str | None = None

    limit: int = 10



class KnowledgeSelection(BaseModel):

    knowledge: tuple[
        KnowledgeRecord,
        ...
    ] = ()

    patterns: tuple[
        PatternRecord,
        ...
    ] = ()

    assets: tuple[
        ReusableAsset,
        ...
    ] = ()



class KnowledgeSelectorEngine:
    """
    Selects the most relevant
    knowledge assets for planning.
    """


    def __init__(
        self,
        registry:
            KnowledgeRegistryEngine,
        pattern_library:
            PatternLibraryEngine,
        reuse_catalog:
            ReuseCatalogEngine,
    ) -> None:

        self._registry = registry

        self._patterns = pattern_library

        self._catalog = reuse_catalog



    def select(
        self,
        request: SelectionRequest,
    ) -> KnowledgeSelection:


        knowledge = (
            self._registry.search(
                KnowledgeQuery(
                    keyword=request.keyword,
                    knowledge_type=
                    request.knowledge_type,
                    limit=request.limit,
                )
            )
        )


        patterns = (
            self._patterns.find_by_category(
                request.keyword
            )
        )


        assets = (
            self._catalog.search(
                request.keyword
            )
        )


        return KnowledgeSelection(
            knowledge=knowledge,
            patterns=patterns,
            assets=assets,
        )
