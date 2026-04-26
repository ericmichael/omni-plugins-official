#!/usr/bin/env python3
"""Pre-flight validator for omniagents eval scenarios.

Catches mistakes before burning a slow eval run:
  - YAML doesn't parse / required fields missing
  - Measure names not registered (typos, renamed measures)
  - Tier names that aren't recognized (typos default-gate)
  - fixture path doesn't exist on disk
  - db_fixture has neither a seeded .db nor a builder script
  - allowed_modified paths don't exist in the fixture (drift)
  - revert_target doesn't exist in the fixture
  - command / test_command set without a corresponding *_timeout_s
  - max_continuations > 0 without a continuation_prompt

Usage (from any omniagents-based project root):
    python <skill>/scripts/validate_scenario.py
    python <skill>/scripts/validate_scenario.py --scenario autopilot_fitness_bug
    python <skill>/scripts/validate_scenario.py --file path/to/foo.yml
    python <skill>/scripts/validate_scenario.py --project-root /path/to/project
    python <skill>/scripts/validate_scenario.py --json

Project root resolution (in priority order):
    1. ``--project-root`` flag
    2. Walk up from cwd until a directory containing ``evaluations/scenarios/``
       or ``project.yml`` is found
    3. cwd as the last resort

Exit code:
    0   no errors (warnings allowed)
    1   one or more errors
    2   bad invocation (file not found, etc.)
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


KNOWN_TIERS = frozenset({"outcome", "quality", "process", "guard"})
GATING_TIERS = frozenset({"outcome", "quality", "guard"})


def _find_project_root(override: Optional[str] = None) -> Path:
    """Resolve the omniagents project root."""
    if override:
        p = Path(override).expanduser().resolve()
        if not p.is_dir():
            sys.exit(f"--project-root not a directory: {p}")
        return p
    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "evaluations" / "scenarios").is_dir():
            return candidate
        if (candidate / "project.yml").is_file():
            return candidate
    return cwd


# ─────────────────────────────────────────────────────────────────────


@dataclass
class Check:
    scenario: str
    level: str  # "error" | "warn" | "info"
    message: str
    suggestion: Optional[str] = None
    field: Optional[str] = None


@dataclass
class Report:
    checks: List[Check] = field(default_factory=list)
    scenarios_seen: int = 0

    def add(self, scenario: str, level: str, message: str, **kwargs) -> None:
        self.checks.append(Check(scenario=scenario, level=level, message=message, **kwargs))

    @property
    def errors(self) -> List[Check]:
        return [c for c in self.checks if c.level == "error"]

    @property
    def warnings(self) -> List[Check]:
        return [c for c in self.checks if c.level == "warn"]


# ─────────────────────────────────────────────────────────────────────


def _load_measure_registry(project_root: Path) -> set[str]:
    """Import evaluations.measures from the project so its decorators
    register, then read the omniagents registry."""
    measures_path = project_root / "evaluations" / "measures.py"
    if not measures_path.is_file():
        # No project-local measures — that's OK; the validator still
        # checks tier syntax / paths. Empty registry skips name-existence
        # checks (with a warning so the user knows).
        print(
            f"note: no evaluations/measures.py under {project_root} — "
            "skipping measure-name registry check",
            file=sys.stderr,
        )
        return set()
    sys.path.insert(0, str(project_root))
    try:
        import evaluations.measures  # noqa: F401
    except Exception as exc:
        print(f"warning: could not import evaluations.measures: {exc}", file=sys.stderr)
        return set()
    try:
        from omniagents.core.evaluation.registry import _MEASURES
    except Exception as exc:
        print(f"warning: could not load omniagents registry: {exc}", file=sys.stderr)
        return set()
    return set(_MEASURES.keys())


def _parse_measures(value: Any) -> tuple[List[str], Dict[str, str]]:
    """Mirror of omniagents.core.eval.measure_tiers.parse_measures.

    Embedded so this validator runs even if the framework patch hasn't
    landed locally yet.
    """
    if value is None:
        return [], {}
    if isinstance(value, list):
        names = [str(m) for m in value if m is not None]
        return names, {n: "outcome" for n in names}
    if isinstance(value, dict):
        flat: List[str] = []
        tier_by_name: Dict[str, str] = {}
        for tier_name, names in value.items():
            tier = str(tier_name)
            for n in (names or []):
                if n is None:
                    continue
                m = str(n)
                if m not in tier_by_name:
                    flat.append(m)
                tier_by_name[m] = tier
        return flat, tier_by_name
    return [], {}


def _suggest(name: str, candidates: set[str]) -> Optional[str]:
    matches = difflib.get_close_matches(name, candidates, n=1, cutoff=0.6)
    return matches[0] if matches else None


# ─────────────────────────────────────────────────────────────────────


def validate_scenario(
    sc: Dict[str, Any],
    measure_registry: set[str],
    report: Report,
    project_root: Path,
) -> None:
    fixtures_workspaces = project_root / "evaluations" / "fixtures" / "workspaces"
    fixtures_dbs = project_root / "evaluations" / "fixtures" / "dbs"

    name = sc.get("name") or "<unnamed>"

    # Required fields
    if not sc.get("name"):
        report.add(name, "error", "missing 'name' field", field="name")
    # A scenario must have either a single `prompt` (single-turn / sentinel-loop)
    # or `prompts` (multi-turn scripted). Both shapes are supported by the runner.
    has_prompt = bool(sc.get("prompt"))
    has_prompts = bool(sc.get("prompts"))
    if not has_prompt and not has_prompts:
        report.add(name, "error", "missing 'prompt' or 'prompts' field", field="prompt")
    if has_prompt and has_prompts:
        report.add(
            name, "warn",
            "both 'prompt' and 'prompts' set — runner will pick one (likely 'prompts')",
            field="prompt",
        )

    # Measures: parse + registry check
    measures, tier_by_name = _parse_measures(sc.get("measures"))
    if not measures:
        report.add(name, "warn", "no measures defined — scenario won't be scored")

    for m in measures:
        if measure_registry and m not in measure_registry:
            report.add(
                name,
                "error",
                f"unknown measure: {m!r}",
                suggestion=_suggest(m, measure_registry),
                field="measures",
            )

    # Tier names
    for m, tier in tier_by_name.items():
        if tier not in KNOWN_TIERS:
            report.add(
                name,
                "warn",
                f"measure {m!r} uses unrecognized tier {tier!r} (will gate CI by default)",
                field="measures",
            )

    # fixture
    fixture = sc.get("fixture")
    fixture_dir: Optional[Path] = None
    if fixture:
        fixture_dir = fixtures_workspaces / fixture
        if not fixture_dir.is_dir():
            try:
                rel = fixture_dir.relative_to(project_root)
            except ValueError:
                rel = fixture_dir
            report.add(
                name,
                "error",
                f"fixture {fixture!r} not found at {rel}/",
                field="fixture",
            )
            fixture_dir = None

    # db_fixture
    db_fixture = sc.get("db_fixture")
    if db_fixture:
        db_file = fixtures_dbs / f"{db_fixture}.db"
        builder = fixtures_dbs / f"build_{db_fixture}.py"
        if not db_file.is_file() and not builder.is_file():
            try:
                rel_db = db_file.relative_to(project_root)
                rel_b = builder.relative_to(project_root)
            except ValueError:
                rel_db, rel_b = db_file, builder
            report.add(
                name,
                "error",
                f"db_fixture {db_fixture!r}: neither {rel_db} nor {rel_b} exists",
                field="db_fixture",
            )
        elif not db_file.is_file():
            try:
                rel_b = builder.relative_to(project_root)
            except ValueError:
                rel_b = builder
            report.add(
                name,
                "warn",
                f"db_fixture {db_fixture!r}: builder exists but no seeded .db — "
                f"run `python {rel_b}`",
                field="db_fixture",
            )

    # expect block
    expect = sc.get("expect") or {}

    # revert_target
    revert_target = expect.get("revert_target")
    if revert_target and fixture_dir:
        rt = fixture_dir / revert_target
        if not rt.is_file():
            report.add(
                name,
                "error",
                f"revert_target {revert_target!r} not found in fixture {fixture!r}",
                field="expect.revert_target",
            )

    # allowed_modified paths
    allowed_modified = expect.get("allowed_modified") or []
    if fixture_dir:
        for path in allowed_modified:
            ap = fixture_dir / path
            if not ap.exists():
                report.add(
                    name,
                    "warn",
                    f"allowed_modified path {path!r} doesn't exist in fixture (drift?)",
                    field="expect.allowed_modified",
                )

    # Command timeouts
    if expect.get("command") and "command_timeout_s" not in expect:
        report.add(
            name,
            "warn",
            "expect.command set without command_timeout_s (defaults to 120s)",
            field="expect.command_timeout_s",
        )
    if expect.get("test_command") and "test_timeout_s" not in expect:
        report.add(
            name,
            "warn",
            "expect.test_command set without test_timeout_s (defaults to 240s)",
            field="expect.test_timeout_s",
        )

    # Continuation prompts
    max_cont = sc.get("max_continuations") or 0
    if max_cont > 0 and not sc.get("continuation_prompt"):
        report.add(
            name,
            "warn",
            f"max_continuations={max_cont} but no continuation_prompt set",
            field="continuation_prompt",
        )

    # Sentinel sanity
    sentinel = sc.get("until_sentinel")
    if sentinel and max_cont == 0:
        report.add(
            name,
            "warn",
            "until_sentinel set but max_continuations is 0 (sentinel never checked)",
            field="until_sentinel",
        )


# ─────────────────────────────────────────────────────────────────────


def _load_yaml_files(paths: List[Path]) -> List[tuple[Path, Dict[str, Any]]]:
    out = []
    for p in paths:
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            print(f"YAML parse error in {p}: {exc}", file=sys.stderr)
            sys.exit(2)
        out.append((p, data))
    return out


def _format_check(c: Check) -> str:
    icons = {"error": "✗", "warn": "⚠", "info": "·"}
    icon = icons.get(c.level, "·")
    line = f"  {icon} [{c.level:>5}] {c.message}"
    if c.suggestion:
        line += f"\n      did you mean: {c.suggestion!r}?"
    return line


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", help="Scenario name (e.g. autopilot_fitness_bug)")
    parser.add_argument("--file", help="Path to a scenario YAML")
    parser.add_argument("--project-root", help="Override project root (default: cwd-walk)")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of pretty output")
    args = parser.parse_args()

    project_root = _find_project_root(args.project_root)
    scenarios_dir = project_root / "evaluations" / "scenarios"

    if args.file:
        files = [Path(args.file).resolve()]
    elif args.scenario:
        files = [scenarios_dir / f"{args.scenario}.yml"]
    else:
        if not scenarios_dir.is_dir():
            print(
                f"no evaluations/scenarios/ under {project_root} — "
                "pass --file, --project-root, or run from a project root",
                file=sys.stderr,
            )
            return 2
        files = sorted(scenarios_dir.glob("*.yml"))

    for f in files:
        if not f.is_file():
            print(f"file not found: {f}", file=sys.stderr)
            return 2

    measure_registry = _load_measure_registry(project_root)
    report = Report()
    parsed = _load_yaml_files(files)

    for path, data in parsed:
        scenarios = data.get("scenarios") or []
        if not scenarios:
            print(f"warning: {path} has no 'scenarios' list", file=sys.stderr)
            continue
        for sc in scenarios:
            report.scenarios_seen += 1
            validate_scenario(sc, measure_registry, report, project_root)

    if args.json:
        out = {
            "scenarios_seen": report.scenarios_seen,
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "checks": [
                {
                    "scenario": c.scenario,
                    "level": c.level,
                    "message": c.message,
                    "suggestion": c.suggestion,
                    "field": c.field,
                }
                for c in report.checks
            ],
        }
        print(json.dumps(out, indent=2))
        return 1 if report.errors else 0

    by_scenario: Dict[str, List[Check]] = defaultdict(list)
    for c in report.checks:
        by_scenario[c.scenario].append(c)

    if not by_scenario:
        print(f"All {report.scenarios_seen} scenario(s) clean.")
        return 0

    for scenario in sorted(by_scenario):
        print(f"\n{scenario}:")
        for c in by_scenario[scenario]:
            print(_format_check(c))

    n_err = len(report.errors)
    n_warn = len(report.warnings)
    print(
        f"\n{report.scenarios_seen} scenario(s) checked: "
        f"{n_err} error(s), {n_warn} warning(s)"
    )
    return 1 if n_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
