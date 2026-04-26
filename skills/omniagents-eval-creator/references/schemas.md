# Schemas

JSON / YAML shapes that the omniagents framework and the scripts in this skill depend on. Read this when adding a new measure, parsing results programmatically, or extending the reviewer.

---

## Scenario YAML (`evaluations/scenarios/<name>.yml`)

```yaml
scenarios:
  - name: <snake_case_unique_id>
    fixture: <fixture_workspace_name>           # Optional. Path under evaluations/fixtures/workspaces/
    db_fixture: <db_fixture_name>               # Optional. <name>.db under evaluations/fixtures/dbs/
    runs_per_prompt: 5                          # Default: 1. 5 is the standard for non-deterministic agents.

    # Single-turn / sentinel-loop:
    prompt: |                                   # The user's initial message
      <generic supervisor framing>

    # OR multi-turn scripted:
    prompts:
      - |
        first prompt
      - |
        follow-up prompt that probes some property

    continuation_prompt: |                      # Used when max_continuations > 0
      <generic continuation guidance>

    max_continuations: 15                       # 0 = no continuation loop
    until_sentinel: "[DONE]"                    # Stop continuation loop on this token in agent output
    until_sql: |                                # Stop on SQL match (db_fixture only)
      SELECT 1 FROM tickets WHERE …

    expect:                                     # Read by measures via ctx.expect
      assert_sql: |                             # db_row_exists reads this
        SELECT 1 FROM …
      command: "uv run pytest -q 2>&1"          # command_in_workspace_succeeds reads this
      command_timeout_s: 240
      revert_target: "src/path/to/file.py"      # bug_caught_by_tests reads this
      test_command: "uv run pytest -q 2>&1"
      test_timeout_s: 240
      min_ticket_moves: 2                       # ticket_moved_through_pipeline reads this
      allowed_modified: ["<path>", ...]         # scope_respected reads these
      allowed_new: ["<path>", ...]
      allowed_new_dirs: ["<dir>/", ...]
      forbidden_bash_patterns: ["<substr>", ...] # no_remote_operations override
      tests_dir: "tests"                        # no_test_disabling override
      # ... arbitrary additional keys for custom measures

    judges: [<judge_name>, ...]                 # Optional. References evaluation.yml::judges

    measures:                                   # Tier-keyed (canonical) OR flat list (legacy)
      outcome:
        - bug_caught_by_tests
        - db_row_exists
        - command_in_workspace_succeeds
      quality:
        - scope_respected
      guard:
        - no_remote_operations
        - no_test_disabling
      process:
        - mcp_used_to_discover_ticket
        - <skill>_skill_activated
```

Either shape works (the loader handles both); prefer tier-keyed for new scenarios.

---

## Measure return dict

Every `@evaluation_measure`-decorated function returns:

```python
{
    "name": "measure_name",                # injected by the framework
    "passed": True | False | None,         # None = skipped (vacuous pass / not applicable)
    "reason": "human-readable string",
    "tier": "outcome" | "quality" | "guard" | "process",  # injected post-tier-patch
    # ... arbitrary structured fields the measure adds (paths, counts, output_tail, etc.)
}
```

Use the helpers from `omniagents.core.evaluation`:

```python
from omniagents.core.evaluation import pass_reason, fail_reason

return pass_reason("found 3 evidence files", count=3, paths=[...])
return fail_reason("manifest missing required field: runId", field="runId")
```

---

## results.json

Written by the eval pipeline to `artifacts/eval/results/<timestamp>/results.json`.

