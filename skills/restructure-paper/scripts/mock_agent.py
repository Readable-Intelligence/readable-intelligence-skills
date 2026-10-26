#!/usr/bin/env python3
"""Stub standing in for both models in `duo.py --mock`. Writes schema-valid outputs so that the
orchestrator's control flow, staging, locking and bookkeeping can be tested without any model."""
import json, os, random, re, shutil, sys, tempfile
from pathlib import Path

role, ws, main = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
FAIL = set(filter(None, os.environ.get("MOCK_FAIL", "").split(",")))
MARK = Path(os.environ.get("MOCK_STATE") or ws.parent.parent / "_tmp")   # shared by all steps of a run
def once(tag):
    f = MARK / f".mock_{tag}"
    if tag in FAIL and not f.exists():
        f.write_text("x"); return True
    return False
def debt_hit():
    """MOCK_DEBT=2,5: the 2nd and 5th proof-check jobs of the run (counted across the run) report an unsupported step."""
    f = MARK / ".mock_check_count"
    n = int(f.read_text()) + 1 if f.exists() else 1
    f.write_text(str(n))
    return str(n) in os.environ.get("MOCK_DEBT", "").split(",")
import time; time.sleep(float(os.environ.get("MOCK_SLEEP", "0")))


def check_inputs():
    """Fail if the rendered prompt lists an input that the orchestrator did not stage (the chain test of --mock)."""
    pr = (ws / "_prompt.md").read_text()
    if "## Inputs" not in pr:
        return
    sec = pr.split("## Inputs", 1)[1].split("\n## ", 1)[0]
    optional = re.compile(r"if present|only|optional|absent|supplementary|re-check", re.I)
    for line in sec.splitlines():
        if not line.lstrip().startswith("-") or optional.search(line):
            continue
        for name in re.findall(r"`([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]*)?)`", line):
            if "." not in name and not name.endswith("/"):
                continue
            if name.startswith("schemas/") or name.endswith(".schema.json") or "<" in name:
                continue
            target = ws / name.rstrip("/")
            if not target.exists() and not any(ws.glob("*/" + name.rstrip("/"))):
                sys.exit(f"missing input {name} for {role}")


check_inputs()
if not os.environ.get("TMPDIR", "").startswith(str(ws)):
    sys.exit(f"TMPDIR {os.environ.get('TMPDIR')} is not inside the workspace")
if once("ratelimit_" + role):
    print("Claude AI usage limit reached|1700000000", file=sys.stderr); sys.exit(1)
rnd = random.Random(os.environ.get("MOCK_SEED", "0") + role + ws.name)
J = lambda o, f: (ws / f).parent.mkdir(parents=True, exist_ok=True) or (ws / f).write_text(json.dumps(o, indent=1))
W = lambda s, f: (ws / f).parent.mkdir(parents=True, exist_ok=True) or (ws / f).write_text(s)


def page_quote():
    t = (ws / "manuscript.txt").read_text() if (ws / "manuscript.txt").exists() else "<<<PAGE 1>>>\nabc"
    m = re.search(r"<<<PAGE (\d+)>>>\n(.*?\S.{10,60})", t, re.S)
    return (int(m.group(1)), m.group(2).strip().split("\n")[-1][:60]) if m else (1, "abc")


def copy_out(tag):
    shutil.copytree(ws / "src", ws / "out")
    p = ws / "out" / main
    txt = p.read_text()
    if tag == "buildfix":
        txt = txt.replace("\\mockbreak", "")
    if tag == "baseline" and once("build_break"):
        txt = txt.replace("\\begin{document}", "\\begin{document}\\mockbreak", 1)
    if tag == "baseline2" and "\\end{document}" in txt:
        # a new paragraph with mathematics, so that the audit of additions has regions to audit
        para = (f"\n\nBy construction we obtain $a_{{{rnd.randint(1, 99)}}} \\le b$ in this {tag} paragraph "
                f"{rnd.randint(1000, 9999)}, since the bound holds termwise.\n\n")
        i = txt.rindex("\\end{proof}") if "\\end{proof}" in txt else txt.rindex("\\end{document}")
        txt = txt[:i] + para + txt[i:]          # inside the last proof: an expanded proof passage to be checked
    p.write_text(txt + f"\n% mock {tag}\n")


