"""LaTeX helpers used by the orchestrator: build, render text, strip comments,
number lines, extract theorem-like statements, diff sources. Standard library only
(plus latexmk and pdftotext on PATH)."""
import difflib, re, shutil, subprocess, tempfile
from pathlib import Path

TEX_EXT = {".tex", ".sty", ".cls", ".bib", ".bbl", ".bst"}
JUNK = {".aux", ".log", ".out", ".fls", ".fdb_latexmk", ".toc", ".blg", ".gz"}
DEFAULT_ENVS = ["theorem", "lemma", "proposition", "corollary", "definition", "claim",
                "conjecture", "remark", "example", "assumption", "hypothesis", "fact", "observation"]


def find_main(src: Path) -> str:
    """The root file: has \\documentclass and \\begin{document}; prefer one that typesets a title, then the largest."""
    cands = []
    for p in src.rglob("*.tex"):
        s = p.read_text(errors="ignore")
        if "\\documentclass" in s and "\\begin{document}" in s:
            score = (("\\maketitle" in s or "\\title" in s), "standalone" not in s.split("\\documentclass", 1)[1][:80],
                     p.name in ("main.tex", "paper.tex", "ms.tex"), len(s))
            cands.append((score, p))
    if not cands:
        raise SystemExit(f"no root .tex file (with \\documentclass and \\begin{{document}}) under {src}")
    return str(max(cands, key=lambda c: c[0])[1].relative_to(src))


def copy_source(src: Path, dst: Path):
    """Copy a source tree without build products."""
    if dst.exists():
        shutil.rmtree(dst)
    def ign(d, names):
        names_set = set(names)
        skip = [n for n in names if Path(n).suffix in JUNK or n in ("_tmp", "__pycache__")]
        # a PDF is a build product only if a .tex file with the same stem sits next to it
        skip += [n for n in names if n.endswith(".pdf") and (Path(n).stem + ".tex") in names_set]
        return skip
    shutil.copytree(src, dst, ignore=ign)


def paged_text(pdf: Path) -> str:
    raw = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    out = []
    for i, page in enumerate(raw.split("\f"), 1):
        if page.strip():
            out.append(f"\n<<<PAGE {i}>>>\n{page}")
    return "".join(out)


def build(src: Path, main: str, out_prefix: Path, timeout=900) -> dict:
    """Compile a copy of src; write out_prefix.pdf/.txt; return a build report."""
    rep = {"ok": False, "pdf": False, "undefined_refs": [], "undefined_cites": [], "qq": 0, "pages": 0, "log_tail": ""}
    with tempfile.TemporaryDirectory() as td:
        t = Path(td) / "b"
        copy_source(src, t)
        main_dir = (t / main).parent
        try:
            r = subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                                Path(main).name], cwd=main_dir, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep["log_tail"] = "latexmk timed out"
            return rep
        logf = main_dir / (Path(main).stem + ".log")
        log = logf.read_text(errors="ignore") if logf.exists() else r.stdout + r.stderr
        rep["log_tail"] = log[-6000:]
        pdf = main_dir / (Path(main).stem + ".pdf")
        if r.returncode != 0 or not pdf.exists():
            return rep
        rep["undefined_refs"] = sorted(set(re.findall(r"Reference `([^']+)' on page", log)))
        rep["undefined_cites"] = sorted(set(re.findall(r"Citation `([^']+)' on page", log)))
        shutil.copy(pdf, str(out_prefix) + ".pdf")
        txt = paged_text(pdf)
        Path(str(out_prefix) + ".txt").write_text(txt)
        rep["qq"] = len(re.findall(r"\?\?", txt))
        rep["pages"] = txt.count("<<<PAGE ")
        rep["pdf"] = True
        stem = main_dir / Path(main).stem
        rep["toc"] = parse_toc(stem.with_suffix(".toc"))
        rep["label_pages"] = parse_label_pages(stem.with_suffix(".aux"))
        rep["ok"] = not rep["undefined_refs"] and not rep["undefined_cites"]
    return rep


_COMMENT = re.compile(r"(?<!\\)%.*$")


