#!/usr/bin/env python3
"""verify_project.py — smoke-test an OmniAgents project.

Usage:  python verify_project.py <project-dir> [--no-llm-check]

Runs in two phases:

  1. Structural checks (always run, no API calls):
     - project.yml exists and parses
     - agents/<entrypoint>/agent.yml exists and parses
     - agent name field matches the agent directory name
     - tools/ and evaluations/ directories exist
     - evaluations files (scenarios.yml, measures.py, metrics.yml) parse

  2. End-to-end check (requires OPENAI_API_KEY in env, opt out with --no-llm-check):
     - Runs `omniagents eval suite run` which loads the agent and evaluates it
     - Captures stdout/stderr; reports pass/fail and any exit error

Exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required (it's a transitive dependency of omniagents).", file=sys.stderr)
    print("       Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}!{RESET} {msg}")


def info(msg: str) -> None:
    print(f"  {DIM}·{RESET} {msg}")


class CheckError(Exception):
    """Raised when a structural check fails."""


def load_yaml(path: Path) -> dict:
    with path.open() as f:
        try:
            return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise CheckError(f"YAML parse error in {path}: {e}") from e


def check_project_yml(project_dir: Path) -> tuple[str, str]:
    """Return (project_name, entrypoint_agent_name)."""
    project_yml = project_dir / "project.yml"
    if not project_yml.is_file():
        raise CheckError(f"missing {project_yml}")
    ok(f"project.yml exists at {project_yml}")

    data = load_yaml(project_yml)
    ok("project.yml parses as YAML")

    project_name = data.get("name")
    if not project_name:
        raise CheckError("project.yml has no 'name' field")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", project_name):
        raise CheckError(
            f"project.yml name {project_name!r} is invalid (must be lowercase, "
            "start with a letter, contain only letters/digits/underscores)"
        )
    ok(f"project name: {project_name}")

    agents_section = data.get("agents") or {}
    entrypoint = agents_section.get("entrypoint")

    # Discover agent dirs to determine entrypoint if not set explicitly.
    agents_root = project_dir / (data.get("paths", {}).get("agents") or "agents")
    if not agents_root.is_dir():
        raise CheckError(f"agents directory not found: {agents_root}")
    agent_dirs = sorted(p for p in agents_root.iterdir() if p.is_dir() and (p / "agent.yml").is_file())
    if not agent_dirs:
        raise CheckError(f"no agents found under {agents_root}/<name>/agent.yml")

    if entrypoint is None:
        if len(agent_dirs) == 1:
            entrypoint = agent_dirs[0].name
            ok(f"entrypoint: {entrypoint} (auto-detected, single agent)")
        else:
            raise CheckError(
                f"project.yml has no 'agents.entrypoint' but found {len(agent_dirs)} "
                f"agents: {[p.name for p in agent_dirs]}"
            )
    else:
        if not any(p.name == entrypoint for p in agent_dirs):
            raise CheckError(
                f"agents.entrypoint={entrypoint!r} but no directory "
                f"{agents_root}/{entrypoint}/ found"
            )
        ok(f"entrypoint: {entrypoint}")

    return project_name, entrypoint


def check_agent(project_dir: Path, entrypoint: str) -> None:
    agent_yml = project_dir / "agents" / entrypoint / "agent.yml"
    if not agent_yml.is_file():
        raise CheckError(f"missing {agent_yml}")
    ok(f"agent.yml exists at {agent_yml.relative_to(project_dir)}")

    data = load_yaml(agent_yml)
    ok("agent.yml parses as YAML")

    agent_name = data.get("name")
    if agent_name != entrypoint:
        raise CheckError(
            f"agent.yml name field is {agent_name!r} but directory is {entrypoint!r}. "
            "These MUST match — the framework rejects mismatches at runtime."
        )
    ok(f"agent name field matches directory: {agent_name}")

    instructions_file = data.get("instructions_file")
    if instructions_file:
        instructions_path = agent_yml.parent / instructions_file
        if not instructions_path.is_file():
            raise CheckError(f"instructions_file references missing: {instructions_path}")
        ok(f"instructions_file exists: {instructions_file}")

    tools = data.get("tools") or []
    if not tools:
        warn("agent.yml has no tools listed (the agent will have no actions to take)")
    else:
        ok(f"agent declares {len(tools)} tool(s): {', '.join(tools)}")


def check_tools_dir(project_dir: Path) -> None:
    tools_dir = project_dir / "tools"
    if not tools_dir.is_dir():
        warn("no tools/ directory (agent will only have access to built-in tools)")
        return
    py_files = [p for p in tools_dir.glob("*.py") if p.name != "__init__.py"]
    if not py_files:
        warn(f"tools/ exists but contains no .py tool files")
    else:
        ok(f"tools/ contains {len(py_files)} tool file(s): {', '.join(p.name for p in py_files)}")


def check_evaluations(project_dir: Path) -> None:
    evals_dir = project_dir / "evaluations"
    if not evals_dir.is_dir():
        raise CheckError(
            f"missing evaluations/ directory — this is a full project without an eval harness. "
            "If that's intentional, this skill isn't the right fit; use omniagents-basic instead."
        )
    ok("evaluations/ directory exists")

    required = ["scenarios.yml", "measures.py", "metrics.yml", "evaluation.yml"]
    for fname in required:
        fpath = evals_dir / fname
        if not fpath.is_file():
            raise CheckError(f"missing evaluations/{fname}")
        if fname.endswith(".yml"):
            load_yaml(fpath)  # raises CheckError on parse failure
        elif fname.endswith(".py"):
            try:
                ast.parse(fpath.read_text())
            except SyntaxError as e:
                raise CheckError(f"evaluations/{fname} has Python syntax error: {e}") from e
        ok(f"evaluations/{fname} present and valid")

    measures_text = (evals_dir / "measures.py").read_text()
    if "@evaluation_measure" not in measures_text:
        warn("evaluations/measures.py does not use @evaluation_measure — no measures will be discovered")
    if "from omniagents.core.evaluation import" not in measures_text:
        warn(
            "evaluations/measures.py does not import from omniagents.core.evaluation. "
            "Measures must be decorated with @evaluation_measure from that exact module."
        )

    scenarios = load_yaml(evals_dir / "scenarios.yml").get("scenarios") or []
    if not scenarios:
        warn("evaluations/scenarios.yml has no scenarios — eval suite will run zero tests")
    else:
        ok(f"evaluations/scenarios.yml declares {len(scenarios)} scenario(s)")


def run_eval_suite(project_dir: Path) -> bool:
    info("Running `omniagents eval suite run` (this calls the LLM and may take 10-60s)...")
    try:
        result = subprocess.run(
            ["omniagents", "eval", "suite", "run"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        fail("`omniagents` CLI not found in PATH — install with `pip install -r requirements.txt`")
        return False
    except subprocess.TimeoutExpired:
        fail("eval suite run timed out after 180s — check network/model latency")
        return False

    if result.returncode == 0:
        ok("eval suite run completed successfully")
        # Surface the last few lines so the user sees pass-rate output.
        tail = "\n".join(result.stdout.splitlines()[-10:])
        if tail.strip():
            for line in tail.splitlines():
                print(f"    {DIM}{line}{RESET}")
        return True
    else:
        fail(f"eval suite run exited with code {result.returncode}")
        if result.stderr.strip():
            print(f"    {DIM}stderr:{RESET}")
            for line in result.stderr.splitlines()[-20:]:
                print(f"    {DIM}{line}{RESET}")
        if result.stdout.strip():
            print(f"    {DIM}stdout:{RESET}")
            for line in result.stdout.splitlines()[-20:]:
                print(f"    {DIM}{line}{RESET}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project_dir", type=Path, help="Path to the OmniAgents project root")
    parser.add_argument(
        "--no-llm-check",
        action="store_true",
        help="Skip the eval suite run (which calls the LLM). Structural checks only.",
    )
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    if not project_dir.is_dir():
        print(f"ERROR: {project_dir} is not a directory", file=sys.stderr)
        return 2

    print(f"{BOLD}Verifying OmniAgents project at {project_dir}{RESET}")
    print()
    print(f"{BOLD}Phase 1: structural checks{RESET}")

    try:
        project_name, entrypoint = check_project_yml(project_dir)
        check_agent(project_dir, entrypoint)
        check_tools_dir(project_dir)
        check_evaluations(project_dir)
    except CheckError as e:
        print()
        print(f"{RED}{BOLD}FAIL{RESET}: {e}")
        return 1

    print()
    print(f"{BOLD}Phase 2: end-to-end check{RESET}")

    if args.no_llm_check:
        info("--no-llm-check passed; skipping eval suite run")
        print()
        print(f"{GREEN}{BOLD}OK{RESET} — structural checks passed (eval run skipped)")
        return 0

    # The omniagents CLI auto-loads .env from the project dir, so we don't need
    # OPENAI_API_KEY in our own environment — only require credentials to be
    # available somewhere (env var OR .env in the project root).
    has_env_file = (project_dir / ".env").is_file()
    has_env_var = bool(os.environ.get("OPENAI_API_KEY"))
    if not has_env_file and not has_env_var:
        warn("No .env file in project root and OPENAI_API_KEY not in environment.")
        info("Copy .env.example to .env and fill in OPENAI_API_KEY, or pass --no-llm-check.")
        print()
        print(f"{YELLOW}{BOLD}PARTIAL{RESET} — structural checks passed, eval run not attempted")
        return 0

    if run_eval_suite(project_dir):
        print()
        print(f"{GREEN}{BOLD}OK{RESET} — project verified end-to-end")
        return 0
    else:
        print()
        print(f"{RED}{BOLD}FAIL{RESET} — structural checks passed but eval run failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
