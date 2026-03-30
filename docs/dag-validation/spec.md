# Codex Implementation Spec: DAG Validation for Multi-Agent Task Decomposition

## Context & Purpose

This is the `agentonomics-sample` repository — a benchmarking system that compares
single-agent vs multi-agent architectures for completing structured goals using the
Strands Agents framework (Anthropic). It runs the same goal through two execution
patterns and produces detailed performance reports comparing cost, token usage,
execution time, and output quality.

This spec adds **optional DAG validation** to the multi-agent execution path. When
enabled via a CLI flag, it detects cycles and structural errors in the LLM-generated
task decomposition **before orchestrator and sub-agent execution** (the decomposition
step itself is already an LLM call — this validation runs after that, but before the
expensive multi-agent orchestration begins).

---

## Repo Structure (Current)

```
agentonomics-sample/
├── benchmark.py                     # CLI entry point (~780 lines)
├── mcp.json                         # MCP filesystem server config
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── config.py                    # BenchmarkConfig dataclass, MODEL_SPECS, cost calc
│   ├── conversation_logger.py
│   ├── mcp_manager.py
│   ├── metrics_tracker.py           # MetricsTracker, MultiAgentMetricsTracker
│   ├── multi_agent.py               # SubAgentExecutor, MultiAgentExecutor  ← MODIFY
│   ├── prompt_loader.py
│   ├── report_generator.py
│   ├── requirements.py
│   ├── rubric_evaluator.py
│   ├── sandbox_tools.py
│   ├── single_agent.py              # SingleAgentExecutor (DO NOT TOUCH)
│   ├── task_decomposer.py           # TaskDecomposer, TaskDecomposition, SubTask
│   ├── tracked_conversation_manager.py
│   └── validator.py                 # OutputValidator, ValidationResult (reference pattern)
└── examples/
    └── goals/
        └── coding/
            ├── simple_goal.md
            └── complex_goal.md
```

**No test directory currently exists. This PR creates it.**

---

## Key Existing Code (Exact Signatures)

### `src/task_decomposer.py`

```python
class SubTask(BaseModel):
    id: str
    name: str
    description: str
    tools_required: list[str]
    dependencies: list[str] = Field(default_factory=list)
    rationale: str

    @field_validator('dependencies', mode='before')
    @classmethod
    def ensure_list(cls, v): ...  # coerces None -> []

class TaskDecomposition(BaseModel):
    original_goal: str
    decomposition_approach: str
    separation_rationale: str
    tasks: list[SubTask]

class TaskDecomposer:
    def __init__(self, api_key: str, model_id: str, max_tokens: int): ...
    def decompose(self, goal: str, tool_descriptions: str) -> TaskDecomposition: ...
    def save_decomposition(self, decomposition: TaskDecomposition, output_path: str): ...
```

### `src/multi_agent.py`

```python
class SubAgentExecutor:
    def __init__(self, task: SubTask, api_key: str, model_id: str,
                 output_dir: Path, mcp_manager: MCPManager, workspace_dir: Path,
                 max_tokens: int = 16384, model_params: dict | None = None): ...
    def execute(self, context: str = "") -> dict[str, Any]: ...

class MultiAgentExecutor:
    def __init__(self, config: BenchmarkConfig, api_key: str, mcp_manager: MCPManager): ...
    def execute(self, goal: str) -> dict[str, Any]: ...
    def get_metrics(self) -> dict[str, Any]: ...
    def get_sub_agent_metrics(self) -> list[dict[str, Any]]: ...
    def get_decomposition_report(self) -> str: ...
```

Key lines in `MultiAgentExecutor.execute()`:
```python
# line ~329 — decomposition happens here (LLM call), BEFORE orchestrator runs
self.decomposition = self.decomposer.decompose(goal, tool_instructions)

# line ~333 — decomposition saved here
self.decomposer.save_decomposition(self.decomposition, str(decomp_file))

# >>> DAG VALIDATION INSERTS HERE <<<

# line ~336 — orchestrator prompt built here
orchestrator_prompt = self._create_orchestrator_prompt(...)
```

### `src/config.py`

```python
@dataclass
class BenchmarkConfig:
    goal_file: Path
    mcp_config_file: Path
    output_dir: Path
    model_id: str = DEFAULT_MODEL
    max_tokens: int = 16384
    temperature: float = 1.0
    top_p: float | None = None
    top_k: int | None = None
    workspace_dir: Path | None = None
    # NO validate_dag field — do not add one
```

