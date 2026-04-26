#!/usr/bin/env python3
"""Diff two omniagents results.json runs by tier and measure.

Surfaces what moved between iterations: per-tier pass-rate deltas,
top movers (sorted by absolute change), measures that appeared or
disappeared, and a CI-gate net summary.

Usage:
    # Latest two runs under artifacts/eval/results/:
    python scripts/compare_iterations.py

    # Specific runs:
    python scripts/compare_iterations.py PREV CURR
    python scripts/compare_iterations.py \\
        artifacts/eval/results/20260426_104500/results.json \\
        artifacts/eval/results/20260426_111232/results.json

    # Output modes:
    python scripts/compare_iterations.py --markdown
    python scripts/compare_iterations.py --json

Tier handling matches generate_review.py: reads `tier` directly from
each measure result if present (post-omniagents-patch), otherwise
falls back to parsing scenario_config.measures.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


GATING_TIERS = frozenset({"outcome", "quality", "guard"})
TIER_ORDER: List[str] = ["outcome", "quality", "guard", "process"]
DEFAULT_TIER = "outcome"


# ─────────────────────────────────────────────────────────────────────


def _find_project_root(override: Optional[str] = None) -> Path:
    """Resolve the omniagents project root via override → cwd-walk → cwd."""
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


def _find_latest_two(project_root: Path) -> Tuple[Path, Path]:
    base = project_root / "artifacts" / "eval" / "results"
    if not base.is_dir():
        sys.exit(f"{base} not found — run an eval first")
    candidates = [
        d for d in base.iterdir()
        if d.is_dir() and (d / "results.json").is_file()
    ]
    if len(candidates) < 2:
        sys.exit(f"need at least 2 results.json under {base}/, found {len(candidates)}")
    sorted_dirs = sorted(candidates, key=lambda p: p.stat().st_mtime)
    return sorted_dirs[-2] / "results.json", sorted_dirs[-1] / "results.json"


def _parse_measures(value: Any) -> Tuple[List[str], Dict[str, str]]:
    """Mirror of omniagents.core.eval.measure_tiers.parse_measures."""
    if value is None:
        return [], {}
    if isinstance(value, list):
        names = [str(m) for m in value if m is not None]
        return names, {n: DEFAULT_TIER for n in names}
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


def _resolve_tier(measure: Dict[str, Any], scenario_tier_map: Dict[str, str]) -> str:
    explicit = measure.get("tier")
    if isinstance(explicit, str) and explicit:
        return explicit
    return scenario_tier_map.get(measure.get("name") or "", DEFAULT_TIER)


def _gates_ci(tier: str) -> bool:
    if not tier:
        return True
    return tier in GATING_TIERS or tier not in {"process"}


def _aggregate(results: Dict[str, Any]) -> Dict[str, Any]:
    runs = results.get("runs") or []
    by_measure: Dict[str, Dict[str, Any]] = {}
    by_tier: Dict[str, Dict[str, int]] = {}
    scenarios = set()

    for r in runs:
        scenarios.add(r.get("scenario") or "?")
        sc = r.get("scenario_config") or {}
        _, scenario_tier_map = _parse_measures(sc.get("measures"))
        for m in r.get("measures") or []:
            name = m.get("name") or "?"
            tier = _resolve_tier(m, scenario_tier_map)
            entry = by_measure.setdefault(
                name,
                {"name": name, "tier": tier, "passed": 0, "failed": 0, "skipped": 0},
            )
            if m.get("tier"):
                entry["tier"] = m["tier"]
            pv = m.get("passed")
            if pv is True:
                entry["passed"] += 1
            elif pv is False:
                entry["failed"] += 1
            else:
                entry["skipped"] += 1

            tally = by_tier.setdefault(
                entry["tier"],
                {"passed": 0, "failed": 0, "skipped": 0},
            )
            if pv is True:
                tally["passed"] += 1
            elif pv is False:
                tally["failed"] += 1
            else:
                tally["skipped"] += 1

    for entry in by_measure.values():
        total = entry["passed"] + entry["failed"]
        entry["total_runs"] = total
        entry["pass_rate"] = (entry["passed"] / total) if total else None

    return {
        "by_measure": by_measure,
        "by_tier": by_tier,
        "n_runs": len(runs),
        "scenarios": sorted(scenarios),
    }


# ─────────────────────────────────────────────────────────────────────


def _gating_totals(by_tier: Dict[str, Dict[str, int]]) -> Tuple[int, int]:
    """Returns (passed, total) summed over gating tiers only."""
    passed = total = 0
    for tier, tally in by_tier.items():
        if tier not in GATING_TIERS:
            continue
        passed += tally["passed"]
        total += tally["passed"] + tally["failed"]
    return passed, total


def _diff(prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the diff between two aggregates."""
    prev_meas = prev["by_measure"]
    curr_meas = curr["by_measure"]
    all_names = set(prev_meas) | set(curr_meas)

    movers: List[Dict[str, Any]] = []
    new_measures: List[Dict[str, Any]] = []
    removed_measures: List[Dict[str, Any]] = []

    for name in all_names:
        p = prev_meas.get(name)
        c = curr_meas.get(name)
        if c is None:
            removed_measures.append({
                "name": name,
                "tier": p.get("tier", DEFAULT_TIER),
                "prev_rate": p.get("pass_rate"),
            })
            continue
        if p is None:
            new_measures.append({
                "name": name,
                "tier": c.get("tier", DEFAULT_TIER),
                "curr_rate": c.get("pass_rate"),
                "curr_str": f"{c['passed']}/{c['total_runs']}",
            })
            continue
        prev_rate = p.get("pass_rate")
        curr_rate = c.get("pass_rate")
        if prev_rate is None or curr_rate is None:
            delta = None
        else:
            delta = curr_rate - prev_rate
        movers.append({
            "name": name,
            "tier": c.get("tier", p.get("tier", DEFAULT_TIER)),
            "prev_rate": prev_rate,
            "curr_rate": curr_rate,
            "delta": delta,
            "prev_str": f"{p['passed']}/{p['total_runs']}",
            "curr_str": f"{c['passed']}/{c['total_runs']}",
        })

    movers.sort(
        key=lambda m: abs(m["delta"]) if m["delta"] is not None else -1,
        reverse=True,
    )

    tier_diff: List[Dict[str, Any]] = []
    all_tiers = set(prev["by_tier"]) | set(curr["by_tier"])
    ordered_tiers = [t for t in TIER_ORDER if t in all_tiers] + sorted(
        all_tiers - set(TIER_ORDER)
    )
    for tier in ordered_tiers:
        p = prev["by_tier"].get(tier, {"passed": 0, "failed": 0})
        c = curr["by_tier"].get(tier, {"passed": 0, "failed": 0})
        p_total = p["passed"] + p["failed"]
        c_total = c["passed"] + c["failed"]
        prev_rate = (p["passed"] / p_total) if p_total else None
        curr_rate = (c["passed"] / c_total) if c_total else None
        delta = (
            curr_rate - prev_rate
            if (prev_rate is not None and curr_rate is not None)
            else None
        )
        tier_diff.append({
            "tier": tier,
            "gating": tier in GATING_TIERS,
            "prev_rate": prev_rate,
            "curr_rate": curr_rate,
            "delta": delta,
            "prev_str": f"{p['passed']}/{p_total}",
            "curr_str": f"{c['passed']}/{c_total}",
        })

    pp, pt = _gating_totals(prev["by_tier"])
    cp, ct = _gating_totals(curr["by_tier"])

    return {
        "tiers": tier_diff,
        "movers": movers,
        "new_measures": sorted(new_measures, key=lambda m: m["name"]),
        "removed_measures": sorted(removed_measures, key=lambda m: m["name"]),
        "gating": {
            "prev_passed": pp,
            "prev_total": pt,
            "curr_passed": cp,
            "curr_total": ct,
        },
    }


