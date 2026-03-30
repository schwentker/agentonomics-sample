# DAG Validation Implementation Plan

## Scope

Implement optional DAG validation for multi-agent task decomposition. The feature is
off by default, applies only to the multi-agent path, runs after decomposition and
before orchestrator/sub-agent execution, and records invalid DAGs as failed
multi-agent runs without aborting benchmark report generation.

## Files To Create

### `src/graph_utils.py`

Create pure graph helpers with no project-local imports and no I/O:

- `build_adjacency(tasks)`
- `detect_cycles(tasks)`
- `topological_sort(tasks)`
- `execution_levels(tasks)`

Required behavior:

- Accept any objects with `.id` and `.dependencies`
- Raise on duplicate task IDs
- Raise on missing dependency references
- Silently deduplicate repeated dependencies within a single task
- Preserve original task list order for deterministic output
- Keep `_normalized_dependencies()` defined in this module as the single shared
  normalization helper and import it from the validator layer rather than duplicating it
- Document in `detect_cycles()` that it traverses reverse edges while
  `build_adjacency()` uses forward edges, and that cycle existence is invariant under
  edge reversal

### `src/dag_validator.py`

Create the validator layer:

- `DecompositionValidator` protocol
- `DAGValidationResult` dataclass
- `DEEP_CHAIN_WARNING_THRESHOLD = 5`
- `DAGValidator.validate()`

Required behavior:

- Error on empty decomposition
- Error on duplicate task IDs
- Error on dangling dependency references
- Error on cycles
- Warn on isolated tasks only when `task_count > 1`
- Warn on deep dependency chains
- Populate `topological_order`, `execution_levels`, `graph_depth`, `task_count`,
  `max_fan_in`, `max_fan_out`, and `parallelism_width` only for valid DAGs
- Short-circuit later checks when earlier checks make graph analysis invalid

### `tests/__init__.py`

Create as an empty file.

### `tests/test_graph_utils.py`

Create pure unit tests for graph algorithms:

- adjacency construction
- missing references
- duplicate task IDs
- duplicate dependency deduplication
- cycle detection
- topological ordering
- execution level grouping
- deterministic tie-breaking
- disconnected graph without a cycle

### `tests/test_dag_validator.py`

Create validator-layer unit tests:

- valid linear chain
- valid diamond DAG
- empty decomposition
- duplicate task IDs
- dangling dependency reference
- cycle detection
- isolated-task warning
- single-task no-warning case
- deep-chain warning
- graph metrics population
- explicit `graph_depth` and `task_count` assertions
- `DAGValidationResult.to_dict()` key coverage

## Files To Edit

### `src/multi_agent.py`

Update `MultiAgentExecutor`:

- Add optional `validator=None` parameter to `__init__`
- Store `self._validator`
- Store `self._dag_validation = None`
- Run validation after `task_decomposition.json` is written and before orchestrator setup
- Write `dag_validation.json`
- Raise `ValueError` when validation returns `valid=False`
- Add `get_dag_validation() -> dict | None`

Constraints:

- Keep validator usage duck-typed
- Do not import validator types into this module
- Do not modify `SubAgentExecutor`
- Do not change orchestrator setup beyond inserting validation before it

### `benchmark.py`

Update CLI and benchmark wiring:

- Add `--validate-dag`
- Add `BENCHMARK_VALIDATE_DAG` env var support
- Pass `validate_dag` into `run_benchmark()`
- Lazily construct `DAGValidator` only when flag is enabled
- Ensure invalid DAGs do not abort the benchmark
- Record invalid DAGs as failed multi-agent results and continue to report generation

Implementation note:

- The current `MultiAgentExecutor.execute()` `try/except` begins after decomposition
  and orchestrator setup, so DAG-validation exceptions inserted earlier will
  propagate unless the `try/except` scope is expanded or `run_benchmark()` adds a
  wrapper around `multi_executor.execute(goal)`.

### `README.md`

Add minimal product-facing documentation:

- Document `--validate-dag`
- Document `BENCHMARK_VALIDATE_DAG`
- Explain that DAG validation is optional and multi-agent only
- Note that validation runs after decomposition and before orchestrator/sub-agent execution
- Document the `multi_agent/dag_validation.json` artifact
- Explain that invalid DAGs mark multi-agent as failed but do not stop report generation

## Test Plan

### Unit Tests

Run:

```bash
pytest tests/ -v
```

Expected coverage:

- `tests/test_graph_utils.py`
  - empty graph
  - single task
  - forward edge construction
  - missing dependency reference
  - duplicate task IDs
  - duplicate dependency deduplication
  - self-loop
  - two-node cycle
  - transitive cycle
  - disconnected graph with and without cycle
  - topological ordering constraints
  - stable ordering for equal-priority tasks
  - execution level grouping
  - cycle failure paths

- `tests/test_dag_validator.py`
  - valid chain
  - valid diamond
  - empty decomposition
  - duplicate IDs
  - dangling reference
  - cycle detection
  - isolated-task warning
  - single-task no-warning case
  - deep-chain warning
  - graph metric population

### CLI Sanity Checks

Run:

```bash
python benchmark.py --help
```

Verify:

- `--validate-dag` appears in help output
- `BENCHMARK_VALIDATE_DAG` appears in env var documentation

### Integration Note

If a full benchmark execution is not run as part of implementation, note that explicitly.
The most important integration behavior to confirm later is:

- valid DAG: benchmark runs normally and writes `dag_validation.json`
- invalid DAG: multi-agent is marked failed, `dag_validation.json` is written, and report generation still completes
