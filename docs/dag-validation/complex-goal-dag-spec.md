# Spec: `complex_goal_dag.md` — DAG-Optimized Benchmark Goal

## Purpose

`examples/goals/coding/complex_goal_dag.md` is the third benchmark goal in the
agentonomics-sample repository. Unlike `simple_goal.md` (flat, no dependencies) or
`complex_goal.md` (deep but mostly linear), this goal is specifically designed to
produce a **wide diamond DAG** during LLM task decomposition — making it the primary
test case for the `--validate-dag` feature.

---

## What It Describes

The goal asks the agent to build **workato-comm-voices**: an MCP (Model Context
Protocol) server that aggregates community posts from Reddit, Slack, Discord, and
Systematic into a unified schema, backed by Neon Postgres, deployed on Fly.io.

The project is real — it exists at `github.com/schwentker/workato-comm-voices` — and
the goal spec is derived from its actual architecture. This gives the benchmark goal
realistic complexity rather than synthetic toy structure.

---

## Why This Goal Exercises DAG Validation

The deliverables in `complex_goal_dag.md` are structured to produce a task
decomposition with the following graph properties:

| Property | Description | Why it matters for DAG validation |
|---|---|---|
| **Hub node** | `types.ts` has 0 deps but 8+ dependents | Tests fan-out from a single root |
| **Fan-out** | 4 parallel adapter tasks branch from `config.ts` (+ `types.ts`) | Tests parallel level grouping |
| **Fan-in** | `CommunityAggregator` depends on all 4 adapters + DB | Tests convergence detection |
| **Diamond dependency** | `config.ts` is needed at depth 1 and depth 3 | Tests multi-path convergence |
| **Linear chain** | MCP Server → HTTP/SSE → Deployment | Tests serial dependency ordering |
| **Wide leaf layer** | Tests reference many upstream modules | Tests high fan-in at leaf nodes |

### Expected DAG Structure

```
types.ts (L0)
    |
    +-- config.ts (L1)
    |       |
    |       +-- db.ts (L2)
    |       |
    |       +-- RedditAdapter (L2)
    |       +-- SystematicAdapter (L2)
    |       +-- SlackAdapter (L2)
    |       +-- DiscordAdapter (L2)
    |               |
    |               +-- CommunityAggregator (L3 — depends on all 4 adapters + db)
    |                       |
    |                       +-- MCP Server (L4)
    |                               |
    |       +-----------------------+-- HTTP/SSE Layer (L5)
    |                                       |
    |                                       +-- Deployment (L6)
    |
    +-- tsconfig / .env.example (L1)
    |
    +-- Tests (L6 — depends on adapters, aggregator, db, HTTP; may share level with Deployment)
```

### Expected Validation Metrics

When run through `--validate-dag`, the target shape is:

| Metric | Target range | Notes |
|---|---|---|
| `task_count` | 8–13 | Lower end if adapters merge or types+config merge; higher if deployment splits |
| `graph_depth` | 5–8 levels | Merging types+config reduces by 1; splitting tests adds 1 |
| `max_fan_out` | 3–7 (from types or config) | 7 when types.ts feeds config, db, 4 adapters, and tsconfig directly; lower if decomposer collapses indirect deps |
| `max_fan_in` | 4–7 (at aggregator or tests) | 5 at aggregator (4 adapters + db); up to 7 at tests (adapters + aggregator + db + HTTP) |
| `parallelism_width` | 2–5 (the adapter level) | 5 if db shares the adapter layer; 4 when adapters alone; 2 if some merge |

These are broad target ranges, not pass/fail thresholds. LLM decomposition variance
means the exact task IDs and groupings will differ across runs. The structural
properties (hub → fan-out → fan-in → chain) should be stable even when counts shift.

### Acceptable Decomposition Merges

The following merges are valid and do not indicate a goal or validator bug:

| Merge | Effect on metrics | Still exercises |
|---|---|---|
| `types.ts` + `config.ts` into one task | depth −1, fan-out origin shifts | Fan-out, fan-in, diamond |
| `tsconfig` + `.env.example` merged into deployment | task_count −1 | No change to critical path |
| Tests split per module (unit, integration, E2E) | task_count +2, leaf fan-in splits | Wide leaf layer |
| `db.ts` grouped with adapters at same level | parallelism_width +1 | Fan-out widens, fan-in unchanged |