def strip_comments(src: Path, dst: Path):
    """Copy src to dst removing LaTeX comments but keeping every line (line numbers stay valid)."""
    copy_source(src, dst)
    for p in dst.rglob("*.tex"):
        lines = p.read_text(errors="ignore").split("\n")
        out = []
        for ln in lines:
            if "\\verb" in ln or "\\url" in ln or "\\href" in ln:
                out.append(ln)          # be conservative where % may be literal
            else:
                out.append(_COMMENT.sub("", ln).rstrip())
        p.write_text("\n".join(out))


def number_lines(src: Path, dst: Path):
    copy_source(src, dst)
    index = []
    for p in sorted(dst.rglob("*.tex")):
        lines = p.read_text(errors="ignore").split("\n")
        p.write_text("\n".join(f"{i:5d}| {l}" for i, l in enumerate(lines, 1)))
        index.append(f"{p.relative_to(dst)}\t{len(lines)}")
    return index


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def resolve_file(src: Path, file: str):
    """Map a location's file name to a file under src. Agents see the source as `src/` (or the numbered copy
    as `src_numbered/`) inside their workspace, so `src/main.tex` and `main.tex` must both resolve."""
    f = file.strip().lstrip("./")
    for pre in ("src/", "src_numbered/", "src_clean/"):
        if f.startswith(pre):
            f = f[len(pre):]
            break
    p = src / f
    return (p, f) if p.is_file() else (None, f)


def snippet_ok(src: Path, file: str, line: int, snippet: str, slack=3) -> bool:
    p, _ = resolve_file(src, file)
    if p is None or not snippet.strip():
        return False
    lines = p.read_text(errors="ignore").split("\n")
    window = " ".join(lines[max(0, line - 1 - slack): line + slack])
    return _norm(snippet)[:120] in _norm(window)


def relocate(src: Path, file: str, line: int, snippet: str, near=40):
    """Find the snippet if its line number is off. Returns (file relative to src, line) or None.
    Searches near the stated line first, then the whole file, then the other source files; an occurrence is
    accepted only if it is unique at its search level, so a repeated phrase is never silently re-anchored."""
    key = _norm(snippet)[:120]
    if not key or len(key) < 12:
        return None
    p, f = resolve_file(src, file)
    files = ([p] if p else []) + [q for q in sorted(src.rglob("*.tex")) if q != p]

    def hits(q, lo=None, hi=None):
        lines = q.read_text(errors="ignore").split("\n")
        lo, hi = max(0, (lo or 1) - 1), min(len(lines), hi or len(lines))
        out = []
        for i in range(lo, hi):
            # the snippet may wrap over the following lines
            if key in _norm(" ".join(lines[i:i + 4])) and key not in _norm(" ".join(lines[i + 1:i + 4])):
                out.append(i + 1)
        return out

    if p:
        h = hits(p, line - near, line + near)
        if len(h) == 1:
            return f, h[0]
        if len(h) > 1:
            return None
        h = hits(p)
        if len(h) == 1:
            return f, h[0]
        if len(h) > 1:
            return None
    found = [(q, n) for q in files[1 if p else 0:] for n in hits(q)]
    if len(found) == 1:
        return str(found[0][0].relative_to(src)), found[0][1]
    return None


def theorem_envs(src: Path):
    envs = set(DEFAULT_ENVS)
    for p in src.rglob("*.tex"):
        for m in re.finditer(r"\\newtheorem\*?\{(\w+)\}", p.read_text(errors="ignore")):
            envs.add(m.group(1))
    return sorted(envs)


def extract_statements(src: Path):
    envs = theorem_envs(src)
    pat = re.compile(r"\\begin\{(" + "|".join(map(re.escape, envs)) + r")\*?\}(\[[^\]]*\])?(.*?)\\end\{\1\*?\}", re.S)
    out = []
    for p in sorted(src.rglob("*.tex")):
        t = p.read_text(errors="ignore")
        for m in pat.finditer(t):
            body = m.group(3)
            lab = re.search(r"\\label\{([^}]+)\}", body)
            out.append({"file": str(p.relative_to(src)), "line": t[:m.start()].count("\n") + 1,
                        "env": m.group(1), "title": (m.group(2) or "").strip("[]"),
                        "label": lab.group(1) if lab else "",
                        "body": re.sub(r"\s+", " ", body).strip()})
    return out


