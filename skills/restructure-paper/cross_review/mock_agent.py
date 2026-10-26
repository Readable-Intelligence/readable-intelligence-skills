#!/usr/bin/env python3
"""Stub standing in for both models in `review.py --mock` and `rounds.py --mock`: writes outputs of the right form, so
that the tool's control flow, staging, checks and bookkeeping can be tested without any model.

  mock_agent.py ROLE WORKSPACE JOB_NAME

Each reviewer edits two lines of the root file; list A's second edit and list B's first change the same line, so the
merge has one group to combine. Environment: MOCK_BAD_FIRST=review.A,merge,revise (the first attempt of these jobs
fails its checks: an `old` not in the source, overlapping findings left unmerged, a source that does not compile);
MOCK_REJECT=B2,AO1 (the cross reviewer rejects these findings or open problems); MOCK_REPAIR=A1,BN1,AO1 (it writes a
fix for these instead: a correction, a fix for a place decided not to be an issue, or for an open problem);
MOCK_REJECT_CHECK=A1 (the author rejects the judge's fix of these); MOCK_LEAVE_OUT=A2 (the merge leaves out these
accepted findings); MOCK_EMPTY=B (that list has no issues); MOCK_DEVIATE=1 (the editor makes one change that is not in the
list); MOCK_SLEEP=5 (each agent waits that many seconds first). The merge requires each rejected fix to carry its edits
and the reason it was rejected.
Each reviewer saves one mock work in `sources/`; the judges and the checks require both reviewers' works. Each reviewer
decides the reported problems (`reported.json`): the first by its first issue, the others as places that are not issues.
"""
import json, os, shutil, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tex  # noqa: E402

role, ws, name = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
env = lambda k: [x for x in os.environ.get(k, "").split(",") if x]
prompt = (ws / "_prompt.md").read_text()
retry = "A previous attempt" in prompt
bad = name in env("MOCK_BAD_FIRST") and not retry


def J(obj, f):
    (ws / f).parent.mkdir(parents=True, exist_ok=True)
    (ws / f).write_text(json.dumps(obj, indent=1))


def W(s, f):
    (ws / f).parent.mkdir(parents=True, exist_ok=True)
    (ws / f).write_text(s)


def need(*paths):
    for p in paths:
        if not (ws / p).exists():
            sys.exit(f"mock {role}: missing input {p}")


def lines_of(src):
    """The root file and its lines of plain text after \\begin{document} that occur there once."""
    main = tex.find_main(src)
    t = (src / main).read_text()
    body = t.split("\\begin{document}", 1)[-1]
    return main, [l for l in body.split("\n") if len(l) > 30 and not l.lstrip().startswith(("\\", "%")) and t.count(l) == 1]


time.sleep(float(os.environ.get("MOCK_SLEEP", 0)))
if not prompt.lstrip().startswith("# Role"):
    sys.exit("mock: the prompt has no task (was a prompt file read empty?)")
if not os.environ.get("TMPDIR", "").startswith(str(ws)) or "Isolation (mandatory)" not in prompt:
    sys.exit("mock: the workspace isolation was not set up")
if "{standard}" in prompt or "{main}" in prompt:
    sys.exit("mock: a placeholder was left in the prompt")
if retry and name in env("MOCK_BAD_FIRST"):
    carried = {"review": "issues.json", "cross": "verdicts.json", "check": "verdicts.json", "merge": "final.json",
               "revise": "output"}[role]
    if not (ws / carried).exists() or "already holds that attempt's outputs" not in prompt:
        sys.exit("mock: the failed attempt's outputs were not carried over")

if role == "review":
    need("paper", "paper.pdf", "paper.txt", "literature", "reported.json", "reported.md", "schemas/issues.schema.json")
    main, lines = lines_of(ws / "paper")
    r = name.split(".")[1]
    picks = [] if r in env("MOCK_EMPTY") else (lines[0:2] if r == "A" else lines[1:3])
    issues = [{"location": f"line of {main}", "problem": f"mock problem {r}{k}", "pattern": "mock pattern", "evidence": "mock evidence",
               "fix": "mock fix", "edits": [{"file": main, "old": l, "new": l + f" (revised by {r})"}]}
              for k, l in enumerate(picks, 1)]
    if bad and issues:
        issues[0]["edits"][0]["old"] += " not in the source"
    nots = [{"location": f"mock place {k}", "cost": f"mock cost {r}{k}", "reason": "mock reason"} for k in (1, 2)]
    rids = [x["id"] for x in json.loads((ws / "reported.json").read_text())["problems"]]
    if rids and issues:
        issues[0]["reported"], rids = rids[:1], rids[1:]
    if rids:
        nots[0]["reported"] = rids
    J({"issues": issues, "open": [{"location": "mock", "problem": f"mock open problem {r}", "evidence": "mock"}],
       "not_issues": nots}, "issues.json")
    W("Mock notes on the paper.\n", "notes/paper.md")
    W("Mock patterns of the literature.\n", "notes/patterns.md")
    W("Mock notes on the literature: " + ", ".join(sorted(str(p.relative_to(ws / "literature"))
                                                         for p in (ws / "literature").rglob("*"))) + "\n",
      "notes/literature.md")
    W(f"Mock work saved by reviewer {r}\nWhere: https://example.org/{r}\nExact text.\n\nMock text.\n",
      f"sources/mock_work_{r}.txt")

