# GPT 5.4 / Codex Audit Prompt (Round 3): Final Gate Review

This is the **third and final** audit prompt. Run it after applying fixes from
Round 2. Its purpose is narrow: confirm the three Round 2 fixes landed cleanly,
run one full decomposition simulation, and give a ship/no-ship verdict.

Paste this prompt into Codex (or GPT 5.4) along with the **final** contents of:
1. `examples/goals/coding/complex_goal_dag.md`
2. `docs/dag-validation/complex-goal-dag-spec.md`

Optionally also attach:
3. `docs/dag-validation/spec.md` (main DAG validation implementation spec)
4. Round 2 audit output (so you can verify each finding was addressed)

---

## Prompt

```text
You are performing a final gate review of two documents from the agentonomics-sample
benchmarking system. Two prior audit rounds have been completed and fixes applied.
Your job is to verify the last round of fixes, perform one clean decomposition
simulation, and deliver a ship/no-ship verdict.

CONTEXT: This system compares single-agent vs multi-agent LLM architectures for
completing structured goals. Optional DAG validation verifies that LLM-generated task
decompositions form valid directed acyclic graphs before multi-agent orchestration.

The two documents:

FILE 1: `complex_goal_dag.md` — Benchmark goal describing a real MCP server project
(workato-comm-voices). Designed to produce a wide diamond DAG during LLM task
decomposition. Contains 10 numbered deliverables with explicit dependency descriptions
and a dependency graph diagram.

FILE 2: `complex-goal-dag-spec.md` — Design spec documenting the goal's intended DAG
properties, expected metric ranges, acceptable decomposition merges, DAG success
profile, and position in the benchmark suite.

---

### PART 1: Verify Round 2 Fixes (3 items)

#### FIX A: "Acceptable merges" removed from goal file
- **Round 2 finding**: The goal file contained an "Acceptable decomposition merges"
  paragraph that was decomposer input, actively encouraging the merges the goal was
  trying to prevent (especially "all 4 adapters as a single task").
- **Expected fix**: That paragraph is deleted from the goal file entirely. Merge
  guidance lives only in the spec file.
- **Check**: Confirm the goal file contains NO mention of "acceptable merges,"
  "acceptable decomposition," or any guidance about which task merges are OK. The
  spec file should still have its "Acceptable Decomposition Merges" table — verify
  it no longer lists "all 4 adapters as a single task" as acceptable, and instead
  explicitly marks it as not acceptable.

#### FIX B: Hardcoded fixture path removed
- **Round 2 finding**: The goal referenced `fixtures/reddit_r_workato.json` but no
  such file existed in the repo.
- **Expected fix**: The concrete path is replaced with a description: the adapter
  should ship with a bundled fixture containing sample posts. No phantom file path.
- **Check**: Confirm the goal file does NOT contain the string
  `fixtures/reddit_r_workato.json`. Confirm the Reddit adapter deliverable still
  describes fallback behavior with enough detail for an implementer to build it.

#### FIX C: parallelism_width widened to 2–5
- **Round 2 finding**: The spec's parallelism_width target of 2–4 was too narrow
  because db.ts can naturally land at the same level as the 4 adapters.
- **Expected fix**: Range updated to 2–5 with a note explaining why 5 is possible.
- **Check**: Confirm the spec shows 2–5 for parallelism_width. Confirm the
  explanatory note mentions db sharing the adapter level.

---

### PART 2: Full Decomposition Simulation

You are the task decomposer LLM. You receive ONLY the contents of
`complex_goal_dag.md` as your input (not the spec). Produce a complete decomposition:

For each task, output:
- task_id (e.g., T1, T2, ...)
- task_name (short label)
- dependencies (list of task_ids this task depends on)

Rules:
- Follow the goal's explicit instruction to represent each adapter as its own task
- Use the dependency descriptions in each deliverable to determine edges
- Use the dependency graph diagram as structural guidance
- Do NOT read the spec's expected DAG — derive your decomposition purely from the goal

After producing the decomposition, compute:
- task_count
- graph_depth (longest path from any root to any leaf)
- parallelism_width (maximum number of tasks at the same depth level)
- max_fan_out (maximum number of tasks that depend on a single task)
- max_fan_in (maximum number of dependencies a single task has)

Compare your computed metrics against the spec's target ranges and DAG Success
Profile minimums. Report whether each metric falls within range.

---

### PART 3: Consistency Cross-Check

With your decomposition in hand, verify:

1. **Goal ↔ Decomposition**: Does every deliverable in the goal map to at least one
   task? Are there any deliverables you had to split or merge?

2. **Decomposition ↔ Spec DAG**: Does your decomposition's shape match the spec's
   expected DAG structure? Note any structural differences (different depth, different
   fan-out point, different convergence point).

3. **Metrics ↔ Spec ranges**: For any metric outside the spec's target range, is the
   spec range wrong or is the goal ambiguous?

4. **Self-contradictions**: Does the goal file contain any instruction that contradicts
   another instruction in the same file? (e.g., "each adapter is its own task" vs.
   something that implies bundling)

5. **Decomposer hazards**: Is there anything in the goal file that could cause a
   different LLM (Claude, Gemini, Llama) to produce a fundamentally different graph
   shape (flat, fully linear, or cyclic)?

---

### PART 4: Ship Verdict

Based on everything above, provide:

**Ship decision**: SHIP / SHIP WITH NITS / DO NOT SHIP

**Confidence**: How confident are you that this goal will reliably produce a diamond
DAG across 10 runs with different LLM decomposers? (High / Medium / Low)

**Remaining items** (if any): List only items that would block shipping. Mark
everything else as "nit" or "future improvement."

**Final grade**: Rate the goal's decomposition-friendliness:
- A: Will reliably produce a diamond DAG across models and runs
- A-: Will reliably produce a diamond DAG with minor variance in width/depth
- B+: Will usually produce a diamond DAG; occasional runs may flatten one level
- B: Hit or miss depending on the decomposer model
- C or below: Unreliable

---

### Output format

Keep your response under 1200 words. Use this structure:

```
## Round 2 Fix Verification
FIX A: [VERIFIED / NOT FIXED]  — one sentence
FIX B: [VERIFIED / NOT FIXED]  — one sentence
FIX C: [VERIFIED / NOT FIXED]  — one sentence