def match_statements(a, b):
    """Best-effort matching (label first, then text similarity). Returns a readable report."""
    lines, used = [], set()
    bylab = {s["label"]: i for i, s in enumerate(b) if s["label"]}
    for s in a:
        j = bylab.get(s["label"]) if s["label"] else None
        if j is None:
            best, j = 0.0, None
            for k, t in enumerate(b):
                if k in used:
                    continue
                r = difflib.SequenceMatcher(None, s["body"][:600], t["body"][:600]).quick_ratio()
                if r > best:
                    best, j = r, k
            if best < 0.5:
                j = None
        if j is None:
            lines.append(f"UNMATCHED original {s['env']} {s['label']} ({s['file']}:{s['line']}): {s['body'][:300]}")
            continue
        used.add(j)
        t = b[j]
        if s["body"] == t["body"]:
            lines.append(f"IDENTICAL {s['env']} {s['label']} -> {t['env']} {t['label']}")
        else:
            d = "\n".join(difflib.unified_diff(s["body"].split(". "), t["body"].split(". "), lineterm="", n=0))
            lines.append(f"CHANGED {s['env']} {s['label']} ({s['file']}:{s['line']}) -> {t['env']} {t['label']} ({t['file']}:{t['line']})\n{d}")
    for k, t in enumerate(b):
        if k not in used:
            lines.append(f"NEW in current {t['env']} {t['label']} ({t['file']}:{t['line']}): {t['body'][:300]}")
    return "\n\n".join(lines)


def source_diff(a: Path, b: Path) -> str:
    out = []
    fa = {str(p.relative_to(a)) for p in a.rglob("*") if p.is_file() and p.suffix in TEX_EXT}
    fb = {str(p.relative_to(b)) for p in b.rglob("*") if p.is_file() and p.suffix in TEX_EXT}
    for f in sorted(fa | fb):
        ta = (a / f).read_text(errors="ignore").split("\n") if f in fa else []
        tb = (b / f).read_text(errors="ignore").split("\n") if f in fb else []
        out.extend(difflib.unified_diff(ta, tb, fromfile=f"before/{f}", tofile=f"after/{f}", lineterm="", n=2))
    return "\n".join(out)


def deletions_only(a: Path, b: Path):
    """The passages removed from source tree `a` to give `b`, as (file, text) pairs, if `b` only deletes text: the same
    LaTeX files (the generated .bbl aside), each a token subsequence of its counterpart in `a` (tokens: control
    sequences, words, single other characters). None if `b` adds or changes anything."""
    tok = lambda p: re.findall(r"\\[A-Za-z@]+|\w+|\S", p.read_text(errors="ignore"))
    ext = TEX_EXT - {".bbl"}
    fa = {str(p.relative_to(a)) for p in a.rglob("*") if p.is_file() and p.suffix in ext}
    fb = {str(p.relative_to(b)) for p in b.rglob("*") if p.is_file() and p.suffix in ext}
    if fa != fb:
        return None
    removed = []
    for f in sorted(fa):
        ta, tb = tok(a / f), tok(b / f)
        it = iter(ta)
        if not all(t in it for t in tb):
            return None
        sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
        removed += [(f, " ".join(ta[i1:i2])) for op, i1, i2, _, _ in sm.get_opcodes() if op != "equal"]
    return removed


def chunk_text(txt: str, dst: Path, pages_per_chunk=10):
    dst.mkdir(parents=True, exist_ok=True)
    pages = re.split(r"(?=\n<<<PAGE \d+>>>\n)", txt)
    pages = [p for p in pages if p.strip()]
    for i in range(0, len(pages), pages_per_chunk):
        (dst / f"pages_{i + 1:03d}-{min(i + pages_per_chunk, len(pages)):03d}.txt").write_text("".join(pages[i:i + pages_per_chunk]))


def _groups(s, i, n):
    """Read n balanced {...} groups starting at index i of s; return (groups, end index) or (None, i)."""
    out = []
    for _ in range(n):
        while i < len(s) and s[i] in " \t\n":
            i += 1
        if i >= len(s) or s[i] != "{":
            return None, i
        depth, j = 0, i
        while j < len(s):
            depth += {"{": 1, "}": -1}.get(s[j], 0)
            if depth == 0:
                break
            j += 1
        out.append(s[i + 1:j])
        i = j + 1
    return out, i


def _page(x):
    x = x.strip()
    return int(x) if x.isdigit() else None


