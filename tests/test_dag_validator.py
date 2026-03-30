from dataclasses import dataclass, field

from src.dag_validator import DAGValidationResult, DAGValidator


@dataclass
class SimpleTask:
    id: str
    dependencies: list[str] = field(default_factory=list)


@dataclass
class SimpleDecomposition:
    tasks: list[SimpleTask]


def test_valid_linear_chain():
    decomposition = SimpleDecomposition(
        tasks=[
            SimpleTask("A"),
            SimpleTask("B", ["A"]),
            SimpleTask("C", ["B"]),
        ]
    )

    result = DAGValidator().validate(decomposition)

    assert result.valid is True
    assert result.errors == []
    assert result.topological_order == ["A", "B", "C"]


def test_valid_diamond():
    decomposition = SimpleDecomposition(
        tasks=[
            SimpleTask("A"),
            SimpleTask("B", ["A"]),
            SimpleTask("C", ["A"]),
            SimpleTask("D", ["B", "C"]),
        ]
    )

    result = DAGValidator().validate(decomposition)

    assert result.valid is True
    assert result.parallelism_width >= 2


def test_empty_decomposition():
    result = DAGValidator().validate(SimpleDecomposition(tasks=[]))

    assert result.valid is False
    assert any("empty" in error.lower() or "no tasks" in error.lower() for error in result.errors)


def test_duplicate_task_ids():
    decomposition = SimpleDecomposition(
        tasks=[SimpleTask("A"), SimpleTask("A")]
    )

    result = DAGValidator().validate(decomposition)

    assert result.valid is False
    assert any("duplicate" in error.lower() for error in result.errors)


def test_dangling_reference():
    decomposition = SimpleDecomposition(
        tasks=[SimpleTask("A", ["missing"])]
    )

    result = DAGValidator().validate(decomposition)

    assert result.valid is False
    assert any("unknown task id" in error.lower() for error in result.errors)


def test_cycle_detected():
    decomposition = SimpleDecomposition(
        tasks=[SimpleTask("A", ["B"]), SimpleTask("B", ["A"])]
    )

    result = DAGValidator().validate(decomposition)

    assert result.valid is False
    assert any("cycle" in error.lower() for error in result.errors)


def test_isolated_task_warning_multi():
    decomposition = SimpleDecomposition(
        tasks=[
            SimpleTask("A"),
            SimpleTask("B", ["A"]),
            SimpleTask("C"),
        ]
    )

    result = DAGValidator().validate(decomposition)

    assert result.valid is True
    assert any("isolated" in warning.lower() for warning in result.warnings)


def test_single_task_no_warning():
    result = DAGValidator().validate(SimpleDecomposition(tasks=[SimpleTask("A")]))

    assert result.valid is True
    assert result.warnings == []


def test_deep_chain_warning():
    decomposition = SimpleDecomposition(
        tasks=[
            SimpleTask("A"),
            SimpleTask("B", ["A"]),
            SimpleTask("C", ["B"]),
            SimpleTask("D", ["C"]),
            SimpleTask("E", ["D"]),
            SimpleTask("F", ["E"]),
        ]
    )

    result = DAGValidator().validate(decomposition)

    assert result.valid is True
    assert any("deep" in warning.lower() or "levels" in warning.lower() for warning in result.warnings)


def test_graph_metrics_populated():
    decomposition = SimpleDecomposition(
        tasks=[
            SimpleTask("A"),
            SimpleTask("B", ["A"]),
            SimpleTask("C", ["A"]),
            SimpleTask("D", ["B", "C"]),
        ]
    )

    result = DAGValidator().validate(decomposition)

    assert result.valid is True
    assert result.max_fan_in > 0
    assert result.max_fan_out > 0
    assert result.parallelism_width > 0
    assert result.graph_depth == 3
    assert result.task_count == 4


def test_dag_validation_result_to_dict():
    result = DAGValidationResult(
        valid=True,
        errors=[],
        warnings=["warning"],
        topological_order=["A", "B"],
        execution_levels=[["A"], ["B"]],
        graph_depth=2,
        task_count=2,
        max_fan_in=1,
        max_fan_out=1,
        parallelism_width=1,
    )

    data = result.to_dict()

    assert isinstance(data, dict)
    assert set(data) == {
        "valid",
        "errors",
        "warnings",
        "topological_order",
        "execution_levels",
        "graph_depth",
        "task_count",
        "max_fan_in",
        "max_fan_out",
        "parallelism_width",
    }
