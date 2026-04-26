#!/usr/bin/env python3
"""Generate an HTML review of an omniagents eval run.

Reads a results.json (and the per-run transcripts it points at) and
produces a self-contained HTML report. Adapted from skill-creator's
eval-viewer pattern.

Two top tabs:
  - Runs: per-run measures grouped by tier, transcript view, feedback box
  - Summary: pass-rates per measure / per tier, deltas vs. previous run

Usage:
    # Latest run, browser opens automatically:
    python scripts/generate_review.py

    # Specific run, vs. previous, write static file (headless):
    python scripts/generate_review.py \\
        --results artifacts/eval/results/20260426_111232/results.json \\
        --previous artifacts/eval/results/20260426_104500/results.json \\
        --static /tmp/review.html

Tier handling: if a measure result already carries a `tier` field
(post-omniagents-patch), it's used. Otherwise the scenario_config's
measures field is parsed and the tier is inferred. Unclassified measures
default to ``outcome``.

Stdlib only.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import socketserver
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Tier constants — embedded so the script works without omniagents installed.
GATING_TIERS = frozenset({"outcome", "quality", "guard"})
TIER_ORDER: List[str] = ["outcome", "quality", "guard", "process"]
DEFAULT_TIER = "outcome"

TIER_PALETTE = {
    "outcome": {"label": "Outcome",  "bg": "#1f3a4d", "border": "#3d6e8c"},
    "quality": {"label": "Quality",  "bg": "#2d2438", "border": "#5e3d80"},
    "guard":   {"label": "Guard",    "bg": "#3a2b1f", "border": "#8c5a3d"},
    "process": {"label": "Process",  "bg": "#2a2a2a", "border": "#555555"},
}

PASS_COLOR = "#3ddc84"
FAIL_COLOR = "#ff6b6b"
SKIP_COLOR = "#888888"


# ─────────────────────────────────────────────────────────────────────
# Loading
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


def _find_latest_results(project_root: Path) -> Path:
    base = project_root / "artifacts" / "eval" / "results"
    if not base.is_dir():
        sys.exit(f"{base} not found — run an eval first")
    candidates = [
        d for d in base.iterdir()
        if d.is_dir() and (d / "results.json").is_file()
    ]
    if not candidates:
        sys.exit(f"no results.json under {base}/*/")
    return sorted(candidates, key=lambda p: p.stat().st_mtime)[-1] / "results.json"


def _parse_scenario_measures(value: Any) -> Tuple[List[str], Dict[str, str]]:
    """Mirror of omniagents.core.eval.measure_tiers.parse_measures.

    Embedded so the script works against both legacy (flat list) and
    tier-keyed scenario configs without depending on the framework patch
    landing.
    """
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
    name = measure.get("name") or ""
    return scenario_tier_map.get(name, DEFAULT_TIER)


def _gates_ci(tier: str) -> bool:
    if not tier:
        return True
    # Anything not in the explicit non-gating set gates.
    non_gating = frozenset(t for t in TIER_PALETTE if t not in GATING_TIERS)
    return tier not in non_gating


def _load_transcript(path: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict):
        history = data.get("history")
        return history if isinstance(history, list) else None
    if isinstance(data, list):
        return data
    return None


# ─────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────


def _aggregate(results: Dict[str, Any]) -> Dict[str, Any]:
    """Compute per-measure pass rates and per-tier rollups across all runs."""
    runs = results.get("runs") or []
    by_measure: Dict[str, Dict[str, Any]] = {}
    by_tier: Dict[str, Dict[str, int]] = {}

    for r in runs:
        sc = r.get("scenario_config") or {}
        _, scenario_tier_map = _parse_scenario_measures(sc.get("measures"))
        for m in r.get("measures") or []:
            name = m.get("name") or "?"
            tier = _resolve_tier(m, scenario_tier_map)
            entry = by_measure.setdefault(
                name,
                {"name": name, "tier": tier, "passed": 0, "failed": 0, "skipped": 0},
            )
            # Tier from post-patch measure dict overrides scenario config lookup
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

    # Add pass_rate
    for entry in by_measure.values():
        total = entry["passed"] + entry["failed"]
        entry["total_runs"] = total
        entry["pass_rate"] = (entry["passed"] / total) if total else None

    return {"by_measure": by_measure, "by_tier": by_tier, "n_runs": len(runs)}


def _delta_table(curr: Dict[str, Any], prev: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-measure deltas: current pass_rate vs previous pass_rate."""
    if not prev:
        return []
    prev_by = prev.get("by_measure") or {}
    rows = []
    seen = set()
    for name, c in curr.get("by_measure", {}).items():
        seen.add(name)
        p = prev_by.get(name) or {}
        rows.append({
            "name": name,
            "tier": c.get("tier", DEFAULT_TIER),
            "curr": c.get("pass_rate"),
            "prev": p.get("pass_rate"),
            "in_curr": True,
            "in_prev": name in prev_by,
        })
    for name, p in prev_by.items():
        if name in seen:
            continue
        rows.append({
            "name": name,
            "tier": p.get("tier", DEFAULT_TIER),
            "curr": None,
            "prev": p.get("pass_rate"),
            "in_curr": False,
            "in_prev": True,
        })
    return rows