def parse_toc(toc: Path):
    """[(level, number, title, page)] from a .toc file (standard, amsart \\tocsection and \\numberline forms)."""
    if not toc.exists():
        return []
    s, out, i = toc.read_text(errors="ignore"), [], 0
    while True:
        i = s.find("\\contentsline", i)
        if i < 0:
            break
        g, i = _groups(s, i + len("\\contentsline"), 3)
        if not g:
            continue
        level, entry, page = g
        num, title = "", entry
        m = re.match(r"\s*\\toc\w+\s*", entry)
        if m:
            sub, _ = _groups(entry, m.end(), 3)
            if sub:
                num, title = sub[1], sub[2]
        else:
            m = re.match(r"\s*\\numberline\s*", entry)
            if m:
                sub, k = _groups(entry, m.end(), 1)
                if sub:
                    num, title = sub[0], entry[k:]
        title = re.sub(r"\s+", " ", re.sub(r"\\[a-zA-Z@]+\*?|[{}]", " ", title)).strip()
        out.append([level, num.strip(), title, _page(page)])
    return out


def parse_label_pages(aux: Path):
    """{label: page} from \\newlabel entries of an .aux file."""
    if not aux.exists():
        return {}
    s, out, i = aux.read_text(errors="ignore"), {}, 0
    while True:
        i = s.find("\\newlabel", i)
        if i < 0:
            break
        g, i = _groups(s, i + len("\\newlabel"), 2)
        if not g:
            continue
        inner, _ = _groups(g[1], 0, 2)
        if inner:
            pg = _page(inner[1])
            if pg is not None:
                out[g[0]] = pg
    return out


MAIN_ENVS = ("theorem", "thm", "maintheorem", "mainthm", "theoremA", "proposition", "corollary")


def structure_metrics(statements, build_rep):
    """Where the paper first states a main-type result, how long its introduction is, and where its sections start."""
    lp, toc = build_rep.get("label_pages", {}), build_rep.get("toc", [])
    secs = [e for e in toc if e[0] == "section" and e[3] is not None]
    first = None
    for s in statements:            # in source order (files sorted, then position)
        if s["env"].lower().rstrip("*") in MAIN_ENVS or s["env"].lower().startswith("main"):
            if s.get("label") and s["label"] in lp:
                first = {"env": s["env"], "label": s["label"], "page": lp[s["label"]]}
                break
    intro_end = None
    if len(secs) >= 2:
        intro_end = max(secs[1][3] - 1, secs[0][3])
    return {"pages": build_rep.get("pages"), "first_main_type_statement": first,
            "intro_first_page": secs[0][3] if secs else None, "intro_last_page": intro_end,
            "sections": [{"number": e[1], "title": e[2], "page": e[3]} for e in secs]}


def inventory(src: Path, statements, build_rep) -> str:
    """A finding aid for reviewers: macros, theorem-like environments with labels and pages, section starts."""
    lp = build_rep.get("label_pages", {})
    L = ["# Inventory (built by script; a finding aid, not a judgment)", "", "## Sections", ""]
    L += [f"- {e[1]} {e[2]} — p. {e[3]}" for e in build_rep.get("toc", []) if e[0] in ("section", "subsection")]
    L += ["", "## Theorem-like environments", ""]
    for s in statements:
        pg = lp.get(s["label"]) if s.get("label") else None
        L.append(f"- {s['env']}{' [' + s['title'] + ']' if s['title'] else ''} `{s['label'] or '(no label)'}`"
                 f" — {s['file']}:{s['line']}" + (f", p. {pg}" if pg else ""))
    L += ["", "## Macros defined in the source", ""]
    pat = re.compile(r"\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z@]+)\}?|\\DeclareMathOperator\*?\s*\{\\([A-Za-z]+)\}"
                     r"|\\def\\([A-Za-z@]+)")
    for p in sorted(src.rglob("*.tex")):
        lines = p.read_text(errors="ignore").split("\n")
        for i, ln in enumerate(lines, 1):
            for m in pat.finditer(ln):
                name = next(g for g in m.groups() if g)
                L.append(f"- `\\{name}` — {p.relative_to(src)}:{i}: `{ln.strip()[:140]}`")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# Deterministic detectors. They do not judge mathematics; they make sure the model checkers look at every place where
