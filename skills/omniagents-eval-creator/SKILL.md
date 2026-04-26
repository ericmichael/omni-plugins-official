---
name: omniagents-eval-creator
description: Design, validate, and iterate on omniagents evaluation scenarios for agentic coding workflows. Use this skill whenever the user wants to create a new eval scenario, audit existing measures, hill-climb an agent's prompt or skill against a measurable bar, debug why an eval result looks the way it does, or set up a CI gate against agent behavior in an omniagents-based project. Triggers on phrases like "write an eval for X", "create a scenario", "add a measure", "why are we failing this scenario", "validate measures before tuning", "compare iterations", "specificity check", or "review eval results". Especially when the project uses `omniagents.cli eval suite run`, has an `evaluations/scenarios/` tree, or imports from `omniagents.core.evaluation`. Also use when discussing eval design principles for agents (Outcome / Quality / Process / Guard tiers, end-state-first design, sensitivity vs specificity validation).
---

# omniagents-eval-creator

A skill for designing, validating, and iterating on omniagents evaluation scenarios. Built around three principles:

1. **End-state first.** Define done before writing the prompt. Derive verifiers, then derive the minimum input.
2. **Validate measures before hill-climbing.** Sensitivity (catches bad runs) AND specificity (passes good runs) — both, every time, before optimizing prompts/skills.
3. **Tier-aware gating.** Outcome / Quality / Guard gate CI; Process is diagnostic only.

This skill orchestrates the workflow and delegates specific tasks to focused subagents and scripts.

## When to use this skill

Trigger this skill whenever the user is doing eval *authoring* or *iteration* — creating a new scenario, drafting a measure, validating a hand-completed solution, comparing iterations, reviewing failures, or auditing measures for relevance.

Skip it when:

- The user is just *running* an existing eval (`omniagents.cli eval suite run`) — no skill needed.
- The user is asking general questions about LLM evaluation theory unconnected to omniagents — point them at the framework but don't do the full skill workflow.

## The workflow

There are five phases. The user may be at any of them. Figure out where they are and jump in.

### Phase 1 — Capture intent

What behavior is the eval verifying? Happy path or sad path? What's the *artifact* that represents "done"?

**Questions to ask** (be tight; the goal is to set up phase 2 quickly):

1. What does the agent need to do? In one sentence.
2. What does the *artifact* look like at the end? Codebase state, DB row, file output, screenshot — point at it.
3. Have we observed the failure mode this scenario probes? (If sad-path: do we have evidence, or is it imagined? See the prune heuristic in `references/eval_design.md`.)

If the user can't name the artifact, that's a sign the scenario isn't scoped clearly enough yet.

### Phase 2 — End-state-first design (interview)

For each property of the end state that matters, get a verifier hint. Drop properties that have no verifier — they don't belong in the eval.

**The verifier hierarchy** (prefer earlier):

1. **Deterministic** — file exists, JSON parses, byte compare, SQL row exists.
2. **Threshold** — count > N, latency < X, size > Y.
3. **Subprocess** — run a command, check exit code.
4. **Revert+rerun** — write known-bad input, rerun a command, expect a specific result, restore.
5. **Tool-call-pattern** — examine the agent's trace for presence/absence.
6. **Oracle** — Claude judge call. Last resort. Expensive, slow, non-deterministic.

For each property: name the verifier shape and what input it needs. If you find yourself reaching for an oracle, double-check whether a deterministic version is possible.

After the interview you should have:

- Goal sentence
- End-state description
- A list of `(property, verifier_hint, tier)` triples
- An existing fixture name OR `"new"` (and same for db_fixture)

### Phase 3 — Draft

Hand off to the **scenario-author** subagent (`agents/scenario-author.md`). Pass it the interview output. It produces:

- Full scenario YAML (under `evaluations/scenarios/<name>.yml`)
- Fixture skeleton checklist
- Measures-still-needed handoff list