Note: Merging all 4 adapters into a single task is **not** an acceptable merge —
the goal explicitly instructs the decomposer to represent each adapter separately.

### DAG Success Profile

For automated benchmark gates, use these minimum thresholds:

| Metric | Minimum to pass |
|---|---|
| `task_count` | ≥ 7 |
| `graph_depth` | ≥ 4 |
| `parallelism_width` | ≥ 2 |
| `max_fan_in` | ≥ 2 |
| `valid` | `true` (no cycles, no dangling refs) |

---

## Relationship to Other Goals

| Goal file | Complexity | Dependency depth | Parallelism | DAG shape |
|---|---|---|---|---|
| `simple_goal.md` | Low | 0 (flat) | None | Trivial |
| `complex_goal.md` | High | Deep but narrow | Minimal | Mostly linear chain |
| `complex_goal_dag.md` | High | Deep and wide | Significant | Wide diamond |

The three goals together provide coverage across the full spectrum of task
decomposition structures:

- **simple_goal**: validates that DAG validation passes trivially on flat graphs
- **complex_goal**: validates deep chains and serial dependencies
- **complex_goal_dag**: validates fan-out, fan-in, diamonds, and parallel levels

---

## How to Use It

```bash
# Run benchmark with DAG validation on the new goal
python benchmark.py \
  --goal examples/goals/coding/complex_goal_dag.md \
  --validate-dag

# Run all three goals for comparison
for goal in simple_goal.md complex_goal.md complex_goal_dag.md; do
  python benchmark.py \
    --goal "examples/goals/coding/$goal" \
    --validate-dag
done
```

### What to Look For in Results

After a `--validate-dag` run with `complex_goal_dag.md`, check:

1. **`multi_agent/dag_validation.json`** — should show `valid: true` with:
   - `execution_levels` having 4+ levels (target 5–8)
   - `parallelism_width` of 2+ (target 4 when adapters split)
   - `max_fan_in` of 2+ (target 4–6 at the aggregator or tests)
   - No errors, possibly a deep-chain warning

2. **`multi_agent/task_decomposition.json`** — should show tasks with rich
   `dependencies` lists, not just empty arrays

3. **Benchmark report** — compare single-agent vs multi-agent:
   - Multi-agent should show measurable parallelism benefit at the adapter level
   - Cost difference reflects the overhead of orchestrator + sub-agents

---

## Design Decisions

### Why workato-comm-voices?

1. **Real project** — the architecture is grounded in a deployed system, not
   synthetic. LLMs produce more realistic decompositions from real specs.

2. **Natural diamond structure** — adapters are genuinely parallel (Reddit, Slack,
   Discord, Systematic), and the aggregator genuinely depends on all of them. This
   isn't forced parallelism.

3. **Cross-cutting config** — the config module is needed at multiple depths, which
   creates the diamond dependency pattern naturally.

4. **Hub-and-spoke types** — a shared type system that everything imports from
   creates the hub node pattern without artificial coupling.

### Why include the expected DAG in the goal file?

The "Dependency Graph" section at the bottom of `complex_goal_dag.md` is intentional.
It gives the LLM decomposer a structural hint — increasing the probability that the
generated `SubTask.dependencies` lists reflect the actual architecture rather than
being flat or randomly connected. This makes the goal more reliable as a DAG
validation test case.

### Why not make the goal intentionally cyclic?

A valid goal should produce a valid DAG. Testing cycle detection is the job of
`tests/test_graph_utils.py` and `tests/test_dag_validator.py` with synthetic inputs.
The benchmark goal tests the full pipeline: real spec → LLM decomposition →
DAG validation → multi-agent execution.

---

## Files Involved

| File | Action | Description |
|---|---|---|
| `examples/goals/coding/complex_goal_dag.md` | NEW | The benchmark goal spec |
| `docs/dag-validation/complex-goal-dag-spec.md` | NEW | This document |
| `docs/dag-validation/gpt-audit-prompt.md` | NEW | GPT 5.4 review prompt |

---

## Authorship

Created by Robert Schwentker (Sandbox Labs AI) as part of the DAG validation
feature branch. Goal content derived from the workato-comm-voices project
architecture.
