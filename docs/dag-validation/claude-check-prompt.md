# Claude Completion Check Prompt

Use this prompt with Claude to verify the DAG validation implementation:

```text
Review the DAG validation implementation in this repository and verify whether it is complete and correct relative to the plan in docs/dag-validation/implementation-plan.md.

Focus on:

1. Code correctness
- Check src/graph_utils.py for:
  - duplicate task ID detection
  - missing dependency detection
  - dependency deduplication
  - deterministic ordering
  - correct cycle detection
  - correct topological sorting
  - correct execution level grouping

- Check src/dag_validator.py for:
  - empty decomposition error
  - duplicate ID handling
  - dangling reference handling
  - cycle handling
  - isolated task warning rule
  - deep-chain warning rule
  - graph metric computation
  - short-circuit behavior

- Check src/multi_agent.py for:
  - optional validator injection
  - dag_validation.json writing
  - invalid DAG rejection before orchestrator/sub-agent execution
  - get_dag_validation() behavior
  - no direct import coupling to validator types

- Check benchmark.py for:
  - --validate-dag CLI flag
  - BENCHMARK_VALIDATE_DAG env var support
  - lazy DAGValidator construction
  - invalid DAG handling that records multi-agent failure and continues to report generation
  - avoiding accidental swallowing of unrelated ValueErrors

- Check README.md for:
  - flag/env var docs
  - DAG validation behavior docs
  - artifact docs

2. Test coverage
- Review tests/test_graph_utils.py and tests/test_dag_validator.py
- Identify missing edge cases, weak assertions, or incorrect assumptions

3. Behavioral risks
- Call out any mismatch between the implementation and the intended runtime behavior
- Call out any likely bugs, regressions, or hidden edge cases

4. Verification status
- If possible, run or reason about:
  - pytest tests/ -v
  - python benchmark.py --help
- If you cannot run something, state exactly why

Output format:

- Findings first, ordered by severity
- Then open questions / assumptions
- Then a brief completion summary

If there are no findings, say that explicitly and mention any residual risks or unverified areas.
```
