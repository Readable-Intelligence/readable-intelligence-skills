#!/usr/bin/env python3
"""restructure-paper orchestrator, fully automated, no user input. GPT writes a baseline revision and its proof
sketch; then each round's revision is written by the cross review (cross_review/: Claude and GPT review the writing
against the paper's literature, each judges the other's list, GPT revises), which also decides the problems that the
checks of the version before found. Every version is checked against the original (fidelity, proof check, a review
against the editorial standard, a blind vote); a version with soundness debt goes to the repair loop.

  python3 duo.py run    --src PAPER_SRC_DIR --out RUN_DIR [--config my.json] [--mock]
  python3 duo.py resume --out RUN_DIR [--config my.json] [--mock]
  python3 duo.py status --out RUN_DIR
  python3 duo.py unlock --out RUN_DIR      # restore directory permissions after a crash
  python3 duo.py probe-mixed --out RUN_DIR # test whether Claude and GPT steps can run at the same time

Standard library only. Needs on PATH: claude (Claude Code), codex (Codex CLI), latexmk, pdftotext.
"""
import argparse, difflib, json, os, random, re, shutil, signal, stat, subprocess, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(HERE))
import texutil as tx  # noqa: E402
import standard as sd  # noqa: E402
CROSS = PKG / "cross_review"            # the cross review that writes each round's revision (cross_review/README.md)
sys.path.insert(1, str(CROSS))
import rounds as crossrounds  # noqa: E402

CONF_RANK = {"low": 0, "medium": 1, "high": 2}
DEFAULT_CODEX_OPTIONAL = ["features.memories=false", "features.skills=false", 'history.persistence="none"', "project_doc_max_bytes=0"]
RATE_PAT = re.compile(r"(usage limit|rate.?limit|\b429\b|quota|limit reached|too many requests|overloaded|resets at)", re.I)
# Roles whose work grows with the paper: their timeout is at least timeout_per_page_min per page of the original.
PAGE_TIMED = {"gpt_baseline.md", "gpt_baseline_2.md", "gpt_sketch.md", "gpt_execute.md", "accept.md", "pairwise.md",
              "fidelity.md", "check.md", "claude_calibrate.md"}
BAD_STATUS = ("unsupported", "false")
AGENT_RECORDS = {"changes.md", "sources.md", "notes.json", "receipt.json", "audit.json", "audit.md"}


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def jload(p, default=None):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else default


def jdump(obj, p):
    """Write JSON atomically: a kill mid-write must not leave an empty state file."""
    p = Path(p)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    os.replace(tmp, p)


def norm_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


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


def effort_for(cfg, model, prompt):
    """Per-role effort override (config `role_effort`), else the model's configured effort."""
    return cfg.get("role_effort", {}).get(prompt) or cfg[model]["effort"]


def model_for(cfg, model, prompt):
    """Per-role model override (config `role_model`), else the model family's configured model."""
    return cfg.get("role_model", {}).get(prompt) or cfg[model]["model"]