if role == "gpt_retrieve.md":
    (ws / "refs").mkdir(exist_ok=True)
    W("Mock reference text. Definition 1.1. A widget is a gadget.", "refs/doe2020.txt")
    man = {"entries": [{"key": "doe2020", "title": "A mock reference", "authors": ["J. Doe"], "year": 2020,
                        "url": "https://arxiv.org/abs/0000.00000", "relation": "builds-on", "why": "mock",
                        "access": "full", "txt": "doe2020.txt"}]}
    if (ws / "refs" / "manifest.json").exists():
        man["entries"] += json.loads((ws / "refs" / "manifest.json").read_text())["entries"]
    J(man, "refs/manifest.json")
    J({"terms": [{"manuscript_term": "widget", "standard_term": "widget", "status": "standard",
                  "source_key": "doe2020", "locator": "Def 1.1", "quote": "A widget is a gadget."}]}, "refs/terms.json")
elif role == "claude_calibrate.md":
    W("# style card (mock)\n", "style_card.md"); W("# anchors (mock)\n", "rubric_anchors.md")
    W("# architecture (mock)\n", "architecture.md")
    J({"papers": [{"key": "doe2020", "pages": 20, "outline": [{"section": "1", "job": "results"}],
                   "first_main_statement_page": 2, "first_main_statement_form": "precise", "intro_pages": 3,
                   "assembly": "closing_assembly"}],
       "synthesis": {"analogues": ["doe2020"], "first_main_statement_page_range": [1, 3], "intro_pages_range": [2, 4],
                     "default_architecture": [{"part": "introduction with results", "function": "mock",
                                               "support": "unanimous"}]}}, "architecture.json")
    if (ws / "previous").exists() and not (ws / "new_keys.txt").exists():
        sys.exit("supplementary calibration without new_keys.txt")
    J({"gaps": [{"kind": "comparable-length", "detail": "mock gap"}] if once("gaps") else []}, "gaps.json")
elif role == "terms.md":
    if not (ws / "refs" / "terms.json").exists():
        sys.exit("terms verifier without refs/terms.json")
    J({"terms": [{"manuscript_term": "widget", "standard_term": "widget", "check": "verified", "source_key": "doe2020"}]},
      "terms_verified.json")
elif role == "gpt_baseline.md":
    for f in ("architecture.md", "style_card.md"):
        if not (ws / f).exists():
            sys.exit(f"baseline without {f}")
    copy_out("baseline")
    labels = sorted(set(re.findall(r"\\label\{([^}]+)\}", (ws / "src" / main).read_text())))
    if once("plan_incomplete"):
        labels = labels[1:]
    J({"equivalences": [], "open_issues": [], "architecture_plan": [
        {"item": "all results", "new_location": "as before", "presentation": "main-route statement", "reason": "mock",
         "labels": labels}]}, "notes.json")
elif role == "gpt_baseline_2.md":
    if not (ws / "original").exists() or not (ws / "notes_pass1.json").exists():
        sys.exit("second baseline pass without original/ or notes_pass1.json")
    copy_out("baseline2")
    J({"equivalences": [], "open_issues": [{"location": "x", "issue": "mock class 3", "class": "3"}],
       "added_arguments": [{"location": "x", "class": "1", "obligation": "a -> b", "inputs": "mock"}]}, "notes.json")
elif role == "gpt_sketch.md":
    copy_out("sketch")
    (ws / "sketch_notes.md").write_text("# Evidence for the revised proof sketch\n\n1. mock reason: body line 1.\n")
elif role == "check.md":
    cur = ws / "current.txt"
    t = cur.read_text() if cur.exists() else ""
    m = re.search(r"<<<PAGE \d+>>>\n(?:.*\n)*?\s*(\S.{20,70})", t)
    q = m.group(1).strip() if m else "nothing"
    out = {"additions": [], "gaps": []}
    if True:
        regs = json.loads((ws / "regions.json").read_text())
        out["regions"] = [{"id": r["id"], "verdict": "no_new_claim"} for r in regs]
        if regs:
            # quote the region text itself; a region holding a planted defect is therefore "found"
            rq = next((l.strip() for r in regs for l in r["text"].split("\n") if re.search(r"\\(le|ge)\b|\\cite\[", l)),
                      regs[0]["text"].split("\n")[0].strip())
            if os.environ.get("MOCK_BLIND") == "gpt" and (ws / "refs" / "terms.json").exists():
                rq = regs[0]["text"].split("\n")[0].strip()      # a blind GPT checker quotes something else
            status = "unsupported" if (once("audit_reject") or debt_hit()) else rnd.choice(["verified", "standard"])
            out["regions"][0:1] = [{"id": regs[0]["id"], "verdict": "addition", "addition_ids": ["A1"]}]
            out["additions"].append({"id": "A1", "region": regs[0]["id"], "location": regs[0]["file"], "quote": rq[:90],
                                     "kind": "mechanism", "status": status, "justification": "mock"})
        if regs and once("audit_skip_region"):
            out["regions"] = out["regions"][:-1]          # leave one region without a verdict
    out["gaps"].append({"id": "G1", "location": "p. 1", "quote": q, "class": "3", "obligation": "mock obligation"})
    J(out, "audit.json")
    W("mock audit\n", "audit.md")
