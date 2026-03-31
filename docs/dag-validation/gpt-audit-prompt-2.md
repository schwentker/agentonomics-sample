# GPT 5.4 Audit Prompt (Round 2): Post-Revision Review

This is the **second-pass** audit prompt. Run it after applying fixes from the
Round 1 audit (`gpt-audit-prompt.md`). It focuses on verifying the fixes landed
correctly and catches regressions or new issues introduced by the changes.

Paste this prompt into GPT 5.4 (or Codex) along with the **updated** contents of:
1. `examples/goals/coding/complex_goal_dag.md`
2. `docs/dag-validation/complex-goal-dag-spec.md`

Optionally also attach:
3. `docs/dag-validation/spec.md` (the main DAG validation implementation spec)
4. The Round 1 audit output (so GPT can verify each finding was addressed)

---

## Prompt

```text
You are performing a second-pass review of two documents from the agentonomics-sample
benchmarking system. A first-pass audit was already completed and changes were applied.
Your job is to verify the fixes, catch regressions, and surface anything the first
round missed.

CONTEXT: This system compares single-agent vs multi-agent LLM architectures for
completing structured goals. It uses optional DAG validation to verify that
LLM-generated task decompositions form valid directed acyclic graphs before expensive
multi-agent orchestration begins.

The two documents:

FILE 1: `complex_goal_dag.md` — A benchmark goal describing a real MCP server project
(workato-comm-voices). Designed to produce a wide diamond DAG during LLM task
decomposition.

FILE 2: `complex-goal-dag-spec.md` — Design spec explaining the goal's intended DAG
properties, expected metrics, and position in the benchmark suite.

If provided, FILE 3: `spec.md` — Full implementation spec for the DAG validation
feature.

If provided, FILE 4: Round 1 audit output — The findings and verdicts from the
first-pass review.

---

### Round 1 identified these issues. Verify each fix:

#### FIX 1: Adapter dependency clarification
- **Round 1 finding**: Adapters were described as depending on "the shared Post type
  from the database layer" — ambiguous whether they need `db.ts` or just `types.ts`.
- **Expected fix**: Adapters depend on `types.ts` and `config.ts` only. They do NOT
  depend on `db.ts`. Persistence is handled by the aggregator.
- **Check**: Is the wording now unambiguous in the goal file? Does the dependency
  graph match? Does the spec's DAG diagram agree?

#### FIX 2: Reddit live fetch flakiness
- **Round 1 finding**: Live Reddit API dependency makes benchmark runs externally
  flaky.
- **Expected fix**: RedditAdapter falls back to a recorded fixture when the live API
  is unreachable. Success criteria updated accordingly.
- **Check**: Is the fallback described in the deliverable AND the success criteria?
  Is the fixture path specified?

#### FIX 3: Explicit adapter task separation
- **Round 1 finding**: Deliverable 2 lumped all four adapters into one deliverable.
  Some LLMs would keep it as one task, collapsing the fan-out.
- **Expected fix**: Explicit directive that each adapter should be its own task in
  decomposition.
- **Check**: Is the directive present and unambiguous? Is it phrased as an
  instruction to the decomposer, not just a description?

#### FIX 4: Deployment deliverable split
- **Round 1 finding**: Deliverable 9 mixed deployment config, Docker, env template,
  and tsconfig into one bundle.
- **Expected fix**: Split into separate deliverables (tsconfig/.env vs Dockerfile/fly.toml).
- **Check**: Are the two deliverables clearly scoped? Do their dependency
  descriptions make sense independently?

#### FIX 5: Metric ranges widened
- **Round 1 finding**: Expected metrics were too narrow for LLM decomposition variance.
- **Expected fix**: Broader ranges with explanatory notes. "Should produce" replaced
  with "target shape is." New "Acceptable Decomposition Merges" table and "DAG Success
  Profile" section added to the spec.
- **Check**: Are the ranges credible? Do the merge descriptions match the updated
  dependency graph? Are the minimum pass thresholds in the DAG Success Profile
  reasonable (not too loose, not too tight)?

#### FIX 6: Fan-out source corrected in spec
- **Round 1 finding**: Spec said fan-out branches from `db.ts` but adapters don't
  depend on db.
- **Expected fix**: Fan-out branches from `config.ts` (+ `types.ts`).
- **Check**: Is this consistent across the spec's prose, table, and DAG diagram?

---

### Then perform these additional checks:

#### A. REGRESSION SCAN — Did the fixes break anything?

- Do the updated dependency graphs in both files still match each other?
- Did the deliverable renumbering (now 10 deliverables instead of 9) propagate
  correctly through all references?
- Are there any new contradictions between the goal file and the spec?
- Does the "Relationship to Other Goals" table in the spec still hold after
  the structural changes?

#### B. DECOMPOSITION SIMULATION — Walk through it as the LLM

Pretend you are the task decomposer LLM receiving `complex_goal_dag.md` as input.
Produce a plausible decomposition (task names + dependency lists) and compare it
against the spec's expected DAG structure:

- How many tasks did you produce?
- What is the graph depth?
- Where is the widest parallel level?
- Does it match the spec's target ranges?
- If it doesn't match, is the goal or the spec at fault?

#### C. EDGE CASES — What could still go wrong?

- Could a decomposer treat the "Dependency Graph" section as literal task names
  (e.g., create a task literally called "types.ts (hub — no deps, everything
  depends on it)")?
- The goal now has 10 deliverables. Is that too many for reliable decomposition,
  or does the explicit numbering help?
- The "Acceptable Decomposition Merges" section is in both files. Could this
  confuse the decomposer if it reads the goal file? (The goal is input to the
  decomposer; the spec is not.)
- Is the fixture path `fixtures/reddit_r_workato.json` referenced but never
  defined? Should there be a deliverable or note about creating the fixture file?

#### D. BENCHMARK INTEGRATION — Will this work end-to-end?

- Can `python benchmark.py --goal examples/goals/coding/complex_goal_dag.md --validate-dag`
  actually run this goal? Are there any assumptions about the benchmark runner
  that this goal violates?
- The goal asks for Node.js/TypeScript output. Does the benchmark runner support
  non-Python output, or is there a mismatch?
- The DAG Success Profile minimum thresholds — would the existing validator code
  in `src/` actually check against these, or are they documentation-only?

---

### Output format

For each of the 6 Round 1 fixes, provide:
- **Status**: VERIFIED / PARTIALLY FIXED / NOT FIXED / REGRESSED
- **Detail**: One sentence explaining the status

For each of the 4 additional checks (A–D), provide:
- **Verdict**: PASS / PASS WITH NOTES / NEEDS WORK / FAIL
- **Findings**: Specific items ordered by severity (High/Medium/Low)

Then provide a **final assessment**:
- Ready to merge? (YES / YES WITH MINOR NOTES / NO)
- Remaining risk items (if any)
- Grade the goal's decomposition-friendliness after fixes: A / B+ / B / B- / C

Keep your response under 1500 words. Be direct. If something is verified and clean,
say so in one line and move on. Spend your words on anything that still needs attention.
```

