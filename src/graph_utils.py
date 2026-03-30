"""Pure graph algorithms for task dependency analysis."""
from __future__ import annotations

from collections import deque


def _task_ids(tasks: list) -> list[str]:
    return [task.id for task in tasks]


def _normalized_dependencies(task) -> list[str]:
    """Deduplicate repeated dependencies while preserving original order."""
    seen: set[str] = set()
    normalized: list[str] = []

    for dependency in task.dependencies:
        if dependency in seen:
            continue
        seen.add(dependency)
        normalized.append(dependency)

    return normalized


def build_adjacency(tasks: list) -> dict[str, list[str]]:
    """
    Build an adjacency list from a list of SubTask-like objects.

    Returns a mapping of task_id -> list of dependent task IDs, preserving the
    original task list order for deterministic output.
    """
    task_ids: list[str] = []
    seen_ids: set[str] = set()

    for task in tasks:
        if task.id in seen_ids:
            raise ValueError(f"Duplicate task ID found: {task.id}")
        seen_ids.add(task.id)
        task_ids.append(task.id)

    adjacency = {task_id: [] for task_id in task_ids}

    for task in tasks:
        for dependency in _normalized_dependencies(task):
            if dependency not in adjacency:
                raise ValueError(
                    f"Task '{task.id}' depends on unknown task ID '{dependency}'"
                )
            adjacency[dependency].append(task.id)

    return adjacency


def detect_cycles(tasks: list) -> list[list[str]]:
    """
    Detect cycles in the dependency graph using iterative DFS with coloring.

    This traversal walks reverse edges (task -> its dependencies), while
    build_adjacency() builds forward edges (dependency -> dependents). Cycle
    detection is correct in either direction because a graph has a cycle iff its
    edge-reversed graph has a cycle.

    Returns representative cycle paths. Paths do not repeat the start node at
    the end, and duplicate cycle reporting is not guaranteed to be eliminated.
    """
    task_ids = _task_ids(tasks)
    if not task_ids:
        return []

    index_by_id = {task.id: index for index, task in enumerate(tasks)}
    dependency_map = {
        task.id: [dep for dep in _normalized_dependencies(task) if dep in index_by_id]
        for task in tasks
    }

    colors = {task_id: 0 for task_id in task_ids}
    cycles: list[list[str]] = []

    for root_id in task_ids:
        if colors[root_id] != 0:
            continue

        stack: list[tuple[str, int]] = [(root_id, 0)]
        path: list[str] = []
        path_index: dict[str, int] = {}

        while stack:
            current_id, next_neighbor_index = stack[-1]

            if colors[current_id] == 0:
                colors[current_id] = 1
                path_index[current_id] = len(path)
                path.append(current_id)

            neighbors = dependency_map[current_id]
            if next_neighbor_index < len(neighbors):
                neighbor_id = neighbors[next_neighbor_index]
                stack[-1] = (current_id, next_neighbor_index + 1)

                neighbor_color = colors.get(neighbor_id, 0)
                if neighbor_color == 0:
                    stack.append((neighbor_id, 0))
                elif neighbor_color == 1 and neighbor_id in path_index:
                    cycle_start = path_index[neighbor_id]
                    cycles.append(path[cycle_start:].copy())
                continue

            stack.pop()
            colors[current_id] = 2
            if path and path[-1] == current_id:
                path.pop()
            path_index.pop(current_id, None)

    return cycles


def topological_sort(tasks: list) -> list[str]:
    """
    Return task IDs in topological order, preserving original task order for
    zero in-degree tie-breaking.
    """
    if not tasks:
        return []

    adjacency = build_adjacency(tasks)
    in_degree = {task.id: 0 for task in tasks}

    for task in tasks:
        for dependency in _normalized_dependencies(task):
            in_degree[task.id] += 1

    queue = deque(
        task.id
        for task in tasks
        if in_degree[task.id] == 0
    )
    ordered: list[str] = []

    while queue:
        task_id = queue.popleft()
        ordered.append(task_id)

        for dependent_id in adjacency[task_id]:
            in_degree[dependent_id] -= 1
            if in_degree[dependent_id] == 0:
                queue.append(dependent_id)

    if len(ordered) != len(tasks):
        raise ValueError("Cycle detected in task dependency graph")

    return ordered


def execution_levels(tasks: list) -> list[list[str]]:
    """
    Group tasks into parallel execution levels while preserving original task
    order within each level.
    """
    if not tasks:
        return []

    adjacency = build_adjacency(tasks)
    in_degree = {task.id: 0 for task in tasks}
    order_map = {task.id: index for index, task in enumerate(tasks)}

    for task in tasks:
        for dependency in _normalized_dependencies(task):
            in_degree[task.id] += 1

    current_level = [
        task.id
        for task in tasks
        if in_degree[task.id] == 0
    ]
    levels: list[list[str]] = []
    visited_count = 0

    while current_level:
        level = sorted(current_level, key=order_map.__getitem__)
        levels.append(level)
        visited_count += len(level)

        next_level: list[str] = []
        for task_id in level:
            for dependent_id in adjacency[task_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    next_level.append(dependent_id)
        current_level = next_level

    if visited_count != len(tasks):
        raise ValueError("Cycle detected in task dependency graph")

    return levels
