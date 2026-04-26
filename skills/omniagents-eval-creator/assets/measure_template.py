"""Template for a new @evaluation_measure.

Replace every <PLACEHOLDER>. Drop into evaluations/measures.py.

See references/measures_catalog.md for verified patterns by verifier shape:
deterministic, threshold, subprocess, revert+rerun, tool-call-pattern, oracle.

Standard checklist before merging:
  □ Tier classification matches what the measure verifies (outcome /
    quality / guard / process).
  □ Configurable inputs read from ctx.expect with sensible defaults.
  □ Subprocess (if any) has a timeout from ctx.expect.
  □ Mutations to the workspace use try/finally to restore.
  □ Pass/fail messages are specific (the dev shouldn't have to re-read
    the workspace to understand why).
  □ Sensitivity tested: the measure FAILS on a known-bad input.
  □ Specificity tested: the measure PASSES on a hand-completed solution
    for the right reason.
"""

from __future__ import annotations

# Standard imports for measures. Add `subprocess` / `json` / `re` etc. as
# needed. Path is the most common helper.
from pathlib import Path

from omniagents.core.evaluation import (
    EvalContext,
    evaluation_measure,
    fail_reason,
    pass_reason,
)


@evaluation_measure
def <MEASURE_NAME>(ctx: EvalContext) -> dict:
    """<ONE-LINE SUMMARY: what passes vs what fails.>

    Reads from ctx.expect:
      - <KEY>: <description, default value>

    Reads from environment_context:
      - workspace_root: the per-run tempdir
      - fixture_src_dir: pristine fixture (only if revert+rerun)
    """
    # ── 1. Resolve required inputs from context ─────────────────────
    env_ctx = ctx.metadata.get("environment_context", {})
    workspace = env_ctx.get("workspace_root")
    if not workspace:
        # Missing environment context = eval setup is broken (not the
        # agent's fault). Fail loudly so the developer notices.
        return fail_reason("no workspace_root in environment context")

    # ── 2. Resolve scenario configuration with sensible defaults ────
    target_path = ctx.expect.get("<CONFIG_KEY>", "<DEFAULT>")
    if not target_path:
        # Vacuous pass: this scenario didn't ask for this check.
        return pass_reason("no <CONFIG_KEY> specified")

    # ── 3. Compute the verification ─────────────────────────────────
    # Replace this block with the actual check. See measures_catalog.md
    # for shapes by verifier type.
    full = Path(workspace) / target_path
    if not full.is_file():
        return fail_reason(
            f"missing artifact: {target_path}",
            # Structured fields make the result more useful in the
            # reviewer / comparator. Add what's helpful for debugging.
            target=str(full),
        )

    # ── 4. Pass with specific evidence ──────────────────────────────
    return pass_reason(
        f"<HUMAN-READABLE PASS REASON> ({full.stat().st_size} bytes)",
        path=str(full),
        size=full.stat().st_size,
    )
