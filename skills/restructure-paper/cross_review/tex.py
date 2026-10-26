"""LaTeX helpers, copied from the readability lab (`readability_lab/tex.py`): find the root file, copy and build a source,
render text with page markers, and list the passages where two sources differ. Standard library only, plus latexmk and
pdftotext."""
import difflib, re, shutil, subprocess, tempfile
from pathlib import Path

TEX_EXT = {".tex", ".sty", ".cls", ".bib", ".bbl", ".bst"}
JUNK = {".aux", ".log", ".out", ".fls", ".fdb_latexmk", ".toc", ".blg", ".gz", ".brf"}
NOT_SOURCE = {"notes.md", "report.md"}          # records an editing step may leave next to the source


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


def copy_source(src: Path, dst: Path, skip_file=None):
    """Copy a source tree without build products or editing records (nor files for which `skip_file(path)` holds)."""
    if dst.exists():
        shutil.rmtree(dst)

    def ign(d, names):
        names_set = set(names)
        skip = [n for n in names if Path(n).suffix in JUNK or n in ("_tmp", "__pycache__", "_done") or n in NOT_SOURCE]
        if skip_file:
            skip += [n for n in names if skip_file(Path(d) / n)]
        # a PDF is a build product only if a .tex file with the same stem sits next to it
        skip += [n for n in names if n.endswith(".pdf") and (Path(n).stem + ".tex") in names_set]
        return skip
    shutil.copytree(src, dst, ignore=ign)


def paged_text(pdf: Path) -> str:
    raw = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True,
                         errors="replace").stdout
    out = []
    for i, page in enumerate(raw.split("\f"), 1):
        if page.strip():
            out.append(f"\n<<<PAGE {i}>>>\n{page}")
    return "".join(out)


def build(src: Path, main: str, out_dir: Path, timeout=900) -> dict:
    """Compile a copy of src; write out_dir/render.pdf and render.txt; return a build report."""
    rep = {"pdf": False, "undefined_refs": [], "undefined_cites": [], "pages": 0, "log_tail": ""}
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        t = Path(td) / "b"
        copy_source(src, t)
        main_dir = (t / main).parent
        try:
            r = subprocess.run(["latexmk", "-norc", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                                Path(main).name], cwd=main_dir, capture_output=True, text=True, errors="replace",
                               timeout=timeout)
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
        shutil.copy(pdf, out_dir / "render.pdf")
        txt = paged_text(pdf)
        (out_dir / "render.txt").write_text(txt)
        rep["pages"] = txt.count("<<<PAGE ")
        rep["pdf"] = True
    return rep


# ---------------------------------------------------------------------- differences between two sources
_COMMENT = re.compile(r"(?<!\\)%.*$")
_HEADING = re.compile(r"\\(?:sub)*section\*?\{([^}]*)\}")


def _paragraphs(src: Path):
    """(file, heading, paragraph) for every blank-line-separated paragraph of every .tex file, comments removed."""
    out = []
    for p in sorted(src.rglob("*.tex")):
        heading = ""
        lines = [_COMMENT.sub("", l).rstrip() for l in p.read_text(errors="ignore").split("\n")]
        for para in re.split(r"\n\s*\n", "\n".join(lines)):
            para = para.strip()
            if not para:
                continue
            for m in _HEADING.finditer(para):
                heading = m.group(1)
            out.append((str(p.relative_to(src)), heading, para))
    return out


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def differences(a: Path, b: Path, labels=("X", "Y")):
    """The passages where sources a and b differ, as a list of {where, a, b} (paragraph level)."""
    pa, pb = _paragraphs(a), _paragraphs(b)
    sm = difflib.SequenceMatcher(a=[_norm(x[2]) for x in pa], b=[_norm(x[2]) for x in pb], autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        ref = pa[i1] if i1 < len(pa) else (pb[j1] if j1 < len(pb) else pa[-1])
        where = f"{ref[0]}" + (f", in “{ref[1]}”" if ref[1] else "")
        out.append({"where": where, "a": "\n\n".join(x[2] for x in pa[i1:i2]),
                    "b": "\n\n".join(x[2] for x in pb[j1:j2])})
    return out


def differences_md(diffs, labels=("X", "Y")):
    if not diffs:
        return "The two sources do not differ.\n"
    parts = [f"# Passages where the sources differ ({len(diffs)})\n"]
    for n, d in enumerate(diffs, 1):
        parts.append(f"## Difference {n} ({d['where']})\n\n**{labels[0]}:**\n\n{d['a'] or '(nothing)'}\n\n"
                     f"**{labels[1]}:**\n\n{d['b'] or '(nothing)'}\n")
    return "\n".join(parts)


def words(s):
    """Approximate word count of LaTeX text: commands, maths and braces removed."""
    s = re.sub(r"\\(?:cite|ref|eqref|cref|Cref|label|autoref)\*?(\[[^\]]*\])?\{[^}]*\}", " ", s)
    s = re.sub(r"\$[^$]*\$|\\\(.*?\\\)|\\\[.*?\\\]", " x ", s, flags=re.S)
    s = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", s)
    return len(re.findall(r"[A-Za-z][A-Za-z'’-]*", s))
