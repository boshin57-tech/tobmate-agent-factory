from __future__ import annotations

from collections import Counter, deque

from .task_coordination_models import (
    CoordinatedTask,
)
from .task_dependency_models import (
    GraphValidationResult,
    TaskDependencyGraph,
    TaskDependencyNode,
)


class TaskDependencyGraphEngine:
    """
    Builds and validates directed acyclic task graphs.
    """

    def validate(
        self,
        tasks: list[
            CoordinatedTask
        ],
    ) -> GraphValidationResult:
        task_ids = [
            task.task_id
            for task in tasks
        ]

        counts = Counter(task_ids)

        duplicate_ids = sorted(
            task_id
            for task_id, count
            in counts.items()
            if count > 1
        )

        known_ids = set(task_ids)

        unknown_dependencies: dict[
            str,
            list[str],
        ] = {}

        self_dependencies: list[str] = []

        for task in tasks:
            unknown = sorted(
                task.dependencies
                - known_ids
            )

            if unknown:
                unknown_dependencies[
                    task.task_id
                ] = unknown

            if task.task_id in task.dependencies:
                self_dependencies.append(
                    task.task_id
                )

        cycle_ids: list[str] = []

        if (
            not duplicate_ids
            and not unknown_dependencies
            and not self_dependencies
        ):
            cycle_ids = self._detect_cycle_ids(
                tasks
            )

        reasons: list[str] = []

        if duplicate_ids:
            reasons.append(
                "workflow contains duplicate task IDs"
            )

        if unknown_dependencies:
            reasons.append(
                "workflow contains unknown dependencies"
            )

        if self_dependencies:
            reasons.append(
                "workflow contains self dependencies"
            )

        if cycle_ids:
            reasons.append(
                "workflow dependency graph contains a cycle"
            )

        return GraphValidationResult(
            valid=not reasons,
            unknown_dependencies=(
                unknown_dependencies
            ),
            self_dependencies=sorted(
                self_dependencies
            ),
            duplicate_task_ids=(
                duplicate_ids
            ),
            cycle_task_ids=(
                cycle_ids
            ),
            reasons=reasons,
        )

    def build(
        self,
        *,
        workflow_id: str,
        tasks: list[
            CoordinatedTask
        ],
    ) -> TaskDependencyGraph:
        validation = self.validate(
            tasks
        )

        if not validation.valid:
            raise ValueError(
                "; ".join(
                    validation.reasons
                )
            )

        nodes = {
            task.task_id:
                TaskDependencyNode(
                    task_id=task.task_id,
                    dependencies=set(
                        task.dependencies
                    ),
                    estimated_duration_minutes=(
                        task
                        .estimated_duration_minutes
                    ),
                    priority=task.priority,
                )
            for task in tasks
        }

        for task in tasks:
            for dependency_id in (
                task.dependencies
            ):
                dependency_node = nodes[
                    dependency_id
                ]

                nodes[dependency_id] = (
                    dependency_node.model_copy(
                        update={
                            "dependents": {
                                *dependency_node
                                .dependents,
                                task.task_id,
                            }
                        }
                    )
                )

        topological_order = (
            self._topological_order(
                nodes
            )
        )

        nodes = self._apply_depths(
            nodes=nodes,
            topological_order=(
                topological_order
            ),
        )

        waves = self._execution_waves(
            nodes
        )

        critical_path, duration = (
            self._critical_path(
                nodes=nodes,
                topological_order=(
                    topological_order
                ),
            )
        )

        return TaskDependencyGraph(
            workflow_id=workflow_id,
            nodes=nodes,
            topological_order=(
                topological_order
            ),
            execution_waves=waves,
            critical_path=critical_path,
            critical_path_duration_minutes=(
                duration
            ),
            has_cycle=False,
        )

    @staticmethod
    def _topological_order(
        nodes: dict[
            str,
            TaskDependencyNode,
        ],
    ) -> list[str]:
        indegree = {
            task_id:
                len(node.dependencies)
            for task_id, node
            in nodes.items()
        }

        ready = deque(
            sorted(
                task_id
                for task_id, degree
                in indegree.items()
                if degree == 0
            )
        )

        ordered: list[str] = []

        while ready:
            task_id = ready.popleft()

            ordered.append(
                task_id
            )

            for dependent_id in sorted(
                nodes[task_id].dependents
            ):
                indegree[
                    dependent_id
                ] -= 1

                if (
                    indegree[
                        dependent_id
                    ]
                    == 0
                ):
                    ready.append(
                        dependent_id
                    )

        if len(ordered) != len(nodes):
            raise ValueError(
                "workflow dependency graph contains a cycle"
            )

        return ordered

    @staticmethod
    def _detect_cycle_ids(
        tasks: list[
            CoordinatedTask
        ],
    ) -> list[str]:
        nodes = {
            task.task_id:
                set(task.dependencies)
            for task in tasks
        }

        visiting: set[str] = set()
        visited: set[str] = set()
        cycle_nodes: set[str] = set()

        def visit(
            task_id: str,
            path: list[str],
        ) -> None:
            if task_id in visited:
                return

            if task_id in visiting:
                if task_id in path:
                    start = path.index(
                        task_id
                    )

                    cycle_nodes.update(
                        path[start:]
                    )

                cycle_nodes.add(
                    task_id
                )

                return

            visiting.add(
                task_id
            )

            path.append(
                task_id
            )

            for dependency_id in sorted(
                nodes.get(
                    task_id,
                    set(),
                )
            ):
                visit(
                    dependency_id,
                    path,
                )

            path.pop()

            visiting.discard(
                task_id
            )

            visited.add(
                task_id
            )

        for task_id in sorted(nodes):
            if task_id not in visited:
                visit(
                    task_id,
                    [],
                )

        return sorted(
            cycle_nodes
        )

    @staticmethod
    def _apply_depths(
        *,
        nodes: dict[
            str,
            TaskDependencyNode,
        ],
        topological_order: list[str],
    ) -> dict[
        str,
        TaskDependencyNode,
    ]:
        updated = dict(
            nodes
        )

        for task_id in topological_order:
            node = updated[
                task_id
            ]

            if not node.dependencies:
                depth = 0
            else:
                depth = (
                    max(
                        updated[
                            dependency_id
                        ].depth
                        for dependency_id
                        in node.dependencies
                    )
                    + 1
                )

            updated[
                task_id
            ] = node.model_copy(
                update={
                    "depth":
                        depth,
                }
            )

        return updated

    @staticmethod
    def _execution_waves(
        nodes: dict[
            str,
            TaskDependencyNode,
        ],
    ) -> list[
        list[str]
    ]:
        if not nodes:
            return []

        maximum_depth = max(
            node.depth
            for node in nodes.values()
        )

        waves: list[
            list[str]
        ] = []

        for depth in range(
            maximum_depth + 1
        ):
            wave = sorted(
                (
                    node.task_id
                    for node
                    in nodes.values()
                    if node.depth == depth
                ),
                key=lambda task_id: (
                    -nodes[
                        task_id
                    ].priority.rank,
                    task_id,
                ),
            )

            if wave:
                waves.append(
                    wave
                )

        return waves

    @staticmethod
    def _critical_path(
        *,
        nodes: dict[
            str,
            TaskDependencyNode,
        ],
        topological_order: list[str],
    ) -> tuple[
        list[str],
        int,
    ]:
        if not nodes:
            return [], 0

        duration_to: dict[
            str,
            int,
        ] = {}

        predecessor: dict[
            str,
            str | None,
        ] = {}

        for task_id in topological_order:
            node = nodes[
                task_id
            ]

            own_duration = (
                node
                .estimated_duration_minutes
            )

            if not node.dependencies:
                duration_to[
                    task_id
                ] = own_duration

                predecessor[
                    task_id
                ] = None

                continue

            best_dependency = max(
                sorted(
                    node.dependencies
                ),
                key=lambda dependency_id: (
                    duration_to[
                        dependency_id
                    ],
                    dependency_id,
                ),
            )

            duration_to[
                task_id
            ] = (
                duration_to[
                    best_dependency
                ]
                + own_duration
            )

            predecessor[
                task_id
            ] = best_dependency

        terminal_task_id = max(
            sorted(
                topological_order
            ),
            key=lambda task_id: (
                duration_to[
                    task_id
                ],
                task_id,
            ),
        )

        path: list[str] = []

        current: str | None = (
            terminal_task_id
        )

        while current is not None:
            path.append(
                current
            )

            current = predecessor[
                current
            ]

        path.reverse()

        return (
            path,
            duration_to[
                terminal_task_id
            ],
        )