# something can have been lost or added, and they let the run measure whether those checkers catch planted defects.

SCOPE_MARK = re.compile(r"\b(not|no|only|without|neither|nor|need not|requires?|independent|noncanonical|canonical|"
                        r"unless|except|provided)\b", re.I)
REASON_MARK = re.compile(r"\b(hence|thus|therefore|since|because|implies|it follows|so that|we obtain|we get|gives|"
                         r"by (?:lemma|theorem|proposition|corollary|\\ref|\\cite|construction|definition)|follows from)\b", re.I)
MATH_MARK = re.compile(r"\$|\\\[|\\\(|\\begin\{(?:equation|align|gather|multline|eqnarray|displaymath)")


def _body(src: Path):
    """[(file, start_line, raw_paragraph)] for every paragraph after \\begin{document}, files in sorted order."""
    out = []
    for p in sorted(src.rglob("*.tex")):
        text = p.read_text(errors="ignore")
        lines = text.split("\n")
        start = 0
        for i, ln in enumerate(lines):
            if "\\begin{document}" in ln:
                start = i + 1
                break
        buf, first = [], None
        for i in range(start, len(lines) + 1):
            ln = lines[i] if i < len(lines) else ""
            if ln.strip() == "" or i == len(lines):
                if buf:
                    out.append((str(p.relative_to(src)), first + 1, "\n".join(buf)))
                buf, first = [], None
            else:
                if first is None:
                    first = i
                buf.append(ln)
    return out


def _sentences(src: Path):
    t = " ".join(par for _, _, par in _body(src))
    t = re.sub(r"\s+", " ", t)
    return [s.strip() for s in re.split(r"(?<=[.;:])\s+(?=[A-Z\\])", t) if len(s.strip()) > 20]


def _letters(s):
    return re.sub(r"[^a-z ]", "", s.lower())


def scope_losses(orig: Path, cand: Path, threshold=0.6):
    """Sentences of the original that limit or qualify something (contain 'not', 'only', 'without', ...) and have no
    close counterpart in the candidate. Each is a candidate loss that the fidelity checker must rule on."""
    cs = [(_letters(s), s) for s in _sentences(cand)]
    out = []
    for s in _sentences(orig):
        if not SCOPE_MARK.search(s):
            continue
        ls = _letters(s)
        best, bs = 0.0, ""
        for lc, c in cs:
            m = difflib.SequenceMatcher(None, ls, lc, autojunk=False)
            if m.real_quick_ratio() <= best or m.quick_ratio() <= best:
                continue
            r = m.ratio()
            if r > best:
                best, bs = r, c
        reason = None
        if best < threshold:
            reason = "no close counterpart"
        else:
            # a near-identical sentence can still have lost exactly its qualifying clause
            m = SCOPE_MARK.search(s)
            clause = re.split(r"[,;.:]", s[m.start():])[0]
            q = _letters(" ".join(clause.split()[:12]))
            lb = _letters(bs)
            if len(q) >= 12 and q not in lb:
                lm = difflib.SequenceMatcher(None, q, lb, autojunk=False).find_longest_match(0, len(q), 0, len(lb))
                if lm.size < 0.8 * len(q):
                    reason = f"closest sentence lacks the qualifying clause '{clause[:80]}'"
        if reason:
            out.append({"id": f"Q{len(out) + 1}", "original": s[:500], "closest_in_current": bs[:500],
                        "similarity": round(best, 2), "reason": reason})
    return out


DISPLAY_ENV = re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray)(\*?)\}(.*?)\\end\{\1\2\}", re.S)


def lost_displays(orig: Path, cand: Path):
    """Labelled displays of the original (formulas, computations) whose label and whose content are both absent from the
    candidate. Each is a candidate loss of mathematical content that the fidelity checker must rule on; a display that
    was only renumbered or reworded will be ruled kept."""
    cand_src = " ".join(f.read_text(errors="ignore") for f in sorted(Path(cand).rglob("*.tex")))
    labels = set(re.findall(r"\\label\{([^}]+)\}", cand_src))
    flat = re.sub(r"\s+", "", cand_src)
    out = []
    for f in sorted(Path(orig).rglob("*.tex")):
        for m in DISPLAY_ENV.finditer(f.read_text(errors="ignore")):
            lab = re.search(r"\\label\{([^}]+)\}", m.group(3))
            if not lab or lab.group(1) in labels:
                continue
            body = re.sub(r"\s+", "", re.sub(r"\\label\{[^}]*\}", "", m.group(3)))
            if body[:40] and body[:40] in flat:
                continue
            out.append({"id": f"D{len(out) + 1}", "label": lab.group(1), "display": _norm(m.group(0))[:400]})
    return out