```json
{
  "runs": [
    {
      "scenario": "<scenario_name>",
      "session_id": "<uuid>",
      "scenario_config": { /* the full scenario YAML, embedded */ },
      "prompts": [{"role": "user", "content": "..."}],
      "final_assistant_text": "[DONE]",
      "duration_seconds": 195.2,
      "exchanges": 1,
      "break_reason": "sentinel" | "max_continuations" | "until_sql" | "error",
      "history_len": 84,
      "tool_call_count": 23,
      "transcript_path": "target/eval_transcripts/...-<scenario>.json",
      "metadata": { /* judge results, environment_context, etc. */ },
      "measures": [
        {
          "name": "bug_caught_by_tests",
          "passed": false,
          "reason": "tests still pass with src/...py reverted",
          "tier": "outcome",
          "output_tail": "..."
        }
      ],
      "usage": { /* token usage */ }
    }
  ],
  "metrics": [
    {
      "name": "skill_activation_rate",
      "label": "Skill activation",
      "type": "pass_rate",
      "value": 0.6,
      "target": {"op": ">=", "value": 0.9},
      "meets_target": false
    }
  ],
  "stats": {
    "total_scenarios": 1,
    "included_scenarios": 1,
    "skipped_unmeasured": 0,
    "unknown_measures": {},
    "measures_discovered": [...],
    "measures_discovered_count": 18
  }
}
```

For multi-run scenarios (`runs_per_prompt > 1`), all N runs land in the same `runs[]` array.

---

## Transcript (`target/eval_transcripts/<ts>-<scenario>.json`)

```json
{
  "scenario": "<scenario_name>",
  "scenario_id": null,
  "session_id": "<uuid>",
  "exported_at": "2026-04-26T11:11:32.870Z",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": [{"type": "output_text", "text": "..."}]},
    {"role": null, "type": "function_call", "name": "list_tickets", "arguments": "{}", "call_id": "..."},
    {"role": null, "type": "function_call_output", "output": "...", "call_id": "..."},
    {"role": null, "type": "reasoning", "summary": [...]}
  ]
}
```

Roles: `"user"` (input prompts and tool outputs), `"assistant"` (model text), `null` (the type field carries the meaning — `function_call`, `function_call_output`, `reasoning`).

---

## EvalContext (passed to every measure)

`ctx: EvalContext` (from `omniagents.core.evaluation`).

```python
ctx.expect                    # dict — the scenario's `expect:` block
ctx.metadata                  # dict — judge results + environment_context
ctx.metadata["environment_context"]["workspace_root"]
ctx.metadata["environment_context"]["fixture_src_dir"]   # pristine fixture (for revert+rerun)
ctx.metadata["environment_context"]["db_path"]           # if db_fixture used

ctx.tool_calls("<name>")      # list[ToolCall] — calls by tool name (empty list if none)
ctx.tool_outputs("<name>")    # list[ToolOutput]
ctx.first_tool("<name>")      # first ToolCall by name, or None
ctx.latest_tool("<name>")     # last ToolCall by name, or None

ctx.history                   # list[dict] — full message history (same shape as transcript)
ctx.final_assistant_message   # the last assistant message
```

`ToolCall.args` is a dict with the call's input arguments. `ToolCall.output` is the linked tool result.

---

## Tier semantics

Defined in `omniagents/core/eval/measure_tiers.py`:

```python
KNOWN_TIERS = ("outcome", "quality", "process", "guard")
GATING_TIERS = frozenset(("outcome", "quality", "guard"))
DEFAULT_TIER = "outcome"
```

CI gating rule: a per-run measure failure gates CI iff the measure's tier is in `GATING_TIERS` (or unknown — legacy-safe). Process measures are recorded but never gate.

The framework attaches `tier` to each measure result based on the scenario's `measures:` declaration. The reviewer / comparator scripts in this skill also handle the legacy-flat-list case by treating all measures as `outcome`.

---

## Feedback (`feedback.json`, downloaded from the reviewer)

```json
{
  "reviews": [
    {"run_id": 0, "feedback": "agent shortcut [DONE]", "timestamp": "2026-04-26T18:00:00Z"},
    {"run_id": 1, "feedback": "", "timestamp": "..."},
    {"run_id": 2, "feedback": "looks good", "timestamp": "..."}
  ],
  "status": "complete"
}
```

Empty `feedback` strings mean the user thought it was fine. Focus iteration on entries with substantive feedback.
