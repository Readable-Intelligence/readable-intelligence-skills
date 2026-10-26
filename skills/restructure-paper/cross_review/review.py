#!/usr/bin/env python3
"""Cross review of a paper's writing: two reviewers, each checked by the other, then one revision.

  python3 review.py run --name NAME --draft PATH [--literature PATH ...] [--prompts DIR ...] [--reported FILE]
                       [--config FILE] [--mock]
  python3 review.py resume --name NAME [--config FILE] [--mock]
  python3 review.py status --name NAME
  python3 review.py unlock --name NAME      # restore the records' permissions after a crash

1. Review: Claude and GPT, independently, read the whole draft and the literature it relies on, describe how that
   literature writes, and list the places where the draft departs from it at a cost to its reader, each with a fix
   written as exact edits to the source. Their lists are A (Claude) and B (GPT). Each list also gives the problems its
   reviewer leaves open for the author, and the places it noted and decided are not issues, with its reasons.
2. Cross review: each reviewer judges every item of the other's list. It accepts or rejects each finding and each open
   problem, and accepts or disputes each decision that a place is not an issue. Where it finds a fix wrong, an issue
   where the other saw none, or a fix for an open problem, it writes the fix, which the item's author then checks
   (step 2b).
3. Merge: the items that one reviewer proposed and the other accepted are collected, and GPT merges those that overlap
   into one list. It also gets the rejected fixes, and leaves out any part of an accepted fix that has a fault named in
   a reviewer's reason for accepting or rejecting a fix.
4. Revise: GPT applies that list to the draft. A script compares the result with the list applied exactly.

The draft is a LaTeX source directory, or a single .tex file, that compiles. The literature is optional: files or
directories of works the reviewers should read (PDF or text). The reviewers find the rest online, and save the works
they obtain in `sources/`; each judge (step 2) and each author's check (step 2b) gets both reviewers' saved works, so
that a claim about a work can be checked against the text the other reviewer read. `rounds.py` runs this whole process
again on the revised paper. `--prompts` names
folders whose prompt files are used in place of those in prompts/, the first folder that has a file winning; the run
keeps a copy of the prompts it uses in `<run>/prompts/`, so a resumed run uses the same ones.

`--reported` gives problems that other checks of the paper found (`{"problems": [{"id", "check", "location", "quote",
"problem"}]}`, with an optional `"about"`: a paragraph saying where they come from). Each reviewer decides every one of
them, as an issue, an open problem or a place that is not an issue, and names its id in that item's `reported`; the
judge sees them too. `report.md` says how each was decided (`reported_decisions.md`).

Standard library only. Needs on PATH: claude (Claude Code), codex (Codex CLI), latexmk, pdftotext. See README.md.
"""
import argparse, json, os, shutil, signal, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agents as ag  # noqa: E402
import tex  # noqa: E402

PROMPTS, SCHEMAS = HERE / "prompts", HERE / "schemas"
STEP_PROMPTS = ("review", "cross_review", "check_repair", "standard", "merge", "revise")
RUNS = Path(os.environ.get("REVIEW_RUNS") or HERE / "runs.nosync")     # overridable for the tool's own tests
REVIEWERS = {"A": "claude", "B": "gpt"}         # list -> the model that writes it
OTHER = {"A": "B", "B": "A"}
log = ag.log


def deep_merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path=None):
    cfg = ag.jload(HERE / "config.json")
    return deep_merge(cfg, ag.jload(path)) if path else cfg


def read(p):
    return Path(p).read_text(encoding="utf-8", errors="surrogateescape")


def write(p, s):
    Path(p).write_text(s, encoding="utf-8", errors="surrogateescape")


def dump(obj):
    return json.dumps(obj, indent=1, ensure_ascii=False)


def source_words(src: Path):
    return sum(tex.words(read(p)) for p in src.rglob("*.tex"))


# ---------------------------------------------------------------------- edits to the source
def edit_problems(src: Path, groups):
    """Why a set of edits, given as (label, edits) pairs, cannot all be applied to the source: each `old` must occur
    exactly once in its file, and no two edits may change the same text."""
    probs, spans, texts, root = [], [], {}, src.resolve()
    for label, edits in groups:
        for k, e in enumerate(edits, 1):
            tag = f"{label}, edit {k}"
            f = (src / e["file"]).resolve()
            if not f.is_relative_to(root) or not f.is_file() or f.suffix not in tex.TEX_EXT:
                probs.append(f"{tag}: {e['file']!r} is not a source file of the paper (give the path within paper/)")
                continue
            t = texts.setdefault(f, read(f))
            n = t.count(e["old"]) if e["old"] else 0
            if n != 1:
                probs.append(f"{tag}: `old` occurs {n} times in {e['file']}; copy it exactly from the file, with "
                             "enough text to occur there exactly once")
            elif e["new"] == e["old"]:
                probs.append(f"{tag}: `new` is the same as `old`")
            else:
                i = t.index(e["old"])
                spans.append((str(f), i, i + len(e["old"]), tag))
    last = None
    for s in sorted(spans):
        if last and s[0] == last[0] and s[1] < last[2]:
            probs.append(f"{last[3]} and {s[3]} change overlapping text in {Path(s[0]).relative_to(root)}")
        if not last or s[0] != last[0] or s[2] > last[2]:
            last = s
    return probs