# ─────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────


def _esc(s: Any) -> str:
    return html_lib.escape(str(s) if s is not None else "")


def _short(s: Any, n: int = 1500) -> str:
    s = str(s) if s is not None else ""
    return s if len(s) <= n else s[:n] + "…"


def _render_transcript(history: Optional[List[Dict[str, Any]]]) -> str:
    if not history:
        return "<em class='muted'>(no transcript)</em>"
    parts: List[str] = []
    for msg in history:
        role = msg.get("role")
        if role == "user":
            content = msg.get("content") or ""
            if isinstance(content, list):
                content = "\n".join(
                    c.get("text", "") if isinstance(c, dict) else str(c)
                    for c in content
                )
            parts.append(
                f"<div class='msg msg-user'>"
                f"<div class='msg-role'>user</div>"
                f"<pre>{_esc(_short(content, 4000))}</pre></div>"
            )
        elif role == "assistant":
            content = msg.get("content")
            text = ""
            if isinstance(content, list):
                texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "output_text"]
                text = "\n".join(t for t in texts if t)
            elif isinstance(content, str):
                text = content
            if text:
                parts.append(
                    f"<div class='msg msg-assistant'>"
                    f"<div class='msg-role'>assistant</div>"
                    f"<pre>{_esc(_short(text, 4000))}</pre></div>"
                )
        else:
            mtype = msg.get("type")
            if mtype == "function_call":
                name = msg.get("name", "?")
                args = msg.get("arguments", "")
                if isinstance(args, str):
                    try:
                        parsed = json.loads(args)
                        args = json.dumps(parsed, indent=2)
                    except Exception:
                        pass
                parts.append(
                    f"<div class='msg msg-tool-call'>"
                    f"<div class='msg-role'>→ {_esc(name)}()</div>"
                    f"<pre>{_esc(_short(args, 1500))}</pre></div>"
                )
            elif mtype == "function_call_output":
                output = msg.get("output", "")
                parts.append(
                    f"<div class='msg msg-tool-output'>"
                    f"<div class='msg-role'>tool result</div>"
                    f"<pre>{_esc(_short(output, 1500))}</pre></div>"
                )
            # Skip "reasoning" — encrypted, not human-useful.
    return "\n".join(parts)


def _measure_badge(m: Dict[str, Any], tier: str) -> str:
    pv = m.get("passed")
    if pv is True:
        color = PASS_COLOR
        sym = "✓"
    elif pv is False:
        color = FAIL_COLOR
        sym = "✗"
    else:
        color = SKIP_COLOR
        sym = "—"
    palette = TIER_PALETTE.get(tier, TIER_PALETTE["outcome"])
    name = _esc(m.get("name") or "?")
    reason = _esc(_short(m.get("reason"), 600))
    gates = _gates_ci(tier)
    gate_marker = "" if gates else " <span class='diag-tag'>diagnostic</span>"
    return (
        f"<div class='measure' style='border-left:4px solid {palette['border']}'>"
        f"<div class='measure-head'>"
        f"<span class='measure-status' style='color:{color}'>{sym}</span>"
        f"<span class='measure-name'>{name}</span>"
        f"<span class='tier-tag' style='background:{palette['bg']};border:1px solid {palette['border']}'>{palette['label']}</span>"
        f"{gate_marker}"
        f"</div>"
        f"<div class='measure-reason'>{reason}</div>"
        f"</div>"
    )