def claude_cmd(cfg, prompt, effort=None, model=None):
    c, iso = cfg["claude"], cfg["isolation"]
    cmd = [c["bin"], "-p", prompt, "--model", model or c["model"], "--effort", effort or c["effort"],
           "--output-format", "stream-json", "--verbose", "--no-session-persistence",
           "--permission-mode", "acceptEdits", "--tools", ",".join(iso.get("claude_tools", ["Read", "Write", "Edit", "Glob", "Grep"])),
           "--disallowedTools", "Bash", "WebFetch", "WebSearch", "mcp__*",
           "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
    for flag, key in (("--restricted", "claude_restricted"), ("--safe-mode", "claude_safe_mode")):
        if iso.get(key, True):
            cmd.append(flag)
    if iso.get("claude_permission_prompts_none", True):
        cmd += ["--permission-prompts", "none"]
    return cmd + c.get("extra_args", [])


def codex_cmd(cfg, ws, prompt, web, effort=None, model=None):
    g = cfg["gpt"]
    cmd = [g["bin"], "exec", "--cd", str(ws), "--skip-git-repo-check", "--sandbox", "workspace-write",
           "--json", "--ephemeral", "--ignore-user-config", "-o", str(Path(ws) / "_final_message.txt"),
           "-c", f'model_reasoning_effort="{effort or g["effort"]}"', "-c", 'approval_policy="never"',
           "-c", f"sandbox_workspace_write.network_access={'true' if web else 'false'}"]
    for opt in g.get("optional_config", DEFAULT_CODEX_OPTIONAL):
        cmd += ["-c", opt]
    cmd += ["-c", f'web_search="{"live" if web else "disabled"}"']
    if model or g.get("model"):
        cmd += ["-m", model or g["model"]]
    return cmd + g.get("extra_args", []) + [prompt]


def foreign_store_paths(models):
    """Session and history stores an agent of the *other* family must not read while `models` run."""
    paths = []
    if "gpt" in models and not os.environ.get("CLAUDECODE"):
        # When launched from inside Claude Code, its live session writes here; rely on the audit instead.
        paths += ["~/.claude/projects", "~/.claude/todos", "~/.claude/shell-snapshots",
                  "~/.claude/file-history", "~/.claude/history.jsonl"]
    if "claude" in models:
        paths += ["~/.codex/sessions", "~/.codex/archived_sessions", "~/.codex/history.jsonl", "~/.codex/memories"]
    return paths


def synced_folder(path: Path):
    """The synced root containing `path`, if a known sync service mirrors it (macOS iCloud Drive, including
    Desktop & Documents sync, Dropbox, OneDrive, Google Drive); None otherwise. A path component ending in `.nosync`
    is excluded from iCloud sync."""
    path = path.resolve()
    if any(part.endswith(".nosync") for part in path.parts):
        return None
    home = Path.home()
    roots = []
    cloud = home / "Library" / "Mobile Documents"
    if cloud.exists():
        roots.append(cloud)
        docs = cloud / "com~apple~CloudDocs"
        for name in ("Desktop", "Documents"):
            link = docs / name
            if link.is_symlink() or link.is_dir():
                roots.append(link.resolve())
    cs = home / "Library" / "CloudStorage"
    if cs.exists():
        roots += [d.resolve() for d in cs.iterdir() if d.is_dir()]
    roots += [home / n for n in ("Dropbox", "OneDrive", "Google Drive") if (home / n).exists()]
    for r in roots:
        try:
            path.relative_to(r.resolve())
            return r
        except ValueError:
            continue
    return None


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


USER_CODEX_AUTH = Path("~/.codex/auth.json").expanduser()
_AUTH_LOCK = threading.Lock()


def isolated_codex_home(out: Path):
    """Codex steps run with their own CODEX_HOME inside the run directory, holding only a link to the user's login.
    `--ignore-user-config` skips only config.toml: the user's global AGENTS.md, installed skills, memories and session
    history all live in the Codex home and would otherwise reach every step."""
    home = out / "_codex_home"
    home.mkdir(parents=True, exist_ok=True)
    link = home / "auth.json"
    if not link.is_symlink():
        if link.exists():
            link.unlink()
        link.symlink_to(USER_CODEX_AUTH)
    return home


def keep_codex_login(home: Path, before: bytes):
    """If Codex refreshed the login by replacing the link with a file, carry the refreshed login back to the user's
    auth.json (only if that file is unchanged since the step started) and restore the link, so the user's own Codex
    stays logged in after a token rotation."""
    link = home / "auth.json"
    with _AUTH_LOCK:
        if link.is_symlink() or not link.exists():
            return
        fresh = link.read_bytes()
        if USER_CODEX_AUTH.exists() and USER_CODEX_AUTH.read_bytes() == before and fresh != before:
            tmp = USER_CODEX_AUTH.with_name("auth.json.duo-tmp")
            tmp.write_bytes(fresh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, USER_CODEX_AUTH)
            log("codex refreshed its login during a step; the refreshed login was written back to ~/.codex/auth.json")
        link.unlink()
        link.symlink_to(USER_CODEX_AUTH)


class Locks:
    """chmod 000 on directories an agent must not read. Persisted so `unlock` can recover after a crash."""

    def __init__(self, run_dir):
        self.file = run_dir / "locks.json"
        self.held = jload(self.file, {})

    def lock(self, paths):
        for p in paths:
            p = Path(p).expanduser()
            if p.exists() and str(p) not in self.held:
                self.held[str(p)] = stat.S_IMODE(p.stat().st_mode)
                jdump(self.held, self.file)
                os.chmod(p, 0)

    def unlock_all(self):
        for p, mode in list(self.held.items()):
            try:
                os.chmod(p, mode)
            except FileNotFoundError:
                pass
            del self.held[p]
        jdump(self.held, self.file)


class Job:
    """One role invocation in a fresh workspace."""

    def __init__(self, name, model, prompt, files, expect, web=False, extra=None, rename=None, postcheck=None):
        self.name, self.model, self.prompt, self.files = name, model, prompt, files
        self.expect, self.web, self.extra = expect, web, extra or {}
        self.rename = rename or {}          # output file -> name under which the panel stores it
        self.postcheck = postcheck          # ws -> [problems]: coverage checks beyond the schema
        self.note, self.attempt, self.ws, self.result, self.proc = "", 0, None, None, None
        self.t0 = self.t1 = None


class Run:
    def __init__(self, out: Path, cfg: dict, mock=False):
        self.out, self.cfg, self.mock = out, cfg, mock
        self.vault, self.wsroot = out / "vault", out / "ws"
        for d in (self.vault, self.wsroot):
            d.mkdir(parents=True, exist_ok=True)
        self.state = jload(self.vault / "state.json")
        self.locks = Locks(out)
        self.m0_pages = 0
        self.procs = set()          # running agent processes (each in its own process group)
        self.cross_proc = None      # the running cross review, if any
        self.sems = None            # per-family limits when Claude and GPT jobs share one pool
        self._text, self._paras = {}, {}    # per-version text caches for the debt ledger (cleared on every build)

    def save(self):
        jdump(self.state, self.vault / "state.json")

    def V(self, *parts):
        return self.vault.joinpath(*parts)

    # paths kept in state.json are relative to the vault, so a run directory can be moved or renamed between resumes
    def rel(self, p):
        return str(Path(p).relative_to(self.vault))

    def absp(self, s):
        return Path(s) if Path(s).is_absolute() else self.V(s)

    # ------------------------------------------------------------------ lock effectiveness
    def check_lock_holds(self):
        """Some sync tools (iCloud Drive, Dropbox, OneDrive) silently restore permissions, which makes the vault
        lock useless. Test it once, empirically, before any step runs."""
        if self.mock or not self.cfg["isolation"].get("lock_vault", True):
            return
        synced = synced_folder(self.out)
        if synced:
            raise SystemExit(f"the run directory {self.out} is inside {synced}, which a sync service mirrors; it resets "
                             "directory permissions and makes the vault lock ineffective (observed with iCloud Drive). "
                             "Use a run directory outside it, or (iCloud Drive) a directory whose name ends in `.nosync`.")
        synced = synced_folder(PKG)
        if synced:
            raise SystemExit(f"the skill package {PKG} is inside {synced}, which a sync service mirrors; when the disk "
                             "fills, the service evicts local copies and a step fails while copying its prompts or schemas "
                             "(observed with iCloud Drive). Keep the package outside it, or in a folder ending in `.nosync`.")
        probe = self.out / "_locktest"
        probe.mkdir(exist_ok=True)
        try:
            os.chmod(probe, 0)
            time.sleep(self.cfg.get("lock_test_seconds", 6))
            mode = stat.S_IMODE(probe.stat().st_mode)
        finally:
            os.chmod(probe, 0o700)
            probe.rmdir()
        if mode != 0:
            raise SystemExit(
                f"directory permissions under {self.out} are reset by another program within seconds (mode {mode:o}); "
                "this happens in folders synced by iCloud Drive, Dropbox or OneDrive, and it makes the vault lock "
                "ineffective. Use a run directory outside the synced folder, or (iCloud Drive) give the run directory "
                "a name ending in `.nosync`.")

    # ------------------------------------------------------------------ prompts and staging
    def render(self, job):
        text = sd.render((PKG / "prompts" / job.prompt).read_text())
        for k, v in {"MAIN": self.state["main"], **job.extra}.items():
            text = text.replace("{{" + k + "}}", v)
        iso = [f"\n## Isolation (mandatory)\nYour workspace is `{job.ws}`. Read and write only inside it. Do not read, "
               "list or search any other path on this machine, including your home directory, other workspaces, "
               "and any other agent's files or logs."]
        if job.web:
            ids = ", ".join(json.dumps(s) for s in self.state["target"]["identifiers"])
            iso.append("Web access is allowed only to find and download the reference literature. Never open, download "
                       f"or search for the target manuscript itself or anything about it (identifiers: {ids}).")
        else:
            iso.append("Do not access the network.")
        iso.append("Write every required output file before you finish; outputs are validated by script.")
        if job.note:
            iso.append("\n\n" + job.note)
        return text + "\n" + " ".join(iso) + "\n"

    def stage(self, job):
        ws = self.wsroot / os.urandom(6).hex()     # opaque name: the agent cannot infer the round or role
        if ws.exists():
            shutil.rmtree(ws)
        ws.mkdir(parents=True)
        for dst, src in job.files.items():
            d, src = ws / dst, Path(src)
            d.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, d, ignore=shutil.ignore_patterns("_tmp"), dirs_exist_ok=True)
            else:
                shutil.copy(src, d)
        (ws / "schemas").mkdir(exist_ok=True)
        for s in (PKG / "schemas").glob("*.json"):
            shutil.copy(s, ws / "schemas" / s.name)
        shutil.copy(PKG / "prompts" / "hard_rules.md", ws / "hard_rules.md")
        job.ws = ws
        (ws / "_prompt.md").write_text(self.render(job))

    def command(self, job):
        prompt = (job.ws / "_prompt.md").read_text()
        if self.mock:
            return [sys.executable, str(HERE / "mock_agent.py"), job.prompt, str(job.ws), self.state["main"]]
        eff, mdl = effort_for(self.cfg, job.model, job.prompt), model_for(self.cfg, job.model, job.prompt)
        if job.model == "claude":
            return claude_cmd(self.cfg, prompt, eff, mdl)
        return codex_cmd(self.cfg, job.ws, prompt, job.web, eff, mdl)

    # ------------------------------------------------------------------ running jobs
    def parallelism(self, models):
        c, g = self.cfg.get("max_parallel_claude", 4), self.cfg.get("max_parallel_gpt", 2)
        if models == {"claude"}:
            return c
        if models == {"gpt"}:
            return g
        # Claude and GPT steps lock each other's stores; they overlap only if the start-up probe showed it is safe here.
        return c + g if self.cfg["isolation"].get("allow_mixed_parallel") is True else 1

    def run_jobs(self, jobs):
        """Stage (vault unlocked) -> lock -> run in parallel -> unlock -> validate/archive; retry failures."""
        pending, done = list(jobs), {}
        wait = self.cfg["rate_limit"]["initial_wait_min"] * 60
        while pending:
            for j in pending:
                j.attempt += 1
                self.stage(j)
            # read while the vault is still unlocked; run_one needs it for page-based timeouts
            self.m0_pages = jload(self.V("versions", "M0", "build.json"), {}).get("pages", 0)
            models = {j.model for j in pending}
            self.lock_for(models)
            broken = []
            stop_watch = threading.Event()
            watcher = threading.Thread(target=self.watch_lock, args=(stop_watch, broken), daemon=True)
            watcher.start()
            try:
                par = self.parallelism(models)
                if par == 1 and len(models) > 1:
                    # without mixed parallelism, run each model family's jobs as its own batch
                    for fam in ("claude", "gpt"):
                        fam_jobs = [j for j in pending if j.model == fam]
                        if fam_jobs:
                            self.locks.unlock_all()
                            self.lock_for({fam})
                            with ThreadPoolExecutor(max_workers=self.parallelism({fam})) as ex:
                                list(ex.map(self.run_one, fam_jobs))
                else:
                    if len(models) > 1:
                        # one thread per job; per-family semaphores (not pool slots) enforce each family's limit, so a
                        # job waiting for its family never blocks a job of the other family
                        self.sems = {"claude": threading.Semaphore(self.parallelism({"claude"})),
                                     "gpt": threading.Semaphore(self.parallelism({"gpt"}))}
                        par = len(pending)
                    with ThreadPoolExecutor(max_workers=par) as ex:
                        list(ex.map(self.run_one, pending))
            finally:
                self.sems = None
                stop_watch.set()
                watcher.join(timeout=10)
                self.locks.unlock_all()
            self.record_timings(pending)
            if broken:
                raise SystemExit(f"the vault lock was undone while steps ran ({broken[0]}); stopping. Move the run "
                                 "directory out of any synced folder and `resume`.")
            retry, rate_limited = [], False
            for j in pending:
                status, problems = self.check(j)
                if status == "ok":
                    done[j.name] = self.archive(j.ws, j.name)
                    continue
                self.archive(j.ws, j.name, f"attempt{j.attempt}" + ("_ratelimited" if status == "rate" else ""))
                if status == "rate":
                    rate_limited = True
                    j.attempt -= 1          # do not count against the retry budget
                    retry.append(j)
                    continue
                log(f"{j.name}: attempt {j.attempt} problems: {problems[:4]}")
                if status == "violation" and j.attempt >= 2:
                    raise SystemExit(f"isolation violation persisted in {j.name}: {problems}")
                if j.attempt > self.cfg["retries"]:
                    raise SystemExit(f"step {j.name} failed after {j.attempt} attempts: {problems[:6]}")
                j.note = ("A previous attempt at this task (in a separate session) had these problems; avoid them:\n- "
                          + "\n- ".join(problems[:20]))
                retry.append(j)
            if rate_limited:
                log(f"usage/rate limit detected; sleeping {wait // 60} min before retrying")
                time.sleep(wait)
                wait = min(wait * 2, self.cfg["rate_limit"]["max_wait_min"] * 60)
            pending = retry
        return [done[j.name] for j in jobs]

    def watch_lock(self, stop, broken):
        if self.mock or not self.cfg["isolation"].get("lock_vault", True):
            return
        while not stop.wait(3):
            if str(self.vault) in self.locks.held:
                mode = stat.S_IMODE(self.vault.stat().st_mode)
                if mode != 0 and not stop.wait(1.5) and str(self.vault) in self.locks.held:
                    mode = stat.S_IMODE(self.vault.stat().st_mode)   # re-check: the lock may have just been applied
                    if mode != 0:
                        broken.append(f"vault mode {mode:o} at {time.strftime('%H:%M:%S')}")
                        log(f"LOCK-BROKEN: {broken[-1]}")
                        return

    def record_timings(self, jobs):
        with open(self.V("timings.jsonl"), "a") as fh:
            for j in jobs:
                if j.t0:
                    fh.write(json.dumps({"step": j.name, "model": j.model, "attempt": j.attempt,
                                         "start": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(j.t0)),
                                         "minutes": round((j.t1 - j.t0) / 60, 1)}) + "\n")

    def run_one(self, j):
        sem = self.sems.get(j.model) if self.sems else None
        if sem:
            sem.acquire()
        try:
            log(f"[{j.model}] {j.name} (attempt {j.attempt})")
            to = self.cfg[j.model]["timeout_min"] * 60
            if j.prompt in PAGE_TIMED:
                to = max(to, int(self.m0_pages * self.cfg.get("timeout_per_page_min", 2) * 60))
            tmpd = j.ws / "_tmp"            # the agent's temporary files stay inside its own workspace
            tmpd.mkdir(exist_ok=True)
            env = dict(os.environ, TMPDIR=str(tmpd))
            auth_before = USER_CODEX_AUTH.read_bytes() if j.model == "gpt" and USER_CODEX_AUTH.exists() else b""
            j.t0 = time.time()
            proc = subprocess.Popen(self.command(j), cwd=j.ws, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    env=env, start_new_session=True)
            self.procs.add(proc)
            try:
                out, err = proc.communicate(timeout=to)
                rc = proc.returncode
            except subprocess.TimeoutExpired:
                kill_group(proc)
                out, err = proc.communicate()
                rc, err = -9, (err or "") + "\nTIMEOUT"
            finally:
                self.procs.discard(proc)
            j.result = (rc, out, err)
            j.t1 = time.time()
            if j.model == "gpt" and os.environ.get("CODEX_HOME"):
                keep_codex_login(Path(os.environ["CODEX_HOME"]), auth_before)
            (j.ws / "_stdout.jsonl").write_text(j.result[1] or "")
            (j.ws / "_stderr.txt").write_text(j.result[2] or "")
        finally:
            if sem:
                sem.release()

    def stop_children(self):
        if self.cross_proc:
            kill_group(self.cross_proc, grace=60)       # it first stops its own agents and unlocks its records
        for proc in list(self.procs):
            kill_group(proc, grace=5)

    @staticmethod
    def rate_limited(out, err):
        """A usage/rate limit reported by the CLI itself: in stderr, or in its final error/result event — not anywhere in
        tool output (numbered source lines, page numbers and words like "overloaded" occur there)."""
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
        viol = self.audit_tools(j, out or "")
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
                    errs = validate(json.loads(p.read_text()), jload(PKG / "schemas" / f"{sch}.schema.json"))
                    problems += [f"{rel}: {e}" for e in errs[:20]]
                except json.JSONDecodeError as e:
                    problems.append(f"{rel}: invalid JSON ({e})")
        if not problems and j.postcheck:
            problems += j.postcheck(j.ws)
        if problems and all(p.startswith("process exited") for p in problems):
            problems = []           # outputs are complete and valid; a non-zero exit alone is tolerated
        return ("ok", []) if not problems else ("fail", problems)

    def archive(self, ws, name, suffix=""):
        dst = self.V("steps", name + (f".{suffix}" if suffix else ""))
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(ws), str(dst))
        return dst

    def one(self, *a, **k):
        return self.run_jobs([Job(*a, **k)])[0]

    def lock_for(self, models):
        if self.mock or not self.cfg["isolation"].get("lock_vault", True):
            return
        paths = [self.vault, self.out / "cross"]     # the cross review's records too
        if self.cfg["isolation"].get("lock_foreign_stores", True):
            paths += foreign_store_paths(models)
        self.locks.lock(paths)

    def audit_tools(self, j, stdout):
        """Flag access to anything that could carry the other model's (or another step's) output."""
        if self.mock:
            return []
        sensitive = [str(self.vault), str(self.wsroot), str(Path("~/.claude").expanduser()),
                     str(Path("~/.codex").expanduser()), str(self.out)]
        own = str(j.ws)
        ids = [s.lower() for s in self.state["target"]["identifiers"]]
        bad = set()
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if j.model == "claude":
                msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
                for c in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                    if c.get("type") != "tool_use":
                        continue
                    name, inp = c.get("name", ""), c.get("input", {})
                    if name in ("Bash", "WebFetch", "WebSearch") or name.startswith("mcp__"):
                        bad.add(f"forbidden tool {name}")
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
                if item.get("type") == "web_search" and not j.web:
                    bad.add("web search in an offline step")
                if j.web and any(i and i in text.lower() for i in ids) and re.search(r"curl|wget|fetch|open_page", text):
                    bad.add(f"fetched something matching the target: {text[:160]}")
        return sorted(bad)[:20]

    # ------------------------------------------------------------------ versions
    def build_version(self, name, src_dir):
        """Build a version. The original may carry undefined references; later versions may not add new ones."""
        vd = self.V("versions", name)
        self._text.pop(name, None)
        self._paras.pop(name, None)
        tx.copy_source(Path(src_dir), vd / "src")
        if name != "M0":
            # editing records an agent may leave next to the manuscript never become part of a version
            for f in vd.joinpath("src").rglob("*"):
                if f.is_file() and f.name in AGENT_RECORDS:
                    log(f"{name}: removed agent record {f.relative_to(vd / 'src')} from the source")
                    f.unlink()
        rep = tx.build(vd / "src", self.state["main"], vd / "render")
        if name == "M0":
            rep["ok"] = rep["pdf"]
        elif rep["pdf"]:
            m0 = jload(self.V("versions", "M0", "build.json"))
            new_refs = set(rep["undefined_refs"]) - set(m0["undefined_refs"])
            new_cites = set(rep["undefined_cites"]) - set(m0["undefined_cites"])
            rep["new_undefined"] = sorted(new_refs | new_cites)
            rep["ok"] = not rep["new_undefined"]
        jdump(rep, vd / "build.json")
        if rep["ok"]:
            tx.strip_comments(vd / "src", vd / "src_clean")
            jdump(tx.extract_statements(vd / "src_clean"), vd / "statements.json")
        return rep

    def registrar_fix(self, name, tag, exec_out):
        """The registrar (GPT, its own session) applies the names-and-symbols rule to version `name` and fixes the source
        itself; the version is rebuilt from its output. It runs once, after the last structural change (`terms`). The
        source it started from is kept; if the registrar's source does not build, that source (`exec_out`) stands."""
        vd = self.V("versions", name)
        shutil.copytree(vd / "src_clean", vd / "exec_src_clean", dirs_exist_ok=True)
        shutil.copy(vd / "render.txt", vd / "exec_render.txt")
        (vd / "src_index.txt").write_text("\n".join(tx.number_lines(vd / "src", vd / "_numbered")))
        res = self.one(f"{tag}_registrar", "gpt", "registrar.md",
                       {"src": vd / "src", "src_index.txt": vd / "src_index.txt", "manuscript.txt": vd / "render.txt",
                        "refs": self.V("refs"), "terms_verified.json": self.V("terms_verified.json")},
                       {"out/" + self.state["main"]: None, "registry.md": None})
        rep = self.ensure_builds(name, res / "out")
        if not rep["ok"]:
            log(f"{name}: the registrar's source does not build; the version without its changes stands")
            return self.ensure_builds(name, exec_out)
        shutil.copy(res / "registry.md", vd / "registry.md")
        self.state.setdefault("registry_of", {})[name] = self.rel(vd / "registry.md")
        diff = tx.source_diff(vd / "exec_src_clean", vd / "src_clean").split("\n")
        n = sum(1 for l in diff if l[:1] in ("+", "-") and not l.startswith(("+++", "---")))
        log(f"{name}: the registrar changed {n} source line(s)")
        return rep

    def ensure_builds(self, name, src_dir):
        rep = self.build_version(name, src_dir)
        for t in (1, 2):
            if rep["ok"]:
                break
            log(f"build of {name} failed; GPT build fixer, try {t}")
            vd = self.V("versions", name)
            (vd / "build_log.txt").write_text(rep["log_tail"] + "\nundefined refs: " + ", ".join(rep["undefined_refs"])
                                              + "\nundefined cites: " + ", ".join(rep["undefined_cites"]))
            res = self.one(f"{name}_buildfix{t}", "gpt", "gpt_buildfix.md",
                           {"src": vd / "src", "build_log.txt": vd / "build_log.txt"}, {"out/" + self.state["main"]: None})
            rep = self.build_version(name, res / "out")
        return rep

    def vf(self, name):
        vd = self.V("versions", name)
        return vd / "render.pdf", vd / "render.txt", vd / "src", vd / "src_clean"

    # ------------------------------------------------------------------ setup
    def init(self, src: Path):
        self.state = {"main": tx.find_main(src), "phase": "retrieve", "round": 1, "accepted": ["M0"],
                      "current": "M0", "candidate": None, "baseline": None, "rejections_in_a_row": 0,
                      "ledger": [], "history": [], "target": {}, "pending": {}, "n_versions": 1,
                      "audit_of": {}, "stop_reason": None, "version": "v12"}
        self.save()
        rep = self.build_version("M0", src)
        if not rep["ok"]:
            raise SystemExit("the original source does not compile:\n" + rep["log_tail"][-1500:])
        title = self.guess_title(src)
        self.state["target"] = {"title": title,
                                "identifiers": sorted({title, re.sub(r"\W+", "-", title.lower()).strip("-")})}
        self.save()

    def guess_title(self, src):
        for p in src.rglob("*.tex"):
            t = p.read_text(errors="ignore")
            i = t.find("\\title")
            if i < 0:
                continue
            j, depth, k = t.find("{", i), 0, None
            for k in range(j, len(t)):
                depth += {"{": 1, "}": -1}.get(t[k], 0)
                if depth == 0:
                    break
            raw = t[j + 1:k]
            return re.sub(r"\s+", " ", re.sub(r"\\\\|\\[a-zA-Z]+\*?|[{}$]", " ", raw)).strip()
        return self.V("versions", "M0", "render.txt").read_text().strip().split("\n")[1].strip()

    def filter_refs(self, refs):
        man = jload(refs / "manifest.json")
        t = self.state["target"]["title"].lower()
        keep = []
        for e in man["entries"]:
            if difflib.SequenceMatcher(None, e["title"].lower(), t).ratio() > 0.8:
                log(f"dropping a reference that matches the target: {e['title']}")
                for f in (e.get("txt"), e.get("pdf")):
                    if f and (refs / Path(f).name).exists():
                        (refs / Path(f).name).unlink()
                continue
            keep.append(e)
        man["entries"] = keep
        jdump(man, refs / "manifest.json")

    def drop_refs(self, keys, why):
        refs = self.V("refs")
        man = jload(refs / "manifest.json")
        for e in man["entries"]:
            if e["key"] in keys:
                log(f"dropping reference {e['key']} ({why})")
                for f in (e.get("txt"), e.get("pdf")):
                    if f and (refs / Path(f).name).exists():
                        (refs / Path(f).name).unlink()
        man["entries"] = [e for e in man["entries"] if e["key"] not in keys]
        jdump(man, refs / "manifest.json")

    def claude_refs(self):
        """The reference bundle as Claude sees it: source texts and bibliographic data only. GPT-written
        descriptions (`why`) and GPT's term mapping are withheld; Claude uses its own verified table."""
        d = self.V("refs_for_claude")
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(self.V("refs"), d, ignore=shutil.ignore_patterns("terms.json", "_tmp"))
        man = jload(d / "manifest.json")
        for e in man["entries"]:
            e.pop("why", None)
        jdump(man, d / "manifest.json")
        return d

    def retrieve(self, supplementary=False, before=None):
        pdf, txt, _, _ = self.vf("M0")
        jdump(self.state["target"], self.V("target.json"))
        if before is None:
            before = {e["key"] for e in jload(self.V("refs", "manifest.json"), {"entries": []})["entries"]}
        files = {"manuscript.pdf": pdf, "manuscript.txt": txt, "target.json": self.V("target.json")}
        if supplementary:
            files.update({"gaps.json": self.V("gaps.json"), "refs": self.V("refs")})
        res = self.one("r0_retrieve" + ("_2" if supplementary else ""), "gpt", "gpt_retrieve.md", files,
                       {"refs/manifest.json": "manifest", "refs/terms.json": "terms"}, web=True)
        self.filter_refs(res / "refs")
        shutil.copytree(res / "refs", self.V("refs"), dirs_exist_ok=True)
        after = {e["key"] for e in jload(self.V("refs", "manifest.json"))["entries"]}
        (self.V("new_keys.txt")).write_text("\n".join(sorted(after - before)) + "\n")

    CALIB_OUT = ("architecture.json", "architecture.md", "style_card.md", "rubric_anchors.md", "gaps.json")

    def calibrate(self, supplementary=False):
        """Two Claude jobs in parallel: the standard (bundle check, architecture table, style card, rubric) and the
        terminology table. In supplementary mode each job extends its earlier output with the new references."""
        pdf, txt, _, _ = self.vf("M0")
        refs = self.claude_refs()
        tag = "_2" if supplementary else ""
        fa = {"manuscript.pdf": pdf, "manuscript.txt": txt, "refs": refs}
        fb = {"manuscript.txt": txt, "refs": self.V("refs")}
        if supplementary:
            prev = self.V("calibration_previous")
            if prev.exists():
                shutil.rmtree(prev)
            prev.mkdir()
            for f in self.CALIB_OUT + ("terms_verified.json",):
                if self.V(f).exists():
                    shutil.copy(self.V(f), prev / f)
            fa.update({"previous": prev, "new_keys.txt": self.V("new_keys.txt")})
            fb.update({"previous/terms_verified.json": prev / "terms_verified.json", "new_keys.txt": self.V("new_keys.txt")})
        ja = Job("r0_calibrate" + tag, "claude", "claude_calibrate.md", fa,
                 {"architecture.json": "architecture", "architecture.md": None, "style_card.md": None,
                  "rubric_anchors.md": None, "gaps.json": "gaps"})
        jb = Job("r0_terms" + tag, "gpt", "terms.md", fb, {"terms_verified.json": "terms_verified"})
        ra, rb = self.run_jobs([ja, jb])
        for f in self.CALIB_OUT:
            shutil.copy(ra / f, self.V(f))
        shutil.copy(rb / "terms_verified.json", self.V("terms_verified.json"))
        self.check_term_quotes()
        excl = {x["key"] for x in jload(self.V("gaps.json")).get("exclude", [])}
        if excl:
            self.drop_refs(excl, "calibrator: not human-written, irrelevant, or about the manuscript itself")
            tv = jload(self.V("terms_verified.json"))
            for t in tv["terms"]:
                if t.get("source_key") in excl and t["check"] == "verified":
                    t["check"], t["note"] = "unverified", (t.get("note", "") + " Source excluded from the bundle.").strip()
            jdump(tv, self.V("terms_verified.json"))

    def check_term_quotes(self):
        """A term marked verified must have its quotation in the cited reference text (script check)."""
        tv = jload(self.V("terms_verified.json"))
        quotes = {norm_ws(e["manuscript_term"]).lower(): e for e in jload(self.V("refs", "terms.json"), {"terms": []})["terms"]}
        texts, down = {}, 0
        for t in tv["terms"]:
            src = quotes.get(norm_ws(t["manuscript_term"]).lower())
            if t["check"] != "verified" or not src:
                continue
            key = t.get("source_key") or src["source_key"]
            if key not in texts:
                f = self.V("refs", f"{key}.txt")
                texts[key] = norm_ws(f.read_text(errors="ignore")) if f.exists() else ""
            if norm_ws(src["quote"])[:80] not in texts[key]:
                t["check"], t["note"] = "unverified", (t.get("note", "") + " Quotation not found in the source text.").strip()
                down += 1
        jdump(tv, self.V("terms_verified.json"))
        if down:
            log(f"terminology: {down} entr{'y' if down == 1 else 'ies'} marked verified without a findable quotation; downgraded")

    def baseline(self):
        """Three GPT steps: (1) arrangement, statements, terminology; (2) local proofs; (3) the introduction's proof
        sketch (`gpt_sketch.md`, the prompt that wrote the v6 sketch in the single-step tests)."""
        st = self.state
        pdf, txt, src, _ = self.vf("M0")
        lit = {"architecture.md": self.V("architecture.md"), "architecture.json": self.V("architecture.json"),
               "style_card.md": self.V("style_card.md")}
        if not st.get("b1_done"):
            labels = [s["label"] for s in jload(self.V("versions", "M0", "statements.json"), []) if s.get("label")]

            def plan_covers(ws):
                plan = json.dumps((jload(ws / "notes.json", {}) or {}).get("architecture_plan", []))
                miss = [l for l in labels if l not in plan]
                return [f"notes.json: architecture_plan has no placement decision naming {', '.join(miss[:25])}"] if miss else []
            res = self.run_jobs([Job("r0_baseline", "gpt", "gpt_baseline.md",
                                     {"src": src, "manuscript.pdf": pdf, "manuscript.txt": txt, "refs": self.V("refs"), **lit},
                                     {"out/" + st["main"]: None, "notes.json": "notes"}, postcheck=plan_covers)])[0]
            shutil.copy(res / "notes.json", self.V("notes_baseline_pass1.json"))
            rep = self.ensure_builds("B1", res / "out")
            if not rep["ok"]:
                log("first baseline pass does not build; no candidate")
                st["candidate"] = None
                return
            st["b1_done"] = True
            self.save()
        if not st.get("b2_done"):
            b1pdf, b1txt, b1src, _ = self.vf("B1")
            res = self.one("r0_baseline_2", "gpt", "gpt_baseline_2.md",
                           {"src": b1src, "manuscript.pdf": b1pdf, "manuscript.txt": b1txt, "original": src,
                            "original.txt": txt, "notes_pass1.json": self.V("notes_baseline_pass1.json"),
                            "refs": self.V("refs"), **lit},
                           {"out/" + st["main"]: None, "notes.json": "notes"})
            shutil.copy(res / "notes.json", self.V("notes_baseline.json"))
            rep = self.ensure_builds("B2", res / "out")
            if not rep["ok"]:
                log("second baseline pass does not build; no candidate")
                st["candidate"] = None
                return
            st["b2_done"] = True
            self.save()
        b2txt, b2src = self.vf("B2")[1:3]
        res = self.one("r0_sketch", "gpt", "gpt_sketch.md",
                       {"src": b2src, "manuscript.txt": b2txt, "refs": self.V("refs"), "style_card.md": self.V("style_card.md")},
                       {"out/" + st["main"]: None, "sketch_notes.md": None})
        shutil.copy(res / "sketch_notes.md", self.V("sketch_notes.md"))
        rep = self.ensure_builds("M1", res / "out")
        st["n_versions"] = 2
        st["candidate"] = "M1" if rep["ok"] else None

    # ------------------------------------------------------------------ one evaluation (Claude panel)
    # ------------------------------------------------------------------ the editorial standard and its review
    def criteria_dir(self):
        """The standard as an acceptance reviewer receives it: `criteria.md` and the numbered `conditions.json`."""
        d = self.V("criteria")
        d.mkdir(exist_ok=True)
        (d / "criteria.md").write_text(sd.criteria_md())
        jdump(sd.conditions(), d / "conditions.json")
        return d

    def accept_job(self, name, version, rd, model):
        """An acceptance review of `version` against every condition of the standard, by `model`. The reviewer writes
        its reading record (`reading.json`) before it may open the standard; for Claude the tool log proves the order."""
        cpdf, ctxt = self.vf(version)[:2]
        if not (rd / "sections").exists():
            tx.chunk_text(ctxt.read_text(), rd / "sections")
        ids = [c["id"] for c in sd.conditions()]

        def post(ws):
            acc = jload(ws / "acceptance.json", {}) or {}
            got = {c.get("id") for c in acc.get("conditions", [])}
            probs = [f"acceptance.json: no verdict for {', '.join(sorted(set(ids) - got))}"] if set(ids) - got else []
            bare = [c.get("id") for c in acc.get("conditions", []) if c.get("status") == "FAIL"
                    and not (c.get("required_repair") or "").strip()]
            if bare:
                probs.append(f"acceptance.json: FAIL without required_repair for {', '.join(map(str, bare[:12]))}")
            if model == "claude" and not self.mock:
                probs += self.read_before_criteria(ws)
            return probs
        files = {"manuscript.pdf": cpdf, "manuscript.txt": ctxt, "sections": rd / "sections",
                 "original.txt": self.vf("M0")[1], "criteria": self.criteria_dir(),
                 "architecture.md": self.V("architecture.md"), "style_card.md": self.V("style_card.md"),
                 "terms_verified.json": self.V("terms_verified.json"),
                 "refs": self.claude_refs() if model == "claude" else self.V("refs")}
        return Job(name, model, "accept.md", files,
                   {"reading.json": "reading", "acceptance.json": "acceptance", "acceptance.md": None},
                   extra={"MODEL_NAME": "Claude" if model == "claude" else "GPT"}, postcheck=post)

    @staticmethod
    def read_before_criteria(ws):
        """From the Claude tool log: `reading.json` must be written before anything in `criteria/` is read."""
        wrote, read_crit, n = None, None, 0
        for line in (ws / "_stdout.jsonl").read_text(errors="ignore").splitlines() if (ws / "_stdout.jsonl").exists() else []:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            for c in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                if c.get("type") != "tool_use":
                    continue
                n += 1
                name, inp = c.get("name", ""), c.get("input", {}) or {}
                target = str(inp.get("file_path") or inp.get("path") or "")
                if wrote is None and name in ("Write", "Edit") and target.endswith("reading.json"):
                    wrote = n
                if read_crit is None and name in ("Read", "Grep") and "criteria" in target:
                    read_crit = n
        if read_crit is not None and (wrote is None or read_crit < wrote):
            return ["the standard in criteria/ was opened before reading.json was written; write the reading record "
                    "first, from the manuscript alone, and only then open criteria/"]
        return []

    @staticmethod
    def failed(rd):
        """Number of FAILed conditions in the acceptance review of a panel, or None if it has none."""
        acc = jload(rd / "acceptance.json")
        return None if acc is None else sum(c["status"] == "FAIL" for c in acc["conditions"])

    def structure_check(self, version):
        m = tx.structure_metrics(jload(self.V("versions", version, "statements.json"), []),
                                 jload(self.V("versions", version, "build.json"), {}))
        syn = (jload(self.V("architecture.json"), {}) or {}).get("synthesis", {})
        band, ib = syn.get("first_main_statement_page_range") or [], syn.get("intro_pages_range") or []
        m["reference_first_main_statement_page_range"], m["reference_intro_pages_range"] = band, ib
        m["original_pages"] = jload(self.V("versions", "M0", "build.json"), {}).get("pages")
        notes = []
        first = (m.get("first_main_type_statement") or {}).get("page")
        if first and len(band) == 2 and first > band[1]:
            notes.append(f"the first main-type statement is on p. {first}; in the analogue references it is on "
                         f"pp. {band[0]}–{band[1]}")
        if m.get("intro_first_page") and m.get("intro_last_page") and len(ib) == 2:
            n = m["intro_last_page"] - m["intro_first_page"] + 1
            if n > ib[1]:
                notes.append(f"the introduction spans about {n} pages; in the analogue references {ib[0]}–{ib[1]}")
        if first is None:
            notes.append("no labelled theorem/proposition/corollary was found; the script could not locate the "
                         "first main-result statement")
        if m.get("pages") and m.get("original_pages") and m["pages"] > 1.4 * m["original_pages"]:
            notes.append(f"{m['pages']} pages against the original's {m['original_pages']}; check that the growth is in "
                         "mechanisms the reader needs, not routine expansion")
        m["outside_reference_range"] = notes
        return m

    def ref_index(self):
        if getattr(self, "_ref_index", None) is None:
            texts = {p.stem: p.read_text(errors="ignore") for p in self.V("refs").glob("*.txt")}
            if self.V("style_card.md").exists():
                texts["style_card"] = self.V("style_card.md").read_text()
            self._ref_index = tx.ref_ngram_index(texts)
        return self._ref_index

    @staticmethod
    def body_text(render_txt):
        """Rendered text without the bibliography (shared bibliography entries are not copying)."""
        lines = render_txt.split("\n")
        cut = max([i for i, l in enumerate(lines) if re.match(r"^\s*(References|REFERENCES|Bibliography|BIBLIOGRAPHY)\s*$", l)]
                  or [len(lines)])
        return "\n".join(lines[:cut])

    def fidelity_checks(self, version):
        return {"statements": tx.unmatched_statements(jload(self.V("versions", "M0", "statements.json"), []),
                                                      jload(self.V("versions", version, "statements.json"), [])),
                "qualifications": tx.scope_losses(self.vf("M0")[3], self.vf(version)[3]),
                "displays": tx.lost_displays(self.vf("M0")[3], self.vf(version)[3])}

    def fidelity_job(self, name, version, checks_file, rd, model="gpt"):
        _, otxt, _, oclean = self.vf("M0")
        _, ctxt, _, cclean = self.vf(version)
        ids = [c["id"] for k in ("statements", "qualifications", "displays") for c in jload(checks_file).get(k, [])]

        def post(ws):
            out = jload(ws / "fidelity.json", {}) or {}
            got = {c.get("id") for c in out.get("checks", [])}
            miss = [i for i in ids if i not in got]
            return [f"fidelity.json: no verdict in `checks` for {', '.join(miss[:30])}"] if miss else []
        return Job(name, model, "fidelity.md",
                   {"original": oclean, "current": cclean, "original.txt": otxt, "current.txt": ctxt,
                    "statements_original.json": self.V("versions", "M0", "statements.json"),
                    "statements_current.json": self.V("versions", version, "statements.json"),
                    "statement_diff.txt": rd / "statement_diff.txt", "checks.json": checks_file,
                    "build_report.json": self.V("versions", version, "build.json"),
                    "refs": self.claude_refs() if model == "claude" else self.V("refs")},
                   {"fidelity.json": "fidelity", "fidelity.md": None}, postcheck=post)

    def audit_jobs(self, prefix, version, regions, rd, sub, model="gpt"):
        """The independent check of rewritten or expanded proof passages: one job per shard of regions; each must give
        a verdict for every region of its shard."""
        _, otxt, _, oclean = self.vf("M0")
        _, ctxt, _, cclean = self.vf(version)
        size = max(5, int(self.cfg.get("audit_shard_size", 35)))
        jobs = []
        for n, s in enumerate(range(0, len(regions), size)):
            shard = regions[s:s + size]
            f = rd / f"{sub}regions_{n + 1}.json"
            jdump(shard, f)
            ids = {r["id"] for r in shard}

            def post(ws, ids=ids):
                out = jload(ws / "audit.json", {}) or {}
                got = {r.get("id") for r in out.get("regions", [])}
                probs = [f"audit.json: no verdict in `regions` for {', '.join(sorted(ids - got)[:30])}"] if ids - got else []
                stray = [a.get("id") for a in out.get("additions", []) if a.get("region") not in ids]
                if stray:
                    probs.append(f"audit.json: additions {', '.join(map(str, stray[:10]))} name no region of regions.json")
                return probs
            jobs.append(Job(f"{prefix}_check{'' if n == 0 else '_' + str(n + 1)}", model, "check.md",
                            {"regions.json": f, "original": oclean, "original.txt": otxt, "current": cclean,
                             "current.txt": ctxt, "refs": self.claude_refs() if model == "claude" else self.V("refs")},
                            {"audit.json": "audit", "audit.md": None}, postcheck=post,
                            rename={"audit.json": f"{sub}audit_{n + 1}.json", "audit.md": f"{sub}audit_{n + 1}.md"}))
        return jobs

    def merge_audit(self, rd, sub, n_shards, regions, carried, version):
        add, gaps, regs = list(carried["additions"]), list(carried["gaps"]), []
        for n in range(1, n_shards + 1):
            for f in (rd / f"{sub}audit_{n}.json", rd / f"{sub}audit_{n}_b.json"):   # _b: second, independent instance
                if not f.exists():
                    continue
                au = jload(f)
                tag = f.stem[len(sub):]
                for a in au.get("additions", []):
                    add.append({**a, "id": f"{tag}:{a['id']}"})
                gaps += [{**g, "id": f"{tag}:{g['id']}"} for g in au.get("gaps", [])]
                regs += au.get("regions", [])
        rank = {"false": 4, "unsupported": 3, "unverifiable": 2, "standard": 1, "verified": 0}
        best = {}
        for e in add:     # one entry per quoted step; the worst verdict of any checker wins, a fresh one beats a carried one
            k = norm_ws(e.get("quote"))[:100] or e["id"]
            old = best.get(k)
            if old is None or (rank.get(e["status"], 2), not e.get("carried_forward")) > \
                    (rank.get(old["status"], 2), not old.get("carried_forward")):
                best[k] = e
        add = list(best.values())
        seen, g2 = set(), []
        for g in gaps:
            k = (norm_ws(g.get("quote"))[:100], g.get("class"))
            if k not in seen:
                seen.add(k); g2.append(g)
        gaps = g2
        merged = {"additions": add, "gaps": gaps, "regions": regs,
                  "coverage": {"regions": len(regions), "with_verdict": len({r["id"] for r in regs}),
                               "carried_forward": len(carried["additions"])}}
        jdump(merged, rd / f"{sub}audit.json")
        self.check_audit_quotes(rd / f"{sub}audit.json", version)
        return merged

    def merge_fidelity(self, rd, sub):
        """Union of one or two independent fidelity checks; a script-flagged place ruled `lost` by either becomes a
        finding even if the checker forgot to list it."""
        files = sorted(rd.glob(f"{sub}fidelity_*.json"))
        items, checks = [], {}
        for f in files:
            fd = jload(f)
            tag = f.stem[len(sub):]
            items += [{**i, "id": f"{tag}:{i['id']}"} for i in fd.get("items", [])]
            for c in fd.get("checks", []):
                if c["verdict"] == "lost" or c["id"] not in checks:
                    checks[c["id"]] = c
        cj = jload(rd / f"{sub}checks.json", {"statements": [], "qualifications": [], "displays": []})
        quoted = {i.get("quote_original", "")[:60] for i in items}
        for k, sev in (("statements", "H"), ("qualifications", "M"), ("displays", "H")):
            for c in cj.get(k, []):
                v = checks.get(c["id"])
                if v and v["verdict"] == "lost":
                    orig = c.get("statement") or c.get("original") or c.get("display") or ""
                    if orig[:60] not in quoted:
                        items.append({"id": f"script:{c['id']}", "severity": sev, "kind": "lost" if k == "statements"
                                      else "qualification_lost", "quote_original": orig[:300],
                                      "explanation": f"ruled lost in the script-flagged check {c['id']}: {v.get('where', '')}"})
        counts = {s: sum(i["severity"] == s for i in items) for s in ("H", "M", "L")}
        merged = {"counts": counts, "items": items, "checks": list(checks.values()), "build_ok": True}
        jdump(merged, rd / f"{sub}fidelity.json")
        return merged

    def panel(self, tag, cand, prev=None, light=False, pair_with=None):
        """One evaluation. Claude: the acceptance review against the editorial standard, and the blind vote that guards
        against regressions. GPT: the fidelity check and the independent check of rewritten proof passages (one job per
        shard). The registry is the one the registrar wrote for the version. In round 1 the fidelity check and the
        checker also receive a copy with planted defects; if they miss one, every later panel adds a Claude instance of
        both. `light` (repair attempts and the terminology gate): fidelity, check and one vote. The proof check is local
        to the changes since `prev`; the vote compares with `pair_with` (default `prev`)."""
        cpdf, ctxt, _, cclean = self.vf(cand)
        rd = self.V("rounds", tag)
        rd.mkdir(parents=True, exist_ok=True)
        cstat = jload(self.V("versions", cand, "statements.json"), [])
        cbuild = jload(self.V("versions", cand, "build.json"), {})
        (rd / "src_index.txt").write_text("\n".join(tx.number_lines(cclean, rd / "_numbered")))
        (rd / "inventory.md").write_text(tx.inventory(cclean, cstat, cbuild))
        jdump(self.structure_check(cand), rd / "structure_check.json")
        tx.chunk_text(ctxt.read_text(), rd / "sections")
        (rd / "statement_diff.txt").write_text(tx.match_statements(jload(self.V("versions", "M0", "statements.json")), cstat))
        jdump(tx.copied_phrases(self.body_text(self.vf("M0")[1].read_text()), self.body_text(ctxt.read_text()),
                                self.ref_index()), rd / "copied_phrases.json")
        jdump([b for b in tx.new_bib_entries(self.vf("M0")[3], cclean,
                                             jload(self.V("refs", "manifest.json"), {"entries": []})["entries"])
               if not b["bundle_match"]], rd / "bib_check.json")
        backup = bool(self.state.get("claude_backup"))
        jobs, audit_meta, canary = [], None, None
        if not light:
            reg = (self.state.get("registry_of") or {}).get(cand)
            (rd / "registry.md").write_text(self.absp(reg).read_text() if reg else
                                            "<!-- no registry: the registrar puts names and symbols in order once, after the last round -->\n")
            jobs.append(self.accept_job(f"{tag}_accept", cand, rd, "claude"))
        if cand != "M0":
            jdump(self.fidelity_checks(cand), rd / "checks.json")
            for fam, sfx in (("gpt", "a"), ("claude", "b")):
                if fam == "claude" and not backup:
                    continue
                j = self.fidelity_job(f"{tag}_fidelity{'' if sfx == 'a' else '_b'}", cand, rd / "checks.json", rd, fam)
                j.rename = {"fidelity.json": f"fidelity_{sfx}.json", "fidelity.md": f"fidelity_{sfx}.md"}
                jobs.append(j)
            # check only what is new: regions unchanged since a checked predecessor keep their earlier verdicts
            prev_audit = self.absp(self.state["audit_of"][prev]) if prev and prev != "M0" and \
                self.state.get("audit_of", {}).get(prev) else None
            regions = tx.changed_regions(self.vf("M0")[3], self.vf(prev)[3] if prev_audit else None, cclean)
            jdump(regions, rd / "regions.json")
            carried = self.carry_forward(prev_audit, regions, cand)
            n_shards = 0
            for fam in ("gpt", "claude"):
                if fam == "claude" and not backup:
                    continue
                cj = self.audit_jobs(f"{tag}{'' if fam == 'gpt' else '_b'}", cand, regions, rd, "", fam)
                if fam == "claude":
                    for j in cj:
                        j.rename = {k: x.replace(".json", "_b.json").replace(".md", "_b.md") for k, x in j.rename.items()}
                else:
                    n_shards = len(cj)
                jobs += cj
            audit_meta = (n_shards, regions, carried)
            if self.cfg.get("canary_check", True) and not light and not self.state.get("canary"):
                canary = self.canary_jobs(tag, cand, rd, regions)
                if canary:
                    jobs += canary["jobs"]
        else:
            jdump({"counts": {"H": 0, "M": 0, "L": 0}, "items": [], "checks": [], "build_ok": True}, rd / "fidelity.json")
            jdump({"additions": [], "gaps": [], "regions": [], "coverage": {}}, rd / "audit.json")
        if prev:
            std_text = ("`architecture.md`, `style_card.md`, `rubric_anchors.md` — the standard derived from the reference "
                        "bundle; `refs/` — the reference texts.")
            std = {"architecture.md": self.V("architecture.md"), "style_card.md": self.V("style_card.md"),
                   "rubric_anchors.md": self.V("rubric_anchors.md"), "refs": self.claude_refs()}
            first_x = random.random() < 0.5
            other = pair_with or prev
            for v in range(1 if light else max(1, int(self.cfg.get("pairwise_votes", 1)))):
                newer_is_x = first_x if v % 2 == 0 else not first_x     # further votes swap the labels
                X, Y = (self.vf(cand)[:2], self.vf(other)[:2]) if newer_is_x else (self.vf(other)[:2], self.vf(cand)[:2])
                sfx = "" if v == 0 else f"_{v + 1}"
                jdump({"newer": "X" if newer_is_x else "Y", "X": cand if newer_is_x else other,
                       "Y": other if newer_is_x else cand}, rd / f"pairwise_labels{sfx}.json")
                jobs.append(Job(f"{tag}_pairwise{sfx}", "claude", "pairwise.md",
                                {"X.pdf": X[0], "X.txt": X[1], "Y.pdf": Y[0], "Y.txt": Y[1], **std},
                                {"pairwise.json": "pairwise", "pairwise.md": None},
                                extra={"MODEL_NAME": "Claude", "STANDARD_FILES": std_text},
                                rename={"pairwise.json": f"pairwise{sfx}.json", "pairwise.md": f"pairwise{sfx}.md"}))
        for job, res in zip(jobs, self.run_jobs(jobs)):
            for rel in job.expect:
                shutil.copy(res / rel, rd / job.rename.get(rel, Path(rel).name))
        if cand != "M0":
            for f in rd.glob("fidelity_*.json"):
                self.check_fidelity_quotes(f, cand)
            self.merge_fidelity(rd, "")
            self.merge_audit(rd, "", audit_meta[0], audit_meta[1], audit_meta[2], cand)
            self.state.setdefault("audit_of", {})[cand] = self.rel(rd / "audit.json")
            self.add_evidence(rd, cand)
            if canary:
                self.evaluate_canary(canary, rd, cand)
        if not light:
            self.state.setdefault("review_of", {})[cand] = self.rel(rd)
        self.save()
        return rd

    def carry_forward(self, prev_audit, regions, version):
        """Earlier check entries whose text is unchanged in this version and lies outside the regions checked now."""
        if not prev_audit or not prev_audit.exists():
            return {"additions": [], "gaps": []}
        au, text = jload(prev_audit), self.version_text(version)
        fresh = " ".join(norm_ws(r["text"]) for r in regions)
        keep = lambda e: (len(norm_ws(e.get("quote"))) >= 12 and norm_ws(e["quote"])[:100] in text
                          and norm_ws(e["quote"])[:100] not in fresh)
        pre = lambda i: i if str(i).startswith("prev:") else f"prev:{i}"
        return {"additions": [{**a, "id": pre(a["id"]), "carried_forward": True} for a in au.get("additions", []) if keep(a)],
                "gaps": [{**g, "id": pre(g["id"]), "carried_forward": True} for g in au.get("gaps", []) if keep(g)]}

    # ------------------------------------------------------------------ measuring the checkers (planted defects)
    def canary_jobs(self, tag, cand, rd, regions):
        """Plant defects in a copy of the candidate and give that copy to the fidelity checker and the proof checker,
        exactly as a real candidate. They cannot tell it apart; whether they report the planted defects measures them."""
        name = f"C_{cand}"
        work = self.V("canary_work", name)
        if work.exists():
            shutil.rmtree(work)
        prefer = {(r["file"], ln) for r in regions for ln in range(r["start_line"], r["end_line"] + 1)}
        plants = tx.plant_canaries(self.vf(cand)[3], work, tx.theorem_envs(self.vf(cand)[3]), prefer)
        if not plants:
            log("canary: no defect could be planted; checker sensitivity not measured")
            return None
        rep = self.build_version(name, work)
        if not rep["ok"]:
            log("canary: the copy with planted defects does not build; checker sensitivity not measured")
            return None
        cd = rd / "canary"
        cd.mkdir(exist_ok=True)
        jdump(plants, cd / "plants.json")
        jdump(self.fidelity_checks(name), cd / "checks.json")
        (cd / "statement_diff.txt").write_text(tx.match_statements(jload(self.V("versions", "M0", "statements.json")),
                                                                   jload(self.V("versions", name, "statements.json"), [])))
        fj = self.fidelity_job(f"{tag}_fidelity_c", name, cd / "checks.json", cd, "gpt")
        fj.rename = {"fidelity.json": "canary/fidelity.json", "fidelity.md": "canary/fidelity.md"}
        # check the regions that contain a planted line (plus neighbours, to make an ordinary-looking shard)
        cregs = tx.changed_regions(self.vf("M0")[3], None, self.vf(name)[3])
        hit = [i for i, r in enumerate(cregs) if any(p["file"] == r["file"] and r["start_line"] <= p["line"] <= r["end_line"]
                                                     for p in plants)]
        size = max(5, int(self.cfg.get("audit_shard_size", 35)))
        pick = sorted({k for i in hit for k in range(max(0, i - 3), min(len(cregs), i + 4))})[:size]
        cj = self.audit_jobs(f"{tag}_c", name, [cregs[i] for i in pick], cd, "", "gpt") if pick else []
        for j in cj:
            j.rename = {k: "canary/" + v for k, v in j.rename.items()}
        return {"version": name, "plants": plants, "jobs": [fj] + cj, "dir": cd}

    def evaluate_canary(self, canary, rd, cand):
        cd = canary["dir"]
        fid = jload(cd / "fidelity.json", {}) or {}
        findings = list(fid.get("items", []))
        lost_checks = {c["id"] for c in fid.get("checks", []) if c["verdict"] == "lost"}
        cj = jload(cd / "checks.json")
        findings += [{"quote_current": c.get("statement", "")} for c in cj["statements"] if c["id"] in lost_checks]
        chk = []
        for f in sorted(cd.glob("audit_*.json")):
            au = jload(f)
            chk += [a for a in au.get("additions", []) if a["status"] not in ("verified", "standard")] + au.get("gaps", [])
        rendered = tx.rendered_changes(self.vf(cand)[1].read_text(), self.vf(canary["version"])[1].read_text())
        res = []
        for p in canary["plants"]:
            by_f, by_c = tx.canary_detected(p, findings, rendered), tx.canary_detected(p, chk, rendered)
            res.append({**p, "found_by_fidelity": by_f, "found_by_check": by_c, "found": by_f or by_c})
        missed = [r for r in res if not r["found"]]
        summary = {"round": rd.name, "planted": len(res), "found": len(res) - len(missed), "results": res,
                   "action": "added a Claude fidelity check and a Claude proof check to every later panel" if missed else "none"}
        jdump(summary, cd / "canary.json")
        self.state["canary"] = self.rel(cd / "canary.json")
        if missed:
            self.state["claude_backup"] = True
        log(f"canary: {summary['found']}/{summary['planted']} planted defects reported by the GPT checkers"
            + (f"; missed {[m['kind'] for m in missed]} -> Claude checks added from now on" if missed else ""))

    # ------------------------------------------------------------------ quotations, votes and decisions
    def version_text(self, v):
        if v not in self._text:
            _, txt, _, clean = self.vf(v)
            src = " ".join(p.read_text(errors="ignore") for p in clean.rglob("*.tex"))
            self._text[v] = norm_ws(txt.read_text()) + " " + norm_ws(src)
        return self._text[v]

    def check_fidelity_quotes(self, path, cand):
        """An H finding must quote text that really exists; unverifiable H findings are downgraded to M."""
        fid = jload(path)
        texts = {"M0": self.version_text("M0"), cand: self.version_text(cand)}
        changed = 0
        for it in fid["items"]:
            if it["severity"] != "H":
                continue
            qo, qc = norm_ws(it.get("quote_original"))[:100], norm_ws(it.get("quote_current"))[:100]
            ok = (qo and qo in texts["M0"]) or (qc and qc in texts[cand])
            if not ok:
                it["severity"], it["downgraded"] = "M", "H finding whose quotations could not be found in either version"
                changed += 1
        if changed:
            fid["counts"]["H"] -= changed
            fid["counts"]["M"] += changed
            jdump(fid, path)
            log(f"fidelity: {changed} unverifiable H finding(s) downgraded to M")

    def check_audit_quotes(self, path, version):
        """Mark each audit entry whose quotation is not in the version; such entries cannot reject it."""
        au, text = jload(path), self.version_text(version)
        missing = 0
        for e in au.get("additions", []) + au.get("gaps", []):
            if e.get("carried_forward"):
                continue
            q = norm_ws(e.get("quote"))[:100]
            e["quote_found"] = bool(q) and q in text
            missing += not e["quote_found"]
        jdump(au, path)
        if missing:
            log(f"audit {path.name}: {missing} entr{'y' if missing == 1 else 'ies'} with quotations not found "
                "(passed on as unconfirmed)")

    @staticmethod
    def audit_rejects(au):
        return [a for a in (au or {}).get("additions", []) if a["status"] in BAD_STATUS and a.get("quote_found", True)]

    # ------------------------------------------------------------------ soundness debt: one ledger of evidence
    def add_evidence(self, rd, version):
        ev = self.state.setdefault("evidence", [])
        if not any(e["rd"] == self.rel(rd) for e in ev):
            ev.append({"rd": self.rel(rd), "version": version})

    def para_of(self, v, q):
        """The normalised source paragraph of `v` that contains `q`, or None."""
        if v not in self._paras:
            self._paras[v] = [norm_ws(p) for f in sorted(self.vf(v)[3].rglob("*.tex"))
                              for p in re.split(r"\n\s*\n", f.read_text(errors="ignore"))]
        return next((p for p in self._paras[v] if q in p), None)

    def findings(self, rd):
        """Blocking findings recorded in a check directory: fidelity H items and rejecting proof-check entries."""
        fid, au = jload(rd / "fidelity.json", {}) or {}, jload(rd / "audit.json", {}) or {}
        out = [{"kind": "fidelity", "id": i["id"], "quote": i.get("quote_current") or "",
                "lost": "" if i.get("quote_current") else i.get("quote_original") or "", "item": i}
               for i in fid.get("items", []) if i["severity"] == "H"]
        return out + [{"kind": "audit", "id": a["id"], "quote": a.get("quote") or "", "lost": "", "item": a}
                      for a in self.audit_rejects(au)]

    def debt(self, v):
        """Phi(v), the soundness debt: every blocking finding of every check run so far whose text is still in `v`, in a
        paragraph unchanged since the version it was found in. Every version is measured on the same evidence, so a
        defect found late in text that a predecessor shares counts against the predecessor too, and a later check that
        merely finds an old defect never looks like a regression. A finding whose paragraph was rewritten is left to
        the check of the version that rewrote it. The original is taken as correct (debt zero)."""
        if v == "M0":
            return []
        text, out, seen = self.version_text(v), [], set()
        for e in self.state.get("evidence", []):
            for f in self.findings(self.absp(e["rd"])):
                q = norm_ws(f["quote"])[:100]
                if q:
                    if q not in text:
                        continue
                    pv, pf = self.para_of(v, q), self.para_of(e["version"], q)
                    if pv is not None and pf is not None and pv != pf:
                        continue
                    key = q
                else:                   # a lost statement: still lost while the original's wording is absent
                    lo = norm_ws(f["lost"])[:100]
                    if not lo or lo in text:
                        continue
                    key = "lost: " + lo
                if key not in seen:
                    seen.add(key)
                    out.append({**f, "key": key, "flagged_in": e["version"], "panel": e["rd"]})
        return out

    def debt_dir(self, v, from_rd, dst):
        """Check files for a sheet whose base is `v`: those of `from_rd`, with exactly the blocking findings in Phi(v)."""
        dst.mkdir(parents=True, exist_ok=True)
        for f, default in (("copied_phrases.json", []), ("bib_check.json", [])):
            jdump(jload(from_rd / f, default), dst / f)
        jdump(jload(from_rd / "structure_check.json") or self.structure_check(v), dst / "structure_check.json")
        debt = self.debt(v)
        keys = {f["key"] for f in debt}
        fid = jload(from_rd / "fidelity.json", {}) or {}
        au = jload(from_rd / "audit.json", {}) or {}
        fkey = lambda f: norm_ws(f["quote"])[:100] or "lost: " + norm_ws(f["lost"])[:100]
        own = [f for f in self.findings(from_rd) if f["kind"] == "fidelity"]
        items = [i for i in fid.get("items", []) if i["severity"] != "H"] + \
                [f["item"] for f in own if fkey(f) in keys] + \
                [f["item"] for f in debt if f["kind"] == "fidelity" and f["key"] not in {fkey(o) for o in own}]
        bad = lambda a: a["status"] in BAD_STATUS and a.get("quote_found", True)
        adds = [a for a in au.get("additions", []) if not bad(a) or norm_ws(a.get("quote"))[:100] in keys]
        have = {norm_ws(a.get("quote"))[:100] for a in adds}
        adds += [f["item"] for f in debt if f["kind"] == "audit" and f["key"] not in have]
        jdump({**fid, "items": items, "counts": {s: sum(i["severity"] == s for i in items) for s in ("H", "M", "L")}},
              dst / "fidelity.json")
        jdump({**au, "additions": adds, "gaps": au.get("gaps", [])}, dst / "audit.json")
        return dst

    def deliverable(self):
        """The last accepted version without soundness debt on all evidence so far (the original at worst)."""
        return next((v for v in reversed(self.state["accepted"]) if not self.debt(v)), "M0")

    def review_rd(self, v):
        """The full panel (referee report and registry) of `v` or of the version it was repaired from."""
        r = self.state.get("review_of", {}).get(v)
        return self.absp(r) if r else self.review_dir(v)

    def votes(self, rd):
        """Pairwise votes from the panel (predecessor vs candidate), each mapped to newer/older."""
        out = []
        for lab_f in sorted(rd.glob("pairwise_labels*.json")):
            sfx = lab_f.stem[len("pairwise_labels"):]
            pw, lab = jload(rd / f"pairwise{sfx}.json"), jload(lab_f)
            newer = lab["newer"]
            m = lambda v: {newer: "newer", "tie": "tie"}.get(v, "older")
            out.append({"overall": m(pw["overall"]["verdict"]), "conf": pw["overall"]["confidence"],
                        "field": (m(pw["field_reader"]["verdict"]), pw["field_reader"]["confidence"]),
                        "checking": (m(pw["checking_reader"]["verdict"]), pw["checking_reader"]["confidence"]),
                        "candidate": lab[newer]})
        return out

    @staticmethod
    def worse(vs):
        """The blind vote finds the newer version worse: overall with medium confidence or more, or for one reader with
        high confidence. This is the vote's only role: it guards against regressions; it does not define progress."""
        return any(v["overall"] == "older" and CONF_RANK[v["conf"]] >= CONF_RANK["medium"] for v in vs) or \
            any(v[r] == ("older", "high") for v in vs for r in ("field", "checking"))

    def decide(self, rd, k, light=False):
        """A version is accepted when it builds, carries no soundness debt, and the vote does not find it worse than the
        version it was compared with. What is still wrong is the acceptance review's business, not the vote's. A version
        that fails only on debt goes to the repair loop instead of being discarded."""
        fid, au, vs = jload(rd / "fidelity.json"), jload(rd / "audit.json"), self.votes(rd)
        cand = vs[0]["candidate"]
        build_ok = jload(self.V("versions", cand, "build.json"))["ok"]
        debt = self.debt(cand) if build_ok else []
        worse = self.worse(vs)
        d = {"candidate": cand, "build_ok": build_ok, "light_gate": light, "votes": vs, "worse": worse,
             "pairwise_overall": [f"{v['overall']}/{v['conf']}" for v in vs], "failed_conditions": self.failed(rd),
             "fidelity_H": fid["counts"]["H"], "audit_rejecting": [x["id"] for x in self.audit_rejects(au)],
             "debt": [f["key"][:160] for f in debt], "repairable": bool(build_ok and debt and not worse)}
        d["decision"] = "accept" if build_ok and not debt and not worse else "reject"
        jdump(d, rd / "decision.json")
        return d

    def decide_repair(self, rd, frm, cand):
        """A local repair of `frm` is progress when it builds, the vote (against the current deliverable) does not find
        it worse, and it strictly lowers the soundness debt, both versions measured on the same evidence. Progress to
        debt zero accepts it."""
        vs = self.votes(rd)
        build_ok = jload(self.V("versions", cand, "build.json"))["ok"]
        worse = self.worse(vs)
        before, after = self.debt(frm), (self.debt(cand) if build_ok else None)
        progress = bool(build_ok and not worse and len(after) < len(before))
        fid = jload(rd / "fidelity.json", {"counts": {"H": 0}})
        d = {"candidate": cand, "from": frm, "build_ok": build_ok, "votes": vs, "worse": worse,
             "pairwise_overall": [f"{v['overall']}/{v['conf']}" for v in vs], "fidelity_H": fid["counts"]["H"],
             "audit_rejecting": [x["id"] for x in self.audit_rejects(jload(rd / "audit.json", {}))],
             "debt_before": [f["key"][:160] for f in before], "debt": [f["key"][:160] for f in after or []],
             "progress": progress, "decision": "accept" if progress and not after else "progress" if progress else "reject"}
        jdump(d, rd / "decision.json")
        return d

    def review_dir(self, version):
        """Round directory holding a full panel (acceptance review, registry, fidelity, audit) of `version`; runs one if
        there is none."""
        for h in self.state["history"]:
            if h.get("candidate") == version and h.get("panel") and (self.V("rounds", h["panel"], "acceptance.json")).exists():
                return self.V("rounds", h["panel"])
        rd = self.panel(f"base_{version}", version)
        self.state["history"].append({"candidate": version, "panel": f"base_{version}", "decision": "base"})
        self.save()
        return rd

    # ------------------------------------------------------------------ repair sheets: compile and execute
    def compile(self, k, base, base_rd, mode, checks_rd, pair_rd, sub, extra_files=None):
        """A sheet for the blocking findings of `base` (mode `repair`, or `revert` to the original's wording). `base_rd`
        supplies the acceptance review and registry of the base, `checks_rd` its fidelity, audit and script checks with
        exactly the findings in its debt, and `pair_rd` the vote shown with them."""
        _, txt, _, clean = self.vf(base)
        cd = self.V("rounds", f"r{k}", sub)
        cd.mkdir(parents=True, exist_ok=True)
        (cd / "mode.txt").write_text(mode)
        cap = self.cfg.get("max_items")         # None: every blocking finding gets an item
        jdump({"max_items": cap, "round": k}, cd / "limits.json")
        jdump({"ledger": self.state["ledger"]}, cd / "ledger.json")
        tx.number_lines(clean, cd / "src_numbered")
        files = {"mode.txt": cd / "mode.txt", "limits.json": cd / "limits.json", "ledger.json": cd / "ledger.json",
                 "src": clean, "src_numbered": cd / "src_numbered", "base.txt": txt,
                 "acceptance.json": base_rd / "acceptance.json", "criteria": self.criteria_dir(),
                 "registry.md": base_rd / "registry.md",
                 "fidelity.json": checks_rd / "fidelity.json", "audit.json": checks_rd / "audit.json",
                 "structure_check.json": checks_rd / "structure_check.json",
                 "copied_phrases.json": checks_rd / "copied_phrases.json", "bib_check.json": checks_rd / "bib_check.json",
                 "terms_verified.json": self.V("terms_verified.json"), "architecture.md": self.V("architecture.md"),
                 "style_card.md": self.V("style_card.md"), "refs/manifest.json": self.claude_refs() / "manifest.json",
                 **(extra_files or {})}
        labels = []
        if (pair_rd / "pairwise.json").exists():
            lab = jload(pair_rd / "pairwise_labels.json")
            accepted = (jload(pair_rd / "decision.json", {}) or {}).get("decision", "").startswith("accept")
            labels.append(f"In pairwise.json, label {lab['newer']} is the latest revision and the other label is the "
                          f"version it was made from. This revision was {'accepted' if accepted else 'rejected'}.")
            files["pairwise.json"] = pair_rd / "pairwise.json"
            if (pair_rd / "pairwise_2.json").exists():
                lab2 = jload(pair_rd / "pairwise_labels_2.json")
                labels.append(f"A second, independent comparison is in pairwise_2.json; there the latest revision is "
                              f"label {lab2['newer']}.")
                files["pairwise_2.json"] = pair_rd / "pairwise_2.json"
        (cd / "pairwise_labels.txt").write_text("\n".join(labels) + "\n")
        files["pairwise_labels.txt"] = cd / "pairwise_labels.txt"
        expect = {"instructions.json": "instructions", "instructions.md": None, "ledger_update.json": "ledger_update"}
        job = Job(f"r{k}_{sub}", "claude", "claude_compiler.md", files, expect)
        bad = []
        for attempt in range(2):
            res = self.run_jobs([job])[0]
            ins = jload(res / "instructions.json")
            bad = self.anchor_items(ins, clean)
            jdump(ins, res / "instructions.json")
            if cap is not None and len(ins["items"]) > cap:
                bad.append(f"{len(ins['items'])} items exceeds the limit of {cap}")
            if not bad:
                break
            if attempt == 0:
                log(f"{len(bad)} anchor problem(s) left after script re-anchoring; one corrected compile")
                job = Job(f"r{k}_{sub}_fix", "claude", "claude_compiler.md", files, expect)
                job.note = ("A script checked a previous attempt and found these problems; fix every one:\n- "
                            + "\n- ".join(bad[:30]))
        if bad:
            log(f"compiler anchors still imperfect: {bad[:5]} (continuing; the executor may decline those items)")
        for f in expect:
            shutil.copy(res / f, cd / f)
        upd = jload(res / "ledger_update.json")
        for d in upd["decisions"]:
            d.update({"id": f"L{len(self.state['ledger']) + 1}", "round": k})
            self.state["ledger"].append(d)
        jdump(upd, cd / "ledger_update_applied.json")
        return cd / "instructions.json"

    def anchor_items(self, ins, clean):
        """Normalise every location to a file relative to src/, re-anchor line numbers that are off, and return the
        locations that still cannot be found."""
        bad, moved = [], 0
        for it in ins["items"]:
            for loc in it["locations"]:
                p, rel = tx.resolve_file(clean, loc["file"])
                if p is not None:
                    loc["file"] = rel
                if tx.snippet_ok(clean, loc["file"], loc["line"], loc["snippet"]):
                    continue
                hit = tx.relocate(clean, loc["file"], loc["line"], loc["snippet"])
                if hit:
                    loc["file"], loc["line"], moved = hit[0], hit[1], moved + 1
                    continue
                bad.append(f"item {it['id']}: snippet not found near {loc['file']}:{loc['line']}")
        if moved:
            log(f"re-anchored {moved} location(s) by script")
        return bad

    def execute(self, base, instr, tag):
        pdf, txt, src, _ = self.vf(base)
        res = self.one(tag, "gpt", "gpt_execute.md",
                       {"src": src, "manuscript.pdf": pdf, "manuscript.txt": txt, "instructions.json": instr,
                        "instructions.md": instr.with_suffix(".md"), "refs": self.V("refs"),
                        "architecture.md": self.V("architecture.md"), "style_card.md": self.V("style_card.md")},
                       {"out/" + self.state["main"]: None, "receipt.json": "receipt"})
        name = f"M{self.state['n_versions']}"
        self.state["n_versions"] += 1
        rep = self.ensure_builds(name, res / "out")
        return name if rep["ok"] else None

    # ------------------------------------------------------------------ rounds of cross review
    REPORTED_ABOUT = (
        "These problems come from checks of this version against the paper's original version and its sources: a "
        "fidelity check (does this version keep every statement, argument and qualification of the original?), a check "
        "of the proof passages that revisions added or changed, a review of the proofs against a written standard, a "
        "blind comparison with the version before, and script checks. The paper's statements keep the strength they "
        "have in the original: where a problem could be fixed only by changing a statement, or with an assumption or "
        "result that neither the paper nor its sources supply, it is an open problem for the author. A step of the "
        "original's argument may be left out only where the paper shows, from its hypotheses and definitions or from a "
        "cited result as its source states it, that the case the step treats does not arise or that another step "
        "covers it.")

    def reported_problems(self, base, base_rd, checks_rd):
        """The problems of `base` that the checks found, for the next cross-review round to decide, each fixed there in
        the shortest correct way or left for the author: every fidelity finding of severity H or M; every added step the
        proof check did not confirm, and every gap it found that the paper's inputs or a source would close (class 1 or
        2); every failed condition of the standard on local proofs (P04) and every mathematical issue of the acceptance
        review; every passage the vote marked as a false or unsupported claim; passages copied from reference papers;
        added bibliography entries that match no paper of the bundle; and the reports of other readers. A finding
        whose quotation is no longer in `base`, or a lost passage of the original that is back, is left out."""
        text = self.version_text(base)
        here = lambda q: bool(norm_ws(q)) and norm_ws(q)[:100] in text
        out = []

        def add(check, location, quote, problem):
            out.append({"id": f"R{len(out) + 1}", "check": check, "location": location or "-", "quote": quote or "",
                        "problem": norm_ws(problem)})
        for i in (jload(checks_rd / "fidelity.json", {}) or {}).get("items", []):
            q, qo = i.get("quote_current") or "", i.get("quote_original") or ""
            if i["severity"] in ("H", "M") and (here(q) if q else not here(qo)):
                add("fidelity check", (i.get("current_loc") or "-")
                    + (f" (in the original: {i['original_loc']})" if i.get("original_loc") else ""), q,
                    f"{i.get('explanation', '')} The original version reads: \"{qo}\"" if qo else i.get("explanation", ""))
        au = jload(checks_rd / "audit.json", {}) or {}
        for a in au.get("additions", []):
            if a["status"] not in ("verified", "standard") and a.get("quote_found", True) and here(a.get("quote")):
                add("check of added proof steps", a.get("location"), a["quote"],
                    f"The check rated this step {a['status']}: {a.get('justification', '')}")
        for g in au.get("gaps", []):
            if g["class"] in ("1", "2") and g.get("quote_found", True) and here(g.get("quote")):
                add("check of added proof steps", g.get("location"), g["quote"],
                    f"The check found this step unjustified ({'the inference holds, but the page does not show why' if g['class'] == '1' else 'it follows from the paper or a cited source, but the argument is missing'}): "
                    f"what is missing is {g.get('obligation', '')}")
        acc = jload(base_rd / "acceptance.json", {}) or {}
        text_of = {c["id"]: c["text"] for c in sd.conditions()}
        for c in acc.get("conditions", []):
            if c["id"].startswith("P04.") and c["status"] == "FAIL":
                locs = c.get("locations", [])
                if not locs or any(here(x.get("quote")) for x in locs):
                    add("review of the proofs against the standard", "; ".join(f"p. {x['page']}" for x in locs),
                        "\n".join(x["quote"] for x in locs if here(x.get("quote"))),
                        f"This condition fails: \"{text_of.get(c['id'], c['id'])}\" {c.get('evidence', '')} "
                        f"What it needs: {c.get('required_repair', '')}")
        for m in acc.get("math_issues", []):
            if here(m.get("quote")):
                add("review of the proofs against the standard", f"p. {m['page']}", m["quote"],
                    f"{m['kind']}: {m['explanation']} What is needed: {m['needed']}")
        for lab_f in sorted(base_rd.glob("pairwise_labels*.json")):
            lab, pw = jload(lab_f), jload(base_rd / f"pairwise{lab_f.stem[len('pairwise_labels'):]}.json", {}) or {}
            for r in pw.get("regressions", {}).get(lab["newer"], []):
                if r.get("false_or_unsupported_claim") and here(r.get("quote")):
                    add("blind comparison with the version before", f"p. {r['page']}", r["quote"],
                        f"The comparison found a false or unsupported claim here: {r['what']}")
        for c in jload(checks_rd / "copied_phrases.json", []) or []:
            if here(c.get("text")):
                add("copied-text check", "-", c["text"],
                    f"This passage repeats {c.get('words', 'many')} words of the reference paper {c.get('reference')} word for word.")
        for b in jload(checks_rd / "bib_check.json", []) or []:
            add("bibliography check", f"bibliography entry {b.get('key')}", b.get("entry", ""),
                "A revision added this bibliography entry, and it matches no paper of the reference bundle: check that "
                "the work exists and says what the paper cites it for.")
        for r in (jload(self.V("reader_reports.json"), {}) or {}).get("reports", []):
            if not r.get("quote") or here(r["quote"]):
                add("report of another reader", f"p. {r.get('page', '-')}, {r.get('location', '')}", r.get("quote"),
                    r["problem"])
        return {"about": self.REPORTED_ABOUT, "problems": out}

    def cross_config(self):
        """The cross review's config.json with this run's models; the strings that identify the target paper, which the
        reviewers search the web around but must not open; and this run's directory and package, which its agents must
        not read. `cross_review` in this run's config overrides any of it."""
        cfg = jload(CROSS / "config.json")
        for fam in ("claude", "gpt"):
            cfg[fam].update({key: self.cfg[fam][key] for key in ("bin", "model", "effort")})
        cfg.update(avoid=self.state["target"]["identifiers"], sensitive=[str(self.out), str(PKG)])
        for key, v in self.cfg.get("cross_review", {}).items():
            cfg[key] = {**cfg.get(key, {}), **v} if isinstance(v, dict) else v
        return cfg

    def run_cross(self, args):
        """Run `cross_review/review.py` as its own process, with the vault locked: it reads only the copies staged for it
        under `cross/`. Its own steps lock its records and audit every tool call."""
        if not self.mock and self.cfg["isolation"].get("lock_vault", True):
            self.locks.lock([self.vault])
        broken, stop_watch = [], threading.Event()
        watcher = threading.Thread(target=self.watch_lock, args=(stop_watch, broken), daemon=True)
        watcher.start()
        try:
            self.cross_proc = subprocess.Popen([sys.executable, str(CROSS / "review.py"), *args], stdin=subprocess.DEVNULL,
                                               env=dict(os.environ, REVIEW_RUNS=str(self.out / "cross")),
                                               start_new_session=True)
            rc = self.cross_proc.wait()
        finally:
            self.cross_proc = None
            stop_watch.set()
            watcher.join(timeout=10)
            self.locks.unlock_all()
        if broken:
            raise SystemExit(f"the vault lock was undone during the cross review ({broken[0]}); stopping. Move the run "
                             "directory out of any synced folder and `resume`.")
        if rc != 0:
            raise SystemExit(f"the cross review stopped (exit {rc}); see its output above, then `resume`")

    def cross_round(self, k, base, base_rd, checks_rd):
        """Round k's revision of `base`: one run of the cross review (`cross_review/`), outside the vault. Claude and GPT
        each review the paper's writing against its literature and judge the other's list; GPT merges the accepted
        findings and revises the paper. The reviewers also decide every problem the checks of `base` found
        (`reported_problems`). The works they save are passed to later rounds. Returns the revised version, or None if
        the round changed nothing (marked `unchanged`) or its result does not build."""
        st = self.state
        c = st.setdefault("cross_rounds", {}).setdefault(str(k), {"base": base})
        if "version" in c:
            return c["version"]
        top, name = self.out / "cross", f"round{k}"
        stage = top / "inputs" / name
        if not c.get("staged"):
            if stage.exists():
                shutil.rmtree(stage)
            stage.mkdir(parents=True)
            tx.copy_source(self.vf(base)[2], stage / "draft")
            reported = self.reported_problems(base, base_rd, checks_rd)
            jdump(reported, stage / "reported.json")
            jdump(reported, self.V("rounds", f"r{k}", "reported.json"))
            if not (top / "literature").exists():
                shutil.copytree(self.claude_refs(), top / "literature")      # the bundle without GPT's descriptions
            jdump(self.cross_config(), top / "config.json")
            c.update(staged=True, reported=len(reported["problems"]))
            self.save()
        rd = top / name
        if (rd / "state.json").exists():
            args = ["resume", "--name", name]
        else:
            obtained = [str(top / "obtained")] if (top / "obtained").is_dir() else []
            args = ["run", "--name", name, "--draft", str(stage / "draft"), "--literature", str(top / "literature"),
                    *obtained, "--reported", str(stage / "reported.json")]
        log(f"round {k}: cross review of {base}; {c['reported']} problem(s) found by the checks go to its reviewers")
        self.run_cross(args + ["--config", str(top / "config.json")] + (["--mock"] if self.mock else []))
        cst = jload(rd / "state.json", {})
        if not crossrounds.finished(cst):
            raise SystemExit(f"cross-review round {k} stopped before finishing; `resume` continues it")
        crossrounds.collect_sources(top, k, [top / "literature"])
        if "revised" not in cst:
            c.update(version=None, unchanged=True)
        else:
            v = f"M{st['n_versions']}"
            st["n_versions"] += 1
            c["version"] = v if self.ensure_builds(v, rd / "revised")["ok"] else None
        self.save()
        return c["version"]

    # ------------------------------------------------------------------ main loop
    def go(self):
        st = self.state
        for d in self.wsroot.iterdir():       # workspaces left by an interrupted run
            self.archive(d, "_orphan_" + d.name)
        if st["phase"] == "retrieve":
            self.retrieve(); st["phase"] = "calibrate"; self.save()
        if st["phase"] == "calibrate":
            self.calibrate()
            gaps = self.check_architecture_evidence(jload(self.V("gaps.json"))["gaps"])
            st["phase"] = "supplement" if gaps and self.cfg.get("supplementary_retrieval", True) else "baseline"
            self.save()
        if st["phase"] == "supplement":
            # Before the baseline on purpose: the missing references are usually exactly the comparable-length papers
            # and imported-result sources that the writer and the auditor need.
            log("reference gaps reported; one supplementary retrieval and an incremental recalibration")
            if "keys_before_supplement" not in st:
                st["keys_before_supplement"] = sorted(e["key"] for e in jload(self.V("refs", "manifest.json"))["entries"])
                self.save()
            if not st.get("supplement_retrieved"):
                self.retrieve(supplementary=True, before=set(st["keys_before_supplement"]))
                st["supplement_retrieved"] = True
                self.save()
            self.calibrate(supplementary=True)
            st["phase"] = "baseline"; self.save()
        if st["phase"] == "baseline":
            self.baseline(); st["phase"] = "loop"; self.save()
        while st["phase"] == "loop":
            k, p = st["round"], st["pending"]
            if st["candidate"] is None:
                if k == 1:
                    log("no buildable baseline; finishing"); st["stop_reason"] = "no candidate"
                else:
                    log("the revised version does not build; finishing")
                    st["stop_reason"] = "revised version did not build"
                st["phase"] = "final"; self.save(); break
            if p.get("k") != k:
                st["pending"] = p = {"k": k}
            if "dec" not in p:          # the panel ran and its decision is recorded (a repair may still be pending)
                rd = self.panel(f"r{k}", st["candidate"], st["current"])
                dec = self.decide(rd, k)
                st["history"].append({"round": k, "candidate": st["candidate"], "panel": f"r{k}", "decision": dec["decision"]})
                log(f"round {k}: {st['candidate']} vs {st['current']} -> {dec['decision']} {dec['pairwise_overall']}"
                    + (f"; {dec['failed_conditions']} condition(s) of the standard fail" if dec["failed_conditions"] is not None else "")
                    + (f" (audit rejects {dec['audit_rejecting']})" if dec["audit_rejecting"] else "")
                    + (f" (fidelity H {dec['fidelity_H']})" if dec["fidelity_H"] else ""))
                p["dec"] = dec["decision"]
                p["repairable"] = dec["repairable"] and self.cfg.get("repair_on_reject", True)
                self.save()
            if "decision" not in p and p.get("repairable") and p["dec"] == "reject" and "chosen" not in p:
                rec = p.setdefault("repairs", {})
                best = self.repair_loop(rec, k, st["candidate"], self.V("rounds", f"r{k}"), "repair")
                p["chosen"] = None
                if not self.debt(best):
                    p["dec"], p["chosen"] = "accept_repaired", best
                elif self.open_base_ok(self.V("rounds", f"r{k}")):
                    p["dec"], p["chosen"] = "accept_open", best
                    log(f"round {k}: {best} becomes the working base with {len(self.debt(best))} open blocking "
                        "finding(s); only a version without debt is delivered")
                self.save()
            if "decision" not in p:
                if p["dec"].startswith("accept"):
                    new = p.get("chosen") or st["candidate"]
                    if k == 1:
                        st["baseline"] = new
                    st["current"] = new
                    st["accepted"].append(new)
                    st["rejections_in_a_row"] = 0
                    checks = f"r{k}"
                    if p["dec"] in ("accept_repaired", "accept_open"):
                        # the next round sees the base's checks with exactly its debt, and the round's own vote (candidate
                        # against its predecessor), now marked with the round's outcome
                        checks = f"r{k}/base_checks"
                        self.debt_dir(new, self.absp(p["repairs"].get("best_rd") or f"rounds/r{k}"), self.V("rounds", checks))
                        dj = jload(self.V("rounds", f"r{k}", "decision.json"))
                        dj.update({"gate_decision": dj.get("gate_decision", dj["decision"]), "decision": p["dec"], "chosen": new})
                        jdump(dj, self.V("rounds", f"r{k}", "decision.json"))
                    p.update({"base": new, "base_rd": f"r{k}", "checks_rd": checks})
                else:
                    st["rejections_in_a_row"] += 1
                    # also in round 1: the base is the original, and the rejected baseline's findings are not about it
                    p.update({"base": st["current"], "base_rd": None})
                p["decision"] = p["dec"]
                self.save()
            if p["decision"].startswith("accept") and self.no_issues(self.V("rounds", p["base_rd"]),
                                                                     self.V("rounds", p["checks_rd"])):
                log("every condition of the standard passes and the checks are clean; finishing")
                st["phase"] = "final"; st["stop_reason"] = "all conditions pass"; self.save(); break
            reason = ("two rejections in a row" if st["rejections_in_a_row"] >= self.cfg["max_consecutive_rejections"] else
                      "round limit" if k >= self.cfg["rounds"] + 1 else None)
            if reason:
                st["stop_reason"] = reason
                st["phase"] = "final"; self.save(); break
            base_rd = self.V("rounds", p["base_rd"]) if p.get("base_rd") else self.review_dir(p["base"])
            checks_rd = self.V("rounds", p["checks_rd"]) if p.get("checks_rd") else base_rd
            if self.no_issues(base_rd, checks_rd):
                log("every condition of the standard passes and the checks are clean; finishing")
                st["phase"] = "final"; st["stop_reason"] = "all conditions pass"; self.save(); break
            st["candidate"] = self.cross_round(k, p["base"], base_rd, checks_rd)
            if st["cross_rounds"][str(k)].get("unchanged"):
                log(f"round {k}: the cross review changed nothing; finishing")
                st["phase"] = "final"; st["stop_reason"] = "a cross-review round changed nothing"; self.save(); break
            st["round"] = k + 1
            self.save()
        if st["phase"] == "final":
            if self.cfg.get("terminology_pass", True) and not st.get("terms", {}).get("done"):
                self.terms()
            if self.cfg.get("confirmation_check", True) and not st.get("confirm", {}).get("done"):
                self.confirm()
            if self.cfg.get("final_acceptance", True) and not st.get("final_acceptance"):
                self.final_acceptance()
            self.cross_check()
            self.deliver()
            st["phase"] = "done"; self.save()
            log(f"done; see {self.out / 'report.md'}")

    def check_architecture_evidence(self, gaps):
        """The default architecture needs at least two comparable research papers; otherwise ask for them."""
        arch = jload(self.V("architecture.json"), {}) or {}
        n = len((arch.get("synthesis") or {}).get("analogues") or [])
        if n < 2 and not any("comparable" in g.get("kind", "").lower() for g in gaps):
            gaps = gaps + [{"kind": "too few research papers of comparable length and kind for the architecture table",
                            "detail": f"the architecture synthesis names {n} analogue paper(s); at least two are needed"}]
            g = jload(self.V("gaps.json"))
            g["gaps"] = gaps
            jdump(g, self.V("gaps.json"))
            log(f"architecture table rests on {n} analogue paper(s); requesting comparable papers")
        return gaps

    def repair_loop(self, rec, k, cand, cand_rd, name):
        """`cand` was rejected only for blocking findings (fidelity H, unsupported or false added steps) while the vote
        did not prefer the older version: pay its soundness debt locally instead of discarding it. Each attempt is a
        sheet for exactly the findings in Phi of the last version that made progress, executed and checked locally (a
        full fidelity check, a proof check of the passages it changed with earlier verdicts kept elsewhere, one vote
        against the version it repaired). Stops at debt zero, when an attempt makes no progress, or after `max_repairs`
        attempts; if debt remains, one `revert` sheet restores the original's wording of each remaining passage (the
        original is taken as correct, so this always lowers the debt). Returns the last version that made progress."""
        st, att = self.state, rec.setdefault("attempts", [])
        best, best_rd = rec.get("best", cand), rec.get("best_rd", self.rel(cand_rd))
        while not rec.get("done"):
            if not self.debt(best):
                rec["done"] = "debt zero"
                break
            if att and "decision" not in att[-1]:
                a = att[-1]                                     # resume an unfinished attempt
            else:
                last = att[-1] if att else None
                if last and last["mode"] == "revert":
                    rec["done"] = "debt left after the revert sheet"
                    break
                stalled = bool(last) and last["decision"] == "reject"
                if stalled or sum(x["mode"] == "repair" for x in att) >= int(self.cfg.get("max_repairs", 3)):
                    if not self.cfg.get("revert_fallback", True):
                        rec["done"] = "no progress" if stalled else "repair limit"
                        break
                    mode = "revert"
                else:
                    mode = "repair"
                a = {"n": len(att) + 1, "mode": mode, "from": best, "from_rd": best_rd}
                att.append(a)
                self.save()
            n, frm = a["n"], a["from"]
            sub = name if (name == "repair" and n == 1) else f"{name}{n}"
            if "instr" not in a:
                debt = self.debt(frm)
                log(f"round {k}: {a['mode']} sheet {n} for {frm} ({len(debt)} blocking finding(s) on all evidence)")
                dd = self.debt_dir(frm, self.absp(a["from_rd"]), self.V("rounds", f"r{k}", sub + "_debt"))
                # the round's own vote (candidate against its base) is shown on the first sheet only; later votes compare
                # with the deliverable, not with the version a sheet is made from
                a["instr"] = self.rel(self.compile(k, frm, self.review_rd(frm), a["mode"], dd,
                                                   self.absp(a["from_rd"]) if n == 1 else dd, sub,
                                                   extra_files={"original": self.vf("M0")[3]} if a["mode"] == "revert" else None))
                self.save()
            if "candidate" not in a:
                a["candidate"] = self.execute(frm, self.absp(a["instr"]), f"r{k}_{sub}_execute")
                self.save()
            if not a["candidate"]:
                a["decision"] = "reject"
                log(f"round {k}: {a['mode']} {n} does not build")
                self.save()
                continue
            st.setdefault("review_of", {})[a["candidate"]] = st.get("review_of", {}).get(frm) or self.rel(self.review_rd(frm))
            # The vote compares with the current deliverable, not with `frm`: `frm` carries debt and can never be
            # delivered, and a vote against it can reward the very change that created the debt (a statement of the
            # original corrected against R1, say). Against the deliverable both sides are free of debt.
            a["pair_with"] = a.get("pair_with") or self.deliverable()
            prd = self.panel(f"r{k}_{sub}", a["candidate"], frm, light=True, pair_with=a["pair_with"])
            dec = self.decide_repair(prd, frm, a["candidate"])
            a["decision"], a["rd"] = dec["decision"], self.rel(prd)
            st["history"].append({"round": k, "candidate": a["candidate"], "panel": f"r{k}_{sub}",
                                  "decision": f"{dec['decision']} ({a['mode']} {n})"})
            log(f"round {k}: {a['mode']} {n} of {frm}: {a['candidate']} vs deliverable {a['pair_with']} -> {dec['decision']} "
                f"{dec['pairwise_overall']}; debt {len(dec['debt_before'])} -> {len(dec['debt'])}")
            if dec["progress"]:
                best, best_rd = a["candidate"], a["rd"]
                rec["best"], rec["best_rd"] = best, best_rd
            self.save()
        return best

    def open_base_ok(self, rd):
        """After the repair loop a candidate may keep debt. It still becomes the working base when the round's vote
        preferred it with high confidence (`accept.open_base_min_confidence`): it is closer to a good version than its
        predecessor, and only a version without debt is ever delivered."""
        need = CONF_RANK[self.cfg["accept"].get("open_base_min_confidence", "high")]
        vs = self.votes(rd)
        return bool(vs) and all(v["overall"] == "newer" and CONF_RANK[v["conf"]] >= need for v in vs)

    def terms(self):
        """Names and symbols are put in order once, after the last structural change, on the version that would be
        delivered: the registrar works on a copy, and the result passes the light gate (fidelity, a check of the changed
        passages, one vote against that version), like a repair attempt. If it does not build or is rejected and cannot
        be repaired, the version without it stands. The confirmation check and the final acceptance review come after."""
        st = self.state
        t = st.setdefault("terms", {})
        if t.get("done"):
            return
        base = self.deliverable()
        if base == "M0":
            log("terminology pass: nothing was written; skipping")
            t.update({"done": True, "skipped": True}); self.save(); return
        k = st["round"]
        if "candidate" not in t:
            name = f"M{st['n_versions']}"
            st["n_versions"] += 1
            src = self.vf(base)[2]
            rep = self.ensure_builds(name, src)
            if rep["ok"]:
                rep = self.registrar_fix(name, "terms", src)
            t.update({"base": base, "candidate": name if rep["ok"] else None})
            self.save()
        if not t["candidate"]:
            log("terminology pass: the copy does not build; keeping the current version")
            t["done"] = True; self.save(); return
        if "decision" not in t:
            st.setdefault("review_of", {}).setdefault(t["candidate"], self.rel(self.review_rd(base)))
            rd = self.panel("terms", t["candidate"], base, light=True)
            dec = self.decide(rd, k + 1, light=True)
            st["history"].append({"round": k + 1, "candidate": t["candidate"], "panel": "terms",
                                  "decision": dec["decision"] + " (terminology gate)"})
            t["decision"], t["repairable"] = dec["decision"], dec["repairable"]
            log(f"terminology pass: {t['candidate']} vs {base} -> {dec['decision']} {dec['pairwise_overall']}")
            self.save()
        if t["decision"] == "reject" and t.get("repairable") and self.cfg.get("repair_on_reject", True) and "chosen" not in t:
            best = self.repair_loop(t.setdefault("repairs", {}), k, t["candidate"], self.V("rounds", "terms"), "terms_repair")
            t["chosen"] = None if self.debt(best) else best
            if t["chosen"]:
                t["decision"] = "accept_repaired"
            self.save()
        if t["decision"].startswith("accept") and not t.get("applied"):
            st["current"] = t.get("chosen") or t["candidate"]
            st["accepted"].append(st["current"])
            t["applied"] = True
        t["done"] = True
        self.save()

    def confirm(self):
        """Before delivery, one fresh proof check of every rewritten passage of the version about to be delivered, with no
        verdict carried over: debt zero after the per-round checks means no *known* defect, and one check misses real
        ones. What it finds goes through the same repair loop; then the run stops."""
        st = self.state
        c = st.setdefault("confirm", {})
        if "version" not in c:
            c["version"] = self.deliverable()
            self.save()
        v, k = c["version"], st["round"]
        if v == "M0":
            c["done"] = True
            self.save()
            return
        rd = self.V("rounds", "confirm")
        if not c.get("checked"):
            rd.mkdir(parents=True, exist_ok=True)
            regions = tx.changed_regions(self.vf("M0")[3], None, self.vf(v)[3])
            jdump(regions, rd / "regions.json")
            jdump({"counts": {"H": 0, "M": 0, "L": 0}, "items": [], "checks": [], "build_ok": True}, rd / "fidelity.json")
            log(f"confirmation: a fresh check of all {len(regions)} rewritten proof passages of {v}")
            jobs = self.audit_jobs("confirm", v, regions, rd, "")
            for job, res in zip(jobs, self.run_jobs(jobs)):
                for rel in job.expect:
                    shutil.copy(res / rel, rd / job.rename.get(rel, Path(rel).name))
            self.merge_audit(rd, "", len(jobs), regions, {"additions": [], "gaps": []}, v)
            self.add_evidence(rd, v)
            c["checked"] = True
            self.save()
        debt = self.debt(v)
        log(f"confirmation: {len(debt)} blocking finding(s) in {v} on all evidence")
        if debt and "chosen" not in c:
            best = self.repair_loop(c.setdefault("repairs", {}), k, v, rd, "confirm_repair")
            c["chosen"] = None if self.debt(best) else best
            if c["chosen"]:
                st["current"] = best
                st["accepted"].append(best)
        c["done"] = True
        self.save()

    def no_issues(self, rd, checks_rd=None):
        """Nothing left to act on: no condition of the standard fails, and the checks are clean. Math issues that the
        original's own statements raise go to the author (R1) and do not keep the run going."""
        checks_rd = checks_rd or rd
        fid, au = jload(checks_rd / "fidelity.json"), jload(checks_rd / "audit.json", {})
        open_audit = [a for a in au.get("additions", []) if a["status"] not in ("verified", "standard")] + \
                     [g for g in au.get("gaps", []) if g["class"] in ("1", "2")]
        return (self.failed(rd) == 0 and fid["counts"]["H"] + fid["counts"]["M"] == 0 and not open_audit
                and not jload(checks_rd / "copied_phrases.json", []) and not jload(checks_rd / "bib_check.json", []))

    def final_acceptance(self):
        """The delivered version is reviewed once more against the standard, independently by Claude and by GPT, for the
        report. It changes nothing; it says what still fails, by each family's reading."""
        v = self.deliverable()
        rd = self.V("rounds", "final_acceptance")
        rd.mkdir(parents=True, exist_ok=True)
        jobs = [self.accept_job(f"final_accept_{m}", v, rd, m) for m in ("claude", "gpt")]
        for j in jobs:
            j.rename = {k: f"{j.model}_{k}" for k in j.expect}
        log(f"final acceptance review of {v} by Claude and by GPT")
        for job, res in zip(jobs, self.run_jobs(jobs)):
            for rel in job.expect:
                shutil.copy(res / rel, rd / job.rename[rel])
        self.state["final_acceptance"] = {"version": v, "dir": self.rel(rd)}
        self.save()

    # ------------------------------------------------------------------ final cross-model check and delivery
    def cross_check(self):
        """Blind final comparison of the final version with the original, once by each model (in parallel when allowed).
        Each accepted round already beat its predecessor, so a comparison with the baseline would repeat that."""
        final, out = self.deliverable(), {}
        self.state["final"] = final
        if final == "M0":
            jdump(out, self.V("cross_check.json"))
            return out
        jobs, meta = [], {}
        for model in ("claude", "gpt"):
            fx = random.random() < 0.5
            a, b = (final, "M0") if fx else ("M0", final)
            (ap, at, _, _), (bp, bt, _, _) = self.vf(a), self.vf(b)
            if model == "claude":
                std = {"architecture.md": self.V("architecture.md"), "style_card.md": self.V("style_card.md"),
                       "rubric_anchors.md": self.V("rubric_anchors.md"), "refs": self.claude_refs()}
                txt = ("`architecture.md`, `style_card.md`, `rubric_anchors.md` — the standard derived from the "
                       "reference bundle; `refs/` — the reference texts.")
            else:
                std = {"refs": self.V("refs")}
                txt = "`refs/` — the reference bundle (`manifest.json` and `<key>.txt` texts) of the closest human-written papers."
            name = f"final_{model}_vs_M0"
            meta[name] = (model, "X" if fx else "Y")
            jobs.append(Job(name, model, "pairwise.md", {"X.pdf": ap, "X.txt": at, "Y.pdf": bp, "Y.txt": bt, **std},
                            {"pairwise.json": "pairwise", "pairwise.md": None},
                            extra={"MODEL_NAME": "Claude" if model == "claude" else "GPT", "STANDARD_FILES": txt}))
        results = dict(zip([j.name for j in jobs], self.run_jobs(jobs)))
        for name, (model, fl) in meta.items():
            pw = jload(results[name] / "pairwise.json")
            out[f"{model}_vs_M0"] = {"final_label": fl, "overall": pw["overall"], "final_preferred": pw["overall"]["verdict"] == fl,
                                     "other_preferred": pw["overall"]["verdict"] not in (fl, "tie")}
        jdump(out, self.V("cross_check.json"))
        return out

    def defensive_pass(self, base):
        """After everything else, one instruction (GPT) deletes the defensive sentences of the version to be delivered
        that the reader does not need. Its output stands only if it builds and only deletes text (`tx.deletions_only`);
        otherwise `base` stands. Nothing is checked again; the report lists every deletion."""
        st = self.state
        d = st.setdefault("defensive", {"base": base})
        if "chosen" not in d:
            if "candidate" not in d:
                d["candidate"] = f"M{st['n_versions']}"
                st["n_versions"] += 1
                self.save()
            name = d["candidate"]
            res = self.one(f"{name}_defensive", "gpt", "gpt_defensive.md", {"src": self.vf(base)[2]},
                           {"out/" + st["main"]: None})
            ok = self.build_version(name, res / "out")["ok"]
            removed = tx.deletions_only(self.vf(base)[2], self.vf(name)[2]) if ok else None
            d.update({"removed": removed or [], "chosen": name if removed else base,
                      "outcome": f"{len(removed)} deletion(s)" if removed else "no deletions" if removed == [] else
                                 "output rejected: it adds or changes text" if ok else "output rejected: it does not build"})
            if removed and base in st.get("audit_of", {}):
                st["audit_of"][name] = st["audit_of"][base]      # only deletions: the base's proof check still applies
            log(f"defensive pass on {base}: {d['outcome']}; delivering {d['chosen']}")
            self.save()
        return d["chosen"]

    def deliver(self):
        st, cc = self.state, jload(self.V("cross_check.json"), {})
        final = st.get("final") or self.deliverable()      # only a version without soundness debt is delivered
        chosen = final
        # Fall back to the original only if BOTH models independently prefer it to the final version.
        if final != "M0" and cc.get("claude_vs_M0", {}).get("other_preferred") and cc.get("gpt_vs_M0", {}).get("other_preferred"):
            chosen = "M0"
        if chosen != "M0" and self.cfg.get("defensive_pass", True):
            chosen = self.defensive_pass(chosen)
        st["delivered"] = chosen
        dst = self.out / "deliverable"
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir()
        shutil.copytree(self.V("versions", chosen, "src"), dst / "src")
        shutil.copy(self.V("versions", chosen, "render.pdf"), dst / "paper.pdf")
        # a later working base that still carries debt is not delivered; it is handed over with its open findings
        opn = self.out / "deliverable_open"
        if opn.exists():
            shutil.rmtree(opn)
        if st["current"] not in (chosen, "M0") and self.debt(st["current"]):
            opn.mkdir()
            shutil.copytree(self.V("versions", st["current"], "src"), opn / "src")
            shutil.copy(self.V("versions", st["current"], "render.pdf"), opn / "paper.pdf")
            jdump([{k: f[k] for k in ("kind", "id", "key", "flagged_in", "panel")} | {"finding": f["item"]}
                   for f in self.debt(st["current"])], opn / "open_findings.json")
        self.report(chosen, cc)

    def report(self, chosen, cc):
        st = self.state
        L = ["# restructure-paper report", "", f"Delivered: **{chosen}**. Accepted chain: {' → '.join(st['accepted'])}. "
             f"Stopped because: {st.get('stop_reason') or '-'}.", ""]
        au = jload(self.absp(st["audit_of"][chosen])) if st.get("audit_of", {}).get(chosen) else None
        L += ["## Check first", "", "Added proof steps that the independent check did not confirm, and gaps it found in "
              "rewritten proofs (the original's proofs are assumed correct and were not re-checked):", ""]
        flagged = []
        for a in (au or {}).get("additions", []):
            if a["status"] not in ("verified", "standard"):
                flagged.append(f"| {a['status']}{'' if a.get('quote_found', True) else ' (quote not found)'} | {a['location']} | "
                               f"{norm_ws(a['quote'])[:120]} | {norm_ws(a['justification'])[:220]} |")
        for g in (au or {}).get("gaps", []):
            flagged.append(f"| gap, class {g['class']} | {g['location']} | {norm_ws(g['quote'])[:120]} | {norm_ws(g['obligation'])[:220]} |")
        if flagged:
            L += ["| status | location | quotation | reason / obligation |", "|---|---|---|---|"] + flagged
        else:
            L.append("- (nothing flagged)" if au else "- (no check available for the delivered version)")
        # the standard: the final acceptance review of the delivered version by each family
        fa = st.get("final_acceptance") or {}
        rd_fa = self.absp(fa["dir"]) if fa.get("dir") else None
        revs = {m: jload(rd_fa / f"{m}_acceptance.json") for m in ("claude", "gpt")} if rd_fa else {}
        revs = {m: r for m, r in revs.items() if r}
        if revs:
            conds = {c["id"]: c["text"] for c in sd.conditions()}
            verdict = {m: {c["id"]: c for c in r["conditions"]} for m, r in revs.items()}
            fails = {m: sum(c["status"] == "FAIL" for c in r["conditions"]) for m, r in revs.items()}
            L += ["", f"## The editorial standard: final acceptance review of {fa['version']}", "",
                  "Every condition of the standard, judged independently by each family (reading record written before "
                  "the standard was opened). " + "; ".join(f"{m}: {n} FAIL" for m, n in fails.items()) + ".", "",
                  "| condition | " + " | ".join(revs) + " | condition text |", "|---|" + "---|" * len(revs) + "---|"]
            for cid, text in conds.items():
                L.append(f"| {cid} | " + " | ".join(verdict[m].get(cid, {}).get("status", "-") for m in revs)
                         + f" | {norm_ws(text)[:140]} |")
            for m, r in revs.items():
                failed = [c for c in r["conditions"] if c["status"] == "FAIL"]
                if failed:
                    L += ["", f"**What still fails ({m}):**", ""]
                    L += [f"- `{c['id']}` " + "; ".join(f"p. {x['page']}" for x in c.get("locations", [])[:4])
                          + f": {norm_ws(c.get('required_repair', ''))[:300]}" for c in failed]
            orig = self.version_text("M0")
            mi = [(m, x) for m, r in revs.items() for x in r.get("math_issues", [])]
            L += ["", "**Mathematical issues the reviewers raise:**", ""]
            if mi:
                L += ["| by | page | kind | in the original's wording? | quotation | explanation |", "|---|---|---|---|---|---|"]
                L += [f"| {m} | {x['page']} | {x['kind']} | {'yes' if norm_ws(x['quote'])[:80] in orig else 'no'} | "
                      f"{norm_ws(x['quote'])[:100]} | {norm_ws(x['explanation'])[:200]} |" for m, x in mi]
            else:
                L.append("- none")
        author = [d for d in st["ledger"] if d.get("for_author")]
        rounds = {k: jload(self.out / "cross" / f"round{k}" / "state.json", {}) or {}
                  for k in sorted(st.get("cross_rounds", {}), key=int)}
        opens = {k: len(crossrounds.review.open_for_author(c)) for k, c in rounds.items() if "open" in c}
        L += ["", "## Questions for the author", "",
              "Recorded, not disguised: problems that a repair sheet could not resolve without changing a statement of "
              "the original or supplying a new argument (R1), and problems that the cross review's reviewers could not "
              "fix themselves:", ""]
        L += [f"- {d['id']} ({d.get('anchor', '')[:80]}): {norm_ws(d['decision'])[:400]}" for d in author]
        L += [f"- Cross-review round {k}: {n} problem(s) its reviewers left for the author, in "
              f"`cross/round{k}/open_questions.md` (a later round may have fixed some)." for k, n in opens.items() if n]
        if not author and not any(opens.values()):
            L.append("- none")
        L += ["", "## Soundness debt and delivery", "",
              "Debt = blocking findings (fidelity H; unsupported or false added steps) of every check in the run whose "
              "text is still in the version, unchanged. Only a version without debt is delivered.", ""]
        L += [f"- {v}: {len(self.debt(v))} open blocking finding(s)" for v in st["accepted"]]
        cf = st.get("confirm", {})
        if cf.get("checked"):
            n = len(self.findings(self.V("rounds", "confirm")))
            L.append(f"- Confirmation check of {cf['version']} (every rewritten proof passage, fresh, nothing carried over): "
                     f"{n} blocking finding(s)" + (f"; repaired to {cf['chosen']}" if cf.get("chosen") else
                                                   "; repair loop left debt, so an earlier version is delivered" if n else ""))
        if (self.out / "deliverable_open").exists():
            L.append(f"- `deliverable_open/`: {st['current']}, the latest working base, not delivered because it has "
                     f"{len(self.debt(st['current']))} open blocking finding(s) (listed in `open_findings.json`).")
        dp = st.get("defensive", {})
        if dp.get("outcome"):
            L += ["", "## Defensive sentences deleted (final pass)", "",
                  f"After the final review and comparison of {dp['base']}, one instruction asked GPT to delete the defensive "
                  f"sentences the reader does not need. Outcome: {dp['outcome']}; delivered {dp['chosen']}."
                  + ("" if not dp["removed"] else " These deletions were not checked again. Deleted text, by file:"), ""]
            L += [f"- `{f}`: {norm_ws(t)[:300]}" for f, t in dp["removed"]]
        L += ["", "## Defences in this run (what checked what, and whether the checks were shown to work)", ""]
        cn = jload(self.absp(st["canary"])) if st.get("canary") else None
        if cn:
            who = lambda r: "+".join(n for n, k in (("fidelity", "found_by_fidelity"), ("proof check", "found_by_check"))
                                     if r.get(k)) or "MISSED"
            L.append(f"- **Checker sensitivity (planted defects, {cn['round']}):** {cn['found']}/{cn['planted']} found. "
                     + "; ".join(f"{r['kind']}: {who(r)}" for r in cn["results"]) + f". Action: {cn['action']}.")
        else:
            L.append("- **Checker sensitivity:** not measured (no defect could be planted, or the check is switched off).")
        for h in st["history"]:
            rd = self.V("rounds", h["panel"])
            a2, fd, ck = jload(rd / "audit.json", {}), jload(rd / "fidelity.json", {}), jload(rd / "checks.json", {})
            if not a2 and not fd:
                continue
            cov = a2.get("coverage", {})
            lost = [c["id"] for c in fd.get("checks", []) if c["verdict"] == "lost"]
            L.append(f"- **{h['panel']}** ({h['candidate']}): proof check covered {cov.get('with_verdict', 0)}/{cov.get('regions', 0)} "
                     f"rewritten passages (+{cov.get('carried_forward', 0)} earlier verdicts kept); script-flagged places "
                     f"{len(ck.get('statements', []))} statements / {len(ck.get('qualifications', []))} qualifications, "
                     f"ruled lost: {', '.join(lost) or 'none'}; copied passages: {len(jload(rd / 'copied_phrases.json', []))}; "
                     f"added references with no bundle paper: {len(jload(rd / 'bib_check.json', []))}; "
                     f"decision {h['decision']}.")
        sc = self.structure_check(chosen)
        L += ["", "## Arrangement (script measurement against the reference papers)", "",
              f"- First main-type statement: p. {(sc.get('first_main_type_statement') or {}).get('page', '?')}; "
              f"analogue range {sc.get('reference_first_main_statement_page_range')}.",
              f"- Introduction: pp. {sc.get('intro_first_page')}–{sc.get('intro_last_page')}; analogue range "
              f"{sc.get('reference_intro_pages_range')} pages. Length {sc.get('pages')} pages (original {sc.get('original_pages')}).",
              f"- Notes: {'; '.join(sc.get('outside_reference_range') or []) or 'within range'}.", ""]
        L += ["## Rounds", "",
              "| panel | candidate | decision | vote (guard) | conditions failed | fidelity H/M/L | check rejects |",
              "|---|---|---|---|---|---|---|"]
        for h in st["history"]:
            rd = self.V("rounds", h["panel"])
            dec = jload(rd / "decision.json", {})
            fc = jload(rd / "fidelity.json", {"counts": {}})["counts"]
            nf = self.failed(rd)
            L.append(f"| {h['panel']} | {h['candidate']} | {h['decision']} | {dec.get('pairwise_overall', '-')} | "
                     f"{'-' if nf is None else nf} | {fc.get('H')}/{fc.get('M')}/{fc.get('L')} | "
                     f"{len(dec.get('audit_rejecting', []))} |")
        if rounds:
            L += ["", "## Cross-review rounds", "",
                  "Each round revises the accepted version of the round before; its reviewers also decide the problems "
                  "that the checks of that version found (`vault/rounds/r<k>/reported.json`). Records: `cross/round<k>/`.",
                  "", "| round | base | problems reported | of them given a fix | items applied | passages changed | "
                  "deviations from the list | result |", "|---|---|---|---|---|---|---|---|"]
            for k, cst in rounds.items():
                c, rv = st["cross_rounds"][k], cst.get("revised", {})
                fixed = sum(any(x["fixed"] for x in d) for d in crossrounds.review.reported_decisions(cst).values())
                res = (c["version"] if c.get("version") else "changed nothing" if c.get("unchanged") else
                       "does not build" if "version" in c else "unfinished")
                L.append(f"| {k} | {c['base']} | {c.get('reported', '-')} | {fixed} | {len(cst.get('final', []))} | "
                         f"{rv.get('passages_changed', 0)} | {rv.get('deviations', '-')} | {res} |")
        L += ["", "## Final cross-model check (blind, final vs original)", ""]
        L += [f"- {k}: final preferred = {v['final_preferred']}; verdict {v['overall']}" for k, v in cc.items()] or ["- (none)"]
        tim = [json.loads(l) for l in (self.V("timings.jsonl").read_text().splitlines() if self.V("timings.jsonl").exists() else [])]
        if tim:
            L += ["", "## Step times (minutes; parallel steps overlap)", ""]
            L += [f"- {t['step']} ({t['model']}, attempt {t['attempt']}): {t['minutes']}" for t in tim]
        (self.out / "report.md").write_text("\n".join(L) + "\n")


