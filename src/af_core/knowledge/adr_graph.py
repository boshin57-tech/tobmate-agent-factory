from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from .adr_models import (
    ADRRecord,
)


class ADREdgeType:

    DEPENDS_ON = "depends_on"

    DERIVED_FROM = "derived_from"

    SUPERSEDES = "supersedes"

    IMPACTS = "impacts"

    IMPLEMENTS = "implements"



class ADREdge(BaseModel):

    edge_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    source_id: str

    target_id: str

    relation: str



class ADRKnowledgeGraphEngine:
    """
    Graph engine for architecture
    decision relationships.
    """


    def __init__(self) -> None:

        self._nodes: dict[
            str,
            ADRRecord
        ] = {}

        self._edges: list[
            ADREdge
        ] = []


    def add_adr(
        self,
        adr: ADRRecord,
    ) -> ADRRecord:

        self._nodes[
            adr.adr_id
        ] = adr

        return adr



    def connect(
        self,
        source_id: str,
        target_id: str,
        relation: str,
    ) -> ADREdge:

        edge = ADREdge(
            source_id=source_id,
            target_id=target_id,
            relation=relation,
        )

        self._edges.append(
            edge
        )

        return edge



    def get(
        self,
        adr_id: str,
    ) -> ADRRecord | None:

        return self._nodes.get(
            adr_id
        )



    def related(
        self,
        adr_id: str,
        relation: str | None = None,
    ) -> tuple[
        ADRRecord,
        ...
    ]:

        results = []


        for edge in self._edges:

            if (
                edge.source_id
                != adr_id
            ):
                continue


            if (
                relation
                is not None
                and edge.relation
                != relation
            ):
                continue


            target = self.get(
                edge.target_id
            )

            if target:

                results.append(
                    target
                )


        return tuple(
            results
        )



    def edges(
        self,
    ) -> tuple[
        ADREdge,
        ...
    ]:

        return tuple(
            self._edges
        )



    def nodes(
        self,
    ) -> tuple[
        ADRRecord,
        ...
    ]:

        return tuple(
            self._nodes.values()
        )



    @property
    def node_count(
        self,
    ) -> int:

        return len(
            self._nodes
        )


    @property
    def edge_count(
        self,
    ) -> int:

        return len(
            self._edges
        )