For each "measures still needed" entry, hand off to the **measure-author** subagent (`agents/measure-author.md`). It produces a single `@evaluation_measure` function for `evaluations/measures.py`.

Templates live under `assets/`:

- `assets/scenario_template.yml` — tier-keyed scenario boilerplate
- `assets/measure_template.py` — `@evaluation_measure` stub
- `assets/seeder_template.py` — DB fixture seeder skeleton

### Phase 4 — Validate

Two non-negotiable validations before you let an agent loose on the scenario.

**4a. Pre-flight (`scripts/validate_scenario.py`).** Cheap. Catches typos, missing fixtures, missing builders, tier name typos, missing timeouts. Run it first; fix everything it complains about; don't proceed until it's clean.

```bash
python scripts/validate_scenario.py --file evaluations/scenarios/<name>.yml
```

**4b. Sensitivity** (catches bad runs). Run the scenario against an unmodified agent. The Outcome and Quality measures should fire on the seeded "broken" state. If they don't, the bad path is too easy to reach by accident — make the scenario more representative.

```bash
python -m omniagents.cli eval suite run -P project.yml \
    --select 'name:<scenario_name>' --reporter pretty
python scripts/generate_review.py  # human-readable review
```

**4c. Specificity** (passes good runs). Hand-complete the scenario in a copy of the fixture — do the work the way an ideal agent would. Then run all workspace-state measures against that solution. Every measure must pass for the right reason.

The pattern is documented in `references/specificity_validation_walkthrough.md` — copy the harness code from the doc, adapt the four project-specific paths and the `WORKSPACE_MEASURES` list, and run. When measures fail on the good solution, the bug is in the *measure* (not the agent) — fix it.

Don't proceed to phase 5 until 4a + 4b + 4c are all green for the right reasons.

### Phase 5 — Iterate

Hill-climb on prompts/skills, never on "stronger user input." Strict intervention hierarchy:

1. **Extend an existing skill** — first preference.
2. **Create a new focused skill** — when the failure mode doesn't fit any existing skill's scope.
3. **System prompt** — last resort, only after the same principle has shown up in 3+ unrelated workflows AND the rest of the suite is green.

Each iteration:

1. Run the eval with the change. `runs_per_prompt: 5` for stable signal.
2. Compare to the prior iteration: `python scripts/compare_iterations.py`.
3. Spawn the **result-analyzer** subagent (`agents/result-analyzer.md`) to surface non-obvious patterns.
4. Decide: shipped (move on), or another lever to try (return to step 1).

Don't pre-stack interventions. Change one lever per round.

### Phase 6 — Maintenance

Periodically (or before merging into the CI suite), audit the measures with the **measure-critic** subagent (`agents/measure-critic.md`). Measures that have never fired across many runs and don't represent live risk are pruning candidates. Process measures that don't correlate with Outcome are dead weight.

The five quality lenses (`references/eval_design.md`):

1. Specific — concrete observable + falsifiable verifier
2. Actionable — a 20% move maps to a concrete team decision
3. Relevant — observed failure mode OR legal/security/compliance teeth
4. Time-boxed — wall-clock cap, configurable per measure
5. Reproducible — same fixture + same agent → comparable score

## Phase routing — figure out where the user is

When the skill triggers, read the conversation. Common entry points:

- **"Write an eval for X"** → Phase 1.
- **"I have a draft scenario, run it"** → Phase 4 (validate first).
- **"Why are we failing this measure?"** → spawn `result-analyzer` (Phase 5).
- **"This scenario has been growing — should we prune?"** → spawn `measure-critic` (Phase 6).
- **"I added a measure, does it actually work?"** → Phase 4c (specificity check).
- **"How do iterations compare?"** → `scripts/compare_iterations.py` (Phase 5).

## Bundled resources

### Scripts (`scripts/`)

Run from the omniagents-based project's root.