---

## When to Run This

Run this Round 2 audit **after** applying all changes from Round 1 and **before**
creating the pull request. The goal is to catch any regressions from the fixes
and get a final merge confidence signal.

If Round 2 comes back clean (all fixes VERIFIED, no NEEDS WORK verdicts), the
files are ready for PR.

If Round 2 surfaces new issues, fix them and run this prompt again — it is
designed to be idempotent.

---

## Differences from Round 1

| Aspect | Round 1 (`gpt-audit-prompt.md`) | Round 2 (this file) |
|---|---|---|
| **Focus** | Broad discovery — find problems | Targeted verification — confirm fixes |
| **Structure** | 5 open-ended audit areas | 6 specific fix checks + 4 new checks |
| **Expected output** | Findings + severity | Fix status + regression scan |
| **When to use** | First review of new goal | After applying Round 1 changes |
| **Reusable** | Once per goal | Repeatable until clean |

---

## Cross-Model Value

Like Round 1, this audit is intentionally cross-model. Running it through GPT 5.4
(or Codex) after changes were authored by Claude provides:

1. **Fix verification by a different reasoner** — Claude may consider its own fixes
   complete; GPT checks independently
2. **Regression detection** — a fresh model is better at spotting unintended
   side effects from edits
3. **Decomposition simulation** — GPT's simulated decomposition tests whether the
   goal works for a model that didn't write it