# ─────────────────────────────────────────────────────────────────────


def _isatty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _color(s: str, code: str) -> str:
    if not _isatty():
        return s
    return f"\x1b[{code}m{s}\x1b[0m"


def _delta_marker(delta: Optional[float]) -> str:
    if delta is None:
        return "—"
    if delta > 0:
        return _color(f"▲ {delta:+.0%}", "32")
    if delta < 0:
        return _color(f"▼ {delta:+.0%}", "31")
    return _color(f"·  +0%", "90")


def _rate(rate: Optional[float]) -> str:
    if rate is None:
        return "—"
    return f"{rate:.0%}"


def _pretty(diff: Dict[str, Any], prev_path: Path, curr_path: Path,
            prev_agg: Dict[str, Any], curr_agg: Dict[str, Any]) -> str:
    lines: List[str] = []

    lines.append("Comparing:")
    lines.append(
        f"  prev: {prev_path.parent}/  ({prev_agg['n_runs']} runs · {', '.join(prev_agg['scenarios'])})"
    )
    lines.append(
        f"  curr: {curr_path.parent}/  ({curr_agg['n_runs']} runs · {', '.join(curr_agg['scenarios'])})"
    )

    lines.append("")
    lines.append("By tier:")
    lines.append(f"  {'tier':<10} {'role':<10} {'prev':>10}  {'curr':>10}   delta")
    for t in diff["tiers"]:
        role = "gating" if t["gating"] else "diagnostic"
        prev_str = f"{_rate(t['prev_rate'])} ({t['prev_str']})"
        curr_str = f"{_rate(t['curr_rate'])} ({t['curr_str']})"
        lines.append(
            f"  {t['tier']:<10} {role:<10} {prev_str:>10}  {curr_str:>10}   {_delta_marker(t['delta'])}"
        )

    g = diff["gating"]
    p_rate = (g["prev_passed"] / g["prev_total"]) if g["prev_total"] else 0
    c_rate = (g["curr_passed"] / g["curr_total"]) if g["curr_total"] else 0
    g_delta = c_rate - p_rate if g["curr_total"] and g["prev_total"] else None

    lines.append("")
    lines.append("CI gate (outcome + quality + guard tiers):")
    lines.append(
        f"  prev: {g['prev_passed']}/{g['prev_total']} ({_rate(p_rate) if g['prev_total'] else '—'})"
    )
    lines.append(
        f"  curr: {g['curr_passed']}/{g['curr_total']} ({_rate(c_rate) if g['curr_total'] else '—'})  {_delta_marker(g_delta)}"
    )

    movers = [m for m in diff["movers"] if m["delta"] not in (None, 0.0)]
    if movers:
        lines.append("")
        lines.append("Top movers:")
        for m in movers[:15]:
            tier_tag = f"[{m['tier']}]"
            line = (
                f"  {_delta_marker(m['delta'])}  {m['name']:<40} {tier_tag:<11}"
                f"  {m['prev_str']} → {m['curr_str']}"
            )
            lines.append(line)
        if len(movers) > 15:
            lines.append(f"  ... and {len(movers) - 15} more movers")

    if diff["new_measures"]:
        lines.append("")
        lines.append("New measures (in curr only):")
        for m in diff["new_measures"]:
            lines.append(f"  + {m['name']:<40} [{m['tier']}]  {m['curr_str']} ({_rate(m['curr_rate'])})")

    if diff["removed_measures"]:
        lines.append("")
        lines.append("Removed measures (in prev only):")
        for m in diff["removed_measures"]:
            lines.append(f"  - {m['name']:<40} [{m['tier']}]  was {_rate(m['prev_rate'])}")

    return "\n".join(lines)