def apply_edits(src: Path, dst: Path, edits):
    """Copy the source and apply the edits, each at the place of its `old` in the original file."""
    tex.copy_source(src, dst)
    by_file = {}
    for e in edits:
        by_file.setdefault(e["file"], []).append(e)
    for name, es in by_file.items():
        t = read(dst / name)
        for i, e in sorted(((t.index(e["old"]), e) for e in es), key=lambda x: x[0], reverse=True):
            t = t[:i] + e["new"] + t[i + len(e["old"]):]
        write(dst / name, t)


def verdict_problems(data, kinds, src=None):
    """Every item (`kinds` maps its id to its kind) gets exactly one verdict. A `repair` verdict, allowed only where the
    source `src` is given, carries a fix whose edits can be applied. A place decided not to be an issue is not
    rejected: the judge agrees with the decision or writes the fix."""
    vs, got = data["verdicts"], [v["id"] for v in data["verdicts"]]
    probs = ([f"no verdict for {i}" for i in kinds if i not in got]
             + [f"{i} is not one of the items" for i in sorted(set(got) - set(kinds))]
             + [f"more than one verdict for {i}" for i in sorted({i for i in got if got.count(i) > 1})])
    rep = [v for v in vs if v["verdict"] == "repair"]
    if src is None:
        return probs + [f"{v['id']}: the verdict here is `accept` or `reject`" for v in rep]
    probs += [f"{v['id']}: for a place decided not to be an issue, the verdict is `accept` or `repair`" for v in vs
              if kinds.get(v["id"]) == "not_issue" and v["verdict"] == "reject"]
    probs += [f"{v['id']}: a `repair` verdict needs the `fix` and its `edits`" for v in rep
              if not v.get("fix") or not v.get("edits")]
    return probs + edit_problems(src, [(f"fix of {v['id']}", v["edits"]) for v in rep if v.get("edits")])


def final_problems(src: Path, final, accepted):
    """The merged list `final` must cover each accepted finding exactly once, by an item or as left out; keep the edits
    of a finding that is not merged with another, unless its merge note says what was left out; and be applicable as a
    whole."""
    items = final["items"]
    by_id = {f["id"]: f for f in accepted}
    seen = [s for it in items for s in it["sources"]] + [o["id"] for o in final["left_out"]]
    probs = ([f"finding {i} is covered by no item and not left out" for i in by_id if i not in seen]
             + [f"finding {i} is covered more than once" for i in sorted(set(seen)) if seen.count(i) > 1]
             + [f"{i} is not an accepted finding" for i in sorted(set(seen) - set(by_id))])
    same = lambda edits: [(e["file"], e["old"], e["new"]) for e in edits]
    for n, it in enumerate(items, 1):
        one = it["sources"][0]
        if (len(it["sources"]) == 1 and one in by_id and same(it["edits"]) != same(by_id[one]["edits"])
                and not it["merge_note"].strip()):
            probs.append(f"item {n} covers only {one} but changes its edits, and its merge note does not say what was "
                         "left out; a finding that overlaps no other keeps its edits unchanged except for a part left out")
    return probs + edit_problems(src, [(f"item {n}", it["edits"]) for n, it in enumerate(items, 1)])


# ---------------------------------------------------------------------- Markdown views of the lists
def edits_md(edits):
    L = []
    for k, e in enumerate(edits, 1):
        old = f"~~~~latex\n{e['old']}\n~~~~\n"
        L.append(f"Edit {k}, in `{e['file']}`: replace\n\n{old}\nby\n\n~~~~latex\n{e['new']}\n~~~~\n" if e["new"]
                 else f"Edit {k}, in `{e['file']}`: delete\n\n{old}")
    return L


KIND_NAMES = {"open": "a problem left open for the author", "not_issue": "a place decided not to be an issue"}


