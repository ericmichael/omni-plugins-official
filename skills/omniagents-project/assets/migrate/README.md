# Migration templates

These files convert a basic single-agent OmniAgents directory into a full eval-enabled project.

## What you have (basic single-agent)

```
my-agent/
├── agent.yml
├── instructions.md
└── tools/
    └── ...
```

## What you need (full project)

```
my-agent/
├── project.yml                          # NEW (use project.yml template here)
├── agents/<name>/
│   ├── agent.yml                        # MOVED from project root
│   └── instructions.md                  # MOVED from project root
├── tools/                                # stays put
└── evaluations/                          # NEW (copy this whole directory)
    ├── evaluation.yml
    ├── scenarios.yml
    ├── measures.py
    └── metrics.yml
```

## How to apply

1. Pick a project name (`<name>`). It usually matches the agent's existing `name:` field. Lowercase letters, digits, underscores; must start with a letter.
2. `mkdir -p agents/<name>` and move `agent.yml` and `instructions.md` into it.
3. Copy `project.yml` from this directory to the project root and replace `<NAME>` with your project name (two occurrences).
4. Copy the entire `evaluations/` directory from here to your project root.
5. Verify the agent's `name:` field in `agent.yml` matches `<name>` exactly — the framework rejects mismatches.

The agent now runs with `omniagents run -P project.yml` and evaluates with `omniagents eval suite run`.
