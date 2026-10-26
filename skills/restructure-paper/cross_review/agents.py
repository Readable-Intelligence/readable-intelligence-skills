"""Running Claude and GPT agents in isolated workspaces, adapted from the readability lab (`readability_lab/agents.py`).

Each job runs in its own workspace with an opaque name under `<run>/ws/`; its inputs are copied in. While a batch of
jobs runs, the run's records (earlier outputs, prompts, reviews) are locked with chmod 000, and afterwards every tool
call is audited for access outside the job's own workspace. A finished job is archived to `records/jobs/<name>/` with a
`_done` marker, so a resumed run skips it, and with `_activity.md`, a readable account of what the agent did. A job
whose outputs fail their checks is retried in a fresh session that starts from the failed attempt's outputs
(`Job.carry`), so a long review is corrected rather than redone.
"""
import collections, json, os, re, shutil, signal, stat, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
RATE_PAT = re.compile(r"(usage limit|rate.?limit|\b429\b|quota|limit reached|too many requests|overloaded|resets at)", re.I)
DEFAULT_CODEX_OPTIONAL = ["features.memories=false", "features.skills=false", 'history.persistence="none"',
                          "project_doc_max_bytes=0"]
USER_CODEX_AUTH = Path("~/.codex/auth.json").expanduser()
_AUTH_LOCK = threading.Lock()
DATALESS = 0x40000000               # macOS file flag: the content is in iCloud only, and reading it waits for a download


def in_icloud_only(p: Path):
    try:
        return bool(os.stat(p).st_flags & DATALESS)
    except (AttributeError, OSError):
        return False


def require_local(paths):
    """Stop unless every file in `paths` (files or folders) is on this disk. iCloud moves the content of little-used
    files to the cloud when the disk is short of space; reading such a file waits for a download and, when iCloud does
    not deliver, returns nothing, so a step would run with an empty prompt."""
    files = [f for p in map(Path, paths) for f in ([p] if p.is_file() else p.rglob("*") if p.is_dir() else [])]
    away = [str(f) for f in files if f.is_file() and in_icloud_only(f)]
    if away:
        raise SystemExit("these files are in iCloud only; download them (open them, or `brctl download FILE`) and "
                         "start again:\n  " + "\n  ".join(away))
_LOG_LOCK = threading.Lock()


def log(msg):
    with _LOG_LOCK:
        print(time.strftime("%H:%M:%S"), msg, flush=True)


def jload(p, default=None):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else default