def item_md(it, head, verdict=None):
    kind = it.get("kind", "issue")
    L = [f"## {head}" + (f" ({KIND_NAMES[kind]})" if kind in KIND_NAMES else "") + "\n",
         f"**Location.** {it['location']}\n"]
    if kind == "not_issue":
        L += [f"**What was noted.** {it['cost']}\n", f"**Why it was decided not to be an issue.** {it['reason']}\n"]
    else:
        L.append(f"**Problem.** {it['problem']}\n")
    if it.get("pattern"):
        L.append(f"**Pattern of the literature.** {it['pattern']}\n")
    if it.get("evidence"):
        L.append(f"**Evidence.** {it['evidence']}\n")
    if it.get("original_edits"):            # a corrected finding, as shown to its author for checking
        L += [f"**Your original fix.** {it['original_fix']}\n", *edits_md(it["original_edits"]),
              f"**Why the other reviewer corrected it.** {it['judge_reason']}\n", "**The corrected fix.**\n"]
    elif it.get("judge_reason"):            # an open problem or a place, with the fix the other reviewer wrote for it
        L += [f"**Why the other reviewer disagrees.** {it['judge_reason']}\n", "**The other reviewer's fix.**\n"]
    if it.get("fix"):
        L.append(f"**Fix.** {it['fix']}\n")
    if it.get("merge_note"):
        L.append(f"**How it was merged.** {it['merge_note']}\n")
    L += edits_md(it.get("edits", []))
    if it.get("corrected"):                 # in a reviewer's list: the fix the other reviewer wrote for the item
        L += [f"**{'Corrected fix' if kind == 'issue' else 'Fix'}, by the other reviewer.** {it['corrected']['fix']}\n",
              *edits_md(it["corrected"]["edits"])]
    if it.get("accepted_because"):
        L.append(f"**Why the other reviewer accepted it.** {it['accepted_because']}\n")
    if it.get("rejected_because"):
        L.append(f"**Why it was rejected.** {it['rejected_because']}\n")
    if verdict:
        L.append(f"**The other reviewer's verdict: {verdict['verdict']}.** {verdict['reason']}\n")
    return "\n".join(L)


def items_md(items, title, verdicts=None):
    body = [item_md(it, it["id"], (verdicts or {}).get(it["id"])) for it in items] or ["(none)\n"]
    return "\n".join([f"# {title}\n"] + body)


def reported_md(st):
    probs = st.get("reported", [])
    L = ["# Problems that checks of the paper reported\n", st.get("reported_about", "").strip() + "\n" if
         st.get("reported_about") else ""]
    for p in probs:
        L += [f"## {p['id']} (from {p['check']})\n", f"**Location.** {p['location']}\n"]
        if p.get("quote"):
            L.append("**Passage.**\n\n" + "\n".join("> " + l for l in p["quote"].split("\n")) + "\n")
        L.append(f"**Problem.** {p['problem']}\n")
    return "\n".join(L if probs else L + ["(none)\n"])


def reported_problems(out, ids):
    """Each reported problem must be decided by an item of a reviewer's list `out` that names its id."""
    named = [i for k in ("issues", "open", "not_issues") for it in out[k] for i in it.get("reported", [])]
    return ([f"reported problem {i} is decided by no item: decide it as an issue (or part of one), an open problem or "
             "a place that is not an issue, and name its id in that item's `reported`" for i in sorted(ids - set(named))]
            + [f"{i}, named in `reported`, is not the id of a reported problem" for i in sorted(set(named) - ids)])


def reported_decisions(st):
    """For each reported problem, the items that decided it: the item's id and kind, the other reviewer's verdict, the
    author's check of a fix the other reviewer wrote, and whether a fix of it goes to the merge."""
    out = {p["id"]: [] for p in st.get("reported", [])}
    for r in REVIEWERS:
        for kind, key in (("finding", "lists"), ("open problem", "open"), ("not an issue", "not_issues")):
            for it in st.get(key, {}).get(r, []):
                v = (st.get("verdicts", {}).get(r, {}).get(it["id"]) or {}).get("verdict")
                c = (st.get("checks", {}).get(r, {}).get(it["id"]) or {}).get("verdict")
                fixed = (v == "accept" and kind == "finding") or (v == "repair" and c == "accept")
                for i in it.get("reported", []):
                    if i in out:
                        out[i].append({"item": it["id"], "kind": kind, "verdict": v, "check": c, "fixed": fixed})
    return out


def decisions_md(ds):
    return "; ".join(f"{d['item']} ({d['kind']}" + (f", verdict {d['verdict']}" if d["verdict"] else "")
                     + (f", the author {d['check']}ed the fix" if d["check"] else "") + ")" for d in ds) \
        or "decided by no item"


def open_for_author(st):
    """The open problems of a run's state `st` to report to the author: those the other reviewer confirmed, and those for
    which it wrote a fix that the author rejected. Before the cross review, or in runs made before open problems were
    judged, all."""
    out = []
    for r in REVIEWERS:
        for n, o in enumerate(st["open"][r], 1):
            v = st.get("verdicts", {}).get(r, {}).get(o.get("id"))
            c = st.get("checks", {}).get(r, {}).get(o.get("id"))
            if v is None or v["verdict"] == "accept" or (v["verdict"] == "repair" and c and c["verdict"] == "reject"):
                out.append(dict(o, id=o.get("id", f"{r}O{n}"), author=r, judge=v, check=c))
    return out