- **`validate_scenario.py`** — Pre-flight: YAML parses, named measures exist, fixtures + db builders present, tier names valid, paths in `allowed_modified` exist. Exit 1 on errors. Run as the first gate.
- **`generate_review.py`** — Tier-aware HTML reviewer over `results.json` + transcripts. Two tabs (Runs + Summary), per-run measures grouped by tier, deltas vs `--previous`, per-run feedback textarea. `--static` for headless. Stdlib only.
- **`compare_iterations.py`** — Diff two `results.json` runs by tier + measure. Defaults to latest two under `artifacts/eval/results/`. `--markdown` for PR descriptions, `--json` for CI consumption.
(Specificity validation: see `references/specificity_validation_walkthrough.md` — copy the harness code into a project-local script, since the actual paths and measure list are scenario-specific.)

### Agents (`agents/`)

Spawn as subagents. Each is a focused role.

- **`scenario-author.md`** — Draft a scenario YAML + fixture skeleton + measures-still-needed handoff. Doesn't write measure bodies.
- **`measure-author.md`** — Draft a single `@evaluation_measure` from a property + verifier hint + tier. Doesn't pick the tier.
- **`result-analyzer.md`** — Read a `results.json` + selected transcripts; surface non-obvious patterns; recommend the next intervention from the hierarchy.
- **`measure-critic.md`** — Audit existing measures against the five lenses + tier appropriateness. Output keep/prune/refactor/re-tier per measure.

### References (`references/`)

Loaded on demand.

- **`eval_design.md`** — The full framework: five quality criteria, end-state-first design procedure, Outcome/Quality/Process/Guard tier hierarchy, autopilot fitness scenario as worked example.
- **`measures_catalog.md`** — Common measure patterns and verifier shapes. Use as a starting point when handing to `measure-author`.
- **`schemas.md`** — JSON shapes the framework and scripts depend on: scenario YAML, results.json, measure return dict, evals.json equivalent.

### Assets (`assets/`)

Templates to copy + adapt.

- **`scenario_template.yml`** — Tier-keyed scenario boilerplate with the canonical structure.
- **`measure_template.py`** — `@evaluation_measure` stub with the standard signature.
- **`seeder_template.py`** — DB-fixture seeder skeleton (omni-projects MCP cli over stdio).

## Communication tone

Users will range from "I want to add an eval to my CI" to "I'm new to evals." Default to specific, terse responses. Explain "tier" / "sensitivity vs specificity" / "verifier" briefly when first introducing them; assume the user has internalized them after that.

Two terms worth always-explaining when first introducing the concept:

- **Tier** — Outcome (gates CI), Quality (gates), Guard (gates), Process (diagnostic only). Every measure has one.
- **Sensitivity / specificity** — sensitivity = the measure fires when the work is genuinely bad. Specificity = the measure passes when the work is genuinely good. Both are required.

Skip the deeper theory unless asked; the principles are what matter.

## Anti-patterns this skill exists to prevent

- **Designing the prompt before defining "done."** End-state first. Always.
- **Hill-climbing on unvalidated measures.** Sensitivity AND specificity, before any prompt/skill changes.
- **Adding measures because they "feel" useful.** Five lenses applied honestly, every time.
- **Tier-confusion** — putting Process measures under Outcome and gating CI on them. Process is diagnostic.
- **"Stronger user input" as the fix.** The user prompt absorbs real-world ambiguity. Fix the agent's instructions (skill or system prompt), never the eval scenario's prompt.
- **Pre-stacking interventions.** One lever per round. If A and B might both help, propose A, measure, then decide on B.

## Cross-references

- `references/eval_design.md` — full framework
- omni-code's `evaluations/AGENTS.md` (the operator's guide) — running, inspecting, MCP fixtures, intervention hierarchy details
- omniagents framework: `omniagents/core/eval/measure_tiers.py` (tier semantics), `omniagents/core/evaluation/registry.py` (`@evaluation_measure` decorator)