def _render_run_card(idx: int, run: Dict[str, Any]) -> str:
    sc = run.get("scenario_config") or {}
    _, scenario_tier_map = _parse_scenario_measures(sc.get("measures"))

    measures = run.get("measures") or []
    by_tier: Dict[str, List[str]] = {t: [] for t in TIER_ORDER}
    for m in measures:
        tier = _resolve_tier(m, scenario_tier_map)
        by_tier.setdefault(tier, []).append(_measure_badge(m, tier))

    measure_blocks = []
    for tier in TIER_ORDER + [t for t in by_tier if t not in TIER_ORDER]:
        items = by_tier.get(tier) or []
        if not items:
            continue
        palette = TIER_PALETTE.get(tier, TIER_PALETTE["outcome"])
        measure_blocks.append(
            f"<details open class='tier-block'>"
            f"<summary style='border-left:4px solid {palette['border']}'><strong>{palette['label']}</strong> · {len(items)}</summary>"
            f"<div class='measures'>{''.join(items)}</div>"
            f"</details>"
        )

    transcript = _load_transcript(run.get("transcript_path"))
    transcript_html = _render_transcript(transcript)

    sid = (run.get("session_id") or "")[:8]
    duration = run.get("duration_seconds")
    duration_s = f"{duration:.0f}s" if isinstance(duration, (int, float)) else "?"
    exchanges = run.get("exchanges") or "?"
    break_reason = _esc(run.get("break_reason") or "?")
    final_text = _short(run.get("final_assistant_text") or "", 1200)

    return f"""
<div class='run' id='run-{idx}' data-run-id='{idx}'>
  <div class='run-head'>
    <h2>Run {idx + 1} <span class='muted'>· {_esc(sid)}</span></h2>
    <div class='run-meta'>
      <span>duration: {duration_s}</span>
      <span>exchanges: {_esc(exchanges)}</span>
      <span>break: {break_reason}</span>
    </div>
  </div>

  <div class='final-text'>
    <div class='label'>Final assistant message</div>
    <pre>{_esc(final_text)}</pre>
  </div>

  <div class='measures-section'>
    {''.join(measure_blocks)}
  </div>

  <details class='transcript-section'>
    <summary>Transcript ({(len(transcript) if transcript else 0)} messages)</summary>
    <div class='transcript'>{transcript_html}</div>
  </details>

  <div class='feedback-section'>
    <label class='label' for='fb-{idx}'>Feedback for this run</label>
    <textarea id='fb-{idx}' class='feedback' data-run-id='{idx}' rows='3'
              placeholder='What stood out? What should change?'></textarea>
  </div>
</div>
"""


