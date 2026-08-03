from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from itertools import count

from .message_models import AgentMessage


@dataclass(order=True)
class _QueuedMessage:
    """
    Internal heap entry.

    Higher AgentMessage priority values are dispatched first.
    Sequence preserves FIFO ordering among equal priorities.
    """

    sort_priority: int

    sequence: int

    message: AgentMessage = field(
        compare=False,
    )


class PriorityMessageQueue:
    """
    In-memory priority queue for agent messages.

    Priority range:
        9 = highest
        0 = lowest
    """

    def __init__(self) -> None:
        self._heap: list[
            _QueuedMessage
        ] = []

        self._sequence = count()

    def push(
        self,
        message: AgentMessage,
    ) -> None:
        heapq.heappush(
            self._heap,
            _QueuedMessage(
                sort_priority=(
                    -message.priority
                ),
                sequence=next(
                    self._sequence
                ),
                message=message,
            ),
        )

    def pop(
        self,
    ) -> AgentMessage | None:
        if not self._heap:
            return None

        return heapq.heappop(
            self._heap
        ).message

    def peek(
        self,
    ) -> AgentMessage | None:
        if not self._heap:
            return None

        return self._heap[0].message

    def clear(
        self,
    ) -> None:
        self._heap.clear()

    def messages(
        self,
    ) -> tuple[
        AgentMessage,
        ...
    ]:
        ordered = sorted(
            self._heap
        )

        return tuple(
            entry.message
            for entry in ordered
        )

    def __len__(
        self,
    ) -> int:
        return len(
            self._heap
        )

    def __bool__(
        self,
    ) -> bool:
        return bool(
            self._heap
        )
