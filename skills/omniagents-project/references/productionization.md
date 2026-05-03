# Productionization reference

This is the opt-in developer layer that `omniagents new` produces and `trim-to-learner.sh` strips. Keep it (don't trim) when the user wants to:

- Ship the agent as an installable Python package (PyPI or private registry)
- Gate PRs on evaluation results in CI
- Distribute a one-command CLI (`<project>` and `<project>-setup`) to non-technical end users
- Develop in a reproducible devcontainer

If none of those apply, trim it. The agent and evals work fine without any of this.

## What gets kept

```
<project>/
├── <project>/                   # Python package wrapping omniagents CLI
│   ├── __init__.py
│   ├── cli.py                   # `<project>` command — loads creds, runs the agent
│   ├── setup.py                 # `<project>-setup` command — interactive credential wizard
│   └── config.py                # platform-aware config dir handling
├── pyproject.toml                # package metadata + bumpversion config
├── Makefile                      # clean / build / publish / dev / format / bump-* targets
├── .devcontainer/
│   ├── devcontainer.json        # Python 3.12 + Go 1.22 base, VSCode settings
│   └── postCreate.sh            # auto pip install -e . on container start
├── .github/
│   ├── pull_request_template.md # structured PR form (failure mode, change type, eval evidence)
│   └── workflows/
│       ├── omniagents-eval.yml  # runs eval suite on every push/PR
│       ├── publish-pypi.yml     # publishes on `v*` tag
│       └── publish-gemfury.yml  # publishes on `v*` tag (private registry)
└── docs/
    └── RELEASE.md                # how to cut a release
```

## The wrapper Python package

The `<project>/cli.py` and `<project>/setup.py` files create two console scripts via `pyproject.toml`:

- **`<project>`** — runs the agent. Internally: loads `~/.config/<project>/config.env`, sets env vars, then calls `omniagents run --project <auto-detected project.yml>`.
- **`<project>-setup`** — interactive wizard that prompts for OpenAI provider (standard / Azure / custom-compatible), API key, optional org/project, optional SerpAPI key. Writes `~/.config/<project>/config.env` with `0o600` permissions.

This pattern is for **distributing the agent to end users who shouldn't need to know about `.env` files or the omniagents CLI**. They `pip install <project>`, run `<project>-setup` once, then run `<project>`. That's it.

If you're keeping this layer but the wizard's options don't fit (e.g., your agent uses Anthropic instead of OpenAI), edit `setup.py` directly — it's a normal Python file. The pattern is straightforward.

## pyproject.toml

Defines:
- Package name, version, dependencies (mirrors `requirements.txt` plus dev extras)
- The two console scripts: `<project>` and `<project>-setup`
- `bumpversion` config that updates the `version` field automatically
- `black` formatter config

Customize: `description` field, `dependencies` list (add anything your tools need), and the optional `dev` extras.

## Makefile targets

```
clean              rm build/, dist/, *.egg-info
build              python -m build (wheel + sdist into dist/)
publish-pypi       clean + build + twine upload
publish-gemfury    clean + build + curl upload to Gemfury
publish            git push --follow-tags (after a bump-* target)
install            pip install <project> (from PyPI)
install-gemfury    pip install <project> --index-url <gemfury-url>
dev                pip install -e .[dev]
format             black .
bump-patch         bump2version patch (commits + tags)
bump-minor         bump2version minor (commits + tags)
bump-major         bump2version major (commits + tags)
```

The intended release flow: `make bump-patch && make publish` → CI workflows trigger on the new tag and publish the wheel to PyPI / Gemfury.

## CI workflows

### omniagents-eval.yml

Runs on every push to `main` and every pull request:
```yaml
- pip install -r requirements.txt
- omniagents eval suite run
```

Requires repo secrets `OPENAI_API_KEY` and (optionally) `OPENAI_BASE_URL`. The job fails if any gating measure fails — this is your CI gate against agent regressions.

### publish-pypi.yml

Triggers on `v*` tag push (or manual `workflow_dispatch` for TestPyPI). Builds the wheel + sdist, uploads to PyPI via twine, then creates a draft GitHub release. Requires secrets `PYPI_API_TOKEN`, `TEST_PYPI_API_TOKEN`.

### publish-gemfury.yml

Triggers on `v*` tag push. Same build flow, uploads to Gemfury via curl. Requires secrets `FURY_USER`, `FURY_TOKEN`.

**Gemfury note**: Gemfury is a private package registry. Most external users don't need it — delete this workflow file unless the project is for an organization with a Gemfury account.

## PR template

`.github/pull_request_template.md` enforces a structured form for agent changes:
- Failure mode being fixed
- Change type (prompt / RAG / tool / model / evaluator / scenarios / metrics)
- Evaluation evidence (how you know it's better)
- Qualitative before/after example
- CI checklist

This is opinionated toward agent-iteration workflows. Keep it as-is or simplify if your project doesn't follow this discipline.

## requirements.txt vs pyproject.toml

Both list dependencies. They serve different audiences:
- **`pyproject.toml`** is what `pip install <project>` reads when someone installs the published package
- **`requirements.txt`** is what CI uses (`pip install -r requirements.txt`) and what developers use to set up their local checkout

Keep them in sync. The scaffolder includes a `--extra-index-url https://pypi.fury.io/ericmichael/` line in `requirements.txt` that points at the Omni Gemfury — strip this if you're not depending on private Omni packages.

## .devcontainer

Standard VSCode Dev Containers setup with Python 3.12 + Go 1.22, common Python extensions, pytest enabled, and a `postCreate.sh` that installs the project in editable mode. Useful for new contributors who want one-click reproducibility.

Customize: drop the Go feature if you don't need it; change `PIP_EXTRA_INDEX_URL` away from Gemfury if you're not in the Omni ecosystem.

## docs/RELEASE.md

The release runbook — covers prerequisites, the bump-and-tag flow, manual publish commands, and how the CD pipelines react to tags. Edit only if your release process diverges.

## When to swap PyPI for plain pip

If the project will live on PyPI publicly, delete:
- `.github/workflows/publish-gemfury.yml`
- The `publish-gemfury` and `install-gemfury` targets in `Makefile`
- The `--extra-index-url https://pypi.fury.io/ericmichael/` line in `requirements.txt`
- The `PIP_EXTRA_INDEX_URL` line in `.devcontainer/devcontainer.json`

If the project will live only in a private Gemfury registry, keep Gemfury and delete the PyPI workflow + targets.

If both — keep both. They publish independently on tag pushes.