def jdump(obj, p):
    """Write JSON atomically: a kill mid-write must not leave an empty state file."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    os.replace(tmp, p)


def validate(obj, schema, path="$"):
    """Minimal JSON-schema check: type, required, properties, items, enum, minItems."""
    pytypes = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    t = schema.get("type")
    if t and (not isinstance(obj, pytypes[t]) or (t == "integer" and isinstance(obj, bool))):
        return [f"{path}: expected {t}"]
    errs = []
    if "enum" in schema and obj not in schema["enum"]:
        errs.append(f"{path}: {obj!r} not in {schema['enum']}")
    if t == "object":
        errs += [f"{path}: missing '{k}'" for k in schema.get("required", []) if k not in obj]
        for k, sub in schema.get("properties", {}).items():
            if k in obj:
                errs += validate(obj[k], sub, f"{path}.{k}")
    if t == "array":
        if len(obj) < schema.get("minItems", 0):
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        for i, it in enumerate(obj):
            errs += validate(it, schema.get("items", {}), f"{path}[{i}]")
    return errs


def claude_cmd(c, prompt, network=False):
    web = ["WebSearch", "WebFetch"]
    return [c.get("bin", "claude"), "-p", prompt, "--model", c["model"], "--effort", c["effort"],
            "--output-format", "stream-json", "--verbose", "--no-session-persistence",
            "--permission-mode", "acceptEdits", "--tools", ",".join(["Read", "Write", "Edit", "Glob", "Grep"]
                                                                     + (web if network else [])),
            *(["--allowedTools", *web] if network else []),       # pre-approved: nobody can answer a prompt
            "--disallowedTools", "Bash", *([] if network else web), "mcp__*",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--restricted", "--safe-mode", "--permission-prompts", "none"] + c.get("extra_args", [])


def codex_cmd(g, ws, prompt, network=False):
    cmd = [g.get("bin", "codex"), "exec", "--cd", str(ws), "--skip-git-repo-check", "--sandbox", "workspace-write",
           "--json", "--ephemeral", "--ignore-user-config", "-o", str(Path(ws) / "_final_message.txt"),
           "-c", f'model_reasoning_effort="{g["effort"]}"', "-c", 'approval_policy="never"',
           "-c", f"sandbox_workspace_write.network_access={'true' if network else 'false'}",
           "-c", f'web_search="{"live" if network else "disabled"}"']
    for opt in g.get("optional_config", DEFAULT_CODEX_OPTIONAL):
        cmd += ["-c", opt]
    if g.get("model"):
        cmd += ["-m", g["model"]]
    return cmd + g.get("extra_args", []) + [prompt]


def kill_group(proc, grace=5):
    """Terminate an agent and everything it started (it runs in its own process group)."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def isolated_codex_home(run_dir: Path):
    """GPT steps run with their own CODEX_HOME inside the run directory, holding only a link to the user's login:
    the user's global AGENTS.md, skills, memories and session history live in the Codex home and would otherwise reach
    every step."""
    home = run_dir / "_codex_home"
    home.mkdir(parents=True, exist_ok=True)
    link = home / "auth.json"
    if not link.is_symlink():
        if link.exists():
            link.unlink()
        link.symlink_to(USER_CODEX_AUTH)
    return home


def keep_codex_login(home: Path, before: bytes):
    """If Codex refreshed the login by replacing the link with a file, carry the refreshed login back to the user's
    auth.json (only if that file is unchanged since the step started) and restore the link."""
    link = home / "auth.json"
    with _AUTH_LOCK:
        if link.is_symlink() or not link.exists():
            return
        fresh = link.read_bytes()
        if USER_CODEX_AUTH.exists() and USER_CODEX_AUTH.read_bytes() == before and fresh != before:
            tmp = USER_CODEX_AUTH.with_name("auth.json.lab-tmp")
            tmp.write_bytes(fresh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, USER_CODEX_AUTH)
            log("codex refreshed its login during a step; the refreshed login was written back to ~/.codex/auth.json")
        link.unlink()
        link.symlink_to(USER_CODEX_AUTH)


def clip(s, n=300):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + " ..."