elif role == "registrar.md":
    if not (ws / "refs" / "manifest.json").exists():
        sys.exit("registrar without refs/")
    shutil.copytree(ws / "src", ws / "out")         # the stub finds nothing to fix
    W("# registry (mock)\n", "registry.md")
    (MARK / ".mock_registrar_ran").write_text("x")  # the registrar runs once, at the terminology pass
elif role == "accept.md":
    # MOCK_FAILS=3,1,0: the n-th acceptance review of the run fails that many conditions (the last value repeats)
    f = MARK / ".mock_accept_count"
    n = int(f.read_text()) + 1 if f.exists() else 1
    f.write_text(str(n))
    seq = [int(x) for x in os.environ.get("MOCK_FAILS", "0").split(",") if x.strip()]
    nfail = seq[min(n, len(seq)) - 1]
    conds = json.loads((ws / "criteria" / "conditions.json").read_text())
    if not (ws / "criteria" / "criteria.md").exists():
        sys.exit("acceptance review without criteria/criteria.md")
    pg, q = page_quote()
    J({"claims": "mock", "routes": [{"result": "Theorem", "from_introduction": "mock", "from_statements": "mock"}],
       "constructions": [], "reconstruction": [], "nothing_new": []}, "reading.json")
    J({"summary": "mock", "conditions": [dict({"id": c["id"], "status": "FAIL" if i < nfail else "PASS",
                                               "locations": [{"page": pg, "quote": q}], "evidence": "mock"},
                                              **({"required_repair": "mock repair"} if i < nfail else {}))
                                         for i, c in enumerate(conds)],
       "math_issues": [], "optional": [], "coverage": [{"section": "1", "depth": "careful"}]}, "acceptance.json")
    W("mock acceptance\n", "acceptance.md")
elif role == "pairwise.md":
    v = lambda: {"verdict": rnd.choice(["X", "Y", "X", "Y", "tie"]), "confidence": rnd.choice(["medium", "high"])}
    if os.environ.get("MOCK_PAIRWISE") == "longer":     # prefer the version with more text (the newer one in mock runs)
        lx, ly = len((ws / "X.txt").read_text()), len((ws / "Y.txt").read_text())
        pick = "X" if lx > ly else "Y" if ly > lx else "tie"
        v = lambda: {"verdict": pick, "confidence": "high"}
    J({"dimensions": {k: v() for k in "GCLT"}, "field_reader": v() if os.environ.get("MOCK_PAIRWISE") else
       {"verdict": "tie", "confidence": "low"},
       "checking_reader": v() if os.environ.get("MOCK_PAIRWISE") else {"verdict": "tie", "confidence": "low"}, "overall": v(),
       "regressions": {"X": [], "Y": []}}, "pairwise.json")
    W("mock pairwise\n", "pairwise.md")
elif role == "fidelity.md":
    ck = json.loads((ws / "checks.json").read_text())
    ids = [c["id"] for k in ("statements", "qualifications", "displays") for c in ck.get(k, [])]
    lost = once("fidelity_lost")
    # MOCK_FAIL=terms_fidelity_lost: the first fidelity check after the registrar (the terminology gate) reports a blocking finding
    terms_lost = (MARK / ".mock_registrar_ran").exists() and once("terms_fidelity_lost")
    checks = [{"id": i, "verdict": "lost" if (lost and n == 0) else "kept", "where": "mock"} for n, i in enumerate(ids)]
    # report every source line that differs from the original (so planted defects are found unless told to miss)
    orig = set((ws / "original" / main).read_text().split("\n")) if (ws / "original" / main).exists() else set()
    diff = [l for l in (ws / "current" / main).read_text().split("\n") if l.strip() and l not in orig][:6]
    blind = os.environ.get("MOCK_BLIND") == "gpt" and (ws / "refs" / "terms.json").exists()   # GPT staging carries terms.json
    items = [] if (once("canary_miss") or blind) else [{"id": f"F{n}", "severity": "M", "kind": "changed", "quote_current": l.strip()[:120],
                                             "explanation": "mock"} for n, l in enumerate(diff)]
    if terms_lost and items:
        items[0]["severity"] = "H"
    J({"counts": {s: sum(i["severity"] == s for i in items) for s in ("H", "M", "L")}, "items": items, "checks": checks,
       "build_ok": True}, "fidelity.json")
    W("mock fidelity\n", "fidelity.md")