def preflight(cfg, mock):
    need = ["latexmk", "pdftotext"] + ([] if mock else [cfg["claude"]["bin"], cfg["gpt"]["bin"]])
    missing = [b for b in need if not shutil.which(b)]
    if missing:
        raise SystemExit(f"missing executables: {missing}")
    if mock:
        return
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        log("warning: running as root makes directory locks ineffective; isolation then rests on Claude's "
            "--restricted mode and on the audit. Run as an ordinary user if you can.")
    if subprocess.run([cfg["claude"]["bin"], "auth", "status"], stdin=subprocess.DEVNULL, capture_output=True).returncode != 0:
        raise SystemExit("claude is not logged in: run `claude auth login`")
    if subprocess.run([cfg["gpt"]["bin"], "login", "status"], stdin=subprocess.DEVNULL, capture_output=True).returncode != 0:
        log("warning: `codex login status` failed; make sure codex is logged in with your ChatGPT account")
    iso = cfg["isolation"]
    # Probe the exact command lines once; drop optional isolation flags the installed CLIs reject.
    with tempfile.TemporaryDirectory() as td:
        def ok_claude():
            r = subprocess.run(claude_cmd(cfg, "Reply with the single word OK."), cwd=td, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
            if r.returncode != 0 and RATE_PAT.search(r.stderr + r.stdout[-2000:]):
                raise SystemExit("Claude usage limit reached during preflight; try again later")
            return r.returncode == 0, r.stderr
        good, err = ok_claude()
        optional = [("claude_tools", ["Read", "Write", "Edit"]), ("claude_permission_prompts_none", False),
                    ("claude_safe_mode", False), ("claude_restricted", False)]
        if not good:      # drop the single optional setting that fixes it, before dropping several
            for k, v in optional:
                old = iso.get(k, True if k != "claude_tools" else None)
                iso[k] = v
                good, _ = ok_claude()
                if good:
                    log(f"warning: installed claude rejected an option; continuing with {k}={v}")
                    break
                if old is None:
                    iso.pop(k, None)
                else:
                    iso[k] = old
        if not good:
            for k, v in optional:
                iso[k] = v
            good, err = ok_claude()
            if not good:
                raise SystemExit(f"claude command line rejected even without optional isolation flags:\n{err[-800:]}")
            log("warning: all optional Claude isolation flags were dropped; isolation rests on locks and the audit")

        def ok_codex(opts):
            cfg["gpt"]["optional_config"] = opts
            r = subprocess.run(codex_cmd(cfg, td, "Reply with the single word OK.", False), cwd=td, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=600)
            if r.returncode != 0 and RATE_PAT.search(r.stderr + r.stdout[-2000:]):
                raise SystemExit("ChatGPT/Codex usage limit reached during preflight; try again later")
            return r.returncode == 0, r.stderr
        opts = list(cfg["gpt"].get("optional_config", DEFAULT_CODEX_OPTIONAL))
        good, err = ok_codex(opts)
        if not good:
            for o in list(opts):
                trial = [x for x in opts if x != o]
                if ok_codex(trial)[0]:
                    log(f"warning: codex rejected -c {o}; continuing without it")
                    opts, good = trial, True
                    break
        if not good:
            good, err = ok_codex([])
            if not good:
                raise SystemExit(f"codex command line rejected:\n{err[-800:]}")
            log("warning: all optional codex settings were dropped")
            opts = []
        cfg["gpt"]["optional_config"] = opts
        # per-role model/effort overrides must work too (e.g. the independent checker on the strongest GPT setting)
        for prompt in sorted(set(cfg.get("role_model", {})) | set(cfg.get("role_effort", {}))):
            fam = "claude" if prompt.startswith("claude_") else "gpt"
            m, e = model_for(cfg, fam, prompt), effort_for(cfg, fam, prompt)
            cmd = (claude_cmd(cfg, "Reply with the single word OK.", e, m) if fam == "claude"
                   else codex_cmd(cfg, td, "Reply with the single word OK.", False, e, m))
            r = subprocess.run(cmd, cwd=td, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                raise SystemExit(f"role override for {prompt} ({fam} model {m!r}, effort {e!r}) is rejected:\n{r.stderr[-600:]}")
    if Path("~/.claude/CLAUDE.md").expanduser().exists() and not iso.get("claude_safe_mode"):
        log("note: ~/.claude/CLAUDE.md exists and may be loaded into Claude steps; consider moving it aside during the run")


def probe_mixed(cfg, out):
    """Run a small Claude step and a small GPT step at the same time while the union of both lock sets is held; each must
    write a file in its directory, as real steps do. If both succeed, Claude and GPT steps may overlap on this machine."""
    locks = Locks(out)
    paths = foreign_store_paths({"claude", "gpt"})
    log(f"locking {len(paths)} store path(s) of both CLIs and running one trivial step of each, concurrently")
    res = {}
    with tempfile.TemporaryDirectory() as td:
        tc, tg = Path(td) / "c", Path(td) / "g"
        tc.mkdir(); tg.mkdir()

        def run(name, cmd, cwd):
            r = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
            res[name] = (r.returncode, (r.stdout or "")[-400:], (r.stderr or "")[-400:])
        locks.lock(paths)
        try:
            ask = "Create a file named ok.txt in the current directory containing the single word OK, then reply OK."
            th = [threading.Thread(target=run, args=("claude", claude_cmd(cfg, ask), tc)),
                  threading.Thread(target=run, args=("gpt", codex_cmd(cfg, tg, ask, False), tg))]
            for t in th:
                t.start()
            for t in th:
                t.join()
        finally:
            locks.unlock_all()
        wrote = {"claude": (tc / "ok.txt").exists(), "gpt": (tg / "ok.txt").exists()}
    ok = all(v[0] == 0 for v in res.values()) and all(wrote.values())
    for k, w in wrote.items():
        if not w:
            log(f"{k}: did not write its file while the locks were held")
    for k, v in res.items():
        log(f"{k}: exit {v[0]}{'' if v[0] == 0 else ' — ' + v[2]}")
    log("mixed parallelism works here: you may set isolation.allow_mixed_parallel to true" if ok else
        "mixed parallelism failed: keep isolation.allow_mixed_parallel false")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "resume", "status", "unlock", "probe-mixed"])
    ap.add_argument("--src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--config")
    ap.add_argument("--mock", action="store_true", help="replace both models with a stub; tests control flow only")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    cfg = jload(PKG / "config.default.json")
    if a.config:
        user = jload(a.config)
        for k, why in (("instruction_rounds", "it is now `rounds`"), ("cleanup_round", "the final sheet was removed")):
            if k in user:
                raise SystemExit(f"config key {k!r} is no longer used: {why} (see config.default.json)")
        for k, v in user.items():
            cfg[k] = {**cfg.get(k, {}), **v} if isinstance(v, dict) else v
    if a.cmd == "unlock":
        Locks(out).unlock_all(); return
    if a.cmd == "status":
        st = jload(out / "vault" / "state.json")
        print(json.dumps({k: v for k, v in st.items() if k not in ("ledger",)}, indent=1)); return
    # keep every temporary file (LaTeX builds, preflight probes) inside the run directory
    tmp = out / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(tmp)
    tempfile.tempdir = str(tmp)
    if not a.mock:
        os.environ["CODEX_HOME"] = str(isolated_codex_home(out))
    if Locks(out).held:
        log("releasing locks left by an interrupted run")
        Locks(out).unlock_all()
    if a.cmd == "probe-mixed":
        preflight(cfg, False)
        sys.exit(0 if probe_mixed(cfg, out) else 1)
    preflight(cfg, a.mock)
    if cfg["isolation"].get("allow_mixed_parallel") == "auto":
        # one trivial step of each CLI at the same time, with both lock sets held: if both work, panels that mix Claude
        # and GPT jobs can run them together instead of one family after the other
        cfg["isolation"]["allow_mixed_parallel"] = False if a.mock else probe_mixed(cfg, out)
    run = Run(out, cfg, mock=a.mock)

    def bye(*_):
        run.stop_children()                 # agents first, so nothing runs while the vault is unlocked
        run.locks.unlock_all()
        log(f"stopped by a signal; `duo.py resume --out {out}` continues the run, including an unfinished cross-review round")
        sys.exit(1)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, bye)
    try:
        if a.cmd == "run":
            if run.state:
                raise SystemExit("run directory already initialised; use `resume`")
            if not a.src:
                raise SystemExit("--src is required for run")
            run.check_lock_holds()
            run.init(Path(a.src).resolve())
        else:
            if not run.state:
                raise SystemExit("nothing to resume in this run directory")
            run.check_lock_holds()
        run.go()
    finally:
        run.locks.unlock_all()


if __name__ == "__main__":
    main()