### `benchmark.py` (CLI)

The `main()` function builds `BenchmarkConfig` then calls `run_benchmark()`.
The `run_benchmark()` function creates `MultiAgentExecutor(config, api_key, multi_mcp_manager)`.

Existing argparse flags for reference:
- `--goal / -g`
- `--mcp-config / -m`
- `--output / -o`
- `--model`
- `--skip-validation`
- `--temperature`
- `--top-p`
- `--top-k`
- `--max-tokens`
- `--quiet / -q`
- `--yes / -y`

### `src/validator.py` (reference pattern for result objects)

```python
@dataclass
class ValidationResult:
    workspace: str
    files_expected: list[str]
    files_validated: list[FileValidation]
    files_found: int = 0
    files_missing: int = 0
    syntax_errors: int = 0
    test_validation: TestValidation | None = None
    overall_success: bool = False
```

---

## What to Build

### 3 new files, 2 modified files, 0 existing behavior changed by default.

---

### FILE 1 (NEW): `src/graph_utils.py`

Pure functions. No imports from within the project. No I/O. No LLM calls.

```python
"""Pure graph algorithms for task dependency analysis."""
from __future__ import annotations
from collections import deque
```

#### Function: `build_adjacency(tasks)`

```python
def build_adjacency(tasks: list) -> dict[str, list[str]]:
    """
    Build an adjacency list from a list of SubTask-like objects.

    Each task must have:
        - .id: str
        - .dependencies: list[str]

    Returns a dict mapping task_id -> list of task_ids that depend on it
    (i.e., forward edges: if task_2 depends on task_1, then adj[task_1] = [..., task_2]).

    Implementation notes:
    - Raises ValueError if duplicate task IDs are found in the task list.
    - Raises ValueError if a dependency references a task_id not present in the task list.
    - Silently deduplicates repeated entries within a single task's dependency list.
      (e.g., dependencies=["A", "A"] is treated as dependencies=["A"])
    - Preserves insertion order from the original task list for deterministic output.
    """
```

#### Function: `detect_cycles(tasks)`

```python
def detect_cycles(tasks: list) -> list[list[str]]:
    """
    Detect cycles in task dependency graph using iterative DFS with coloring.

    Colors: 0 = unvisited, 1 = in-stack, 2 = done

    Returns a list of cycles found. Each cycle is a list of task IDs
    representing one cycle path (representative — not guaranteed deduplicated,
    start node NOT repeated at the end). Returns empty list if no cycles exist.

    Does NOT raise — callers decide what to do with the result.

    Iterates tasks in original list order for deterministic behavior.
    """
```

#### Function: `topological_sort(tasks)`

```python
def topological_sort(tasks: list) -> list[str]:
    """
    Return task IDs in topological order (dependencies before dependents).

    Uses Kahn's algorithm (BFS-based) for deterministic, readable output.
    Tie-breaking rule: when multiple tasks have zero in-degree, process them
    in the order they appear in the original tasks list (preserves decomposer
    output ordering).

    Raises ValueError if cycles are detected (call detect_cycles first
    if you want the cycle details before raising).

    Returns list of task IDs in valid execution order.
    """
```

#### Function: `execution_levels(tasks)`

```python
def execution_levels(tasks: list) -> list[list[str]]:
    """
    Group tasks into parallel execution levels.

    Level 0: tasks with no dependencies.
    Level N: tasks whose dependencies all appear in levels 0..N-1.

    Tasks within the same level have no dependencies on each other
    and could theoretically run in parallel.

    Tasks within each level are ordered by their position in the original
    tasks list (preserves decomposer output ordering for deterministic results).

    Returns list of lists, each inner list is a set of task IDs
    that can run concurrently.

    Raises ValueError if cycles are detected.
    """
```

**Implementation notes:**
- All four functions accept any list of objects with `.id` and `.dependencies` attributes
  (duck typing — they work on `SubTask` Pydantic models or plain dataclasses or mocks)
- Keep `_normalized_dependencies()` defined only in `graph_utils.py`; do not duplicate
  it in `dag_validator.py`
- `detect_cycles` must handle: empty graph, self-loop (`task_1` depends on `task_1`),
  two-node cycle (`A→B→A`), transitive cycle (`A→B→C→A`), disconnected subgraphs
