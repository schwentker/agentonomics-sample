# GPT 5.4 Audit Prompt: `complex_goal_dag.md` + DAG Validation Spec

Paste this prompt into GPT 5.4 along with the contents of two files:
1. `examples/goals/coding/complex_goal_dag.md`
2. `docs/dag-validation/complex-goal-dag-spec.md`

Optionally also attach:
3. `docs/dag-validation/spec.md` (the main DAG validation implementation spec)

---

## Prompt

```text
You are reviewing two documents from a benchmarking system called agentonomics-sample.
This system compares single-agent vs multi-agent architectures for completing structured
goals using LLM agents. It recently added optional DAG validation to verify that
LLM-generated task decompositions form valid directed acyclic graphs before expensive
multi-agent orchestration begins.

The two documents you are reviewing:

FILE 1: `complex_goal_dag.md` — A benchmark goal that describes a real project
(an MCP server for community intelligence) and is specifically designed to produce
a wide diamond DAG during LLM task decomposition.

FILE 2: `complex-goal-dag-spec.md` — The design spec explaining why this goal was
built, what DAG properties it should exercise, and how it fits into the benchmark
suite.

If provided, FILE 3: `spec.md` — The full implementation spec for the DAG validation
feature, including the graph algorithms, validator class, CLI integration, and test
requirements.

---

### Your audit should cover five areas:

#### 1. GOAL QUALITY — Will an LLM decompose this correctly?

Review `complex_goal_dag.md` as if you were the task decomposition LLM. Ask:

- Are the 9 deliverables clearly scoped with unambiguous boundaries?
- Are the dependency relationships between deliverables explicit enough that a
  decomposer LLM will infer correct `SubTask.dependencies` lists?
- Is there any deliverable that could reasonably be split into 2+ subtasks by the
  LLM, breaking the expected DAG structure?
- Is there any implicit circular dependency hidden in the spec? (e.g., does module A
  need module B which needs module A?)
- Does the "Dependency Graph" section at the bottom help or hurt? Could it confuse
  the decomposer into over-fitting to the exact structure rather than reasoning
  about real dependencies?
- Grade the goal's decomposition-friendliness: A (will reliably produce a diamond
  DAG), B (usually will), C (hit or miss), D (unlikely).

#### 2. DAG COVERAGE — Does this actually test what the spec claims?

Review the "Expected DAG Structure" in the spec and cross-reference with the goal:

- Will the decomposition reliably produce a hub node (types.ts)?
- Will the 4 adapters reliably appear as parallel tasks at the same depth?
- Will the aggregator reliably depend on all 4 adapters?
- Will the linear chain (MCP → HTTP → Deployment) reliably appear?
- Are there any DAG properties from the validator spec (cycles, self-loops, dangling
  references, isolated tasks, deep chains) that this goal does NOT exercise?
  (It should NOT exercise cycles — that's for unit tests — but note any gaps.)
- Is the "Expected Validation Metrics" table in the spec realistic given what a
  typical LLM decomposer would produce?

#### 3. SPEC CONSISTENCY — Do the two documents agree?

Check for contradictions or gaps between the goal file and its spec:

- Does the spec accurately describe the goal's structure?
- Does the spec's "Expected DAG Structure" match the goal's "Dependency Graph"?
- Are the metric ranges in the spec plausible for the goal's complexity?
- Does the spec correctly position this goal relative to `simple_goal.md` and
  `complex_goal.md`? (You don't need to read those files — just check that the
  claims about them are reasonable.)

#### 4. IMPLEMENTATION RISKS — What could go wrong at runtime?

Think about what happens when this goal is actually run through the benchmark:

- Could the LLM decomposer produce a flat decomposition (all tasks independent)
  instead of a diamond? What in the goal prevents this?
- Could the decomposer merge deliverables (e.g., combine config + types into one
  task), collapsing the DAG depth?
- Are there any deliverables that are ambiguous enough to generate different
  dependency graphs across runs, making the "Expected Validation Metrics"
  unreliable?
- If the Reddit API is down or rate-limited during benchmarking, does the goal
  handle that? (Hint: the goal says "live fetch" — is this a risk?)
- The deployment deliverable depends on "HTTP layer being complete" — could a
  decomposer reasonably make deployment depend on everything, turning the DAG
  into a single linear chain?

#### 5. MISSING PIECES — What's not covered?

Identify anything that should exist but doesn't:

- Should there be a negative test goal (one designed to produce an invalid DAG)?
- Should there be a minimal DAG goal (e.g., 3 tasks in a V-shape)?
- Does the goal need a "success criteria" section that maps to specific
  `dag_validation.json` field values?
- Is there documentation missing about how to add new goals to the benchmark?

---

### Output format

For each of the 5 areas, provide:

1. **Verdict**: PASS / PASS WITH NOTES / NEEDS WORK / FAIL
2. **Findings**: Specific, actionable items ordered by severity
3. **Suggestions**: Optional improvements (clearly marked as non-blocking)

Then provide an **overall assessment**:
- Is this goal ready to merge into the benchmark suite? (YES / YES WITH CHANGES / NO)
- What is the single highest-risk item?
- What is the single highest-value improvement?

Keep your response under 1500 words. Be direct. If something is fine, say it's fine
and move on.
```

---

## Why GPT 5.4?

This audit is intentionally cross-model. The benchmark goals are decomposed by
Anthropic's Claude (via Strands Agents). Having a different model family review the
goal spec provides:

1. **Adversarial coverage** — a model with different training data and reasoning
   patterns is more likely to spot ambiguities that Claude would gloss over
2. **Decomposition prediction** — GPT can simulate how it would decompose the goal,
   surfacing structural risks that same-model review might miss
3. **Fresh eyes** — the DAG validation spec was written by Claude; GPT reviews
   without anchoring bias

---

## How to Run the Audit

### Option A: ChatGPT UI
1. Open ChatGPT with GPT 5.4 selected
2. Paste the prompt above
3. Attach or paste the contents of the two (or three) files
4. Submit and review

### Option B: API
```bash
# Concatenate files for context
cat examples/goals/coding/complex_goal_dag.md > /tmp/audit_context.txt
echo -e "\n---\n" >> /tmp/audit_context.txt
cat docs/dag-validation/complex-goal-dag-spec.md >> /tmp/audit_context.txt
echo -e "\n---\n" >> /tmp/audit_context.txt
cat docs/dag-validation/spec.md >> /tmp/audit_context.txt

# Use with your preferred API client
```

### Option C: Claude Cross-Check
For comparison, you can also run this same prompt through Claude to see if the two
models agree on findings. Disagreements between models are the most valuable signals.
