#!/usr/bin/env python3
"""Rounds of cross review: the paper that one round revises is the draft of the next, which fresh reviewers review
again, until a round changes nothing or the rounds run out. One run finds only some of a paper's problems, and a
different set each time; each round finds problems in the paper as the last one left it.

  python3 rounds.py run --name NAME --draft PATH [--literature PATH ...] [--prompts DIR ...] [--rounds N]
                        [--config FILE] [--mock]
  python3 rounds.py resume --name NAME [--config FILE] [--mock]

Each round is a run of `review.py` (`runs.nosync/NAME/roundK/`), with the prompts of the first round. Its reviewers
start without the earlier rounds' notes and lists. They get the paper as the last round left it, the supplied
literature, and the works that the earlier rounds' reviewers obtained online and saved (`NAME/obtained/`, without
repeated downloads of a work they already had). When the rounds
are done: `NAME/report.md` sums them up; `NAME/revised/` and `NAME/revised.pdf` are the paper after the last round;
`NAME/revised_vs_draft.md` gives every passage changed since the draft; `NAME/open_questions.md` collects the problems
that every round left for the author. `resume` continues where the rounds stopped; finished steps are not rerun.
"""
import argparse, hashlib, os, shutil, signal, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agents as ag  # noqa: E402
import review  # noqa: E402
import tex  # noqa: E402

OUTPUTS = ("report.md", "open_questions.md", "revised_vs_draft.md", "revised", "revised.pdf")


def finished(st):
    return "final" in (st or {}) and ("revised" in st or not st["final"])


def collect_sources(top: Path, k: int, literature):
    """Keep the works that round k's reviewers saved, for the reviewers of later rounds. A file identical to one they
    already had (in the supplied literature, saved in an earlier round, or saved by the other reviewer of this round) is
    not kept again, nor are the files saved with it under the same name, such as its text version."""
    files = lambda d: [d] if d.is_file() else sorted(f for f in d.rglob("*") if f.is_file())
    digest = lambda f: hashlib.md5(f.read_bytes()).hexdigest()
    earlier = [d for j in range(1, k) for d in (top / "obtained").glob(f"round{j}_*")]
    have = {digest(f) for d in [*map(Path, literature), *earlier] for f in files(d)}
    for r in review.REVIEWERS:
        src = top / f"round{k}" / "records" / "jobs" / f"review.{r}" / "sources"
        if not src.is_dir():
            continue
        saved = files(src)
        dup = {f.with_suffix("") for f in saved if digest(f) in have}
        skipped = [f.relative_to(src) for f in saved if f.with_suffix("") in dup]
        for f in saved:
            if f.with_suffix("") not in dup:
                dst = top / "obtained" / f"round{k}_{r}" / f.relative_to(src)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
        have |= {digest(f) for f in saved}     # the other reviewer's copy of the same file is a repeat too
        if skipped:
            ag.log(f"round {k}: {len(skipped)} file(s) that reviewer {r} saved repeat a work already obtained and are not "
                   f"passed on again: {', '.join(map(str, skipped))}")