def activity_md(j, d: Path):
    """What the agent of job `j` did, read from its log in `d`: the time, tokens and attempt; then its messages and
    tool calls in order, with paths given within its workspace."""
    ws = str(j.ws)
    short = lambda s: s.replace(ws + "/", "").replace(ws, ".")
    steps, counts, usage = [], collections.Counter(), ""
    log_file = d / "_stdout.jsonl"
    for line in log_file.read_text(errors="replace").splitlines() if log_file.exists() else []:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        if j.model == "claude":
            msg = ev.get("message") if ev.get("type") == "assistant" and isinstance(ev.get("message"), dict) else {}
            for c in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text" and c.get("text", "").strip():
                    steps.append("Said: " + clip(c["text"], 600))
                elif c.get("type") == "tool_use":
                    counts[c.get("name")] += 1
                    inp = {k: v for k, v in (c.get("input") or {}).items() if k not in ("content", "old_string", "new_string")}
                    steps.append(f"{c.get('name')}: " + clip(short(json.dumps(inp, ensure_ascii=False))))
            if ev.get("type") == "result":
                u = ev.get("usage") or {}
                usage = (f"output {u.get('output_tokens')} tokens (thinking {(u.get('output_tokens_details') or {}).get('thinking_tokens')}), "
                         f"{ev.get('num_turns')} turns, ${ev.get('total_cost_usd') or 0:.2f}")
        else:
            it = ev.get("item") if ev.get("type") == "item.completed" and isinstance(ev.get("item"), dict) else None
            kind = (it or {}).get("type")
            if kind == "agent_message":
                steps.append("Said: " + clip(it.get("text", ""), 600))
            elif kind == "command_execution":
                counts["command"] += 1
                steps.append("Ran: " + clip(short(it.get("command", "")).removeprefix("/bin/zsh -lc ")))
            elif kind == "web_search":
                a = it.get("action") or {}
                counts["web " + str(a.get("type"))] += 1
                what = ("; ".join(a.get("queries") or []) if a.get("type") == "search" else a.get("url") or a.get("pattern")
                        or it.get("query") or "")
                steps.append(f"Web ({a.get('type')}): " + clip(what))
            elif kind == "file_change":
                counts["file change"] += 1
                steps.append("Wrote: " + ", ".join(short(c.get("path", "")) for c in it.get("changes", [])))
            if ev.get("type") == "turn.completed":
                u = ev.get("usage") or {}
                usage = (f"input {u.get('input_tokens')} tokens ({u.get('cached_input_tokens')} cached), "
                         f"output {u.get('output_tokens')} (reasoning {u.get('reasoning_output_tokens')})")
    mins = f"{(j.t1 - j.t0) / 60:.1f} min" if j.t0 and j.t1 else "unknown"
    L = [f"# Activity of {j.name} ({j.model}), attempt {j.attempt}", "",
         f"- Time: {mins}. Usage: {usage or 'not reported'}.",
         "- Tool calls: " + (", ".join(f"{k} {n}" for k, n in counts.most_common()) or "none") + "."]
    if j.note:
        L.append("- This attempt was a retry. " + clip(j.note, 2000))
    L += ["", "## In order", ""] + [f"{n}. {s}" for n, s in enumerate(steps, 1)]
    return "\n".join(L) + "\n"


class Text(str):
    """Literal file content in `Job.files`, in place of a path to copy."""


class Job:
    """One agent call. `files` maps workspace paths to sources (files or directories); `expect` maps required output
    paths to a schema name (or None); `role` names the prompt, for the stub agent. `cfg_key` picks the config section
    with the model settings (default: the model's own section); `network` lets the agent use the network. `carry` lists
    the output paths that a retry starts from."""

    def __init__(self, name, model, role, prompt, files, expect, page_timed=False, postcheck=None, cfg_key=None,
                 network=False, carry=()):
        self.name, self.model, self.role, self.prompt = name, model, role, prompt
        self.files, self.expect, self.page_timed, self.postcheck = files, expect, page_timed, postcheck
        self.cfg_key, self.network, self.carry, self.previous = cfg_key or model, network, list(carry), None
        self.attempt, self.note, self.ws, self.result, self.t0, self.t1 = 0, "", None, None, None, None