def unmatched_statements(a, b):
    """Theorem-like statements of the original (`a`) without a counterpart in `b` (same matching as match_statements)."""
    used, out = set(), []
    bylab = {s["label"]: i for i, s in enumerate(b) if s["label"]}
    for s in a:
        j = bylab.get(s["label"]) if s["label"] else None
        if j is None:
            best = 0.0
            for k, t in enumerate(b):
                if k in used:
                    continue
                r = difflib.SequenceMatcher(None, s["body"][:600], t["body"][:600]).quick_ratio()
                if r > best:
                    best, j = r, k
            if best < 0.5:
                j = None
        if j is None:
            out.append({"id": f"S{len(out) + 1}", "env": s["env"], "label": s["label"], "location": f"{s['file']}:{s['line']}",
                        "statement": s["body"][:600]})
        else:
            used.add(j)
    return out


def _proof_lines(src: Path):
    """{(file, line)} inside proof environments, and lines of paragraphs with displayed mathematics after the first
    \\section (derivations written in running text)."""
    out = set()
    for p in sorted(src.rglob("*.tex")):
        rel = str(p.relative_to(src))
        lines = p.read_text(errors="ignore").split("\n")
        for s, e in _envs_spans(lines, {"proof"}):
            out |= {(rel, i + 1) for i in range(s, e + 1)}
    return out


DISPLAY = re.compile(r"\\\[|\\begin\{(?:equation|align|gather|multline|eqnarray|displaymath)")


