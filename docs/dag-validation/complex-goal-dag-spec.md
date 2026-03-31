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
| **Fan-out** | 4 parallel adapter tasks branch from the DB layer | Tests parallel level grouping |
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
    |       |       |
    |       |       +-- RedditAdapter (L3)
    |       |       +-- SystematicAdapter (L3)
    |       |       +-- SlackAdapter (L3)
    |       |       +-- DiscordAdapter (L3)
    |       |               |
    |       |               +-- CommunityAggregator (L4)
    |       |                       |
    |       |                       +-- MCP Server (L5)
    |       |                               |
    |       +-------------------------------+-- HTTP/SSE Layer (L6)
    |                                               |
    |                                               +-- Deployment (L7)
    |
    +-- Tests (L8 — depends on adapters, aggregator, db, HTTP)
```

### Expected Validation Metrics

When run through `--validate-dag`, the decomposition should produce approximately:

| Metric | Expected range |
|---|---|
| `task_count` | 10–12 |
| `graph_depth` | 6–9 levels |
| `max_fan_out` | 4–5 (from db.ts or types.ts) |
| `max_fan_in` | 4–6 (at aggregator or tests) |
| `parallelism_width` | 4 (the adapter level) |

These ranges account for LLM decomposition variance — the exact task IDs and
groupings will differ across runs, but the structural properties should be stable.

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
   - `execution_levels` having 6+ levels
   - `parallelism_width` of 3–4 (the adapter fan-out)
   - `max_fan_in` of 4+ (at the aggregator)
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