def report(top: Path, spec, done):
    """Sum up the rounds, and give the paper after the last round that changed it."""
    L = [f"# Rounds of cross review `{spec['name']}`", "", f"- Draft: `{spec['draft']}`; up to {spec['rounds']} round(s)."]
    opens, last = [], None
    for k in range(1, done + 1):
        rd = top / f"round{k}"
        st = ag.jload(rd / "state.json")
        n_open = len(review.open_for_author(st))
        L.append(f"- Round {k}: {len(st['final'])} item(s) applied, "
                 f"{st['revised']['passages_changed'] if 'revised' in st else 0} passage(s) changed, {n_open} "
                 f"problem(s) left for the author. See `round{k}/report.md`.")
        if n_open:
            opens.append(f"# Round {k}\n\n" + (rd / "open_questions.md").read_text().split("\n", 1)[1].lstrip())
        if "revised" in st:
            last = rd
    if done < spec["rounds"]:
        L.append(f"- Stopped after round {done}: it changed nothing.")
    if last:
        tex.copy_source(last / "revised", top / "revised")
        shutil.copy(last / "revised.pdf", top / "revised.pdf")
        diffs = tex.differences(top / "round1" / "records" / "draft", top / "revised")
        (top / "revised_vs_draft.md").write_text(tex.differences_md(diffs, ("draft", "after the last round")))
        L.append(f"- The paper after round {last.name[5:]}: `revised/`, `revised.pdf`; {len(diffs)} passage(s) changed "
                 "since the draft (`revised_vs_draft.md`).")
    (top / "open_questions.md").write_text("# Problems for the author, from every round (not applied)\n\n"
                                           + ("\n".join(opens) if opens else "(none)\n"))
    L.append("- Problems for the author, from every round: `open_questions.md`. A later round may have fixed some.")
    (top / "report.md").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--draft", required=True, help="the paper's LaTeX source: a directory or a single .tex file")
    r.add_argument("--literature", nargs="*", default=[], help="files or directories of works the reviewers should read")
    r.add_argument("--prompts", nargs="*", default=[], help="folders of prompt files to use in place of those in prompts/")
    r.add_argument("--rounds", type=int, default=3, help="the most rounds to run (default 3)")
    for c in (r, sub.add_parser("resume")):
        c.add_argument("--name", required=True)
        c.add_argument("--config")
        c.add_argument("--mock", action="store_true", help="stub agents, for testing the tool itself")
    a = ap.parse_args()

    top = review.RUNS / a.name
    if a.cmd == "run":
        if top.exists():
            raise SystemExit(f"{top} exists; use `resume` or another --name")
        res = lambda s: str(Path(s).expanduser().resolve())
        spec = {"name": a.name, "draft": res(a.draft), "literature": [res(x) for x in a.literature],
                "prompts": [res(x) for x in a.prompts], "rounds": a.rounds}
        top.mkdir(parents=True)
        ag.jdump(spec, top / "rounds.json")
    else:
        spec = ag.jload(top / "rounds.json")
        if not spec:
            raise SystemExit(f"no rounds {a.name}")
    extra = (["--config", a.config] if a.config else []) + (["--mock"] if a.mock else [])
    child, stopped = [], []

    def on_signal(sig, frame):
        """Pass the stop on to the running round, which stops its agents and unlocks its records."""
        stopped.append(sig)
        for proc in child:
            proc.terminate()
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    done = 0
    for k in range(1, spec["rounds"] + 1):
        rd = top / f"round{k}"
        if not finished(ag.jload(rd / "state.json")):
            if (rd / "state.json").exists():
                cmd = ["resume", "--name", rd.name]
            else:
                prev = top / f"round{k - 1}"
                obtained = [str(top / "obtained")] if (top / "obtained").is_dir() else []
                cmd = ["run", "--name", rd.name, "--draft", str(prev / "revised") if k > 1 else spec["draft"],
                       "--literature", *spec["literature"], *obtained,
                       "--prompts", *([str(top / "round1" / "prompts")] if k > 1 else spec["prompts"])]
            ag.log(f"round {k} of {spec['rounds']}")
            child.append(subprocess.Popen([sys.executable, str(HERE / "review.py"), *cmd, *extra],
                                          env=dict(os.environ, REVIEW_RUNS=str(top)), stdin=subprocess.DEVNULL))
            rc = child[0].wait()
            child.clear()
            if stopped:
                raise SystemExit(f"stopped by signal {stopped[0]}; resume with `rounds.py resume --name {a.name}`")
            if rc != 0 or not finished(ag.jload(rd / "state.json")):
                raise SystemExit(f"round {k} stopped before finishing; see its output above, then use "
                                 f"`rounds.py resume --name {a.name}`")
        collect_sources(top, k, spec["literature"])
        done = k
        if "revised" not in ag.jload(rd / "state.json"):
            break                       # the round changed nothing, so the next would review the same paper
    report(top, spec, done)
    ag.log(f"finished; see {top / 'report.md'}")


if __name__ == "__main__":
    main()