- Add a clarifying comment in `detect_cycles()` that it walks reverse edges
  (task → dependency) while `build_adjacency()` walks forward edges
  (dependency → dependent), and that cycle existence is invariant under edge reversal
- `topological_sort` must handle disconnected subgraphs (tasks with no dependencies
  on anything else still appear in output)
- `build_adjacency` must detect and raise on duplicate task IDs
- `build_adjacency` must silently deduplicate repeated dependencies within a single task
- No external dependencies beyond Python stdlib

---

### FILE 2 (NEW): `src/dag_validator.py`

Thin wrapper that applies graph_utils to a `TaskDecomposition` and returns a
structured result. This is the public API the rest of the codebase uses.

```python
"""DAG validation for task decompositions."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .graph_utils import detect_cycles, topological_sort, execution_levels, build_adjacency
```

#### Protocol: `DecompositionValidator`

```python
@runtime_checkable
class DecompositionValidator(Protocol):
    """Protocol for decomposition validators. Any object with a matching .validate() method."""
    def validate(self, decomposition) -> "DAGValidationResult":
        ...
```

#### Dataclass: `DAGValidationResult`

```python
@dataclass
class DAGValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    topological_order: list[str] = field(default_factory=list)
    execution_levels: list[list[str]] = field(default_factory=list)
    graph_depth: int = 0
    task_count: int = 0
    max_fan_in: int = 0     # max number of dependencies any single task has
    max_fan_out: int = 0    # max number of tasks that depend on any single task
    parallelism_width: int = 0  # max number of tasks in any single execution level

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
```

#### Constants

```python
DEEP_CHAIN_WARNING_THRESHOLD = 5
```

#### Class: `DAGValidator`

```python
class DAGValidator:
    """Validates that a TaskDecomposition forms a valid directed acyclic graph."""

    def validate(self, decomposition) -> DAGValidationResult:
        """
        Validate the decomposition's dependency graph.

        The decomposition object must have a .tasks attribute that is a list of
        objects with .id (str) and .dependencies (list[str]) attributes.

        Checks performed (in order):
        1. Non-empty: decomposition must contain at least one task.
           (Zero tasks = error: decomposition failed semantically.)
        2. Duplicate task IDs: all task IDs must be unique.
           (Duplicate = error: graph algorithms key by ID.)
        3. Dangling references: all dependency references must point to
           existing task IDs. (Missing reference = error.)
        4. Cycles: the dependency graph must be acyclic. (Cycle = error.)
        5. (Warning only) Isolated tasks: tasks with no dependencies AND
           no dependents — only warn when task_count > 1. A single-task
           decomposition is isolated by definition and should not warn.
        6. (Warning only) Deep chains: dependency chains longer than
           DEEP_CHAIN_WARNING_THRESHOLD levels.

        On any error (checks 1-4), valid=False. Warnings (checks 5-6) do not
        cause valid=False.

        Populates topological_order, execution_levels, graph metrics (depth,
        fan_in, fan_out, parallelism_width) only when valid=True.
        """
```

**Implementation notes:**
- `max_fan_in` = max `len(task.dependencies)` across all tasks. Must be computed from
  the normalized (deduplicated) dependency lists returned by `build_adjacency`, NOT from
  raw `task.dependencies` on the model objects. This ensures duplicate deps don't inflate
  the metric.
- `max_fan_out` = max number of forward edges from any single task (from adjacency list)
- `parallelism_width` = `max(len(level) for level in execution_levels)`
- `graph_depth` = `len(execution_levels)` when valid, 0 when invalid
- `DAGValidator` must satisfy the `DecompositionValidator` protocol
- Errors cause `valid=False`. Warnings do not.
- Short-circuit: if check 1 or 2 fails, skip later checks (graph is meaningless).
  If check 3 fails, skip cycle detection (adjacency is broken).

---

### FILE 3 (NEW): `tests/test_graph_utils.py` and `tests/test_dag_validator.py`

Create `tests/__init__.py` (empty).

#### `tests/test_graph_utils.py`

Unit tests for `graph_utils.py` only. Uses pytest. No mocks, no I/O, no LLM.

Create a minimal `SimpleTask` helper inside the test file:

```python
from dataclasses import dataclass, field

@dataclass
class SimpleTask:
    id: str
    dependencies: list[str] = field(default_factory=list)
```

**Required test cases — implement all of these:**

