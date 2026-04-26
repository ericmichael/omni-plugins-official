# Measures Catalog

Common measure patterns for omniagents eval scenarios, organized by verifier shape. Use this as a lookup when handing off a property + verifier hint to `measure-author`.

Every measure follows the standard signature:

```python
from omniagents.core.evaluation import (
    EvalContext,
    evaluation_measure,
    fail_reason,
    pass_reason,
)

@evaluation_measure
def my_measure(ctx: EvalContext) -> dict:
    ...
    return pass_reason("...") | fail_reason("...")
```

---

## Verifier hierarchy

Always prefer earlier:

1. **Deterministic** — read state, compute boolean.
2. **Threshold** — compute a number, compare to a target.
3. **Subprocess** — run a command, check exit code.
4. **Revert+rerun** — write known-bad input, rerun command, expect specific result, restore.
5. **Tool-call-pattern** — examine the agent's trace.
6. **Oracle** — Claude judge call. Last resort.

If you reach for an oracle, double-check whether a deterministic version is possible.

---

## 1. Deterministic — file existence

**Pattern:**

```python
@evaluation_measure
def artifact_exists(ctx: EvalContext) -> dict:
    """Required output file is present in the workspace."""
    workspace = ctx.metadata.get("environment_context", {}).get("workspace_root")
    if not workspace:
        return fail_reason("no workspace_root in environment context")
    rel_path = ctx.expect.get("artifact_path", "out/result.json")
    full = Path(workspace) / rel_path
    if not full.is_file():
        return fail_reason(f"missing artifact: {rel_path}")
    return pass_reason(f"artifact present: {rel_path}", path=str(full))
```

**Tier:** usually `quality` (well-formed presence) or `outcome` (the artifact IS the goal).

**Variants:**
- Glob match (any file under a dir): `Path(workspace).glob(pattern)`
- Multi-file presence: list of paths, all required.
- Strictly-newer-than: compare `stat().st_mtime` against the fixture's pristine mtime.

---

## 2. Deterministic — JSON schema check

**Pattern:**

```python
@evaluation_measure
def manifest_well_formed(ctx: EvalContext) -> dict:
    """Manifest has required fields with correct types."""
    workspace = ctx.metadata.get("environment_context", {}).get("workspace_root")
    if not workspace:
        return fail_reason("no workspace_root")
    manifest_path = Path(workspace) / ctx.expect.get("manifest_path", "out/manifest.json")
    if not manifest_path.is_file():
        return fail_reason("manifest missing")
    try:
        m = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        return fail_reason(f"manifest not valid JSON: {e}")
    required = ["runId", "baseUrl", "stories"]
    for k in required:
        if k not in m:
            return fail_reason(f"manifest missing required field: {k}")
    if not isinstance(m["stories"], list) or not m["stories"]:
        return fail_reason("manifest.stories is not a non-empty list")
    return pass_reason(f"manifest well-formed ({len(m['stories'])} stories)")
```

**Tier:** `quality`. Structural integrity.

---

## 3. Deterministic — internal consistency between artifacts

**Pattern:**

```python
@evaluation_measure
def per_item_manifests_consistent(ctx: EvalContext) -> dict:
    """Every item in the top manifest has a per-item manifest with matching IDs."""
    workspace = Path(ctx.metadata.get("environment_context", {}).get("workspace_root", ""))
    top = json.loads((workspace / "out/manifest.json").read_text())
    issues = []
    for item in top.get("items", []):
        item_id = item.get("id")
        per_path = workspace / f"out/{item_id}/manifest.json"
        if not per_path.is_file():
            issues.append(f"{item_id}: per-item manifest missing")
            continue
        per = json.loads(per_path.read_text())
        if per.get("id") != item_id:
            issues.append(f"{item_id}: per-item id mismatch")
    if issues:
        return fail_reason(f"{len(issues)} consistency issue(s)", issues=issues)
    return pass_reason(f"{len(top['items'])} items consistent")
```

