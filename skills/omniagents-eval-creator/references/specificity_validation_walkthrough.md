# Specificity Validation Walkthrough

How to prove your measures pass on a hand-completed solution — the second leg of EDD validation.

Read this when you're at **Phase 4c** of the workflow, after sensitivity has proven the measures fire on a bad run, and now you need to prove they pass on a good run for the right reason.

## The premise

Sensitivity told you the measure catches the bad path. It says nothing about whether the measure passes for the right reason on the good path. A measure that always passes (or passes for a coincidental reason) is just as broken as one that never fires.

You catch this by hand-completing the work the way an ideal agent would, then running every workspace-state measure against that solution. Every one must pass for the right reason. If any fails, the bug is in *the measure*, not the agent.

This is the load-bearing reason we have a scenario YAML separate from a measures.py: the scenario describes "what done means" and the measures verify it. If your hand-done solution is good but a measure still fails, the measure isn't measuring what the scenario says it is.

## The pattern

There are two parts: produce the solution workspace, then run a tiny harness that exercises each measure.

### Part 1: build the solution workspace

```bash
# Copy the fixture into a scratch dir somewhere outside /tmp (tmpfs has a quota).
SRC=evaluations/fixtures/workspaces/<fixture_name>
DEST=$HOME/scratch/<fixture_name>_solution
rm -rf "$DEST"
cp -r "$SRC" "$DEST"

# Initialize as a git repo so scope_respected has a baseline to diff against.
cd "$DEST" && git init -q && git add -A && git commit -q -m "fixture baseline"
```

Now do the work the way an ideal agent would, by hand:

1. Apply the source fix.
2. Add real regression tests that fail when the source is reverted (verify both directions: pytest passes now AND fails on revert).
3. Install deps if the scenario uses a frontend (`npm --prefix frontend ci` etc.).
4. Run any acceptance tooling the scenario expects (e.g. scaffold the runner, write a story, run it green).
5. Don't simulate work the framework will do — just leave the workspace in the final state an ideal agent would.

### Part 2: a small harness that runs the measures

The harness constructs a stub `EvalContext` with `expect` from the scenario YAML and `environment_context` pointing at your solution workspace + the pristine fixture. Then it imports each measure from your project's `evaluations/measures.py` and calls it directly.

