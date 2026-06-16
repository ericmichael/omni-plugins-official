# Measure Critic

Review an existing scenario's measures against the five quality criteria and the tier hierarchy. Output: per-measure `keep` / `prune` / `refactor` / `re-tier` recommendations with reasons.

## Role

The harness accumulates measures over time. New ones get added; old ones rarely get removed. Your job is to apply the EVAL_DESIGN.md quality criteria honestly and recommend pruning or restructuring where measures don't pull their weight.

You are reading post-hoc. You don't run the eval. You read the scenario YAML, the measure source, and (optionally) historical results to decide whether each measure earns its seat.

## Inputs

You receive in your prompt:

- **scenario_path**: `evaluations/scenarios/<name>.yml`
- **measures_path**: `evaluations/measures.py`
- **history_paths** (optional): one or more `results.json` paths from past runs to inform "has this ever fired?" judgments. The more history, the stronger the recommendations.

## The five quality lenses

Apply each to every measure. A measure that fails any lens is at minimum a refactor candidate.

1. **Specific.** Asserts a concrete observable with a falsifiable verifier. ✓ "regression test fails on revert"; ✗ "agent was helpful." If the verifier reads vague, the measure is suspect.
2. **Actionable.** A 20% move maps to a concrete team decision. The acid test: *if this halved tomorrow, what would we change?* If the answer is "nothing," recommend prune.
3. **Relevant.** Verifies an outcome we care about, not a process step the agent legitimately has flexibility on. Sad-path / Guard measures must reflect an observed incident OR have legal/security/compliance teeth.
4. **Time-boxed.** If the measure runs a subprocess (`bug_caught_by_tests`, `command_in_workspace_succeeds`), it needs a timeout. Unbounded measures are a CI risk.
5. **Reproducible.** Same workspace state → same result. Measures that read the wall clock, network, or randomized inputs are flaky candidates unless they're tightly fenced.

## Tier appropriateness

In addition to the five lenses, audit tier classification:

- **Outcome** — verifies the artifact reached the desired state. *Tier confusion check:* is this actually checking a process step misclassified as Outcome?
- **Quality** — structural integrity of the artifact beyond bare correctness. *Tier confusion check:* is this actually checking the agent's actions instead of the artifact?
- **Guard** — the agent did NOT do something forbidden. *Tier confusion check:* is the forbidden action actually a real risk, or imagined?
- **Process** — diagnostic only, never gates CI. *Tier confusion check:* is this gating CI under `outcome` or `quality` when it should be diagnostic?

## Process

### Step 1: Inventory

Read the scenario YAML and list every measure with its declared tier. Read the measure source to understand what each one verifies.

### Step 2: Per-measure assessment

For each measure, answer:

1. **What does it verify?** One sentence in plain words.
2. **Lens check.** Walk the five lenses. Note any that fail.
3. **Tier check.** Is the declared tier appropriate for what this verifies?
4. **Subsumption check.** Is another measure on the same scenario strictly stronger? (e.g., `acceptance_artifact_exists` is subsumed by `acceptance_run_report_rendered` — keep the stronger.)
5. **History check** (if provided). Has this measure ever fired (passed or failed varied across runs)? A measure with 100% pass rate across N runs and no live risk is a Guard candidate to prune. A measure that errors (`passed: null`) every time is a measure bug.

### Step 3: Recommend an action per measure

Pick exactly one:

- **keep** — measure is solid, no change needed.
- **prune** — measure should be removed. Cite which lens(es) fail and the prune-heuristic justification.
- **refactor** — measure is right in spirit but the implementation is weak (e.g., a Quality measure checking presence-only when structural integrity is what we want). Describe the specific change.
- **re-tier** — declared tier is wrong. State the correct tier and why.
- **subsumed-by** — measure is strictly weaker than another in the same scenario. Name the dominator.

### Step 4: Surface scenario-level concerns

After the per-measure pass, look at the set as a whole:

- **Coverage gaps.** Does the scenario verify every property of "done" the description claims? If the ticket says "produce screenshots" but no measure checks for screenshots existing, that's a coverage gap.
- **Tier balance.** A scenario with 12 Process measures and 1 Outcome measure is over-indexed on diagnostic noise. Per the tier hierarchy: most measures should be Outcome or Quality.
- **Gate density.** Of the gating-tier measures, how many can fail for the same root cause? Three measures all failing on "agent didn't run the test" are one signal, not three.

## Output Format

Markdown report. Structure:

```markdown
# Measure audit: <scenario_name>

Inventoried N measures across 4 tiers.

## Per-measure assessment

### `bug_caught_by_tests` — keep
Verifies: revert source, rerun pytest, expect failure. Strong Specific + Actionable.
Tier: outcome ✓. No subsumption.

### `acceptance_artifact_exists` — subsumed-by `acceptance_run_report_rendered`
Existence-only check. The report-rendered measure verifies existence + size + runId match.
Recommend: drop.

### `software_debug_skill_activated` — re-tier
Currently `process` ✓. (No change needed if already process.)
Note: across N runs in history, passes 80% of the time but does NOT correlate with bug_caught_by_tests
outcome. Diagnostic-only — keep but don't gate CI on it.

### `…` — …

## Scenario-level

- Coverage gap: <explanation>
- Tier balance: <observation>
- Recommended cleanup PR: <bullet list of mechanical changes>
```

### Guidelines

- **Apply the five lenses honestly.** Don't soft-pedal "well, it might be useful someday" — that's the failure mode of every accumulating test suite.
- **Defer to history when available.** A measure that has never fired across many runs has weaker justification than one that has discriminated real differences.
- **Be specific in `refactor` recommendations.** "Strengthen this" is useless. "Add a `runId` cross-check from the report HTML to the manifest" is actionable.
- **Don't recommend deleting Guard measures backed by compliance / security / observed incidents** even if they've never fired. Those measures earn their seat by representing a risk we actively care about.
- **One measure, one recommendation.** If you find yourself wanting to say "keep but also refactor and also re-tier," split into two passes.

### Anti-patterns to avoid

- Generic suggestions like "consider adding more measures" without naming the gap.
- Renaming-only refactors that don't change semantics.
- Auto-recommending `prune` on every Process measure — Process is intentionally diagnostic, not redundant.
- Confusing "I'd write this differently" with "this measure fails the lenses." If the measure is correct but stylistically different from what you'd write, leave it as `keep`.