def changed_regions(orig: Path, prev, cand: Path, threshold=0.92):
    """Proof passages of the candidate that were rewritten or expanded: paragraphs inside proofs (or displayed
    derivations after the introduction) that are not identical to a paragraph of the previous version (if given) and
    not nearly identical to any paragraph of the original. A paragraph that was only moved matches the original
    somewhere and is skipped, so restructuring costs no checking."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    prev_set = {norm(p) for _, _, p in _body(prev)} if prev else set()
    orig_pars = [norm(p) for _, _, p in _body(orig)]
    in_proof = _proof_lines(cand)
    first_section = {}
    for p in sorted(cand.rglob("*.tex")):
        ls = p.read_text(errors="ignore").split("\n")
        secs = [i + 1 for i, l in enumerate(ls) if re.match(r"\s*\\section\*?\{", l)]
        first_section[str(p.relative_to(cand))] = secs[1] if len(secs) > 1 else (secs[0] if secs else 0)
    out = []
    for f, line, par in _body(cand):
        n = norm(par)
        if len(n) < 40:
            continue
        span = range(line, line + par.count("\n") + 1)
        proofish = any((f, i) in in_proof for i in span) or (DISPLAY.search(par) and line >= first_section.get(f, 0))
        if not proofish or n in prev_set:
            continue
        if any(difflib.SequenceMatcher(None, n, o, autojunk=False).real_quick_ratio() >= threshold
               and difflib.SequenceMatcher(None, n, o, autojunk=False).ratio() >= threshold for o in orig_pars):
            continue
        out.append({"id": f"R{len(out) + 1}", "file": f, "start_line": line, "end_line": line + par.count("\n"),
                    "text": par[:1500]})
    return out


# ---- planted defects (canaries) -------------------------------------------------------------------------------
_REL_NUM = re.compile(r"(\\geq?|\\leq?|(?<![\\\w])[<>])(\s*)(\d+)")
_REL_SWAP = re.compile(r"\\(le|ge|leq|geq)(?![a-zA-Z])")
_CITE_LOC = re.compile(r"(\\cite\[[^\]]*?)(\d+)(\][^{]*\{)")


def _envs_spans(lines, names):
    """(start, end) line indices of environments whose name is in `names` (case-insensitive base name)."""
    spans, stack = [], []
    pat = re.compile(r"\\(begin|end)\{([A-Za-z*]+)\}")
    for i, ln in enumerate(lines):
        for m in pat.finditer(ln):
            base = m.group(2).rstrip("*").lower()
            if base not in names:
                continue
            if m.group(1) == "begin":
                stack.append((base, i))
            elif stack:
                b, s = stack.pop()
                spans.append((s, i))
    return spans


_SUB_DIGIT = re.compile(r"([_^])(\{?)(\d)(\}?)")


def plant_canaries(src: Path, dst: Path, statement_envs, prefer=None):
    """Copy `src` to `dst` and plant up to three defects of kinds a fidelity check or audit must catch:
    a changed constant in a theorem-like statement, a reversed inequality inside a proof, and a changed locator in a
    citation inside a proof. `prefer` is a set of (file, line) pairs (lines of passages the rewrite added); the
    inequality is planted there when possible, so that the audit of additions is tested and not only the fidelity
    check. Returns the list of plantings (file, line, before, after)."""
    copy_source(src, dst)
    plants, used = [], set()
    files = sorted(dst.rglob("*.tex"))
    envs = {e.lower() for e in statement_envs} - {"definition", "remark", "example", "conjecture", "notation"}

    def edit(kind, p, lines, i, new):
        plants.append({"kind": kind, "file": str(p.relative_to(dst)), "line": i + 1, "before": lines[i], "after": new})
        lines[i] = new
        used.add((p, i))
        p.write_text("\n".join(lines))

    def safe(ln):
        return not re.search(r"\\(label|ref|eqref|cite|input|include|usepackage)\b", ln)

    for kind in ("statement_constant", "proof_inequality", "citation_locator"):
        done = False
        for p in files:
            lines = p.read_text(errors="ignore").split("\n")
            spans = _envs_spans(lines, envs) if kind == "statement_constant" else _envs_spans(lines, {"proof"})
            # prefer the middle of the paper: a defect on its first line is too easy to stumble on
            spans = sorted(spans, key=lambda s: abs(s[0] - len(lines) // 2))
            rel = str(p.relative_to(dst))
            order = []
            for s, e in spans:
                order += list(range(s, e + 1))
            if prefer and kind == "proof_inequality":
                order = [i for i in order if (rel, i + 1) in prefer] + [i for i in order if (rel, i + 1) not in prefer]
            for s, e in [(i, i) for i in order]:
                for i in range(s, e + 1):
                    if (p, i) in used:
                        continue
                    ln = lines[i]
                    if kind == "statement_constant" and safe(ln):
                        m = _REL_NUM.search(ln)
                        if m:
                            new = ln[:m.start(3)] + str(int(m.group(3)) + 1) + ln[m.end(3):]
                            edit(kind, p, lines, i, new); done = True; break
                        m = _SUB_DIGIT.search(ln)          # e.g. E_3 -> E_4, Pois_n^+ index, R^2 -> R^3
                        if m:
                            new = ln[:m.start(3)] + str((int(m.group(3)) + 1) % 10) + ln[m.end(3):]
                            edit(kind, p, lines, i, new); done = True; break
                        m = _REL_SWAP.search(ln)
                        if m:
                            swap = {"le": "ge", "ge": "le", "leq": "geq", "geq": "leq"}[m.group(1)]
                            new = ln[:m.start()] + "\\" + swap + ln[m.end():]
                            edit(kind, p, lines, i, new); done = True; break
                    elif kind == "proof_inequality" and safe(ln):
                        m = _REL_SWAP.search(ln)
                        if m:
                            swap = {"le": "ge", "ge": "le", "leq": "geq", "geq": "leq"}[m.group(1)]
                            new = ln[:m.start()] + "\\" + swap + ln[m.end():]
                            edit(kind, p, lines, i, new); done = True; break
                    elif kind == "citation_locator":
                        m = _CITE_LOC.search(ln)
                        if m:
                            new = ln[:m.start(2)] + str(int(m.group(2)) + 1) + ln[m.end(2):]
                            edit(kind, p, lines, i, new); done = True; break
                if done:
                    break
            if done:
                break
    return plants


def rendered_changes(txt_a: str, txt_b: str):
    """Lines of rendering b that differ from rendering a (whitespace-normalised)."""
    a = [re.sub(r"\s+", " ", l).strip() for l in txt_a.splitlines()]
    b = [re.sub(r"\s+", " ", l).strip() for l in txt_b.splitlines()]
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            out += [l for l in b[j1:j2] if len(l) > 8]
    return out


def canary_detected(plant, findings, rendered):
    """Whether any finding points at a planted defect: by a quotation overlapping the changed source line or the
    changed rendered line, or by a location naming the line (±3)."""
    norm = lambda s: re.sub(r"\s+", " ", s or "").strip()
    src_line = norm(plant["after"])
    for f in findings:
        for q in (f.get("quote"), f.get("quote_current")):
            q = norm(q)
            if len(q) < 12:
                continue
            if q in src_line or src_line[:60] in q or any(q in r or (len(r) > 20 and r[:40] in q) for r in rendered):
                return True
        loc = " ".join(str(f.get(k, "")) for k in ("current_loc", "location"))
        for m in re.finditer(r"(\d+)(?:\s*[-–]\s*(\d+))?", loc):
            lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
            if plant["file"].split("/")[-1].split(".")[0] in loc and hi - lo <= 12 and lo - 3 <= plant["line"] <= hi + 3:
                return True
    return False


# ---- text copied from the reference papers ---------------------------------------------------------------------
def _words(t):
    return re.findall(r"[a-z]+", t.lower())


def ngram_hashes(words, n):
    return {hash(" ".join(words[i:i + n])) for i in range(max(0, len(words) - n + 1))}


def copied_phrases(orig_text, cand_text, ref_index, n=12, limit=30):
    """Passages of at least n words that the candidate shares with a reference text but not with the original.
    `ref_index` maps n-gram hash -> reference key (see ref_ngram_index)."""
    ow = ngram_hashes(_words(orig_text), n)
    cw = _words(cand_text)
    spans, cur = [], None
    for i in range(max(0, len(cw) - n + 1)):
        h = hash(" ".join(cw[i:i + n]))
        if h in ref_index and h not in ow:
            if cur and i <= cur[1]:
                cur[1] = i + n
            else:
                if cur:
                    spans.append(cur)
                cur = [i, i + n, ref_index[h]]
        elif cur and i > cur[1]:
            spans.append(cur); cur = None
    if cur:
        spans.append(cur)
    return [{"text": " ".join(cw[s:e]), "reference": k, "words": e - s} for s, e, k in spans[:limit]]


def ref_ngram_index(ref_texts, n=12):
    idx = {}
    for key, t in ref_texts.items():
        w = _words(t)
        for i in range(max(0, len(w) - n + 1)):
            idx.setdefault(hash(" ".join(w[i:i + n])), key)
    return idx



# ---- bibliography entries the revision adds -----------------------------------------------------------------------
def bib_entries(src: Path):
    """{key: text} for \\bibitem entries and @entries of .bib files under src."""
    out = {}
    for p in sorted(src.rglob("*.tex")) + sorted(src.rglob("*.bbl")):
        t = p.read_text(errors="ignore")
        for m in re.finditer(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\}|\Z)", t, re.S):
            out.setdefault(m.group(1).strip(), re.sub(r"\s+", " ", m.group(2)).strip())
    for p in sorted(src.rglob("*.bib")):
        t = p.read_text(errors="ignore")
        for m in re.finditer(r"@\w+\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n@|\Z)", t, re.S):
            out.setdefault(m.group(1).strip(), re.sub(r"\s+", " ", m.group(2)).strip())
    return out


def new_bib_entries(orig: Path, cand: Path, manifest_entries):
    """Bibliography entries of the candidate that are not in the original, each matched against the reference bundle
    by title. An entry with no bundle paper behind it is a citation nobody has checked (hard rule R7)."""
    o, c = bib_entries(orig), bib_entries(cand)
    words = lambda s: set(re.findall(r"[a-z]{3,}", re.sub(r"\\[a-zA-Z]+", " ", s.lower())))
    out = []
    for key, text in c.items():
        if key in o:
            continue
        tw = words(text)
        best, bkey = 0.0, None
        for e in manifest_entries:
            mw = words(e.get("title", ""))
            if mw:
                r = len(mw & tw) / len(mw)
                if r > best:
                    best, bkey = r, e.get("key")
        out.append({"key": key, "entry": text[:400], "bundle_match": bkey if best >= 0.7 else None,
                    "title_overlap": round(best, 2)})
    return out