```python
"""Specificity check for <scenario_name>.

Adapt the four PROJECT-SPECIFIC paths at the top, and the
WORKSPACE_MEASURES list to match what's in the scenario's `measures` block.
"""
from __future__ import annotations

import sys
import yaml
from pathlib import Path

# ── PROJECT-SPECIFIC PATHS ────────────────────────────────────────────
PROJECT_ROOT = Path("/home/emm/Omni/Workspace/omni-code")
WORKSPACE = Path("/home/emm/scratch/fitness_solution")
FIXTURE_SRC = PROJECT_ROOT / "evaluations" / "fixtures" / "workspaces" / "fitness_tracker"
SCENARIO_FILE = PROJECT_ROOT / "evaluations" / "scenarios" / "autopilot_fitness_bug.yml"
# ──────────────────────────────────────────────────────────────────────

sys.path.insert(0, str(PROJECT_ROOT))
from omniagents.core.evaluation import EvalContext
from evaluations import measures as M

# Only measures that depend on workspace state. Tool-call / process measures
# require an agent transcript, which we don't have — sensitivity covers them.
WORKSPACE_MEASURES = [
    "scope_respected",
    "no_test_disabling",
    "bug_caught_by_tests",
    "command_in_workspace_succeeds",
    "acceptance_run_manifest_well_formed",
    "acceptance_run_completed",
    "acceptance_run_has_passing_story",
    "acceptance_per_story_manifests_consistent",
    "acceptance_run_has_evidence",
    "acceptance_run_report_rendered",
]


def _load_expect() -> dict:
    cfg = yaml.safe_load(SCENARIO_FILE.read_text())
    return cfg["scenarios"][0]["expect"]


def _make_ctx(expect: dict) -> EvalContext:
    return EvalContext(
        metadata={
            "scenario": {"expect": expect},
            "environment_context": {
                "workspace_root": str(WORKSPACE),
                "fixture_src_dir": str(FIXTURE_SRC),
            },
        },
    )


def main() -> int:
    if not WORKSPACE.is_dir():
        print(f"workspace does not exist: {WORKSPACE}")
        return 2

    expect = _load_expect()
    ctx = _make_ctx(expect)

    failures = 0
    for name in WORKSPACE_MEASURES:
        fn = getattr(M, name, None)
        if fn is None:
            print(f"SKIP {name}: not found in measures module")
            continue
        # @evaluation_measure-decorated callables expose their underlying fn.
        impl = getattr(fn, "_measure_fn", None) or fn
        try:
            result = impl(ctx)
        except Exception as exc:
            print(f"FAIL {name}: raised {type(exc).__name__}: {exc}")
            failures += 1
            continue
        passed = bool(result.get("passed"))
        reason = result.get("reason", "")
        tag = "PASS" if passed else "FAIL"
        print(f"{tag} {name}: {reason}")
        if not passed:
            failures += 1

    print()
    print("-" * 50)
    print(f"{len(WORKSPACE_MEASURES) - failures}/{len(WORKSPACE_MEASURES)} measures passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Save this as e.g. `scripts/check_measures_specificity.py` in your project. Adapt the four PROJECT-SPECIFIC paths and the `WORKSPACE_MEASURES` list to match your scenario.

## Reading the output

Every line is `PASS <measure>: <reason>` or `FAIL <measure>: <reason>`.

Two failure modes are interesting:

**1. Genuine measure bug.** The work IS complete and correct, but a measure fails for a wrong reason. Common patterns:

- *Path resolution bug.* The measure resolves a workspace-relative path against the eval-process cwd instead of `workspace_root`. Fix: thread `Path(workspace) / rel_path`.
- *Schema mismatch.* The measure expects a JSON shape the runner doesn't actually produce. Fix: read the runner output, update the schema check.
- *Hardcoded absolute path.* Measure assumes `/tmp/...` when the workspace is elsewhere. Fix: read the path from `ctx.expect`.
- *Subprocess timeout too short.* Measure times out on a slower machine. Fix: bump default and surface in `ctx.expect`.

**2. The work is missing a property the scenario claims.** You thought you completed everything but a measure caught a real gap. Either complete the missing piece, or accept the property doesn't actually belong in the scenario and prune it.

If a measure passes but you suspect it's passing for the wrong reason (e.g., a hash collision, a coincidence), strengthen the verifier: add a content check, a runId cross-reference, or a structural property that's hard to satisfy by accident.

## When this exposed real bugs

The first time we ran specificity against a hand-completed fitness-tracker solution, two real bugs surfaced that sensitivity wouldn't have caught:

- **`acceptance_run_has_evidence` measure was broken.** It checked `Path(cp_path).is_file()` directly, but the runner emits workspace-relative paths when invoked with a relative `--out-root`. The measure was resolving against the eval process's cwd, so it false-failed when the file actually existed. Fixed by resolving relative paths against `workspace_root`.
- **Runner template bug** (in the `webapp-acceptance-runner` skill). `expectTextEquals` and similar emit `const __textEq = …` per step, so two of the same kind in one story → `SyntaxError: Identifier '__textEq' has already been declared`.

This is the value of EDD: validating measures surfaces problems in the things measures depend on. Without specificity, the framework would have happily reported the first bug as "agent failure" forever.

## What this doesn't cover

This walkthrough exercises only **workspace-state** measures. The tool-call / Process / Guard measures need an actual agent transcript to evaluate (you can't fake `ctx.tool_calls(...)` cleanly). Those are validated by sensitivity — when an agent run produces a real trace, the trace-based measures fire.

If you want to validate trace-based measures separately, build a fake `EvalContext` with synthetic tool calls and run them against it. That's a different harness pattern; consider writing a unit test under your project's `tests/` rather than this walkthrough's shape.

## TL;DR

1. Hand-complete the scenario in a copy of the fixture.
2. Run the harness above (adapt the paths + measure list).
3. Every measure must pass for the right reason.
4. Failures = bugs in measures, not the agent. Fix the measure, not the work.