## Decomposition Simulation
[Table of tasks with task_id, task_name, dependencies]
[Computed metrics vs spec ranges]

## Consistency Cross-Check
[Numbered findings, one line each]

## Ship Verdict
Decision: [SHIP / SHIP WITH NITS / DO NOT SHIP]
Confidence: [High / Medium / Low]
Remaining items: [list or "None"]
Final grade: [A / A- / B+ / B / C]
```

Be direct. If something is clean, say "verified" and move on. Spend words only on
things that need attention.
```

---

## When to Run This

Run this Round 3 audit as the **final gate before creating the PR**. If the verdict
is SHIP or SHIP WITH NITS, proceed to PR. If DO NOT SHIP, fix the blocking items and
re-run this prompt.

This prompt is designed to be terminal — there should not be a Round 4. If Round 3
surfaces blocking issues, fix them and re-run Round 3 (not a new prompt).

---

## Audit Progression

| Round | File | Focus | Expected outcome |
|---|---|---|---|
| 1 | `gpt-audit-prompt.md` | Broad discovery | Find structural problems |
| 2 | `gpt-audit-prompt-2.md` | Fix verification + regression scan | Confirm fixes, catch side effects |
| 3 | `gpt-audit-prompt-3.md` (this file) | Final gate + decomposition sim | Ship/no-ship verdict |

---

## Cross-Model Value

This final audit is the most important one to run cross-model. The decomposition
simulation in Part 2 directly tests whether a non-Claude model would produce the
intended DAG shape from the goal text alone. If GPT 5.4 / Codex produces a flat
or linear decomposition, the goal needs more work regardless of what Claude does.