# ---------------------------------------------------------------------- the run
class CrossReview:
    def __init__(self, run_dir: Path, cfg: dict, mock=False):
        self.dir, self.cfg = run_dir, cfg
        self.rec = run_dir / "records"
        self.state = ag.jload(run_dir / "state.json", {})
        self.runner = ag.Runner(run_dir, cfg, mock)
        self.runner.pages = self.state.get("pages", 0)

    def R(self, *parts):
        return self.rec.joinpath(*parts)

    def save(self):
        ag.jdump(self.state, self.dir / "state.json")

    def prompt(self, name):
        base = self.dir / "prompts" if (self.dir / "prompts").is_dir() else PROMPTS    # runs made before the copy
        text = (base / f"{name}.md").read_text()
        return text.replace("{standard}", (base / "standard.md").read_text().strip()).replace(
            "{main}", self.state["main"]).strip()

    def copy_prompts(self, dirs):
        """Copy each step's prompt into the run, from the first of `dirs` that has it, else from prompts/."""
        dirs = [Path(d).expanduser().resolve() for d in dirs or []]
        for d in dirs:
            if not d.is_dir():
                raise SystemExit(f"prompts folder {d} does not exist")
        (self.dir / "prompts").mkdir()
        used = {}
        for name in STEP_PROMPTS:
            src = next(d / f"{name}.md" for d in [*dirs, PROMPTS] if (d / f"{name}.md").is_file())
            shutil.copy(src, self.dir / "prompts" / f"{name}.md")
            used[name] = str(src)
        return used

    def paper_files(self):
        return {"paper": self.R("draft"), "paper.pdf": self.R("draft_build", "render.pdf"),
                "paper.txt": self.R("draft_build", "render.txt"), "literature": self.R("literature")}

    def reported_files(self):
        """The problems that other checks reported, for the reviewers and the judges (empty for runs without any)."""
        st = self.state
        return {"reported.json": ag.Text(dump({"problems": st.get("reported", [])})),
                "reported.md": ag.Text(reported_md(st))}

    def sources(self, r):
        """The works that the reviewers obtained online and saved, for a later step of reviewer `r`: its own and the
        other's (only those that saved any)."""
        out = {}
        for who, rr in (("yours", r), ("other", OTHER[r])):
            d = self.R("jobs", f"review.{rr}", "sources")
            if d.is_dir() and any(d.iterdir()):
                out[f"sources/{who}"] = d
        return out

    def init(self, a):
        src = Path(a.draft).expanduser().resolve()
        if not src.exists():
            raise SystemExit(f"{src} does not exist")
        draft, skipped = self.R("draft"), []
        self.rec.mkdir(parents=True)
        prompts = self.copy_prompts(a.prompts)

        def skip(p):
            if ag.in_icloud_only(p):
                skipped.append(str(p))
                return True
            return False
        if src.is_file():
            draft.mkdir()
            shutil.copy(src, draft / src.name)
        else:
            tex.copy_source(src, draft, skip_file=skip)
        for f in [draft, *draft.rglob("*")]:
            os.chmod(f, 0o755 if f.is_dir() else 0o644)
        main = tex.find_main(draft)
        rep = tex.build(draft, main, self.R("draft_build"))
        if not rep["pdf"]:
            raise SystemExit("the draft does not build" + (f"; these files are in iCloud only: {skipped}" if skipped
                             else "") + "\n" + rep["log_tail"][-1500:])
        lit = [Path(p).expanduser().resolve() for p in a.literature or []]
        left_out = self.copy_literature(lit)
        reported = ag.jload(Path(a.reported).expanduser()) if a.reported else {"problems": []}
        ids = [p["id"] for p in reported["problems"]]
        if len(set(ids)) != len(ids) or any(not p.get(k) for p in reported["problems"] for k in
                                            ("id", "check", "location", "problem")):
            raise SystemExit("--reported: every problem needs a distinct id, a check, a location and a problem")
        self.state = {"name": a.name, "draft": str(src), "main": main, "pages": rep["pages"],
                      "words": source_words(draft), "undefined_refs": rep["undefined_refs"] + rep["undefined_cites"],
                      "literature": [str(p) for p in lit], "literature_left_out": left_out, "prompts": prompts,
                      "draft_skipped_icloud_only": skipped, "reported": reported["problems"],
                      "reported_about": reported.get("about", ""), "created": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.runner.pages = rep["pages"]
        self.save()
        (self.rec / "reported.md").write_text(reported_md(self.state))
        log(f"draft {main}: {rep['pages']} pages; literature: {len(lit)} path(s), {len(left_out)} file(s) left out"
            + (f"; {len(ids)} reported problem(s)" if ids else ""))

    def copy_literature(self, paths):
        """Copy the supplied works; each PDF also gets a text version with page markers. Files that cannot be used
        are listed in `literature/_left_out.txt`, for the reviewers to find online."""
        dst, left_out = self.R("literature"), []
        dst.mkdir(parents=True)
        for i, s in enumerate(paths, 1):
            if not s.exists():
                raise SystemExit(f"literature {s} does not exist")
            base = dst / (s.name if not (dst / s.name).exists() else f"{i}_{s.name}")
            files = [s] if s.is_file() else sorted(p for p in s.rglob("*") if p.is_file() and not p.name.startswith("."))
            for f in files:
                if ag.in_icloud_only(f):
                    left_out.append(f"{f.name}: in iCloud only")
                    continue
                target = base if s.is_file() else base / f.relative_to(s)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
                if f.suffix.lower() == ".pdf" and not target.with_suffix(".txt").exists() \
                        and not f.with_suffix(".txt").exists():         # a text that comes with the PDF is copied too
                    text = tex.paged_text(target)
                    if text.strip():
                        target.with_suffix(".txt").write_text(text)
                    else:
                        left_out.append(f"{f.name}: no text could be extracted (the PDF itself is there)")
        if left_out:
            (dst / "_left_out.txt").write_text("These supplied files could not be used:\n" + "\n".join(left_out) + "\n")
        return left_out

    # ------------------------------------------------------------------ 1. review
    def review(self):
        st = self.state
        if "lists" in st:
            return
        draft, ids = self.R("draft"), {p["id"] for p in st.get("reported", [])}

        def post(ws):
            out = ag.jload(ws / "issues.json")
            return (edit_problems(draft, [(f"issue {n}", it["edits"]) for n, it in enumerate(out["issues"], 1)])
                    + reported_problems(out, ids))
        jobs = [ag.Job(f"review.{r}", m, "review", self.prompt("review"),
                       {**self.paper_files(), **self.reported_files(),
                        "schemas/issues.schema.json": SCHEMAS / "issues.schema.json"},
                       {"issues.json": "issues", "notes/paper.md": None, "notes/literature.md": None, "notes/patterns.md": None},
                       page_timed=True, postcheck=post, network=True, carry=["issues.json", "notes", "sources"])
                for r, m in REVIEWERS.items()]
        lists, opens, nots = {}, {}, {}     # recorded only once both reviews are done, so that a stopped run resumes here
        for r, d in zip(REVIEWERS, self.runner.run(jobs)):
            out = ag.jload(d / "issues.json")
            lists[r] = [dict(it, id=f"{r}{n}") for n, it in enumerate(out["issues"], 1)]
            opens[r] = [dict(it, id=f"{r}O{n}", kind="open") for n, it in enumerate(out["open"], 1)]
            nots[r] = [dict(it, id=f"{r}N{n}", kind="not_issue") for n, it in enumerate(out["not_issues"], 1)]
        st["lists"], st["open"], st["not_issues"] = lists, opens, nots
        log("review: " + ", ".join(f"list {r} has {len(lists[r])} issue(s), {len(opens[r])} open, {len(nots[r])} "
                                   "not issues" for r in REVIEWERS))
        self.save()

    def items(self, r):
        """Everything list `r` decided: its findings, the problems it left open, and the places it decided are not
        issues (runs made before these were judged have only findings and open problems, without ids)."""
        st = self.state
        return [*(dict(it, kind="issue") for it in st["lists"][r]), *(o for o in st["open"][r] if "id" in o),
                *st.get("not_issues", {}).get(r, [])]

    # ------------------------------------------------------------------ 2. cross review
    def cross(self):
        st = self.state
        if "verdicts" in st:
            return
        jobs, judged, draft = [], [], self.R("draft")
        for r, m in REVIEWERS.items():
            items = self.items(OTHER[r])
            if not items:
                continue
            kinds = {it["id"]: it["kind"] for it in items}
            jobs.append(ag.Job(f"cross.{r}", m, "cross", self.prompt("cross_review"),
                               {**self.paper_files(), **self.reported_files(), **self.sources(r),
                                "notes": self.R("jobs", f"review.{r}", "notes"),
                                "items.json": ag.Text(dump({"items": items})),
                                "items.md": ag.Text(items_md(items, "The other reviewer's list")),
                                "schemas/verdicts.schema.json": SCHEMAS / "verdicts.schema.json"},
                               {"verdicts.json": "verdicts"}, page_timed=True, network=True, carry=["verdicts.json"],
                               postcheck=lambda ws, kinds=kinds: verdict_problems(ag.jload(ws / "verdicts.json"),
                                                                                  kinds, draft)))
            judged.append(OTHER[r])
        verdicts = {r: {} for r in REVIEWERS}
        for r, d in zip(judged, self.runner.run(jobs)):
            verdicts[r] = {v["id"]: {k: v[k] for k in ("verdict", "reason")
                                     + (("fix", "edits") if v["verdict"] == "repair" else ())}
                           for v in ag.jload(d / "verdicts.json")["verdicts"]}
        st["verdicts"] = verdicts
        log(f"cross review: {len(self.judged('accept'))} finding(s) accepted, "
            f"{sum(map(len, self.to_check().values()))} fix(es) written by the judge, for its author to check")
        self.save()

    def to_check(self):
        """The items for which the other reviewer wrote a fix: a correction of a finding's fix (shown with the original),
        or a fix for an open problem or for a place decided not to be an issue."""
        st, out = self.state, {}
        for r in REVIEWERS:
            out[r] = []
            for it in self.items(r):
                v = st["verdicts"][r][it["id"]]
                if v["verdict"] != "repair":
                    continue
                orig = {"original_fix": it["fix"], "original_edits": it["edits"]} if "edits" in it else {}
                out[r].append(dict(it, fix=v["fix"], edits=v["edits"], judge_reason=v["reason"], **orig))
        return out

    # ------------------------------------------------------------------ 2b. the author checks each corrected fix
    def check(self):
        st = self.state
        if "checks" in st:
            return
        jobs, authors = [], []
        for r, items in self.to_check().items():
            if not items:
                continue
            kinds = {it["id"]: it["kind"] for it in items}
            jobs.append(ag.Job(f"check.{r}", REVIEWERS[r], "check", self.prompt("check_repair"),
                               {**self.paper_files(), **self.sources(r), "notes": self.R("jobs", f"review.{r}", "notes"),
                                "items.json": ag.Text(dump({"items": items})),
                                "items.md": ag.Text(items_md(items, "Your list, with the fixes the other reviewer wrote")),
                                "schemas/verdicts.schema.json": SCHEMAS / "verdicts.schema.json"},
                               {"verdicts.json": "verdicts"}, page_timed=True, network=True, carry=["verdicts.json"],
                               postcheck=lambda ws, kinds=kinds: verdict_problems(ag.jload(ws / "verdicts.json"),
                                                                                  kinds)))
            authors.append(r)
        checks = {r: {} for r in REVIEWERS}
        for r, d in zip(authors, self.runner.run(jobs)):
            checks[r] = {v["id"]: {"verdict": v["verdict"], "reason": v["reason"]}
                         for v in ag.jload(d / "verdicts.json")["verdicts"]}
        st["checks"] = checks
        if jobs:
            n = sum(c["verdict"] == "accept" for cs in checks.values() for c in cs.values())
            log(f"check: the authors accepted {n} of {sum(map(len, checks.values()))} fix(es) written by the judge")
        self.save()

    def judged(self, verdict="accept"):
        """With `verdict` accept, the findings to apply: those accepted as written, and the fixes the other reviewer
        wrote (a correction, a fix for an open problem, or a fix for a place decided not to be an issue) that the item's
        author accepted. With reject, the findings rejected as written and the fixes the item's author rejected."""
        st, out, key = self.state, [], f"{verdict}ed_because"
        checks = st.get("checks", {})
        for r in REVIEWERS:
            for it in self.items(r):
                v, c = st["verdicts"][r][it["id"]], checks.get(r, {}).get(it["id"])
                kind = it["kind"]
                if v["verdict"] == verdict and kind == "issue":
                    out.append(dict(it, **{key: v["reason"]}))
                elif v["verdict"] == "repair" and c and c["verdict"] == verdict:
                    why = {"issue": "The other reviewer found the problem real and corrected the fix: ",
                           "open": "The reviewer left this problem open for the author; the other reviewer wrote a "
                                   "fix for it: ",
                           "not_issue": f"The reviewer who noted this decided it was not an issue ({it.get('reason')}); "
                                        "the other reviewer found it an issue and wrote a fix: "}[kind]
                    found = {k: it.get(k, "") for k in ("location", "problem", "pattern", "evidence")}
                    if kind == "not_issue":
                        found["problem"] = it["cost"]
                    out.append(dict(found, id=it["id"], fix=v["fix"], edits=v["edits"], **{key: (
                        f"{why}{v['reason']} The reviewer who wrote the item {verdict}ed the fix: {c['reason']}")}))
        return out

    # ------------------------------------------------------------------ 3. merge
    def merge(self):
        st = self.state
        if "final" in st:
            return
        acc, rej = self.judged("accept"), self.judged("reject")
        if acc:
            draft = self.R("draft")
            job = ag.Job("merge", "gpt", "merge", self.prompt("merge"),
                         {"paper": draft, "paper.txt": self.R("draft_build", "render.txt"),
                          "accepted.json": ag.Text(dump({"findings": acc})),
                          "accepted.md": ag.Text(items_md(acc, "Accepted findings")),
                          "rejected.json": ag.Text(dump({"fixes": rej})),
                          "rejected.md": ag.Text(items_md(rej, "Rejected fixes")),
                          "schemas/final.schema.json": SCHEMAS / "final.schema.json"},
                         {"final.json": "final"}, carry=["final.json"],
                         postcheck=lambda ws: final_problems(draft, ag.jload(ws / "final.json"), acc))
            d = self.runner.run([job])[0]
            final = ag.jload(d / "final.json")
            st["final"] = [dict(it, id=str(n)) for n, it in enumerate(final["items"], 1)]
            st["left_out"] = final["left_out"]
        else:
            st["final"] = []
        log(f"merge: {len(acc)} accepted finding(s) became {len(st['final'])} item(s)"
            + (f"; {len(st['left_out'])} left out" if st.get("left_out") else ""))
        self.save()

    # ------------------------------------------------------------------ 4. revise
    def revise(self):
        st = self.state
        if "revised" in st or not st["final"]:
            return
        draft, main = self.R("draft"), st["main"]
        apply_edits(draft, self.R("expected"), [e for it in st["final"] for e in it["edits"]])
        before = set(st["undefined_refs"])

        def post(ws):
            out = ws / "output"
            if not (out / main).is_file():
                return [f"output/{main} is missing"]
            with tempfile.TemporaryDirectory() as td:
                rep = tex.build(out, main, Path(td))
            if not rep["pdf"]:
                return ["output/ does not compile; the end of the log:\n" + rep["log_tail"][-1500:]]
            new = sorted(set(rep["undefined_refs"] + rep["undefined_cites"]) - before)
            return [f"undefined references or citations that the draft did not have: {new}"] if new else []
        job = ag.Job("revise", "gpt", "revise", self.prompt("revise"),
                     {"input": draft, "final.json": ag.Text(dump({"items": st["final"]})),
                      "final.md": ag.Text(items_md(st["final"], "Revisions to make"))},
                     {"changes.md": None}, page_timed=True, postcheck=post, carry=["output", "changes.md"])
        d = self.runner.run([job])[0]
        revised = self.dir / "revised"
        tex.copy_source(d / "output", revised)
        rep = tex.build(revised, main, self.R("revised_build"))
        shutil.copy(self.R("revised_build", "render.pdf"), self.dir / "revised.pdf")
        shutil.copy(d / "changes.md", self.dir / "changes.md")
        dev = tex.differences(self.R("expected"), revised)
        (self.dir / "deviations.md").write_text(
            "Where the revised paper differs from the list applied exactly. The editor's account is in changes.md.\n\n"
            + tex.differences_md(dev, ("the list applied exactly", "the revised paper")))
        whole = tex.differences(draft, revised)
        (self.dir / "revised_vs_draft.md").write_text(tex.differences_md(whole, ("draft", "revised")))
        st["revised"] = {"pages": rep["pages"], "words": source_words(revised), "deviations": len(dev),
                         "passages_changed": len(whole)}
        log(f"revise: {len(whole)} passage(s) changed, {len(dev)} deviation(s) from the list")
        self.save()

    # ------------------------------------------------------------------ report
    def report(self):
        st, L = self.state, []
        if not st:
            return
        L += [f"# Cross review `{st['name']}`", "",
              f"- Draft: `{st['draft']}` (root file `{st['main']}`), {st['pages']} pages, about {st['words']} words.",
              f"- Literature supplied: {len(st['literature'])} path(s)" + (
                  f"; left out: {'; '.join(st['literature_left_out'])}" if st["literature_left_out"] else "") + "."]
        if "lists" in st:
            for r, m in REVIEWERS.items():
                items, v = self.items(r), st.get("verdicts", {}).get(r)
                counts = []
                if v is not None:
                    c = st.get("checks", {}).get(r, {})
                    items = [dict(it, corrected=v[it["id"]]) if v[it["id"]]["verdict"] == "repair" else it
                             for it in items]
                    v = {i: x if i not in c else {"verdict": f"repair; the author then {c[i]['verdict']}ed the fix",
                                                  "reason": f"{x['reason']}\n\n**The author's check of the fix.** "
                                                  f"{c[i]['reason']}"} for i, x in v.items()}
                    for kind, name in (("issue", "finding(s)"), ("open", "open problem(s)"),
                                       ("not_issue", "place(s) decided not to be issues")):
                        ids = [it["id"] for it in items if it.get("kind", "issue") == kind]
                        n = lambda verdict: sum(st["verdicts"][r][i]["verdict"] == verdict for i in ids)
                        ok = sum(c.get(i, {}).get("verdict") == "accept" for i in ids)
                        counts.append(f"{len(ids)} {name}: " + {
                            "issue": f"accepted {n('accept')}, rejected {n('reject')}, fix corrected {n('repair')} "
                                     f"(the author accepted {ok})",
                            "open": f"confirmed {n('accept')}, rejected {n('reject')}, fixed {n('repair')} "
                                    f"(the author accepted {ok})",
                            "not_issue": f"agreed {n('accept')}, found an issue and wrote a fix {n('repair')} "
                                         f"(the author accepted {ok})"}[kind])
                else:
                    counts.append(f"{len(st['lists'][r])} issue(s)")
                (self.dir / f"list_{r}.md").write_text(items_md(items, f"List {r} (written by {m})", v))
                L.append(f"- List {r}, by {m}" + (f", judged by {REVIEWERS[OTHER[r]]}" if v is not None else "")
                         + f": {'; '.join(counts)}. See `list_{r}.md`.")
            opens = []
            for o in open_for_author(st):
                s = (f"## {o['id']} (from {REVIEWERS[o['author']]}): {o['location']}\n\n**Problem.** {o['problem']}\n\n"
                     f"**Evidence.** {o['evidence']}\n")
                if o["judge"]:
                    s += f"\n**The other reviewer's verdict: {o['judge']['verdict']}.** {o['judge']['reason']}\n"
                if o["check"]:
                    s += f"\n**Why the reviewer who raised the problem rejected that fix.** {o['check']['reason']}\n"
                opens.append(s)
            (self.dir / "open_questions.md").write_text(
                "# Problems for the author (not applied)\n\n" + ("\n".join(opens) if opens else "(none)\n"))
            L.append(f"- Problems for the author, not applied: {len(opens)}. See `open_questions.md`.")
            if st.get("reported"):
                dec = reported_decisions(st)
                (self.dir / "reported_decisions.md").write_text(
                    "# How the reviewers decided the reported problems\n\nThe problems are in `records/reported.md`; "
                    "a finding is applied if it is in `final_list.md`.\n\n"
                    + "\n".join(f"- **{i}:** {decisions_md(d)}" for i, d in dec.items()) + "\n")
                L.append(f"- Problems reported by other checks: {len(dec)}; for {sum(any(x['fixed'] for x in d) for d in dec.values())}"
                         " of them a fix went to the merge. See `reported_decisions.md`.")
        if "final" in st:
            out = st.get("left_out", [])
            (self.dir / "final_list.md").write_text(items_md(
                [dict(it, id=f"Item {it['id']} (from {', '.join(it['sources'])})") for it in st["final"]],
                "The merged list of revisions") + ("\n# Accepted findings left out by the merge\n\n" + "\n".join(
                    f"- **{o['id']}.** {o['reason']}" for o in out) + "\n" if out else ""))
            L.append(f"- Merged list: {len(st['final'])} item(s) from {len(self.judged('accept'))} accepted finding(s)"
                     + (f"; {len(out)} left out" if out else "") + ". See `final_list.md`.")
        if "revised" in st:
            rv = st["revised"]
            L.append(f"- Revised paper: `revised/` and `revised.pdf`, {rv['pages']} pages, about {rv['words']} words; "
                     f"{rv['passages_changed']} passage(s) changed (`revised_vs_draft.md`).")
            L.append(f"- Deviations from the list applied exactly: {rv['deviations']} (`deviations.md`; the editor's "
                     "account is in `changes.md`).")
        elif st.get("final") == []:
            L.append("- The merge left out every accepted finding, so the draft was not revised." if st.get("left_out")
                     else "- The other reviewer accepted no finding of either list, so the draft was not revised.")
        (self.dir / "report.md").write_text("\n".join(L) + "\n")

    def go(self):
        try:
            self.review()
            self.cross()
            self.check()
            self.merge()
            self.revise()
        finally:
            self.save()
            self.report()
        log(f"finished; see {self.dir / 'report.md'}")


# ---------------------------------------------------------------------- commands
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--name", required=True)
    r.add_argument("--draft", required=True, help="the paper's LaTeX source: a directory or a single .tex file")
    r.add_argument("--literature", nargs="*", help="files or directories of works the reviewers should read")
    r.add_argument("--prompts", nargs="*", help="folders of prompt files to use in place of those in prompts/")
    r.add_argument("--reported", help="a JSON file of problems that other checks found, for the reviewers to decide")
    for c in (r, sub.add_parser("resume")):
        c.add_argument("--config")
        c.add_argument("--mock", action="store_true", help="stub agents, for testing the tool itself")
        if c is not r:
            c.add_argument("--name", required=True)
    for n in ("status", "unlock"):
        sub.add_parser(n).add_argument("--name", required=True)
    a = ap.parse_args()

    run_dir = RUNS / a.name
    if a.cmd == "status":
        rep = run_dir / "report.md"
        print(rep.read_text() if rep.exists() else f"no report yet for {a.name}")
        return
    if a.cmd == "unlock":
        held = ag.jload(run_dir / "locked.json")
        if held:
            os.chmod(held["path"], held["mode"] or 0o755)
            (run_dir / "locked.json").unlink()
        print("unlocked")
        return
    ag.require_local([*HERE.glob("*.py"), PROMPTS, SCHEMAS, HERE / "config.json", *(getattr(a, "prompts", None) or [])])
    if a.cmd == "run" and run_dir.exists():
        raise SystemExit(f"{run_dir} exists; use `resume` or another --name")
    if a.cmd == "resume" and not (run_dir / "state.json").exists():
        raise SystemExit(f"no run {a.name}")
    run_dir.mkdir(parents=True, exist_ok=True)
    cr = CrossReview(run_dir, load_config(a.config), mock=a.mock)
    if a.cmd == "run":
        try:
            cr.init(a)
        except BaseException:
            shutil.rmtree(run_dir)          # nothing has run yet; the same --name can be used again
            raise
    else:
        cr.runner.unlock()
        if (cr.rec / "jobs").exists():
            cr.runner.set_aside_leftovers()

    def on_signal(sig, frame):
        cr.runner.stop_children()
        cr.runner.unlock()
        raise SystemExit(f"stopped by signal {sig}; resume with `review.py resume --name {a.name}`")
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    cr.go()


if __name__ == "__main__":
    main()
