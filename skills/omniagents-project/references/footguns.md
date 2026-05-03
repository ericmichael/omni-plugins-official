# Footguns reference

Things the OmniAgents framework enforces silently or by convention. None of these are documented prominently in the framework itself, but each one will eat a half hour of debugging if you miss it.

## Naming and layout

### Agent directory name must match `name:` in agent.yml exactly

`agents/foo/agent.yml` must contain `name: foo`. The framework validates this at project load time and raises `ValueError` with a clear message if they mismatch — but only at load time, so a mismatch from a copy-paste or rename won't surface until you try to run.

```
agents/
└── clinical_reasoning/
    └── agent.yml          # MUST have:  name: clinical_reasoning
```

When migrating from a basic single-agent dir, this is the most common mistake. Double-check after `mv`.

### Project name and agent name follow the same rules

Lowercase letters, digits, underscores. Must start with a letter. Max 64 chars. Validated by `omniagents new` (sanitizes input) and at project load time.

Bad: `My-Agent`, `1clinical`, `clinical-reasoning`, `clinical reasoning`.
Good: `clinical_reasoning`, `legal_qa`, `bird_id_v2`.

### `project.yml` must be named exactly that

Not `omniagents.yml`, not `config.yml`, not `agent.yml`. The CLI looks for `project.yml` specifically when invoked with `-P <dir>`.

## Multi-agent projects

### `entrypoint` required when there's more than one agent

A project with multiple agents under `agents/*/agent.yml` must declare which one runs by default:

```yaml
agents:
  entrypoint: coordinator   # required when 2+ agents exist
```

If only one agent exists, this can be omitted — the framework auto-picks it. Add a second agent without setting `entrypoint` and project load fails.

### Tool name collisions across agents

`paths.tools` is shared across all agents in a project. If two `@function_tool` functions in different files have the same function name, the framework will use only one of them and silently shadow the other. Tool names must be globally unique within a project.

### Handoffs are not a project-level construct

Despite supporting multiple agents, the framework provides no built-in inter-agent handoff orchestration. Handoffs are declared *inside* a single agent's YAML (as tools the agent can call). Multi-agent in OmniAgents means "several agents can be picked at runtime via `--agent <key>`," not "agents collaborate automatically."

For agent-to-agent handoffs, see the `omniagents-basic` skill's section on the `handoffs:` field.

## Paths

### Tool and eval paths in `project.yml` are relative to the project root

```yaml
paths:
  tools: tools          # NOT agents/<name>/tools
  evaluations: evaluations
```

When migrating from a basic single-agent dir where `tools/` lived next to `agent.yml`, the `tools/` directory ends up at the *project root*, not inside `agents/<name>/`. Don't move `tools/` into the agent directory — leave it at the project root.

### `target/` is vestigial

The `omniagents new` scaffolder creates `target/` and gitignores it. The current `omniagents compile` command no longer writes there. It's safe to ignore; don't put anything there yourself.

### `artifacts/` is where eval results land

`omniagents eval suite run` writes to `artifacts/eval/<name>/results_<timestamp>.json`. The directory is gitignored by default. To preserve results, either commit them deliberately or use `--output <path>` to write to a specific location.

## Sessions

### Sessions are per (project, agent) pair

Stored at `~/.omniagents/sessions/<project>/<agent>/sessions.db`. Two agents in the same project don't share session history — switching between them with `--agent` gives each its own conversation memory.

When running by `-c agent.yml` (single-agent mode without a project), sessions go to `~/.omniagents/sessions/default/default/sessions.db` — meaning every agent run that way shares the same database. Use `--session-id <id>` to disambiguate, or run via `-P project.yml` to get isolation automatically.

## Measures and evals

### `@evaluation_measure` must come from `omniagents.core.evaluation`

Not from `omniagents`, not from `omniagents.core`, not from anywhere else. Auto-discovery scans `evaluations/measures.py` for functions decorated with this exact decorator — anything else is invisible.

```python
from omniagents.core.evaluation import evaluation_measure  # this exact import

@evaluation_measure
def my_measure(ctx):
    return {"passed": True}
```

### Every scenario needs a `measures: [...]` list (for `eval suite run`)

`omniagents eval suite run` only includes scenarios that declare which measures to run against them — scenarios without `measures:` are filtered out by design (so CI gates on real scores, not unscored runs). The framework prints a loud WARNING when this happens, so you'll see it, but it's worth knowing up front:

```yaml
scenarios:
  - name: hello
    prompt: Say hello
    measures: [tool_hallucination]    # required for `eval suite run` to score this
```

If you want to run unmeasured scenarios for exploration, use `omniagents eval scenarios run` (which defaults to `--include-unmeasured`) or pass `--include-unmeasured` to `eval suite run`.

The default scaffold from `omniagents new` ships with `measures: [tool_hallucination]` already attached, so freshly-scaffolded projects work end-to-end out of the box.

### `runs_per_prompt: 1` is too low for noisy agents

The default in `evaluation.yml` is one run per scenario. LLM outputs are non-deterministic — a single run gives you an unreliable signal. Bump to `runs_per_prompt: 3` or higher when you actually care about pass/fail rates.

### `dimensions: []` means no synthetic generation

The scaffolded `evaluation.yml` has an empty dimension list. Running `omniagents eval scenarios generate` against an empty catalog produces no useful output. The synthetic-data path is not usable until you populate dimensions — see the `omniagents-eval-creator` skill.

## Tracing

### `tracing.provider: studio` requires Studio set up

The default `project.yml` from `omniagents new` includes:
```yaml
tracing:
  provider: studio
  project: <name>_project
  name: <name>
  settings:
    resume: never
```

If you don't have an OmniAgents Studio backend configured, leave this block in but tracing simply won't reach anywhere — it doesn't fail the run. If you want to remove it cleanly, delete the entire `tracing:` block.

## Environment

### `.env.example` is a template, not a config file

The framework loads `.env`, not `.env.example`. After scaffolding (or trimming), copy `.env.example` to `.env` and fill in real values. `.env` is gitignored; `.env.example` is committed.

### `OPENAI_API_KEY` is required to run anything

Without it, the agent fails immediately on the first model call. The error message is clear, but easy to miss if you scaffolded a project and skipped the `.env` step.