##### `build_adjacency` tests
- `test_build_adjacency_empty`: empty task list returns empty dict
- `test_build_adjacency_single_no_deps`: single task with no dependencies
- `test_build_adjacency_forward_edge`: task_2 depends on task_1 → adj[task_1] contains task_2
- `test_build_adjacency_missing_reference`: raises ValueError when dependency references nonexistent task ID
- `test_build_adjacency_duplicate_task_ids`: raises ValueError when two tasks share the same ID
- `test_build_adjacency_deduplicates_deps`: dependencies=["A", "A"] treated as ["A"], no error

##### `detect_cycles` tests
- `test_detect_cycles_empty`: empty list returns `[]`
- `test_detect_cycles_single_no_deps`: single task → `[]`
- `test_detect_cycles_two_independent`: two independent tasks → `[]`
- `test_detect_cycles_self_loop`: task depends on itself → returns cycle containing that task
- `test_detect_cycles_two_node`: `A→B` and `B→A` → returns cycle
- `test_detect_cycles_transitive`: `A→B→C→A` → returns cycle
- `test_detect_cycles_linear_chain`: `A←B←C` → `[]` (no cycle)
- `test_detect_cycles_diamond`: diamond DAG → `[]` (valid, not a cycle)
- `test_detect_cycles_disconnected_with_cycle`: one component has cycle, one doesn't → detects it
- `test_disconnected_graph_without_cycle`: disconnected acyclic graph → `[]` and topo sort is valid

##### `topological_sort` tests
- `test_topological_sort_empty`: returns `[]`
- `test_topological_sort_single`: returns `[task.id]`
- `test_topological_sort_linear_chain`: dependency order preserved (deps first)
- `test_topological_sort_diamond`: A appears before B and C; B and C appear before D
  (test relative ordering, not exact order between B and C)
- `test_topological_sort_preserves_input_order`: when two tasks have no mutual dependency,
  they appear in the same relative order as the original list (tie-breaking rule)
- `test_topological_sort_raises_on_cycle`: raises ValueError

##### `execution_levels` tests
- `test_execution_levels_empty`: returns `[]`
- `test_execution_levels_single`: returns `[[task.id]]`
- `test_execution_levels_two_independent`: returns one level with both tasks
- `test_execution_levels_linear_chain`: `A→B→C` → `[['A'], ['B'], ['C']]`
- `test_execution_levels_diamond`: `[['A'], [B, C sorted], ['D']]`
- `test_execution_levels_raises_on_cycle`: raises ValueError

#### `tests/test_dag_validator.py`

Unit tests for `DAGValidator`. Uses the same `SimpleTask` helper (or import from test_graph_utils).

```python
from dataclasses import dataclass, field

@dataclass
class SimpleTask:
    id: str
    dependencies: list[str] = field(default_factory=list)

@dataclass
class SimpleDecomposition:
    tasks: list[SimpleTask]
```

**Required test cases:**

- `test_valid_linear_chain`: 3 tasks in a chain → valid=True, no errors, topological_order populated
- `test_valid_diamond`: diamond DAG → valid=True, parallelism_width >= 2
- `test_empty_decomposition`: tasks=[] → valid=False, error mentions "empty" or "no tasks"
- `test_duplicate_task_ids`: → valid=False, error mentions "duplicate"
- `test_dangling_reference`: dependency points to nonexistent ID → valid=False
- `test_cycle_detected`: A→B→A → valid=False, error mentions "cycle"
- `test_isolated_task_warning_multi`: 3 tasks, one isolated → valid=True, warning present
- `test_single_task_no_warning`: 1 task (isolated by definition) → valid=True, no warnings
- `test_deep_chain_warning`: 6+ levels → valid=True, warning about deep chain
- `test_graph_metrics_populated`: valid DAG → max_fan_in, max_fan_out, parallelism_width all > 0
- `test_graph_metrics_populated`: also assert exact `graph_depth` and `task_count`
- `test_dag_validation_result_to_dict`: verifies `.to_dict()` returns a dict with all expected keys
- `test_fan_in_uses_normalized_deps`: task with dependencies=["A", "A"] → max_fan_in = 1, not 2

#### `tests/test_integration_dag_failure.py`

Integration-smoke test for the failure path through `MultiAgentExecutor`. This is
the most fragile seam: "invalid DAG writes `dag_validation.json`, raises `ValueError`,
and the caller can still access `get_dag_validation()`." No LLM calls needed.

