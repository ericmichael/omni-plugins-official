---
name: omniagents-project
description: Scaffold a full OmniAgents project — an AI agent paired with an evaluation harness so you can measure and iterate on it for scientific rigor. Use this whenever the user wants to build an agent they plan to evaluate, benchmark, run scenarios against, validate quantitatively, ship to others, or treat as a real artifact rather than a quick chatbot. Triggers include "make me an agent for [domain] with evals", "I want to measure how well my agent does X", "promote my agent to a project", "scaffold a clinical/research/legal/etc. agent project", "set up evaluations on my agent", "package my agent so others can install it". Also use when the user mentions OmniAgents and the work is bigger than a single throwaway agent.
---

# OmniAgents Project Creator

This skill scaffolds **full OmniAgents projects** — an agent plus an evaluation harness — using the framework's official `omniagents new` scaffolder, then shapes the result for the user's situation.

## Where this skill fits

Three OmniAgents skills exist. Use the right one:

- **`omniagents-basic`** — for a single runnable agent (no evals, no project envelope). Best for quick prototypes, chatbots, demos.
- **`omniagents-project`** (this one) — for an agent **paired with evaluations**. The differentiator is evals: scenarios, measures, metrics, the `omniagents eval suite run` workflow.
- **`omniagents-eval-creator`** — for **designing good scenarios and measures** once the eval harness exists. Hand off to this skill after scaffolding when the user is ready to write meaningful test cases.

If the user already has a `omniagents-basic`-style single-agent directory and wants evals on it, that's the **migration path** in this skill.

## What you produce

Every project this skill scaffolds has:

```
<project>/
├── project.yml                          # multi-agent manifest, tracing, paths
├── agents/<name>/
│   ├── agent.yml                        # the agent
│   └── instructions.md                  # its system prompt
├── tools/
│   ├── __init__.py
│   └── <name>_tools.py                  # custom @function_tool functions
├── evaluations/
│   ├── evaluation.yml                   # eval defaults + synthetic data gen config
│   ├── scenarios.yml                    # test cases
│   ├── measures.py                      # @evaluation_measure functions
│   └── metrics.yml                      # aggregate metrics
├── .env.example                         # secret template
├── .gitignore
├── README.md
└── requirements.txt
```

The user can run two things end-to-end:
- `omniagents run -P project.yml` — talk to the agent
- `omniagents eval suite run` — score the agent against `scenarios.yml` using `measures.py`

That's the deliverable. **Both must work before you declare the scaffold done.** Use `scripts/verify_project.py` from this skill to check.

## The two tiers

`omniagents new` produces *everything* — the agent, evals, **and** a productionization layer (CI workflows, a Python wrapper package with `<project>` and `<project>-setup` console scripts, Makefile publish targets, devcontainer, Gemfury config). For most users this is too much.

Default to **Learner tier** unless the user signals otherwise.

### Learner tier (default)

For: students, faculty, researchers, tinkerers — anyone who wants a working agent + evals locally and isn't shipping a Python package to other people.

After running `omniagents new`, immediately run `assets/trim-to-learner.sh` to strip the productionization layer. This leaves only what the user needs: agent, tools, evaluations, README, .env.example, requirements.txt, .gitignore.

The trimmed project still runs and still evaluates. Nothing functional is lost.

### Developer tier (opt-in)

For: AI engineers shipping an agent as an installable Python package, internal Omni projects, anyone who needs CI gates on evals before merge, or anyone who explicitly says "I want to ship this," "package this," "publish to PyPI," "set up CI."

Skip the trim script. Keep what `omniagents new` produced. See `references/productionization.md` for what the CI workflows do, how the wrapper Python package works, and the version-bump/publish flow.

**How to decide**: ask once if the signal is unclear. "Are you planning to ship this as an installable Python package or just run it locally?" — that's enough. Don't interrogate.

## The two paths

### Greenfield: brand new project

1. **Pick a project name.** Lowercase letters, digits, underscores; must start with a letter. Example: `clinical_reasoning`, `legal_assistant`. The `omniagents new` scaffolder sanitizes anyway.
2. **Pick a parent directory.** Default to the user's current working directory unless they've named one.
3. **Run the scaffolder:**
   ```bash
   omniagents new <name> --dir <parent>
   ```
   Add `--model gpt-4.1` or another model if the user has a preference. The scaffolder defaults to `gpt-4.1`. If the user wants a current top-tier model, `gpt-5.2` is a reasonable choice.
   Add `--no-samples` only if the user explicitly doesn't want the sample `echo`/`word_count` tools wired in.
4. **Trim to learner tier** (unless developer tier was requested):
   ```bash
   bash <skill-dir>/assets/trim-to-learner.sh <project-dir>
   ```
5. **Customize the agent.** This is real work, not boilerplate:
   - Rewrite `agents/<name>/agent.yml`'s `description` and `welcome_text` for the actual use case
   - Fill in `agents/<name>/instructions.md` (the scaffolder leaves a skeleton with Persona/Goal/Starting Context/Guidance/Examples — replace each `<...>` block)
   - Replace or extend the sample tools in `tools/<name>_tools.py` with what the agent actually needs. For tool authoring details (custom Python tools, builtins, MCP, OpenAPI codegen, voice mode), invoke `omniagents-basic` — don't reinvent here.