elif role == "claude_compiler.md":
    f = ws / "src" / main
    lines = f.read_text().split("\n")
    ln = next(i for i, l in enumerate(lines, 1) if l.strip())
    for f in ("audit.json", "structure_check.json", "architecture.md", "pairwise_labels.txt", "copied_phrases.json",
              "bib_check.json"):
        if not (ws / f).exists():
            sys.exit(f"compiler without {f}")
    stale = once("stale_anchor")      # right snippet, wrong line, workspace-relative file name
    far = [i for i, l in enumerate(lines, 1) if i > ln + 50 and len(l.strip()) > 30
           and sum(x.strip() == l.strip() for x in lines) == 1]
    ln2 = far[0] if (stale and far) else ln
    # anchor to the line that carries the first blocking proof-check finding, as a real repair sheet would
    au = json.loads((ws / "audit.json").read_text())
    qs = [a["quote"][:40] for a in au.get("additions", []) if a["status"] in ("unsupported", "false")]
    hit = [i for i, l in enumerate(lines, 1) if qs and qs[0].strip() and qs[0].strip() in l]
    if not hit and (ws / "fidelity.json").exists():     # or the first blocking fidelity finding
        fq = [x["quote_current"][:40] for x in json.loads((ws / "fidelity.json").read_text()).get("items", [])
              if x.get("severity") == "H" and x.get("quote_current")]
        hit = [i for i, l in enumerate(lines, 1) if fq and fq[0].strip() and fq[0].strip() in l]
    ln2 = hit[0] if hit else ln2
    snip = lines[ln2 - 1].strip()[:80]
    J({"round": json.loads((ws / "limits.json").read_text())["round"], "mode": (ws / "mode.txt").read_text().strip(),
       "items": [{"id": "C1", "class": "C", "priority": 1, "title": "mock", "kind": "edit", "locations": [
           {"file": ("src/" + main) if stale else main, "line": ln if stale else ln2,
            "snippet": "NOT IN SOURCE" if once("bad_anchor") else snip}], "instances_complete": True,
           "problem": "mock", "target": "mock", "constraints": "R1"}], "do_not_touch": []}, "instructions.json")
    W("mock instructions\n", "instructions.md")
    J({"decisions": [{"anchor": "x", "decision": "mock", "reason": "mock"}], "reversals": [], "declines": []}, "ledger_update.json")
elif role == "gpt_execute.md":
    ins = json.loads((ws / "instructions.json").read_text())
    # a local repair: rewrite exactly the anchored lines (the text grows, so MOCK_PAIRWISE=longer keeps preferring it)
    shutil.copytree(ws / "src", ws / "out")
    p = ws / "out" / main
    lines = p.read_text().split("\n")
    for loc in (l for it in ins["items"] for l in it["locations"]):
        i = next((j for j, l in enumerate(lines) if loc["snippet"].strip() and loc["snippet"].strip() in l), None)
        if i is not None:
            lines[i] += f" Hence this step follows from the stated inputs ({ins['mode']})."
    txt = "\n".join(lines)
    if once("exec_unbuildable"):          # a break the build fixer does not repair
        txt = txt.replace("\\begin{document}", "\\begin{document}\\undefinedhardbreak", 1)
    p.write_text(txt)
    J({"items": [{"id": "C1", "status": rnd.choice(["done", "declined"]), "reason": "mock"}],
       "consequential_changes": [], "compiles": True}, "receipt.json")
elif role == "gpt_buildfix.md":
    copy_out("buildfix")
elif role == "gpt_defensive.md":
    # deletes "No ... is assumed/needed." sentences; MOCK_FAIL=defensive_adds: also adds a word (the output is rejected)
    shutil.copytree(ws / "src", ws / "out")
    for p in (ws / "out").rglob("*.tex"):
        txt = re.sub(r" ?No [^.]*? (is|are) (assumed|needed)\.", "", p.read_text())
        p.write_text(txt.replace("\\end{document}", "Added.\n\\end{document}") if once("defensive_adds") else txt)
else:
    sys.exit(f"unknown role {role}")
print("mock ok")