elif role == "cross":
    need("paper", "paper.pdf", "literature", "notes/paper.md", "notes/literature.md", "notes/patterns.md", "items.json",
         "items.md", "reported.json", "reported.md", "sources/yours", "sources/other")
    items = json.loads((ws / "items.json").read_text())["items"]
    if {it["kind"] for it in items} != {"issue", "open", "not_issue"} - ({"issue"} if not any(
            it["kind"] == "issue" for it in items) else set()):
        sys.exit("mock cross: the list lacks open problems or places decided not to be issues")
    main, lines = lines_of(ws / "paper")
    verdicts = []
    for it in items:
        v = {"id": it["id"], "verdict": "reject" if it["id"] in env("MOCK_REJECT") else "accept", "reason": "mock reason"}
        if it["id"] in env("MOCK_REPAIR"):
            edits = it.get("edits") or [{"file": main, "old": lines[3 + "AB".index(it["id"][0])], "new": "mock new"}]
            v.update(verdict="repair", fix="mock fix by the judge",
                     edits=[dict(e, new=e["old"] + " (corrected)") for e in edits])
        verdicts.append(v)
    J({"verdicts": verdicts}, "verdicts.json")

elif role == "check":
    need("paper", "paper.pdf", "literature", "notes/paper.md", "items.json", "items.md", "sources/yours", "sources/other")
    items = json.loads((ws / "items.json").read_text())["items"]
    if any(not it.get("judge_reason") or (it["kind"] == "issue") != bool(it.get("original_edits")) for it in items):
        sys.exit("mock check: an item lacks the judge's reason, or a corrected finding lacks its original fix")
    J({"verdicts": [{"id": it["id"], "verdict": "reject" if it["id"] in env("MOCK_REJECT_CHECK") else "accept",
                     "reason": "mock check"} for it in items]}, "verdicts.json")

elif role == "merge":
    need("paper", "paper.txt", "accepted.json", "accepted.md", "rejected.json", "rejected.md")
    if any(not f.get("edits") or not f.get("rejected_because")
           for f in json.loads((ws / "rejected.json").read_text())["fixes"]):
        sys.exit("mock merge: a rejected fix lacks its edits or the reason it was rejected")
    groups, out = [], []
    for f in json.loads((ws / "accepted.json").read_text())["findings"]:
        if f["id"] in env("MOCK_LEAVE_OUT"):
            out.append({"id": f["id"], "reason": "mock: a reason given for rejecting a fix applies to it"})
            continue
        olds = {(e["file"], e["old"]) for e in f["edits"]}
        g = None if bad else next((g for g in groups if g[1] & olds), None)
        if g:
            g[0].append(f)
            g[1].update(olds)
        else:
            groups.append(([f], olds))
    J({"items": [{"sources": [x["id"] for x in m], "location": m[0]["location"],
                  "problem": "; ".join(x["problem"] for x in m), "fix": m[0]["fix"], "edits": m[0]["edits"],
                  "merge_note": "" if len(m) == 1 else "mock: kept the first fix"} for m, _ in groups],
       "left_out": out}, "final.json")

elif role == "revise":
    need("input", "final.json", "final.md")
    shutil.copytree(ws / "input", ws / "output", dirs_exist_ok=True)
    main, lines = lines_of(ws / "output")
    for it in json.loads((ws / "final.json").read_text())["items"]:
        for e in it["edits"]:
            f = ws / "output" / e["file"]
            t = f.read_text()
            if t.count(e["old"]) != 1:
                sys.exit(f"mock revise: edit not applicable in {e['file']}")
            f.write_text(t.replace(e["old"], e["new"]))
    f = ws / "output" / main
    if bad:
        f.write_text(f.read_text().replace("\\end{document}", "\\undefinedmockcommand\n\\end{document}"))
    if os.environ.get("MOCK_DEVIATE"):
        f.write_text(f.read_text().replace(lines[-1], lines[-1] + " (an extra change)"))
    W("Mock: every item applied as written.\n", "changes.md")

else:
    sys.exit(f"mock: unknown role {role}")