**Tier:** `quality`. Catches stub artifacts that pass surface-level existence checks but aren't real.

---

## 4. Threshold — count, size, time

**Pattern:**

```python
@evaluation_measure
def has_evidence(ctx: EvalContext) -> dict:
    """At least N evidence files exist with size > min_bytes."""
    workspace = Path(ctx.metadata.get("environment_context", {}).get("workspace_root", ""))
    pattern = ctx.expect.get("evidence_glob", "out/evidence/*.png")
    min_count = int(ctx.expect.get("evidence_min_count", 1))
    min_bytes = int(ctx.expect.get("evidence_min_bytes", 1024))
    matches = [p for p in workspace.glob(pattern) if p.stat().st_size >= min_bytes]
    if len(matches) < min_count:
        return fail_reason(f"only {len(matches)} evidence files >= {min_bytes} bytes; expected >= {min_count}")
    return pass_reason(f"{len(matches)} evidence files present")
```

**Tier:** usually `quality` or `outcome` depending on what the count gates.

**Variant:** require any single file to be non-trivially sized (> N bytes) AND contain a specific marker string. Catches hand-pasted stubs.

---

## 5. Subprocess — command exit code

**Pattern:**

```python
@evaluation_measure
def command_in_workspace_succeeds(ctx: EvalContext) -> dict:
    """Run a shell command in the workspace; pass on exit 0."""
    cmd = ctx.expect.get("command")
    if not cmd:
        return pass_reason("no command specified")
    workspace = ctx.metadata.get("environment_context", {}).get("workspace_root")
    if not workspace:
        return fail_reason("no workspace_root")
    timeout = int(ctx.expect.get("command_timeout_s", 120))
    try:
        result = subprocess.run(cmd, shell=True, cwd=workspace,
                                capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return fail_reason(f"command timed out after {timeout}s: {cmd}")
    if result.returncode == 0:
        return pass_reason(f"command exited 0: {cmd}")
    output = (result.stdout or "") + (result.stderr or "")
    tail = "\n".join(output.splitlines()[-15:])
    return fail_reason(f"command exited {result.returncode}", output_tail=tail)
```

**Tier:** `outcome`. The command outcome IS the verifier.

**Always:** read `_timeout_s` from `ctx.expect` with a sensible default. Never run an unbounded subprocess.

---

## 6. Revert+rerun — sensitivity check on a regression test

**Pattern:**

```python
@evaluation_measure
def bug_caught_by_tests(ctx: EvalContext) -> dict:
    """Verify the agent's regression test catches the planted bug.

    1. Compare agent's source vs pristine; if unchanged, fail (no fix).
    2. Overwrite agent's source with pristine; rerun tests; expect non-zero.
    3. Restore the agent's version no matter what.
    """
    revert_target = ctx.expect.get("revert_target")
    if not revert_target:
        return pass_reason("no revert_target specified")
    env_ctx = ctx.metadata.get("environment_context", {})
    workspace = env_ctx.get("workspace_root")
    fixture_src = env_ctx.get("fixture_src_dir")
    if not workspace or not fixture_src:
        return fail_reason("missing workspace_root or fixture_src_dir")

    target = Path(workspace) / revert_target
    pristine = Path(fixture_src) / revert_target
    if not target.is_file() or not pristine.is_file():
        return fail_reason(f"revert_target not found: {revert_target}")

    agent_bytes = target.read_bytes()
    pristine_bytes = pristine.read_bytes()
    if agent_bytes == pristine_bytes:
        return fail_reason(f"agent did not modify {revert_target}")

    test_command = ctx.expect.get("test_command", "uv run pytest -q 2>&1")
    timeout = int(ctx.expect.get("test_timeout_s", 240))
    try:
        target.write_bytes(pristine_bytes)
        result = subprocess.run(test_command, shell=True, cwd=workspace,
                                capture_output=True, text=True, timeout=timeout)
    finally:
        target.write_bytes(agent_bytes)  # ALWAYS restore

    if result.returncode == 0:
        return fail_reason(f"tests still pass with {revert_target} reverted — regression test doesn't catch the bug")
    return pass_reason(f"reverting {revert_target} → tests fail (exit {result.returncode}) — regression catches the bug")
```