```python
from dataclasses import dataclass, field

@dataclass
class SimpleTask:
    id: str
    dependencies: list[str] = field(default_factory=list)

@dataclass
class SimpleDecomposition:
    original_goal: str = "test"
    decomposition_approach: str = "test"
    separation_rationale: str = "test"
    tasks: list[SimpleTask] = field(default_factory=list)
```

**Required test cases:**

- `test_dag_failure_raises_valueerror`: Create a `DAGValidator`, call `.validate()` on a
  decomposition with a cycle, confirm result has `valid=False`. Then confirm that if
  `MultiAgentExecutor.execute()` were to raise, the error message contains the cycle
  detail. (Test the validator directly — do NOT instantiate a real `MultiAgentExecutor`,
  which requires API keys and MCP.)

- `test_dag_validation_json_written_on_failure`: Create a `DAGValidator`, validate a
  cyclic decomposition, call `.to_dict()`, write to a temp file with `json.dump`,
  read it back and confirm `valid` is `False` and `errors` is non-empty. (Tests the
  serialization path that `execute()` uses, without needing the full executor.)

- `test_dag_success_populates_all_fields`: Validate a valid 3-task diamond, confirm
  `to_dict()` has all expected keys, `topological_order` has 3 entries,
  `execution_levels` has 2+ levels, and `parallelism_width >= 2`.

---

### FILE 4 (MODIFY): `src/multi_agent.py`

**Change 1: Add optional `validator` parameter to `MultiAgentExecutor.__init__`**

Current signature:
```python
def __init__(self, config: BenchmarkConfig, api_key: str, mcp_manager: MCPManager):
```

New signature:
```python
def __init__(self, config: BenchmarkConfig, api_key: str, mcp_manager: MCPManager,
             validator=None):
    # validator: optional object with .validate(decomposition) -> result with .to_dict()
    # and .valid (bool). See src/dag_validator.py for reference implementation.
    # Default None = no validation, existing behavior unchanged.
```

Store as `self._validator = validator`.
Store `self._dag_validation = None` (will hold the result dict, not the typed object — avoids import).

**Change 2: Call validator in `execute()` after decomposition, before orchestrator runs**

Location: between the `self.decomposer.save_decomposition(...)` call and the
`self._create_orchestrator_prompt(...)` call (approximately lines 333–336).

Insert:
```python
# Run optional DAG validation
if self._validator is not None:
    dag_result = self._validator.validate(self.decomposition)
    self._dag_validation = dag_result.to_dict()
    # Save validation result alongside task_decomposition.json
    dag_validation_file = self.output_dir / "dag_validation.json"
    with open(dag_validation_file, "w") as f:
        json.dump(self._dag_validation, f, indent=2)
    if not dag_result.valid:
        raise ValueError(
            f"DAG validation failed: {'; '.join(dag_result.errors)}"
        )
```

**Change 3: Add accessor method**

```python
def get_dag_validation(self) -> dict | None:
    """Return DAG validation result if validation was enabled, else None."""
    return self._dag_validation
```

**No imports added to `multi_agent.py`.** The validator is duck-typed: it must have
a `.validate(decomposition)` method returning an object with `.valid` (bool),
`.errors` (list[str]), and `.to_dict()`. No import needed.

**What NOT to change in `multi_agent.py`:**
- `SubAgentExecutor` — do not touch
- The orchestrator agent creation
- The `SequentialToolExecutor` usage
- Metrics tracking
- Any existing method signatures except `__init__`

---

### FILE 5 (MODIFY): `benchmark.py`

**Change 1: Add `--validate-dag` flag**

Add to argparse in `main()`, after the `--skip-validation` argument:

```python
parser.add_argument(
    "--validate-dag",
    action="store_true",
    default=get_env_bool("BENCHMARK_VALIDATE_DAG", False),
    help=(
        "Validate multi-agent task decomposition as a DAG before execution. "
        "Detects cycles and invalid dependency references. "
        "Only applies to multi-agent path. (env: BENCHMARK_VALIDATE_DAG)"
    )
)
```

**Change 2: Wire up validator in `run_benchmark()`**

`run_benchmark()` currently has signature:
```python
def run_benchmark(config: BenchmarkConfig, api_key: str, goal: str,
                  mcp_config_path: Path, quiet: bool = False) -> Path:
```

