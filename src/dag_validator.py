"""DAG validation for task decompositions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .graph_utils import (
    _normalized_dependencies,
    build_adjacency,
    detect_cycles,
    execution_levels,
    topological_sort,
)

DEEP_CHAIN_WARNING_THRESHOLD = 5


@runtime_checkable
class DecompositionValidator(Protocol):
    """Protocol for objects that validate a decomposition via `.validate(...)`."""

    def validate(self, decomposition) -> "DAGValidationResult":
        ...


@dataclass
class DAGValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    topological_order: list[str] = field(default_factory=list)
    execution_levels: list[list[str]] = field(default_factory=list)
    graph_depth: int = 0
    task_count: int = 0
    max_fan_in: int = 0
    max_fan_out: int = 0
    parallelism_width: int = 0

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "topological_order": self.topological_order,
            "execution_levels": self.execution_levels,
            "graph_depth": self.graph_depth,
            "task_count": self.task_count,
            "max_fan_in": self.max_fan_in,
            "max_fan_out": self.max_fan_out,
            "parallelism_width": self.parallelism_width,
        }

class DAGValidator:
    """Validates that a decomposition forms a directed acyclic graph."""

    def validate(self, decomposition) -> DAGValidationResult:
        tasks = decomposition.tasks
        result = DAGValidationResult(valid=True, task_count=len(tasks))

        if not tasks:
            result.valid = False
            result.errors.append("Decomposition is empty: no tasks were generated.")
            return result

        seen_ids: set[str] = set()
        duplicate_ids: list[str] = []
        for task in tasks:
            if task.id in seen_ids and task.id not in duplicate_ids:
                duplicate_ids.append(task.id)
            seen_ids.add(task.id)

        if duplicate_ids:
            result.valid = False
            result.errors.extend(
                f"Duplicate task ID found: {task_id}"
                for task_id in duplicate_ids
            )
            return result

        try:
            adjacency = build_adjacency(tasks)
        except ValueError as exc:
            result.valid = False
            result.errors.append(str(exc))
            return result

        cycles = detect_cycles(tasks)
        if cycles:
            result.valid = False
            for cycle in cycles:
                result.errors.append(
                    f"Cycle detected: {' -> '.join(cycle)}"
                )
            return result

        result.topological_order = topological_sort(tasks)
        result.execution_levels = execution_levels(tasks)
        result.graph_depth = len(result.execution_levels)
        result.max_fan_in = max(len(_normalized_dependencies(task)) for task in tasks)
        result.max_fan_out = max((len(dependents) for dependents in adjacency.values()), default=0)
        result.parallelism_width = max((len(level) for level in result.execution_levels), default=0)

        if len(tasks) > 1:
            isolated_tasks = [
                task.id
                for task in tasks
                if not _normalized_dependencies(task) and not adjacency[task.id]
            ]
            for task_id in isolated_tasks:
                result.warnings.append(
                    f"Isolated task '{task_id}' has no dependencies and no dependents"
                )

        if result.graph_depth > DEEP_CHAIN_WARNING_THRESHOLD:
            result.warnings.append(
                "Dependency graph is deep "
                f"({result.graph_depth} levels > {DEEP_CHAIN_WARNING_THRESHOLD})"
            )

        return result