**Tier:** `outcome`. Verifies the agent produced a discriminating regression test.

**Critical:** restoration must happen even on exceptions / timeouts. Use `try/finally`.

---

## 7. Tool-call-pattern — presence

**Pattern:**

```python
@evaluation_measure
def mcp_used_to_discover(ctx: EvalContext) -> dict:
    """Agent used the MCP tools (not just the README) to discover the task."""
    tools = ctx.expect.get("discovery_tools") or ["list_tickets", "get_ticket", "list_projects"]
    found = {t: len(ctx.tool_calls(t)) for t in tools if ctx.tool_calls(t)}
    if not found:
        return fail_reason(f"no calls to any discovery tool: {tools}")
    return pass_reason(f"discovered via MCP: {found}")
```

**Tier:** `process`. Diagnostic — was the agent on a legitimate path?

**Don't gate CI on these.** Process measures explain *why* an Outcome moved; they aren't success criteria.

---

## 8. Tool-call-pattern — absence (Guard)

**Pattern:**

```python
@evaluation_measure
def no_remote_operations(ctx: EvalContext) -> dict:
    """Reject remote git / GitHub operations from execute_bash."""
    forbidden = ctx.expect.get("forbidden_bash_patterns") or [
        "git push", "git remote add", "gh pr create", "gh pr edit",
        "gh issue create", "gh repo create",
    ]
    violations = []
    for call in ctx.tool_calls("execute_bash"):
        cmd = (call.args.get("command") or "").lower()
        for pattern in forbidden:
            if pattern.lower() in cmd:
                violations.append({"pattern": pattern, "command": cmd[:160]})
    if violations:
        return fail_reason(f"executed {len(violations)} forbidden command(s)", violations=violations)
    return pass_reason(f"no forbidden patterns in {len(ctx.tool_calls('execute_bash'))} commands")
```

**Tier:** `guard`. Anti-action check.

**Pruning rule:** Guard measures that have never fired across CI history AND don't represent a live risk are pruning candidates. Keep only Guards backed by an observed incident, compliance teeth, or active-probe value.

---

## 9. Workspace state — git diff against pristine fixture

**Pattern:**

```python
@evaluation_measure
def scope_respected(ctx: EvalContext) -> dict:
    """Agent only modified files within the declared scope."""
    allowed_modified = set(ctx.expect.get("allowed_modified") or [])
    allowed_new = set(ctx.expect.get("allowed_new") or [])
    allowed_new_dirs = [d.rstrip("/") + "/" for d in (ctx.expect.get("allowed_new_dirs") or [])]
    workspace = ctx.metadata.get("environment_context", {}).get("workspace_root")
    if not workspace:
        return fail_reason("no workspace_root")

    def lines(args):
        out = subprocess.run(["git", *args], cwd=workspace, capture_output=True, text=True, check=False)
        return [l for l in out.stdout.splitlines() if l.strip()] if out.returncode == 0 else []

    modified = lines(["diff", "--name-only", "HEAD"])
    added = lines(["ls-files", "--others", "--exclude-standard"])
    deleted = lines(["diff", "--name-only", "--diff-filter=D", "HEAD"])

    bad_modified = [m for m in modified if m not in allowed_modified]
    bad_added = [a for a in added
                 if a not in allowed_new
                 and not any(a.startswith(d) for d in allowed_new_dirs)]

    if bad_modified or bad_added or deleted:
        return fail_reason("out-of-scope changes",
                           modified_out_of_scope=bad_modified,
                           added_out_of_scope=bad_added, deleted=deleted)
    return pass_reason(f"scope respected (modified={len(modified)}, added={len(added)})")
```