class Runner:
    def __init__(self, run_dir: Path, cfg: dict, mock=False):
        self.dir, self.cfg, self.mock = run_dir, cfg, mock
        self.records, self.ws_root = run_dir / "records", run_dir / "ws"
        self.jobs_dir = self.records / "jobs"
        self.ws_root.mkdir(parents=True, exist_ok=True)
        self.locked = run_dir / "locked.json"
        self.procs = set()
        self.pages = 0          # pages of the longest paper in the run, for page-scaled timeouts
        if not mock:
            os.environ["CODEX_HOME"] = str(isolated_codex_home(run_dir))

    # ------------------------------------------------------------------ locking
    def lock(self):
        if not self.cfg.get("lock_records", True) or not self.records.exists():
            return
        jdump({"path": str(self.records), "mode": stat.S_IMODE(self.records.stat().st_mode)}, self.locked)
        os.chmod(self.records, 0)

    def unlock(self):
        held = jload(self.locked)
        if held:
            os.chmod(held["path"], held["mode"] or 0o755)
            self.locked.unlink()

    # ------------------------------------------------------------------ staging
    def set_aside_leftovers(self):
        """Workspaces of jobs interrupted by a stop are moved out of the way (kept, not deleted)."""
        left = [d for d in self.ws_root.iterdir() if d.is_dir()]
        if left:
            dst = self.records / "interrupted" / time.strftime("%Y%m%d-%H%M%S")
            dst.mkdir(parents=True, exist_ok=True)
            for d in left:
                shutil.move(str(d), str(dst / d.name))
            log(f"moved {len(left)} workspace(s) of interrupted jobs to {dst}")

    def done(self, name):
        d = self.jobs_dir / name
        return d if (d / "_done").exists() else None

    def stage(self, j):
        ws = self.ws_root / os.urandom(6).hex()       # opaque name: the agent cannot infer the round or role
        ws.mkdir(parents=True)
        for dst, src in j.files.items():
            d = ws / dst
            d.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(src, Text):
                d.write_text(src)
            elif Path(src).is_dir():
                shutil.copytree(src, d, ignore=shutil.ignore_patterns("_tmp", "_done"), dirs_exist_ok=True)
            else:
                shutil.copy(src, d)
        kept = []
        for rel in j.carry if j.previous else []:
            p = j.previous / rel
            if p.is_dir():
                shutil.copytree(p, ws / rel, dirs_exist_ok=True)
            elif p.is_file():
                (ws / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(p, ws / rel)
            else:
                continue
            kept.append(rel)
        net = ("You may use the network only to consult literature." if j.network else "Do not access the network.")
        avoid = self.cfg.get("avoid", [])
        if j.network and avoid:
            net += (" Never open, download or search for the paper under review itself, in any version, or anything "
                    f"written about it (it is identified by: {', '.join(json.dumps(s) for s in avoid)}).")
        iso = (f"\n\n## Isolation (mandatory)\nYour workspace is `{ws}`. Read and write only inside it. Do not read, list "
               "or search any other path on this machine, including your home directory, other workspaces, and any "
               f"other agent's files or logs. {net} Write every required output file before you "
               "finish; outputs are validated by script.")
        if j.note:
            iso += "\n\n" + j.note
        if kept:
            iso += ("\n\nYour workspace already holds that attempt's outputs (" + ", ".join(f"`{k}`" for k in kept)
                    + "). Start from them: keep what is correct, and correct what the problems above concern.")
        (ws / "_prompt.md").write_text(j.prompt + iso + "\n")
        j.ws = ws

    def command(self, j):
        prompt = (j.ws / "_prompt.md").read_text()
        if self.mock:
            return [sys.executable, str(HERE / "mock_agent.py"), j.role, str(j.ws), j.name]
        sub = self.cfg[j.cfg_key]
        return claude_cmd(sub, prompt, j.network) if j.model == "claude" else codex_cmd(sub, j.ws, prompt, j.network)

    # ------------------------------------------------------------------ running
    def run(self, jobs):
        """Run a batch: skip finished jobs; stage -> lock -> run in parallel -> unlock -> check -> archive; retry."""
        out = {j.name: self.done(j.name) for j in jobs}
        pending = [j for j in jobs if out[j.name] is None]
        wait = self.cfg["rate_limit"]["initial_wait_min"] * 60
        while pending:
            for j in pending:
                j.attempt += 1
                self.stage(j)
            sems = {"claude": threading.Semaphore(self.cfg.get("max_parallel_claude", 4)),
                    "gpt": threading.Semaphore(self.cfg.get("max_parallel_gpt", 6))}
            self.lock()
            try:
                with ThreadPoolExecutor(max_workers=len(pending)) as ex:
                    list(ex.map(lambda j: self.run_one(j, sems[j.model]), pending))
            finally:
                self.unlock()
            self.record_timings(pending)
            retry, rate_limited, refused = [], False, []
            for j in pending:
                status, problems = self.check(j)
                if status == "ok":
                    out[j.name] = self.archive(j, done=True)
                    continue
                prev = self.archive(j, suffix=f"attempt{j.attempt}" + {"rate": "_ratelimited",
                                                                        "refused": "_refused"}.get(status, ""))
                if status == "refused":
                    refused.append(f"{j.name}: {', '.join(problems)}")
                    continue
                if status == "fail":            # not after an isolation violation: those outputs are not reused
                    j.previous = prev
                if status == "rate":
                    rate_limited = True
                    j.attempt -= 1
                    retry.append(j)
                    continue
                log(f"{j.name}: attempt {j.attempt} problems: {problems[:4]}")
                if status == "violation" and j.attempt >= 2:
                    raise SystemExit(f"isolation violation persisted in {j.name}: {problems}")
                if j.attempt > self.cfg.get("retries", 2):
                    raise SystemExit(f"step {j.name} failed after {j.attempt} attempts: {problems[:6]}")
                j.note = ("A previous attempt at this task (in a separate session) had these problems; avoid them:\n- "
                          + "\n- ".join(problems[:20]))
                retry.append(j)
            if refused:
                raise SystemExit("tool calls were refused for lack of permission, a setup problem that a retry cannot "
                                 "fix (finished steps are kept; resume after fixing it): " + "; ".join(refused))
            if rate_limited:
                log(f"usage/rate limit detected; sleeping {wait // 60} min before retrying")
                time.sleep(wait)
                wait = min(wait * 2, self.cfg["rate_limit"]["max_wait_min"] * 60)
            pending = retry
        return [out[j.name] for j in jobs]

    def run_one(self, j, sem):
        with sem:
            log(f"[{j.model}] {j.name} (attempt {j.attempt})")
            to = self.cfg[j.cfg_key]["timeout_min"] * 60
            if j.page_timed:
                to = max(to, int(self.pages * self.cfg.get("timeout_per_page_min", 2) * 60))
            tmpd = j.ws / "_tmp"            # the agent's temporary files stay inside its own workspace
            tmpd.mkdir(exist_ok=True)
            env = dict(os.environ, TMPDIR=str(tmpd))
            before = USER_CODEX_AUTH.read_bytes() if j.model == "gpt" and USER_CODEX_AUTH.exists() else b""
            j.t0 = time.time()
            proc = subprocess.Popen(self.command(j), cwd=j.ws, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)
            self.procs.add(proc)
            try:
                o, e = proc.communicate(timeout=to)
                rc = proc.returncode
            except subprocess.TimeoutExpired:
                kill_group(proc)
                o, e = proc.communicate()
                rc, e = -9, (e or "") + "\nTIMEOUT"
            finally:
                self.procs.discard(proc)
            j.result, j.t1 = (rc, o, e), time.time()
            if j.model == "gpt" and not self.mock:
                keep_codex_login(Path(os.environ["CODEX_HOME"]), before)
            (j.ws / "_stdout.jsonl").write_text(o or "")
            (j.ws / "_stderr.txt").write_text(e or "")

    def stop_children(self):
        for proc in list(self.procs):
            kill_group(proc)

    def record_timings(self, jobs):
        self.records.mkdir(parents=True, exist_ok=True)
        with open(self.records / "timings.jsonl", "a") as fh:
            for j in jobs:
                if j.t0:
                    fh.write(json.dumps({"job": j.name, "model": j.model, "attempt": j.attempt,
                                         "start": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(j.t0)),
                                         "minutes": round((j.t1 - j.t0) / 60, 1)}) + "\n")

    @staticmethod
    def rate_limited(out, err):
        """A usage/rate limit reported by the CLI itself: in stderr, or in its final error/result event."""
        if RATE_PAT.search((err or "")[-4000:]):
            return True
        for line in (out or "").splitlines()[-30:]:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue
            failed = ev.get("type") in ("error", "turn.failed") or ev.get("is_error") is True or \
                str(ev.get("subtype", "")).startswith("error")
            if failed and RATE_PAT.search(json.dumps(ev)[:4000]):
                return True
        return False

    def check(self, j):
        rc, out, err = j.result
        if rc not in (0, -9) and self.rate_limited(out, err):
            j.rate_hits = getattr(j, "rate_hits", 0) + 1
            if j.rate_hits <= int(self.cfg["rate_limit"].get("max_retries", 12)):
                return "rate", []
            return "fail", [f"usage-limit responses {j.rate_hits} times in a row; giving up on this step"]
        refused = self.refused(j, out or "")
        if refused:
            return "refused", refused
        viol = self.audit(j, out or "")
        if viol:
            return "violation", viol
        problems = []
        if rc != 0:
            problems.append(f"process exited with code {rc}: {(err or '')[-300:]}")
        for rel, sch in j.expect.items():
            p = j.ws / rel
            if not p.exists():
                problems.append(f"missing output {rel}")
            elif sch:
                try:
                    errs = validate(json.loads(p.read_text()), jload(HERE / "schemas" / f"{sch}.schema.json"))
                    problems += [f"{rel}: {e}" for e in errs[:20]]
                except json.JSONDecodeError as e:
                    problems.append(f"{rel}: invalid JSON ({e})")
        if not problems and j.postcheck:
            problems += j.postcheck(j.ws)
        if problems and all(p.startswith("process exited") for p in problems):
            problems = []           # outputs are complete and valid; a non-zero exit alone is tolerated
        return ("ok", []) if not problems else ("fail", problems)

    @staticmethod
    def refused(j, stdout):
        """Tool calls that Claude Code refused because nobody could approve them: the tools are misconfigured."""
        if j.model != "claude":
            return []
        names, bad = {}, collections.Counter()
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = ev.get("message") if isinstance(ev, dict) and isinstance(ev.get("message"), dict) else {}
            for c in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use":
                    names[c.get("id")] = c.get("name")
                elif c.get("type") == "tool_result" and c.get("is_error") and \
                        "Permission for this tool use was denied" in json.dumps(c.get("content")):
                    bad[names.get(c.get("tool_use_id"), "a tool")] += 1
        return [f"{n} refused {k} time(s)" for n, k in bad.items()]

    def audit(self, j, stdout):
        """Flag access to anything outside the job's own workspace that could carry another agent's work."""
        if self.mock:
            return []
        sensitive = [str(self.dir.parent), str(Path("~/.claude").expanduser()), str(Path("~/.codex").expanduser()),
                     str(HERE), *self.cfg.get("sensitive", [])]
        own = str(j.ws)
        avoid = [s.lower() for s in self.cfg.get("avoid", []) if s]
        target = lambda text: j.network and any(s in text.lower() for s in avoid)
        bad = set()
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue
            if j.model == "claude":
                msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
                for c in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                    if not isinstance(c, dict) or c.get("type") != "tool_use":
                        continue
                    name, inp = c.get("name", ""), c.get("input", {}) or {}
                    if name == "Bash" or name.startswith("mcp__") or (
                            name in ("WebFetch", "WebSearch") and not j.network):
                        bad.add(f"forbidden tool {name}")
                    if name in ("WebFetch", "WebSearch") and target(json.dumps(inp)):
                        bad.add(f"searched for or fetched the paper under review: {clip(json.dumps(inp), 160)}")
                    for k in ("file_path", "path"):
                        v = inp.get(k)
                        if v and Path(v).is_absolute() and not str(Path(v).resolve()).startswith(own):
                            bad.add(f"{name} outside workspace: {v}")
            else:
                item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
                text = json.dumps(item)
                for p in re.findall(r"(?<![\w.:/])((?:/|~/)[\w./~-]+)", re.sub(r"https?://\S+", "", text)):
                    full = str(Path(p).expanduser())
                    if any(full.startswith(s) for s in sensitive) and not full.startswith(own):
                        bad.add(f"codex touched {p}")
                if item.get("type") == "web_search" and not j.network:
                    bad.add("web search in an offline step")
                if target(text) and (item.get("type") == "web_search" or (       # not the agent's own messages
                        item.get("type") == "command_execution" and re.search(r"curl|wget|fetch", text))):
                    bad.add(f"searched for or fetched the paper under review: {clip(text, 160)}")
        return sorted(bad)[:20]

    def archive(self, j, done=False, suffix=""):
        dst = self.jobs_dir / (j.name + (f".{suffix}" if suffix else ""))
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(j.ws), str(dst))
        (dst / "_activity.md").write_text(activity_md(j, dst))
        if done:
            (dst / "_done").write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
        return dst