def _render_summary(curr: Dict[str, Any], prev: Optional[Dict[str, Any]], n_runs: int) -> str:
    by_tier = curr.get("by_tier") or {}
    by_measure = curr.get("by_measure") or {}

    tier_rows = []
    for tier in TIER_ORDER + [t for t in by_tier if t not in TIER_ORDER]:
        tally = by_tier.get(tier)
        if not tally:
            continue
        palette = TIER_PALETTE.get(tier, TIER_PALETTE["outcome"])
        total = tally["passed"] + tally["failed"]
        rate = (tally["passed"] / total) if total else 0.0
        gating = "gating" if _gates_ci(tier) else "diagnostic"
        tier_rows.append(
            f"<tr>"
            f"<td><span class='tier-tag' style='background:{palette['bg']};border:1px solid {palette['border']}'>{palette['label']}</span></td>"
            f"<td>{gating}</td>"
            f"<td>{tally['passed']}/{total}</td>"
            f"<td>{rate:.0%}</td>"
            f"</tr>"
        )

    deltas = _delta_table(curr, prev)
    measure_rows = []
    for name in sorted(by_measure.keys()):
        m = by_measure[name]
        tier = m.get("tier", DEFAULT_TIER)
        palette = TIER_PALETTE.get(tier, TIER_PALETTE["outcome"])
        rate = m.get("pass_rate")
        rate_str = f"{rate:.0%}" if rate is not None else "—"
        prev_row = next((d for d in deltas if d["name"] == name), None)
        delta_str = ""
        if prev_row and prev_row.get("prev") is not None and rate is not None:
            d = rate - prev_row["prev"]
            arrow = "▲" if d > 0 else ("▼" if d < 0 else "·")
            color = PASS_COLOR if d > 0 else (FAIL_COLOR if d < 0 else SKIP_COLOR)
            delta_str = (
                f"<span style='color:{color}'>{arrow} {d:+.0%}</span>"
            )
        elif prev_row and not prev_row.get("in_prev"):
            delta_str = "<span class='muted'>new</span>"
        measure_rows.append(
            f"<tr>"
            f"<td><span class='tier-tag' style='background:{palette['bg']};border:1px solid {palette['border']}'>{palette['label']}</span></td>"
            f"<td><code>{_esc(name)}</code></td>"
            f"<td>{m['passed']}/{m['total_runs']}</td>"
            f"<td>{rate_str}</td>"
            f"<td>{delta_str}</td>"
            f"</tr>"
        )

    # Removed-measure rows (in prev but not curr)
    for d in deltas:
        if d.get("in_prev") and not d.get("in_curr"):
            tier = d.get("tier", DEFAULT_TIER)
            palette = TIER_PALETTE.get(tier, TIER_PALETTE["outcome"])
            measure_rows.append(
                f"<tr class='removed'>"
                f"<td><span class='tier-tag' style='background:{palette['bg']};border:1px solid {palette['border']}'>{palette['label']}</span></td>"
                f"<td><code>{_esc(d['name'])}</code></td>"
                f"<td>—</td>"
                f"<td>—</td>"
                f"<td><span class='muted'>removed</span></td>"
                f"</tr>"
            )

    return f"""
<h2>Summary</h2>
<p class='muted'>Aggregated over {n_runs} run(s).</p>

<h3>By tier</h3>
<table class='summary-table'>
  <thead><tr><th>Tier</th><th>CI</th><th>Passed</th><th>Pass rate</th></tr></thead>
  <tbody>{''.join(tier_rows) if tier_rows else '<tr><td colspan=4 class=muted>no measures recorded</td></tr>'}</tbody>
</table>

<h3>By measure {('· vs previous' if prev else '')}</h3>
<table class='summary-table'>
  <thead><tr><th>Tier</th><th>Measure</th><th>Passed</th><th>Pass rate</th><th>Δ</th></tr></thead>
  <tbody>{''.join(measure_rows) if measure_rows else '<tr><td colspan=5 class=muted>no measures recorded</td></tr>'}</tbody>
</table>
"""


CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background:#15191e; color:#e0e0e0; margin:0; padding:0; }
header { padding:1rem 1.5rem; border-bottom:1px solid #2a2f37;
         display:flex; align-items:baseline; gap:1rem; }
