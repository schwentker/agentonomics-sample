from dataclasses import dataclass, field

import pytest

from src.graph_utils import build_adjacency, detect_cycles, execution_levels, topological_sort


@dataclass
class SimpleTask:
    id: str
    dependencies: list[str] = field(default_factory=list)


def test_build_adjacency_empty():
    assert build_adjacency([]) == {}


def test_build_adjacency_single_no_deps():
    assert build_adjacency([SimpleTask("task_1")]) == {"task_1": []}


def test_build_adjacency_forward_edge():
    tasks = [SimpleTask("task_1"), SimpleTask("task_2", ["task_1"])]

    assert build_adjacency(tasks) == {"task_1": ["task_2"], "task_2": []}


def test_build_adjacency_missing_reference():
    tasks = [SimpleTask("task_1", ["missing_task"])]

    with pytest.raises(ValueError, match="unknown task ID"):
        build_adjacency(tasks)


def test_build_adjacency_duplicate_task_ids():
    tasks = [SimpleTask("task_1"), SimpleTask("task_1")]

    with pytest.raises(ValueError, match="Duplicate task ID"):
        build_adjacency(tasks)


def test_build_adjacency_deduplicates_deps():
    tasks = [SimpleTask("A"), SimpleTask("B", ["A", "A"])]

    assert build_adjacency(tasks) == {"A": ["B"], "B": []}


def test_detect_cycles_empty():
    assert detect_cycles([]) == []


def test_detect_cycles_single_no_deps():
    assert detect_cycles([SimpleTask("task_1")]) == []


def test_detect_cycles_two_independent():
    tasks = [SimpleTask("task_1"), SimpleTask("task_2")]

    assert detect_cycles(tasks) == []


def test_detect_cycles_self_loop():
    cycles = detect_cycles([SimpleTask("task_1", ["task_1"])])

    assert cycles
    assert "task_1" in cycles[0]


def test_detect_cycles_two_node():
    tasks = [SimpleTask("A", ["B"]), SimpleTask("B", ["A"])]

    cycles = detect_cycles(tasks)

    assert cycles
    assert set(cycles[0]) == {"A", "B"}


def test_detect_cycles_transitive():
    tasks = [
        SimpleTask("A", ["C"]),
        SimpleTask("B", ["A"]),
        SimpleTask("C", ["B"]),
    ]

    cycles = detect_cycles(tasks)

    assert cycles
    assert set(cycles[0]) == {"A", "B", "C"}


def test_detect_cycles_linear_chain():
    tasks = [
        SimpleTask("A"),
        SimpleTask("B", ["A"]),
        SimpleTask("C", ["B"]),
    ]

    assert detect_cycles(tasks) == []


def test_detect_cycles_diamond():
    tasks = [
        SimpleTask("A"),
        SimpleTask("B", ["A"]),
        SimpleTask("C", ["A"]),
        SimpleTask("D", ["B", "C"]),
    ]

    assert detect_cycles(tasks) == []


def test_detect_cycles_disconnected_with_cycle():
    tasks = [
        SimpleTask("A", ["B"]),
        SimpleTask("B", ["A"]),
        SimpleTask("C"),
        SimpleTask("D", ["C"]),
    ]

    cycles = detect_cycles(tasks)

    assert cycles
    assert set(cycles[0]) == {"A", "B"}


def test_disconnected_graph_without_cycle():
    tasks = [
        SimpleTask("A"),
        SimpleTask("B", ["A"]),
        SimpleTask("C"),
        SimpleTask("D", ["C"]),
    ]

    assert detect_cycles(tasks) == []

    order = topological_sort(tasks)

    assert order.index("A") < order.index("B")
    assert order.index("C") < order.index("D")
    assert set(order) == {"A", "B", "C", "D"}


def test_topological_sort_empty():
    assert topological_sort([]) == []


def test_topological_sort_single():
    assert topological_sort([SimpleTask("task_1")]) == ["task_1"]


def test_topological_sort_linear_chain():
    tasks = [
        SimpleTask("A"),
        SimpleTask("B", ["A"]),
        SimpleTask("C", ["B"]),
    ]

    assert topological_sort(tasks) == ["A", "B", "C"]


def test_topological_sort_diamond():
    tasks = [
        SimpleTask("A"),
        SimpleTask("B", ["A"]),
        SimpleTask("C", ["A"]),
        SimpleTask("D", ["B", "C"]),
    ]

    order = topological_sort(tasks)

    assert order.index("A") < order.index("B")
    assert order.index("A") < order.index("C")
    assert order.index("B") < order.index("D")
    assert order.index("C") < order.index("D")


def test_topological_sort_preserves_input_order():
    tasks = [
        SimpleTask("B"),
        SimpleTask("A"),
        SimpleTask("C", ["A"]),
    ]

    assert topological_sort(tasks)[:2] == ["B", "A"]


def test_topological_sort_raises_on_cycle():
    tasks = [SimpleTask("A", ["B"]), SimpleTask("B", ["A"])]

    with pytest.raises(ValueError, match="Cycle detected"):
        topological_sort(tasks)


def test_execution_levels_empty():
    assert execution_levels([]) == []


def test_execution_levels_single():
    assert execution_levels([SimpleTask("task_1")]) == [["task_1"]]


def test_execution_levels_two_independent():
    levels = execution_levels([SimpleTask("task_1"), SimpleTask("task_2")])

    assert len(levels) == 1
    assert sorted(levels[0]) == ["task_1", "task_2"]


def test_execution_levels_linear_chain():
    tasks = [
        SimpleTask("A"),
        SimpleTask("B", ["A"]),
        SimpleTask("C", ["B"]),
    ]

    assert execution_levels(tasks) == [["A"], ["B"], ["C"]]


def test_execution_levels_diamond():
    tasks = [
        SimpleTask("A"),
        SimpleTask("B", ["A"]),
        SimpleTask("C", ["A"]),
        SimpleTask("D", ["B", "C"]),
    ]

    levels = execution_levels(tasks)

    assert levels[0] == ["A"]
    assert sorted(levels[1]) == ["B", "C"]
    assert levels[2] == ["D"]


def test_execution_levels_raises_on_cycle():
    tasks = [SimpleTask("A", ["B"]), SimpleTask("B", ["A"])]

    with pytest.raises(ValueError, match="Cycle detected"):
        execution_levels(tasks)