Add `validate_dag: bool = False` parameter:
```python
def run_benchmark(config: BenchmarkConfig, api_key: str, goal: str,
                  mcp_config_path: Path, quiet: bool = False,
                  validate_dag: bool = False) -> Path:
```

Inside `run_benchmark()`, find where `MultiAgentExecutor` is constructed
(approximately line 350).

Replace the construction with:
```python
# Build optional DAG validator
dag_validator = None
if validate_dag:
    from src.dag_validator import DAGValidator
    dag_validator = DAGValidator()

multi_executor = MultiAgentExecutor(config, api_key, multi_mcp_manager,
                                    validator=dag_validator)
```

**Change 3: Handle DAG validation failure gracefully (REQUIRED)**

CRITICAL: An invalid DAG must NOT abort the entire benchmark. The single-agent
results have already been collected and are valuable. The benchmark should record
"multi-agent failed at decomposition validation" and continue to report generation.

The DAG validation `ValueError` is raised at line ~333 of `execute()`, which is
BEFORE the existing `try:` block that starts at line ~359. The existing
`except Exception` on line ~426 will NOT catch it — the exception propagates out
of `execute()` entirely. Therefore a wrapper in `run_benchmark()` is **required**.

Wrap the multi-agent execution call in `run_benchmark()`. This applies to BOTH
the quiet and non-quiet code paths (the executor is called in two places — inside
the `if quiet:` branch and inside the `else:` with Progress). The cleanest approach
is to wrap the `multi_executor.execute(goal)` call itself, not the entire block:

```python
try:
    multi_result = multi_executor.execute(goal)
    multi_metrics = multi_executor.get_metrics()
    decomp_report = multi_executor.get_decomposition_report()
except Exception as e:
    # DAG validation failure or other preflight error — record as failed multi-agent
    multi_result = {"success": False, "output": "", "error": str(e), "task_results": {}}
    multi_metrics = multi_executor.get_metrics()  # may be empty but won't error
    decomp_report = multi_executor.get_decomposition_report()
    console.print(f"[red]✗ Multi-agent failed (preflight): {e}[/red]")
```

**Artifact note on DAG failure:** When DAG validation fails:
- `dag_validation.json` WILL exist (written before the raise in `execute()`)
- `result.json` will NOT exist (the code that writes it at line ~434 never runs)
- This is intentional — `dag_validation.json` is the authoritative artifact for
  the failure. The `multi_result` dict in `run_benchmark()` carries the error
  forward to the report generator.

**Change 4: Pass flag from `main()` to `run_benchmark()`**

In `main()`, update the `run_benchmark(...)` call to pass `validate_dag=args.validate_dag`.

**Change 5: Update env vars docstring in argparse epilog**

Add:
```
  BENCHMARK_VALIDATE_DAG    Validate multi-agent decomposition as DAG (true/false)
```

**What NOT to change in `benchmark.py`:**
- The single-agent execution path — untouched
- Any existing flags or their defaults
- The `BenchmarkConfig` construction
- Display/reporting logic (besides the DAG failure console message)

---

## Design Constraints

### Coupling Rules
- `multi_agent.py` must NOT import `dag_validator.py` or `graph_utils.py` at the module level
  or at any other point — the validator is purely duck-typed
- `graph_utils.py` must have zero project-local imports
- `dag_validator.py` imports only from `graph_utils` (within project)
- `benchmark.py` imports `DAGValidator` lazily (inside the `if validate_dag:` block only)

### Behavioral Constraints
- When `--validate-dag` is NOT passed: zero behavior change anywhere, no performance impact
- When `--validate-dag` IS passed and validation passes: execution proceeds normally;
  `dag_validation.json` is written to the multi_agent output dir
- When `--validate-dag` IS passed and validation fails: multi-agent is recorded as failed;
  `dag_validation.json` is still written (with `valid: false`); single-agent results
  and report generation proceed normally
- Single-agent path: completely unaffected — no flag, no import, no code path

### Determinism
- Tie-breaking in `topological_sort`: when multiple tasks have zero in-degree simultaneously,
  process them in the order they appear in the original `tasks` list
- Tie-breaking in `execution_levels`: tasks within the same level are ordered by their
  position in the original `tasks` list
- This ensures `dag_validation.json` is stable across runs given the same decomposition