**Tier:** `quality`. Catches "fixed the symptom by editing 30 unrelated files" patterns.

**Note:** the env initializes the workspace as a git repo, so `.gitignore` filters noise (.venv, __pycache__, etc.).

---

## 10. SQL row exists (DB-backed scenarios)

**Pattern:**

```python
@evaluation_measure
def db_row_exists(ctx: EvalContext) -> dict:
    """Run a SQL query against the env-staged DB; pass if it returns a row."""
    sql = ctx.expect.get("assert_sql")
    if not sql:
        return pass_reason("no assert_sql specified")
    db_path = ctx.metadata.get("environment_context", {}).get("db_path")
    if not db_path:
        return fail_reason("no db_path in environment context")
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(sql).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as e:
        return fail_reason(f"sqlite error: {e}")
    if row is None:
        return fail_reason(f"no row matched: {sql.strip()[:100]}")
    return pass_reason(f"row found: {row}")
```

**Tier:** `outcome`. The DB state IS the goal.

---

## 11. Test-suite preservation (anti-tampering Guard)

**Pattern:**

```python
@evaluation_measure
def no_test_disabling(ctx: EvalContext) -> dict:
    """Agent didn't delete or skip/xfail existing tests to make pytest pass."""
    env_ctx = ctx.metadata.get("environment_context", {})
    workspace = env_ctx.get("workspace_root")
    fixture_src = env_ctx.get("fixture_src_dir")
    tests_dir = ctx.expect.get("tests_dir", "tests")
    test_def = re.compile(r"^\s*def\s+test_\w+", re.M)
    skip_dec = re.compile(r"@pytest\.mark\.(skip|xfail)")
    def scan(root):
        n = s = 0
        base = Path(root) / tests_dir
        for f in base.rglob("test_*.py") if base.is_dir() else []:
            text = f.read_text(errors="replace")
            n += len(test_def.findall(text))
            s += len(skip_dec.findall(text))
        return n, s
    init_n, init_s = scan(fixture_src)
    final_n, final_s = scan(workspace)
    if final_n < init_n:
        return fail_reason(f"test count dropped: {init_n} → {final_n}")
    if final_s > init_s:
        return fail_reason(f"skip/xfail decorators added: {init_s} → {final_s}")
    return pass_reason(f"tests preserved (count {init_n} → {final_n}, skips {init_s} → {final_s})")
```

**Tier:** `guard`. Catches "agent disabled the failing test" patterns.

---

## 12. LLM judge (oracle, last resort)

**Pattern:** Define a judge in `evaluations/evaluation.yml` and reference it from the scenario via `judges:`. Then the measure reads the judge's verdict from `ctx.metadata`:

```python
@evaluation_measure
def judge_pass(ctx: EvalContext) -> dict:
    """Agent's output passed the LLM judge."""
    result = ctx.judge_result("my_judge_name") if hasattr(ctx, "judge_result") else None
    if not result:
        return fail_reason("no judge result available")
    if result.get("answer") == "Pass":
        return pass_reason(result.get("reasoning", ""))
    return fail_reason(result.get("reasoning", "judge said Fail"))
```

**Tier:** depends on what the judge evaluates — usually `quality` (subjective property of the artifact) or `outcome` (the artifact's correctness given a hard-to-verify property).

**Use sparingly.** Judges are expensive, slow, and non-deterministic. Always check whether a deterministic verifier exists first.

---

## When NOT to write a new measure

- **The property has no verifier.** Drop the property; it doesn't belong in the eval.
- **An existing measure already covers it.** Reuse via `ctx.expect` config keys instead of duplicating logic.
- **The measure would only fire on specific test inputs the agent rarely sees in real use.** That's a unit test for the framework, not an eval measure.
- **The property is "the agent was helpful / friendly / safe."** Not specific, not falsifiable. Don't measure personality.