6. **Set up evals** (this is the whole reason for full-project scaffolding):
   - The scaffold ships a working baseline: a `hello` scenario with the built-in `tool_hallucination` measure attached, a placeholder `always_pass` measure, and the `unknown_tool_call_rate` metric. `omniagents eval suite run` will pass on the bare scaffold — you can verify before customizing.
   - Replace the placeholder `hello` scenario in `evaluations/scenarios.yml` with realistic prompts the agent will face. **Every scenario needs a `measures: [...]` list** — without it, `eval suite run` filters the scenario out (the framework prints a loud warning, so this is hard to miss).
   - Replace the `always_pass` placeholder in `evaluations/measures.py` with measures that actually check correctness — see `references/evaluations.md` for the `EvalContext` API and the two metric types (`pass_rate` for boolean measures, `rate` for measures emitting `counts.X`).
   - For deeper scenario design (sensitivity/specificity, dimension catalogs, hill-climbing), invoke `omniagents-eval-creator`. This skill scaffolds the harness; that one designs the content.
7. **Set up `.env`:** copy `.env.example` to `.env` and fill in `OPENAI_API_KEY` (and `OPENAI_BASE_URL` if using a custom endpoint).
8. **Smoke test:** run `python <skill-dir>/scripts/verify_project.py <project-dir>`. It runs the agent on a trivial prompt and runs the eval suite, reporting what works and what's broken. Don't hand the project back to the user until both pass.

### Migration: promote a basic single-agent dir to a full project

A `omniagents-basic`-style directory looks like:
```
my-agent/
├── agent.yml
├── instructions.md
└── tools/<...>.py
```

To promote it:

1. **Pick a project name** (often the same as the agent name). Same rules as greenfield.
2. **Restructure the directory.** The agent must move into `agents/<name>/`:
   ```bash
   cd my-agent
   mkdir -p agents/<name>
   mv agent.yml instructions.md agents/<name>/
   # tools/ stays at the project root — already in the right place
   ```
   **Critical**: the agent's `name:` field in `agent.yml` must match the directory name `<name>`. The framework validates this at runtime and fails loudly if they mismatch. See `references/footguns.md`.
3. **Add `project.yml`** at the project root. Use the template at `assets/migrate/project.yml` — substitute `<name>` for the project name. Don't include `tracing:` unless the user has a Studio project set up.
4. **Add the eval harness.** Copy the four files from `assets/migrate/evaluations/` to `<project>/evaluations/`. They're the same templates `omniagents new` uses, with the same `always_pass` placeholder and `hello` scenario — meant to be replaced.
5. **Skip the productionization layer entirely** unless the user has asked for it. Migration's purpose is "add evals," not "add CI/CD."
6. **Customize evals + smoke test** — same as steps 6–8 of greenfield.

## After scaffolding

Once verify_project.py passes, three follow-ups are usually next:

1. **Write real scenarios and measures.** Hand off to `omniagents-eval-creator` if the user wants help designing them well. Otherwise point them at `references/evaluations.md`.
2. **Add real tools.** Hand off to `omniagents-basic` for tool authoring patterns (custom Python, MCP servers, OpenAPI codegen, builtins).
3. **Productionize, if relevant.** If the user later decides to ship the project, point them at `references/productionization.md` — the trimmed files are recoverable by re-running `omniagents new` in a tmpdir and copying the missing pieces back.

## Footguns to surface proactively

The framework enforces a few things silently. Mention these once during scaffolding so the user doesn't trip on them later:

- **Agent directory name must match `name:` in `agent.yml` exactly.** `agents/foo/agent.yml` must have `name: foo`. Validated at runtime.
- **`project.yml` must be named exactly that.** Not `omniagents.yml` or `config.yml`.
- **Tool/eval paths in `project.yml` are relative to the project root**, not the agent directory.
- **Every scenario needs a `measures: [...]` list** — `eval suite run` filters out unmeasured scenarios so CI gates on real scores. The framework warns loudly when this happens, so it's hard to miss; just know up front.
- **Sessions are stored per (project, agent) pair** at `~/.omniagents/sessions/<project>/<agent>/sessions.db`. Two agents in the same project don't share session history.

Full list in `references/footguns.md`.

## Reference files

- `references/evaluations.md` — Eval file contracts: scenarios.yml shape, the `@evaluation_measure` decorator, metrics.yml, the `omniagents eval suite run` command and selectors. Read when wiring or customizing the eval harness.
- `references/productionization.md` — The opt-in developer layer: wrapper Python package, Makefile, CI workflows, version bumps, PyPI vs Gemfury. Read when the user wants to ship.
- `references/footguns.md` — Silent enforcement gotchas. Read on demand when something seems to mysteriously fail.

## Bundled assets

- `assets/trim-to-learner.sh` — Removes the productionization layer from a freshly-scaffolded project. Idempotent and safe to re-run.
- `assets/migrate/project.yml` — Minimal `project.yml` template for the migration path.
- `assets/migrate/evaluations/` — The four eval files from the official scaffolder, ready to copy when migrating.

## Bundled scripts

- `scripts/verify_project.py` — Smoke-test runner. Runs `omniagents run` with a trivial prompt and `omniagents eval suite run`, reports what works and what's broken. Always run this before declaring the scaffold done.