### Output Artifact
When `--validate-dag` is passed:
```
benchmark_results_YYYYMMDD_HHMMSS/
└── multi_agent/
    ├── task_decomposition.json    (existing)
    └── dag_validation.json        (new)
        {
          "valid": true,
          "errors": [],
          "warnings": ["Isolated task 'task_3' has no dependencies and no dependents"],
          "topological_order": ["task_1", "task_2", "task_3"],
          "execution_levels": [["task_1", "task_3"], ["task_2"]],
          "graph_depth": 2,
          "task_count": 3,
          "max_fan_in": 1,
          "max_fan_out": 1,
          "parallelism_width": 2
        }
```

---

## Test File Structure

```
tests/
├── __init__.py                      (empty)
├── test_graph_utils.py              (pure algorithm unit tests)
├── test_dag_validator.py            (validator logic tests)
└── test_integration_dag_failure.py  (failure-path smoke tests — no LLM, no MCP)
```

Run with: `pytest tests/ -v`

All tests must pass with no LLM calls, no network, no file I/O.

---

## Python Version & Dependencies

- Python 3.10+ (uses `X | Y` union syntax, `match` is not used)
- No new dependencies — all graph algorithms use stdlib only (`collections.deque`, etc.)
- `pytest` is already in `requirements.txt`

---

## What Success Looks Like

```bash
# Existing behavior — completely unchanged
python benchmark.py --goal examples/goals/coding/simple_goal.md

# New flag — validates DAG before multi-agent runs
python benchmark.py --goal examples/goals/coding/simple_goal.md --validate-dag

# Tests pass
pytest tests/ -v
# tests/test_graph_utils.py::test_build_adjacency_empty PASSED
# tests/test_graph_utils.py::test_build_adjacency_duplicate_task_ids PASSED
# tests/test_graph_utils.py::test_detect_cycles_self_loop PASSED
# tests/test_dag_validator.py::test_empty_decomposition PASSED
# tests/test_dag_validator.py::test_valid_diamond PASSED
# ... (all tests pass)
```

---

## Anti-Patterns to Avoid

- Do NOT add `validate_dag: bool` to `BenchmarkConfig` — config should not know about
  specific algorithmic features
- Do NOT raise exceptions inside `detect_cycles` — it returns a list, callers decide
- Do NOT make `topological_sort` return `SubTask` objects — return task ID strings only
- Do NOT modify `single_agent.py` in any way
- Do NOT add any imports to `multi_agent.py` for the validator — keep it decoupled
- Do NOT skip the `tests/__init__.py` file
- Do NOT use lexicographic sort for tie-breaking — preserve original task list order
- Do NOT abort the entire benchmark on DAG validation failure — record as failed multi-agent
  and continue to report generation
- Do NOT warn about isolated tasks when there is only one task in the decomposition

---

## Background: Why This Matters

The existing multi-agent system stores task dependencies in `SubTask.dependencies: list[str]`
but never algorithmically verifies them. The orchestrator LLM is trusted (via prompt
instructions) to execute tasks in dependency order. If the decomposer LLM generates
a cycle, nothing catches it — the orchestrator could deadlock or produce incorrect output.

This feature answers a concrete architectural question raised in community discussion:
is the multi-agent system a DAG or not? With `--validate-dag`, the answer becomes
provable rather than assumed.

The flag design keeps this entirely optional: researchers who want the LLM-driven
orchestration behavior untouched can ignore the flag. Those who want graph-theoretic
guarantees before expensive orchestrator/sub-agent execution can opt in.

---

## Future Work (Explicitly Out of Scope for This PR)

These are acknowledged follow-on features. Do not implement them in this PR:

- **Validator chain architecture**: accept a list of validators instead of one.
  Enables composable quality checks (duplicate names, empty rationale, etc.)
- **Repair-once mode**: on DAG failure, feed errors back to decomposer for one retry
- **`dag_validation.md` report**: human-readable markdown summary alongside JSON
- **`--strict-dag-warnings`**: treat warnings as errors for research-quality runs
- **`--decompose-only --validate-dag`**: inspect decomposition without paying for execution
- **Layer 2 (execution ordering hints)**: inject topological order into orchestrator prompt
- **Layer 3 (algorithmic execution control)**: drive execution order from code, not LLM
- **Post-hoc execution order validation**: check if the orchestrator's actual tool-call
  sequence respected the declared dependency graph (benchmark quality metric)