header h1 { margin:0; font-size:1.1rem; font-weight:600; }
header .scenario { color:#9aa6b2; font-size:0.95rem; }
.tabs { display:flex; gap:0.5rem; border-bottom:1px solid #2a2f37; padding:0 1.5rem; }
.tab { padding:0.7rem 1.2rem; cursor:pointer; border:0; background:none; color:#9aa6b2;
       border-bottom:2px solid transparent; font-size:0.95rem; }
.tab.active { color:#e0e0e0; border-bottom-color:#3ddc84; }
.content { padding:1.5rem; max-width:1200px; }
.run { background:#1c2128; border:1px solid #2a2f37; border-radius:6px;
       padding:1rem 1.2rem; margin-bottom:1.5rem; }
.run-head { display:flex; justify-content:space-between; align-items:baseline;
            margin-bottom:0.6rem; flex-wrap:wrap; gap:0.5rem; }
.run-head h2 { margin:0; font-size:1rem; font-weight:600; }
.run-meta { display:flex; gap:1rem; color:#9aa6b2; font-size:0.85rem; }
.muted { color:#7a8390; }
.label { color:#9aa6b2; font-size:0.8rem; text-transform:uppercase;
         letter-spacing:0.05em; margin-bottom:0.3rem; }
.final-text pre { background:#0d1014; padding:0.7rem; border-radius:4px; max-height:120px;
                  overflow:auto; font-size:0.85rem; margin:0; white-space:pre-wrap; }
.measures-section { margin-top:0.8rem; }
.tier-block { margin:0.5rem 0; }
.tier-block summary { cursor:pointer; padding:0.4rem 0.7rem; background:#1f242b;
                       border-radius:3px; user-select:none; }
.measures { padding-top:0.5rem; }
.measure { background:#171b21; border-radius:3px; padding:0.5rem 0.7rem;
           margin-bottom:0.4rem; }
.measure-head { display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap; }
.measure-status { font-size:1.1rem; font-weight:bold; min-width:1.2rem; }
.measure-name { font-family:'SF Mono',Menlo,Consolas,monospace; font-size:0.9rem; }
.tier-tag { font-size:0.7rem; padding:0.1rem 0.5rem; border-radius:3px;
            text-transform:uppercase; letter-spacing:0.05em; color:#e0e0e0; }
.diag-tag { font-size:0.7rem; color:#9aa6b2; font-style:italic; }
.measure-reason { color:#aab2bd; font-size:0.85rem; margin-top:0.3rem;
                  margin-left:1.7rem; }
.transcript-section { margin-top:0.8rem; }
.transcript-section summary { cursor:pointer; padding:0.4rem 0;
                              color:#9aa6b2; user-select:none; }
.transcript { padding-top:0.5rem; }
.msg { margin-bottom:0.5rem; padding:0.4rem 0.7rem; border-radius:3px;
       font-size:0.85rem; }
.msg-role { font-size:0.7rem; color:#9aa6b2; text-transform:uppercase;
            letter-spacing:0.05em; margin-bottom:0.2rem; font-weight:600; }
.msg-user { background:#1f2a35; }
.msg-assistant { background:#1c2128; }
.msg-tool-call { background:#2a201f; }
.msg-tool-output { background:#1f2a25; }
.msg pre { margin:0; white-space:pre-wrap; word-break:break-word; max-height:200px;
           overflow:auto; }
.feedback-section { margin-top:1rem; }
.feedback { width:100%; background:#0d1014; color:#e0e0e0; border:1px solid #2a2f37;
            border-radius:3px; padding:0.5rem; font-family:inherit; font-size:0.9rem;
            resize:vertical; }
.summary-table { width:100%; border-collapse:collapse; margin:0.5rem 0 1.5rem; }
.summary-table th, .summary-table td { text-align:left; padding:0.5rem 0.7rem;
                                       border-bottom:1px solid #2a2f37; }
.summary-table th { color:#9aa6b2; font-weight:500; font-size:0.85rem;
                    text-transform:uppercase; letter-spacing:0.05em; }
.summary-table td code { font-size:0.85rem; color:#cdd2d8; }
.summary-table tr.removed td { opacity:0.5; }
.toolbar { padding:0.5rem 1.5rem; background:#1c2128; border-bottom:1px solid #2a2f37;
           display:flex; gap:0.7rem; align-items:center; }
.btn { background:#2a3038; color:#e0e0e0; border:1px solid #3a4048;
       padding:0.4rem 0.8rem; border-radius:3px; cursor:pointer; font-size:0.85rem; }
.btn:hover { background:#343b44; }
"""


JS = """
function showTab(name) {
  document.querySelectorAll('.tab-content').forEach(el => {
    el.style.display = el.dataset.tab === name ? '' : 'none';
  });
  document.querySelectorAll('.tab').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === name);
  });
}

const FEEDBACK_KEY = 'omniagents_review_feedback_' + (window.RESULTS_ID || 'default');

function loadFeedback() {
  try {
    const stored = JSON.parse(localStorage.getItem(FEEDBACK_KEY) || '{}');
    document.querySelectorAll('.feedback').forEach(el => {
      const id = el.dataset.runId;
      if (stored[id]) el.value = stored[id];
    });
  } catch (e) { console.error(e); }
}

function saveFeedback() {
  const out = {};
  document.querySelectorAll('.feedback').forEach(el => {
    const id = el.dataset.runId;
    if (el.value.trim()) out[id] = el.value;
  });
  localStorage.setItem(FEEDBACK_KEY, JSON.stringify(out));
}

function downloadFeedback() {
  const reviews = [];
  document.querySelectorAll('.feedback').forEach(el => {
    reviews.push({
      run_id: parseInt(el.dataset.runId, 10),
      feedback: el.value,
      timestamp: new Date().toISOString(),
    });
  });
  const blob = new Blob([JSON.stringify({reviews, status: 'complete'}, null, 2)],
                       {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'feedback.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

document.addEventListener('DOMContentLoaded', () => {
  loadFeedback();
  document.querySelectorAll('.feedback').forEach(el => {
    el.addEventListener('input', saveFeedback);
  });
  document.querySelectorAll('.tab').forEach(el => {
    el.addEventListener('click', () => showTab(el.dataset.tab));
  });
  document.querySelectorAll('[data-action=download-feedback]').forEach(el => {
    el.addEventListener('click', downloadFeedback);
  });
  showTab('runs');
});
"""


def _render_html(
    results: Dict[str, Any],
    curr_agg: Dict[str, Any],
    prev_agg: Optional[Dict[str, Any]],
    results_id: str,
) -> str:
    runs = results.get("runs") or []
    scenario_name = ""
    if runs:
        scenario_name = runs[0].get("scenario") or ""

    run_cards = "\n".join(_render_run_card(i, r) for i, r in enumerate(runs))
    summary = _render_summary(curr_agg, prev_agg, len(runs))

    return f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'/>
  <title>Eval review · {_esc(scenario_name)}</title>
  <style>{CSS}</style>
  <script>window.RESULTS_ID = {json.dumps(results_id)};</script>
</head>
<body>
  <header>
    <h1>Eval review</h1>
    <span class='scenario'>{_esc(scenario_name)} · {len(runs)} run(s)</span>
  </header>
  <div class='tabs'>
    <button class='tab' data-tab='runs'>Runs</button>
    <button class='tab' data-tab='summary'>Summary</button>
  </div>
  <div class='toolbar'>
    <button class='btn' data-action='download-feedback'>Download feedback.json</button>
    <span class='muted'>(saves to ~/Downloads)</span>
  </div>
  <div class='content tab-content' data-tab='runs'>
    {run_cards}
  </div>
  <div class='content tab-content' data-tab='summary' style='display:none'>
    {summary}
  </div>
  <script>{JS}</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────
# Server / static output
# ─────────────────────────────────────────────────────────────────────


def _serve(html: str, port: int) -> None:
    encoded = html.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args, **kwargs):
            return  # quiet

    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        url = f"http://127.0.0.1:{port}/"
        print(f"Eval review: {url}", file=sys.stderr)
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", help="Path to results.json (default: latest under <project>/artifacts/eval/results/)")
    parser.add_argument("--previous", help="Path to a previous results.json for delta comparison")
    parser.add_argument("--static", help="Write a self-contained HTML to this path instead of starting a server")
    parser.add_argument("--port", type=int, default=8765, help="Port for the local server (default: 8765)")
    parser.add_argument("--project-root", help="Override project root (default: cwd-walk)")
    args = parser.parse_args()

    project_root = _find_project_root(args.project_root)
    results_path = Path(args.results).expanduser() if args.results else _find_latest_results(project_root)
    if not results_path.is_file():
        sys.exit(f"results.json not found: {results_path}")
    print(f"Reading {results_path}", file=sys.stderr)
    results = json.loads(results_path.read_text(encoding="utf-8"))
    curr_agg = _aggregate(results)

    prev_agg = None
    if args.previous:
        prev_path = Path(args.previous)
        if not prev_path.is_file():
            print(f"warning: --previous {prev_path} not found, ignoring", file=sys.stderr)
        else:
            prev_results = json.loads(prev_path.read_text(encoding="utf-8"))
            prev_agg = _aggregate(prev_results)

    results_id = results_path.parent.name
    html = _render_html(results, curr_agg, prev_agg, results_id)

    if args.static:
        out = Path(args.static)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"Wrote {out} ({len(html):,} chars)", file=sys.stderr)
        return 0

    _serve(html, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