def _markdown(diff: Dict[str, Any], prev_path: Path, curr_path: Path,
              prev_agg: Dict[str, Any], curr_agg: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Eval iteration diff")
    lines.append("")
    lines.append(f"**prev:** `{prev_path.parent.name}` · {prev_agg['n_runs']} runs · _{', '.join(prev_agg['scenarios'])}_")
    lines.append(f"**curr:** `{curr_path.parent.name}` · {curr_agg['n_runs']} runs · _{', '.join(curr_agg['scenarios'])}_")
    lines.append("")

    g = diff["gating"]
    p_rate = (g["prev_passed"] / g["prev_total"]) if g["prev_total"] else 0
    c_rate = (g["curr_passed"] / g["curr_total"]) if g["curr_total"] else 0
    g_delta = (c_rate - p_rate) if g["prev_total"] and g["curr_total"] else None
    delta_str = "—"
    if g_delta is not None:
        if g_delta > 0:
            delta_str = f"📈 {g_delta:+.0%}"
        elif g_delta < 0:
            delta_str = f"📉 {g_delta:+.0%}"
        else:
            delta_str = "·  +0%"

    lines.append(f"## CI gate")
    lines.append("")
    lines.append(f"**{g['prev_passed']}/{g['prev_total']}** → **{g['curr_passed']}/{g['curr_total']}** &nbsp;&nbsp; {delta_str}")
    lines.append("")

    lines.append("## By tier")
    lines.append("")
    lines.append("| Tier | Role | Prev | Curr | Δ |")
    lines.append("|---|---|---|---|---|")
    for t in diff["tiers"]:
        role = "gating" if t["gating"] else "diagnostic"
        d = "—"
        if t["delta"] is not None:
            d = f"{t['delta']:+.0%}"
        lines.append(
            f"| `{t['tier']}` | {role} | {_rate(t['prev_rate'])} ({t['prev_str']}) | {_rate(t['curr_rate'])} ({t['curr_str']}) | {d} |"
        )

    movers = [m for m in diff["movers"] if m["delta"] not in (None, 0.0)]
    if movers:
        lines.append("")
        lines.append("## Top movers")
        lines.append("")
        lines.append("| Δ | Measure | Tier | Prev | Curr |")
        lines.append("|---|---|---|---|---|")
        for m in movers[:25]:
            d = f"{m['delta']:+.0%}" if m["delta"] is not None else "—"
            lines.append(f"| {d} | `{m['name']}` | `{m['tier']}` | {m['prev_str']} | {m['curr_str']} |")

    if diff["new_measures"]:
        lines.append("")
        lines.append("## New measures")
        lines.append("")
        for m in diff["new_measures"]:
            lines.append(f"- `{m['name']}` [{m['tier']}] → {m['curr_str']} ({_rate(m['curr_rate'])})")

    if diff["removed_measures"]:
        lines.append("")
        lines.append("## Removed measures")
        lines.append("")
        for m in diff["removed_measures"]:
            lines.append(f"- `{m['name']}` [{m['tier']}] (was {_rate(m['prev_rate'])})")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("prev", nargs="?", help="Path to previous results.json (or its dir)")
    parser.add_argument("curr", nargs="?", help="Path to current results.json (or its dir)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--markdown", action="store_true", help="Markdown output")
    parser.add_argument("--project-root", help="Override project root (default: cwd-walk)")
    args = parser.parse_args()

    project_root = _find_project_root(args.project_root)

    if args.prev and args.curr:
        prev = Path(args.prev).expanduser()
        curr = Path(args.curr).expanduser()
        if prev.is_dir():
            prev = prev / "results.json"
        if curr.is_dir():
            curr = curr / "results.json"
    elif not args.prev and not args.curr:
        prev, curr = _find_latest_two(project_root)
    else:
        sys.exit("specify both PREV and CURR, or neither (defaults to latest two)")

    if not prev.is_file():
        sys.exit(f"prev results.json not found: {prev}")
    if not curr.is_file():
        sys.exit(f"curr results.json not found: {curr}")

    prev_results = json.loads(prev.read_text(encoding="utf-8"))
    curr_results = json.loads(curr.read_text(encoding="utf-8"))
    prev_agg = _aggregate(prev_results)
    curr_agg = _aggregate(curr_results)
    diff = _diff(prev_agg, curr_agg)

    if args.json:
        print(json.dumps(diff, indent=2))
        return 0

    if args.markdown:
        print(_markdown(diff, prev, curr, prev_agg, curr_agg))
        return 0

    print(_pretty(diff, prev, curr, prev_agg, curr_agg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
