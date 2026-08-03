from __future__ import annotations


class TopicRouter:
    """
    Matches concrete message topics against subscription patterns.

    Supported wildcard syntax:

    *   matches exactly one topic segment
    **  matches zero or more topic segments

    Examples:

    task.requested
        matches only task.requested

    task.*
        matches task.requested
        matches task.completed
        does not match task.lifecycle.completed

    task.**
        matches task
        matches task.requested
        matches task.lifecycle.completed

    **
        matches every valid topic
    """

    SINGLE_WILDCARD = "*"
    MULTI_WILDCARD = "**"

    def validate_topic(
        self,
        topic: str,
    ) -> str:
        normalized = topic.strip()

        if not normalized:
            raise ValueError(
                "topic must not be empty"
            )

        segments = normalized.split(".")

        if any(
            not segment
            for segment in segments
        ):
            raise ValueError(
                "topic contains an empty segment"
            )

        if any(
            segment in {
                self.SINGLE_WILDCARD,
                self.MULTI_WILDCARD,
            }
            for segment in segments
        ):
            raise ValueError(
                "concrete topic must not contain wildcards"
            )

        return normalized

    def validate_pattern(
        self,
        pattern: str,
    ) -> str:
        normalized = pattern.strip()

        if not normalized:
            raise ValueError(
                "topic pattern must not be empty"
            )

        segments = normalized.split(".")

        if any(
            not segment
            for segment in segments
        ):
            raise ValueError(
                "topic pattern contains an empty segment"
            )

        for segment in segments:
            if (
                "*" in segment
                and segment not in {
                    self.SINGLE_WILDCARD,
                    self.MULTI_WILDCARD,
                }
            ):
                raise ValueError(
                    "wildcards must occupy a complete topic segment"
                )

        return normalized

    def matches(
        self,
        pattern: str,
        topic: str,
    ) -> bool:
        normalized_pattern = (
            self.validate_pattern(
                pattern
            )
        )

        normalized_topic = (
            self.validate_topic(
                topic
            )
        )

        pattern_segments = (
            normalized_pattern.split(".")
        )

        topic_segments = (
            normalized_topic.split(".")
        )

        return self._match_segments(
            pattern_segments,
            topic_segments,
            pattern_index=0,
            topic_index=0,
        )

    def _match_segments(
        self,
        pattern_segments: list[str],
        topic_segments: list[str],
        *,
        pattern_index: int,
        topic_index: int,
    ) -> bool:
        while (
            pattern_index
            < len(pattern_segments)
        ):
            pattern_segment = (
                pattern_segments[
                    pattern_index
                ]
            )

            if (
                pattern_segment
                == self.MULTI_WILDCARD
            ):
                if (
                    pattern_index
                    == len(pattern_segments) - 1
                ):
                    return True

                next_pattern_index = (
                    pattern_index + 1
                )

                for candidate_topic_index in range(
                    topic_index,
                    len(topic_segments) + 1,
                ):
                    if self._match_segments(
                        pattern_segments,
                        topic_segments,
                        pattern_index=(
                            next_pattern_index
                        ),
                        topic_index=(
                            candidate_topic_index
                        ),
                    ):
                        return True

                return False

            if (
                topic_index
                >= len(topic_segments)
            ):
                return False

            if (
                pattern_segment
                != self.SINGLE_WILDCARD
                and pattern_segment
                != topic_segments[
                    topic_index
                ]
            ):
                return False

            pattern_index += 1
            topic_index += 1

        return (
            topic_index
            == len(topic_segments)
        )
