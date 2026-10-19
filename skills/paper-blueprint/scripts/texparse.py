"""Mechanical extraction of a dependency skeleton from LaTeX sources.

Finds theorem-like environments, their proofs, labels and cross-references,
and reproduces LaTeX numbering (exactly when a .aux file is present,
approximately otherwise).  Output is a plain dict, see ``extract_tex``.
"""
from __future__ import annotations

import bisect
import os
import re

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

KIND_WORDS = [
    "theorem", "lemma", "proposition", "corollary", "definition", "claim",
    "conjecture", "assumption", "hypothesis", "fact", "observation", "remark",
    "example", "notation", "problem", "question", "exercise", "axiom",
    "construction", "condition", "convention", "setting", "property",
    "principle", "criterion", "note", "algorithm", "statement", "result",
]
ENV_ABBREV = {
    "thm": "theorem", "theo": "theorem", "thrm": "theorem", "mainthm": "theorem",
    "maintheorem": "theorem", "lem": "lemma", "lemm": "lemma", "lma": "lemma",
    "prop": "proposition", "pro": "proposition", "prp": "proposition",
    "cor": "corollary", "coro": "corollary", "corr": "corollary",
    "defn": "definition", "def": "definition", "defi": "definition",
    "dfn": "definition", "defin": "definition", "conj": "conjecture",
    "rem": "remark", "rmk": "remark", "rmrk": "remark", "ex": "example",
    "exa": "example", "exm": "example", "expl": "example", "clm": "claim",
    "cl": "claim", "ass": "assumption", "asm": "assumption", "assm": "assumption",
    "assump": "assumption", "hyp": "hypothesis", "obs": "observation",
    "nota": "notation", "notn": "notation", "prob": "problem", "prb": "problem",
    "qn": "question", "ques": "question", "exer": "exercise", "exc": "exercise",
    "ax": "axiom", "fct": "fact", "cons": "construction", "cond": "condition",
    "conv": "convention",
}
KIND_PREFIX = {
    "theorem": "thm", "lemma": "lem", "proposition": "prop", "corollary": "cor",
    "definition": "def", "claim": "claim", "conjecture": "conj", "assumption": "asm",
    "hypothesis": "hyp", "fact": "fact", "observation": "obs", "remark": "rem",
    "example": "ex", "notation": "not", "problem": "prob", "question": "q",
    "exercise": "exer", "axiom": "ax",
}
# Kinds drawn as boxes (definitions in the Lean-blueprint convention).
DEFINITION_KINDS = {
    "definition", "notation", "assumption", "hypothesis", "axiom",
    "construction", "condition", "convention", "setting", "algorithm",
}
# Kinds that are shown only when some other node refers to them.
HIDDEN_KINDS = {"remark", "example", "note", "exercise", "question", "problem"}

# Environments whose names look like kinds but are floats/lists unless declared by \newtheorem.
NOT_THEOREM_ENVS = {"algorithm", "algorithm2e", "algorithmic", "problem*", "example*", "note",
                    "statement", "result", "property", "setting", "condition", "ex", "def",
                    "cl", "pro", "rem", "cons", "conv", "cond", "ass"}
PROOF_ENVS = {"proof", "proof*", "pf", "pf*", "proofof", "myproof", "subproof"}
SINGLE_EQ_ENVS = {"equation", "multline", "dmath"}
MULTI_EQ_ENVS = {"align", "gather", "flalign", "alignat", "eqnarray", "xalignat"}
SECTION_LEVELS = {"part": 0, "chapter": 1, "section": 2, "subsection": 3,
                  "subsubsection": 4}

REF_CMDS = ("ref|eqref|cref|Cref|autoref|Autoref|vref|Vref|cpageref|Cpageref|"
            "labelcref|nameref|Nameref|pageref|vpageref|thmref|Thmref|subref|"
            "uses|proves")
RANGE_CMDS = "crefrange|Crefrange|cpagerefrange|Cpagerefrange"

TOKEN_RE = re.compile(
    r"\\begin\s*\{(?P<benv>[^}]+)\}"
    r"|\\end\s*\{(?P<eenv>[^}]+)\}"
    r"|\\(?P<sec>part|chapter|section|subsection|subsubsection)(?P<secstar>\*?)(?![A-Za-z])"
    r"|\\(?P<appendix>appendix)(?![A-Za-z])"
    r"|\\label\s*\{(?P<label>[^}]*)\}"
    r"|\\(?P<refcmd>" + REF_CMDS + r")\*?\s*\{(?P<refargs>[^}]*)\}"
    r"|\\(?P<rangecmd>" + RANGE_CMDS + r")\*?\s*\{(?P<r1>[^}]*)\}\s*\{(?P<r2>[^}]*)\}"
    r"|\\hyperref\s*\[(?P<hlabel>[^\]]*)\]"
    r"|\\(?P<citecmd>cite|citep|citet|citealp|citealt|Cite|Citep|Citet|parencite|textcite|autocite|"
    r"footcite|cites)\*?(?:\s*\[[^\]]*\]){0,2}\s*\{(?P<citekeys>[^}]*)\}"
)


# ---------------------------------------------------------------------------
# Small parsing helpers (shared with latex2html)
# ---------------------------------------------------------------------------

def skip_ws(s: str, i: int) -> int:
    n = len(s)
    while i < n and s[i] in " \t\r\n":
        i += 1
    return i


def read_group(s: str, i: int, open_ch: str = "{", close_ch: str = "}"):
    """If s[i:] (after whitespace) starts with open_ch, return (content, end).

    Handles nesting and backslash-escaped delimiters.  Returns (None, i) if
    there is no group at i.
    """
    j = skip_ws(s, i)
    if j >= len(s) or s[j] != open_ch:
        return None, i
    depth = 0
    k = j
    n = len(s)
    while k < n:
        c = s[k]
        if c == "\\":
            k += 2
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return s[j + 1:k], k + 1
        elif open_ch == "[" and c == "{":
            # brackets inside braces do not count: skip the brace group
            _, k2 = read_group(s, k)
            if k2 > k:
                k = k2
                continue
        k += 1
    return None, i


def read_optional(s: str, i: int):
    return read_group(s, i, "[", "]")


def strip_comments(text: str) -> str:
    out = []
    for line in text.split("\n"):
        start = 0
        while True:
            j = line.find("%", start)
            if j < 0:
                out.append(line)
                break
            k, bs = j - 1, 0
            while k >= 0 and line[k] == "\\":
                bs += 1
                k -= 1
            if bs % 2 == 0:
                out.append(line[:j])
                break
            start = j + 1
    return "\n".join(out)


def blank_out(text: str, start: int, end: int) -> str:
    """Replace text[start:end] by spaces, keeping newlines (offsets survive)."""
    chunk = "".join("\n" if c == "\n" else " " for c in text[start:end])
    return text[:start] + chunk + text[end:]


def split_top_level(body: str, sep: str = r"\\") -> list[str]:
    r"""Split an align-like body on ``\\`` at brace/environment depth zero."""
    parts, depth, env_depth, last, i, n = [], 0, 0, 0, 0, len(body)
    while i < n:
        c = body[i]
        if c == "\\":
            if body.startswith(sep, i) and depth == 0 and env_depth == 0:
                parts.append(body[last:i])
                i += len(sep)
                last = i
                continue
            if body.startswith("\\begin", i):
                env_depth += 1
            elif body.startswith("\\end", i):
                env_depth -= 1
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    parts.append(body[last:])
    return parts


def kind_from_name(env: str, display: str | None = None) -> str:
    """Map an environment name / display name to a canonical kind."""
    if display:
        low = display.lower()
        for w in KIND_WORDS:
            if re.search(r"\b" + w, low):
                return w
    base = env.rstrip("*").lower()
    if base in KIND_WORDS:
        return base
    if base in ENV_ABBREV:
        return ENV_ABBREV[base]
    for w in KIND_WORDS:
        if base.startswith(w) or base.endswith(w):
            return w
    for ab, w in sorted(ENV_ABBREV.items(), key=lambda kv: -len(kv[0])):
        if len(ab) >= 3 and (base.startswith(ab) or base.endswith(ab)):
            return w
    return "statement"


def to_alpha(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s or "0"


def clean_text_snippet(s: str, limit: int = 600) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + " …"
    return s


# ---------------------------------------------------------------------------
# Source loading (\input expansion with offset -> file:line mapping)
# ---------------------------------------------------------------------------

INPUT_RE = re.compile(
    r"\\(?P<cmd>input|include|subfile)\s*\{(?P<f>[^}]*)\}"
    r"|\\(?P<cmd2>import|subimport|inputfrom|subinputfrom)\*?\s*\{(?P<d>[^}]*)\}\s*\{(?P<f2>[^}]*)\}"
)


class Source:
    def __init__(self, main_path: str):
        self.main_path = os.path.abspath(main_path)
        self.root = os.path.dirname(self.main_path)
        self.segments: list[tuple[int, str, int]] = []  # (offset, file, line)
        self.files: list[str] = []
        pieces: list[tuple[str, str, int]] = []
        self._expand(self.main_path, self.root, pieces, [])
        text, off = [], 0
        for chunk, f, line in pieces:
            self.segments.append((off, f, line))
            text.append(chunk)
            off += len(chunk)
        self.text = "".join(text)
        self._starts = [s[0] for s in self.segments]

    def _resolve(self, name: str, base: str) -> str | None:
        name = name.strip()
        if not name:
            return None
        for cand in (name, name + ".tex"):
            for b in (base, self.root):
                p = os.path.normpath(os.path.join(b, cand))
                if os.path.isfile(p) and (p.endswith(".tex") or "." not in os.path.basename(p)):
                    return p
        return None

    def _expand(self, path: str, base: str, pieces: list, stack: list):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
        except OSError:
            return
        if path not in self.files:
            self.files.append(path)
        text = strip_comments(raw)
        rel = os.path.relpath(path, self.root)
        pos, line = 0, 1
        for m in INPUT_RE.finditer(text):
            before = text[pos:m.start()]
            pieces.append((before, rel, line))
            line += before.count("\n")
            if m.group("cmd"):
                target = self._resolve(m.group("f"), base)
                newbase = base
            else:
                d = m.group("d")
                newbase = os.path.join(base if m.group("cmd2").startswith("sub") else self.root, d)
                target = self._resolve(os.path.join(d, m.group("f2")), base) or \
                    self._resolve(m.group("f2"), newbase)
            if target and target not in stack and len(stack) < 30:
                self._expand(target, newbase if not m.group("cmd") else os.path.dirname(target),
                             pieces, stack + [path])
                pieces.append(("\n", rel, line))
            else:
                pieces.append((m.group(0), rel, line))
            line += m.group(0).count("\n")
            pos = m.end()
        pieces.append((text[pos:], rel, line))

    def locate(self, offset: int) -> dict:
        i = bisect.bisect_right(self._starts, offset) - 1
        if i < 0:
            return {"file": os.path.basename(self.main_path), "line": 1}
        start, f, line = self.segments[i]
        return {"file": f, "line": line + self.text.count("\n", start, offset)}


def find_main_tex(path: str) -> str:
    """Accept a .tex file or a directory; return the main .tex file."""
    if os.path.isfile(path):
        return path
    cands = []
    for dirpath, _, files in os.walk(path):
        for fn in files:
            if fn.endswith(".tex"):
                p = os.path.join(dirpath, fn)
                try:
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        t = strip_comments(fh.read())
                except OSError:
                    continue
                if ("\\documentclass" in t or "\\documentstyle" in t) and "\\begin{document}" in t:
                    score = len(INPUT_RE.findall(t)) + len(re.findall(r"\\begin\{", t)) / 100
                    if fn in ("main.tex", "paper.tex", "ms.tex"):
                        score += 5
                    cands.append((score, -p.count(os.sep), p))
    if not cands:
        raise SystemExit(f"no main .tex file (with \\documentclass or \\documentstyle) found under {path}")
    cands.sort(reverse=True)
    return cands[0][2]


# ---------------------------------------------------------------------------
# Preamble: theorem declarations and macros
# ---------------------------------------------------------------------------

def split_commas(s: str) -> list[str]:
    """Split on commas at brace depth zero."""
    parts, depth, last = [], 0, 0
    for i, c in enumerate(s):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(s[last:i])
            last = i + 1
    parts.append(s[last:])
    return parts


def parse_kv(s: str) -> dict:
    out = {}
    for part in split_commas(s or ""):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v.strip().strip("{}")
        elif part.strip():
            out[part.strip().lower()] = True
    return out


def parse_theorem_decls(text: str) -> tuple[dict, dict, dict]:
    """Return (envs, counter_alias, numberwithin).

    envs[env] = {display, counter, within, numbered, style, kind}
    """
    envs: dict[str, dict] = {}
    alias: dict[str, str] = {}
    within: dict[str, str] = {}
    style = "plain"
    pat = re.compile(
        r"\\theoremstyle\s*\{(?P<style>[^}]*)\}"
        r"|\\(?P<cmd>newtheorem|spnewtheorem|newmdtheoremenv|newtheoremrep)(?P<star>\*?)(?![A-Za-z])"
        r"|\\declaretheorem(?![A-Za-z])"
        r"|\\newaliascnt\s*\{(?P<a1>[^}]*)\}\s*\{(?P<a2>[^}]*)\}"
        r"|\\(?:numberwithin|counterwithin)\*?\s*\{(?P<n1>[^}]*)\}\s*\{(?P<n2>[^}]*)\}"
    )
    for m in pat.finditer(text):
        if m.group("style") is not None:
            style = m.group("style").strip()
            continue
        if m.group("a1") is not None:
            alias[m.group("a1").strip()] = m.group("a2").strip()
            continue
        if m.group("n1") is not None:
            within[m.group("n1").strip()] = m.group("n2").strip()
            continue
        i = m.end()
        if m.group("cmd"):
            if m.group("cmd") == "newmdtheoremenv":
                _, i = read_optional(text, i)
            env, i = read_group(text, i)
            if env is None:
                continue
            shared, i = read_optional(text, i)
            display, i = read_group(text, i)
            parent, i = read_optional(text, i)
            env = env.strip()
            envs[env] = {
                "display": (display or env).strip(),
                "counter": (shared or env).strip(),
                "within": parent.strip() if parent else None,
                "numbered": not m.group("star"),
                "style": style,
            }
        else:  # \declaretheorem[opts]{env}
            opts, i = read_optional(text, i)
            env, i = read_group(text, i)
            if env is None:
                continue
            kv = parse_kv(opts or "")
            env = env.strip()
            for e in [x.strip() for x in env.split(",") if x.strip()]:
                envs[e] = {
                    "display": kv.get("name") or kv.get("title") or e.capitalize(),
                    "counter": kv.get("sibling") or kv.get("sharenumber") or kv.get("numberlike") or e,
                    "within": kv.get("numberwithin") or kv.get("parent") or kv.get("within"),
                    "numbered": str(kv.get("numbered", "yes")).lower() not in ("no", "false"),
                    "style": kv.get("style", style),
                }
    for e, d in envs.items():
        d["kind"] = kind_from_name(e, d["display"])
    return envs, alias, within


MACRO_DEF_RE = re.compile(
    r"\\(?P<cmd>newcommand|renewcommand|providecommand|DeclareRobustCommand|"
    r"DeclareMathOperator|newrobustcmd|renewrobustcmd)(?P<star>\*?)"
    r"|\\def\s*\\(?P<dname>[A-Za-z@]+)(?P<dparams>(?:#\d)*)\s*\{"
)


def parse_macros(text: str) -> dict:
    """Collect user macros in MathJax `tex.macros` format."""
    macros: dict[str, object] = {}
    for m in MACRO_DEF_RE.finditer(text):
        i = m.end()
        if m.group("dname"):
            body, _ = read_group(text, i - 1)
            if body is None:
                continue
            name = m.group("dname")
            n = len(re.findall(r"#\d", m.group("dparams") or ""))
            if "@" in name:
                continue
            macros[name] = [body, n] if n else body
            continue
        cmd = m.group("cmd")
        j = skip_ws(text, i)
        if j < len(text) and text[j] == "{":
            name, i = read_group(text, j)
        else:
            mm = re.match(r"\\([A-Za-z@]+|.)", text[j:])
            if not mm:
                continue
            name, i = mm.group(0), j + mm.end()
        if not name:
            continue
        name = name.strip().lstrip("\\")
        if not re.fullmatch(r"[A-Za-z]+", name):
            continue
        if cmd == "DeclareMathOperator":
            body, i = read_group(text, i)
            if body is None:
                continue
            op = "\\operatorname*" if m.group("star") else "\\operatorname"
            macros[name] = op + "{" + body + "}"
            continue
        nargs, i = read_optional(text, i)
        default, i2 = read_optional(text, i)
        if default is not None:
            i = i2
        body, i = read_group(text, i)
        if body is None:
            continue
        if cmd == "providecommand" and name in macros:
            continue
        try:
            n = int(nargs) if nargs else 0
        except ValueError:
            n = 0
        if n and default is not None:
            macros[name] = [body, n, default]
        elif n:
            macros[name] = [body, n]
        else:
            macros[name] = body
    # MathJax does not know these; make them harmless.
    for name, val in list(macros.items()):
        def fix(b):
            b = re.sub(r"\\ensuremath\s*", "", b)
            b = b.replace("\\xspace", "").replace("\\mathbbm", "\\mathbb")
            b = b.replace("\\mathds", "\\mathbb").replace("\\bm{", "\\boldsymbol{")
            return b
        macros[name] = [fix(val[0])] + list(val[1:]) if isinstance(val, list) else fix(val)
    return macros


PKG_TO_MATHJAX = {
    "mathtools": "mathtools", "physics": "physics", "braket": "braket",
    "cancel": "cancel", "bm": "boldsymbol", "upgreek": "upgreek",
    "mhchem": "mhchem", "amscd": "amscd", "bbm": None, "xcolor": "color",
    "color": "color", "extpfeil": "extpfeil", "unicode-math": None,
    "colonequals": "colonequals", "centernot": "centernot",
}


def used_packages(preamble: str) -> list[str]:
    pk = []
    for m in re.finditer(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", preamble):
        pk += [p.strip() for p in m.group(1).split(",") if p.strip()]
    return pk


def local_style_text(root: str, packages: list[str]) -> str:
    out = []
    for p in packages:
        f = os.path.join(root, p + ".sty")
        if os.path.isfile(f):
            with open(f, encoding="utf-8", errors="replace") as fh:
                out.append(strip_comments(fh.read()))
    return "\n".join(out)


def parse_aux(main_path: str) -> dict:
    """label -> number from the .aux file next to the main tex (if any)."""
    aux = os.path.splitext(main_path)[0] + ".aux"
    out: dict[str, str] = {}
    if not os.path.isfile(aux):
        return out
    with open(aux, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    for m in re.finditer(r"\\newlabel\{([^}]*)\}\{", text):
        label = m.group(1)
        if label.endswith("@cref"):
            continue
        num, _ = read_group(text, m.end() - 1)
        if num is None:
            continue
        first, _ = read_group(num, 0)
        if first is None:
            continue
        first = re.sub(r"\\[A-Za-z]+\s*", "", first).replace("{", "").replace("}", "").strip()
        out[label] = first
    # \@input{chapter.aux}
    for m in re.finditer(r"\\@input\{([^}]*)\}", text):
        sub = os.path.join(os.path.dirname(aux), m.group(1))
        if os.path.isfile(sub):
            out.update(parse_aux(sub[:-4] + ".tex"))
    return out


def parse_bibliography(main_path: str, text: str) -> dict:
    """cite key -> label as printed ([12] or Author (Year))."""
    src = text
    bbl = os.path.splitext(main_path)[0] + ".bbl"
    if os.path.isfile(bbl):
        with open(bbl, encoding="utf-8", errors="replace") as fh:
            src += "\n" + fh.read()
    out, n = {}, 0
    for m in re.finditer(r"\\bibitem\s*(\[(?:[^\[\]]|\[[^\]]*\])*\])?\s*\{([^}]*)\}", src):
        key = m.group(2).strip()
        if key in out:
            continue
        n += 1
        opt = m.group(1)
        if opt:
            lab = re.sub(r"\\[A-Za-z]+\s*|[{}\[\]]", "", opt[1:-1]).strip()
            out[key] = lab or str(n)
        else:
            out[key] = str(n)
    return out


ARXIV_ID_RE = re.compile(r"(?i)(?:arxiv[:\s/]*|abs/|e-print/|eprint\s*=\s*\{?)(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})")
DOI_RE = re.compile(r"(?i)\b(10\.\d{4,9}/[^\s}{,]+)")


def parse_references(main_path: str, text: str) -> dict:
    """cite key -> {label, text, arxiv, doi} from \\bibitem entries (.tex / .bbl) or .bib files."""
    src = text
    bbl = os.path.splitext(main_path)[0] + ".bbl"
    if os.path.isfile(bbl):
        with open(bbl, encoding="utf-8", errors="replace") as fh:
            src += "\n" + fh.read()
    labels = parse_bibliography(main_path, text)
    out: dict[str, dict] = {}
    items = list(re.finditer(r"\\bibitem\s*(\[(?:[^\[\]]|\[[^\]]*\])*\])?\s*\{([^}]*)\}", src))
    for k, m in enumerate(items):
        key = m.group(2).strip()
        if key in out:
            continue
        end = items[k + 1].start() if k + 1 < len(items) else min(len(src), m.end() + 1500)
        end = min(end, src.find("\\end{thebibliography}", m.end()) if "\\end{thebibliography}" in src[m.end():end] else end)
        body = src[m.end():end]
        out[key] = _ref_record(labels.get(key, key), body)
    # .bib files (biblatex / bibtex without a .bbl)
    root = os.path.dirname(main_path)
    bibs = re.findall(r"\\(?:bibliography|addbibresource)\s*\{([^}]*)\}", text)
    for group in bibs:
        for name in group.split(","):
            path = os.path.join(root, name.strip())
            path = path if path.endswith(".bib") else path + ".bib"
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                bib = fh.read()
            for m in re.finditer(r"@\w+\s*\{\s*([^,\s]+)\s*,", bib):
                key = m.group(1)
                if key in out:
                    continue
                nxt = bib.find("\n@", m.end())
                out[key] = _ref_record(labels.get(key, key), bib[m.end(): nxt if nxt > 0 else m.end() + 2000],
                                       bibtex=True)
    return out


def _ref_record(label: str, body: str, bibtex: bool = False) -> dict:
    if bibtex:
        fields = dict(re.findall(r"(\w+)\s*=\s*[{\"](.+?)[}\"]\s*,?\s*\n", body))
        text = "; ".join(fields.get(f, "") for f in ("author", "title", "journal", "year") if fields.get(f))
    else:
        text = body
    import latex2html
    text = re.sub(r"\\(newblock|url|href|doi)\b", " ", text)
    text = latex2html.plain(text)[:300]
    a = ARXIV_ID_RE.search(body)
    d = DOI_RE.search(body)
    return {"label": label, "text": text, "arxiv": a.group(1) if a else None,
            "doi": d.group(1).rstrip(".") if d else None}


def find_title(preamble: str, body: str) -> tuple[str, str, str]:
    title = authors = abstract = ""
    for src in (preamble, body):
        m = re.search(r"\\title\s*(?:\[[^\]]*\])?\s*\{", src)
        if m and not title:
            t, _ = read_group(src, m.end() - 1)
            title = t or ""
        m = re.search(r"\\author\s*(?:\[[^\]]*\])?\s*\{", src)
        if m and not authors:
            a, _ = read_group(src, m.end() - 1)
            authors = a or ""
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", body, re.S)
    if m:
        abstract = m.group(1).strip()
    title = re.sub(r"\\\\(\[[^\]]*\])?", " ", title)
    title = re.sub(r"\\thanks\{[^}]*\}", "", title)
    authors = re.sub(r"\\(thanks|footnote)\{[^}]*\}", "", authors)
    authors = re.sub(r"\\\\|\\and\b", ", ", authors)
    return title.strip(), re.sub(r"\s+", " ", authors).strip(" ,"), abstract


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def extract_tex(path: str, include_all: bool = False) -> dict:
    main = find_main_tex(path)
    src = Source(main)
    text = src.text
    # Drop comment environments and \iffalse blocks, keeping offsets.
    for pat in (r"\\begin\{comment\}.*?\\end\{comment\}", r"\\iffalse\b.*?\\fi\b"):
        for m in reversed(list(re.finditer(pat, text, re.S))):
            text = blank_out(text, m.start(), m.end())

    bd = text.find("\\begin{document}")
    preamble = text[:bd] if bd >= 0 else ""
    body_start = bd + len("\\begin{document}") if bd >= 0 else 0
    ed = text.find("\\end{document}", body_start)
    body_end = ed if ed >= 0 else len(text)

    packages = used_packages(preamble)
    style_text = local_style_text(src.root, packages)
    decl_text = style_text + "\n" + text
    envs, counter_alias, numberwithin = parse_theorem_decls(decl_text)
    macros = parse_macros(style_text + "\n" + preamble + "\n" + text[body_start:body_end])
    mj_packages = sorted({PKG_TO_MATHJAX[p] for p in packages if PKG_TO_MATHJAX.get(p)})
    aux = parse_aux(main)
    docclass = re.search(r"\\document(?:class|style)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", preamble)
    docclass = docclass.group(1).strip() if docclass else "article"
    has_chapters = docclass in ("book", "report", "amsbook", "memoir", "scrbook", "scrreprt") \
        or re.search(r"\\chapter\*?\s*[\[{]", text[body_start:body_end]) is not None

    def is_theorem_env(name: str) -> bool:
        if name in envs:
            return True
        base = name.rstrip("*")
        if base in envs or name in PROOF_ENVS:
            return base in envs
        low = base.lower()
        if low in NOT_THEOREM_ENVS:
            return False
        return low in KIND_WORDS or low in ENV_ABBREV

    def env_info(name: str) -> dict:
        if name in envs:
            return envs[name]
        base = name.rstrip("*")
        if base in envs:
            d = dict(envs[base])
            d["numbered"] = False
            return d
        kind = kind_from_name(name)
        return {"display": kind.capitalize(), "counter": base, "within": None,
                "numbered": not name.endswith("*"), "style": "plain", "kind": kind}

    # ---- counters --------------------------------------------------------
    sec_count = {k: 0 for k in SECTION_LEVELS}
    appendix = [False]
    thm_count: dict[str, int] = {}
    eq_count = [0]
    top_level = "chapter" if has_chapters else "section"
    eq_within = numberwithin.get("equation", "chapter" if has_chapters else None)

    def sec_number(level: str) -> str:
        lv = SECTION_LEVELS[level]
        parts = []
        for name, l in SECTION_LEVELS.items():
            if l == 0 or l > lv:
                continue
            if name == "chapter" and not has_chapters:
                continue
            v = sec_count[name]
            if name == top_level and appendix[0]:
                parts.append(to_alpha(v))
            else:
                parts.append(str(v))
        return ".".join(parts)

    def counter_root(c: str) -> str:
        seen = set()
        while c in counter_alias and c not in seen:
            seen.add(c)
            c = counter_alias[c]
        while c in envs and envs[c]["counter"] != c and c not in seen:
            seen.add(c)
            c = envs[c]["counter"]
        return c

    def counter_within(c: str) -> str | None:
        if c in numberwithin:
            return numberwithin[c]
        if c in envs:
            return envs[c]["within"]
        return None

    def next_thm_number(info: dict) -> str | None:
        if not info["numbered"]:
            return None
        c = counter_root(info["counter"])
        thm_count[c] = thm_count.get(c, 0) + 1
        w = counter_within(c) or info.get("within")
        val = str(thm_count[c])
        if w in SECTION_LEVELS:
            return sec_number(w) + "." + val
        if w in thm_count:  # within another theorem counter (rare)
            return str(thm_count[w]) + "." + val
        return val

    def next_eq_number() -> str:
        eq_count[0] += 1
        if eq_within in SECTION_LEVELS:
            return sec_number(eq_within) + "." + str(eq_count[0])
        return str(eq_count[0])

    def section_event(level: str):
        lv = SECTION_LEVELS[level]
        sec_count[level] += 1
        for name, l in SECTION_LEVELS.items():
            if l > lv:
                sec_count[name] = 0
        for c in list(thm_count):
            w = counter_within(c)
            if w in SECTION_LEVELS and SECTION_LEVELS[w] >= lv:
                thm_count[c] = 0
        if eq_within in SECTION_LEVELS and SECTION_LEVELS[eq_within] >= lv:
            eq_count[0] = 0

    # ---- scan ------------------------------------------------------------
    nodes: list[dict] = []
    by_id: dict[str, dict] = {}
    labels: dict[str, dict] = {}
    refs: list[dict] = []          # {label, cmd, frame, offset}
    cites: list[dict] = []         # {key, frame, offset}
    eq_lines: list[tuple[int, int, str]] = []  # numbered display-math lines (start, end, number)
    proofs: list[dict] = []
    sections: list[dict] = []
    stack: list[dict] = []
    handled_labels: set[int] = set()
    last_closed_node = [None]
    last_section = {"number": "", "title": "", "label": None}
    last_sec_end = [-1]
    auto_id = [0]

    def current_frame():
        for fr in reversed(stack):
            if fr["type"] in ("node", "proof"):
                return fr
        return None

    pos = body_start
    for m in TOKEN_RE.finditer(text, body_start, body_end):
        if m.start() < pos:
            continue
        if m.group("benv") is not None:
            env = m.group("benv").strip()
            after = m.end()
            if env in ("restatable", "restatable*"):
                opt, after = read_optional(text, after)
                inner, after = read_group(text, after)
                _, after = read_group(text, after)
                if inner is None:
                    continue
                tenv, topt = inner.strip(), opt
                if not is_theorem_env(tenv):
                    continue
            elif is_theorem_env(env) and env not in PROOF_ENVS:
                tenv = env
                topt, after2 = read_optional(text, after)
                if topt is not None:
                    after = after2
            elif env in PROOF_ENVS:
                opt, after2 = read_optional(text, after)
                if opt is not None:
                    after = after2
                fr = {"type": "proof", "env": env, "start": after, "opt": opt,
                      "prev": last_closed_node[0], "offset": m.start(),
                      "parent_frame": current_frame()}
                stack.append(fr)
                continue
            elif env.rstrip("*") in SINGLE_EQ_ENVS | MULTI_EQ_ENVS:
                endm = re.compile(r"\\end\s*\{" + re.escape(env) + r"\}").search(text, after, body_end)
                if not endm:
                    continue
                bodytxt = text[after:endm.start()]
                starred = env.endswith("*")
                base = env.rstrip("*")
                if base == "alignat" or base == "xalignat":
                    _, k = read_group(bodytxt, 0)
                    bodytxt_eff = bodytxt[k:] if k else bodytxt
                else:
                    bodytxt_eff = bodytxt
                lines = [bodytxt_eff] if base in SINGLE_EQ_ENVS else split_top_level(bodytxt_eff)
                nums = []
                frame = current_frame()
                line_off = after + (len(bodytxt) - len(bodytxt_eff))
                for ln in lines:
                    tag = re.search(r"\\tag\*?\s*\{([^}]*)\}", ln)
                    if tag:
                        num = tag.group(1)
                    elif starred or re.search(r"\\(nonumber|notag)\b", ln):
                        num = None
                    elif base in MULTI_EQ_ENVS and not ln.strip() and ln is lines[-1] and len(lines) > 1:
                        num = None  # trailing \\ produces an empty last line
                    else:
                        num = next_eq_number()
                    nums.append(num)
                    if num and not tag:
                        eq_lines.append((line_off, line_off + len(ln), num))
                    for lm in re.finditer(r"\\label\s*\{([^}]*)\}", ln):
                        lab = lm.group(1).strip()
                        handled_labels.add(line_off + lm.start())
                        labels[lab] = {"type": "equation", "number": num, "frame": frame,
                                       "offset": line_off + lm.start(),
                                       "section": dict(last_section)}
                    line_off += len(ln) + 2
                continue
            else:
                stack.append({"type": "other", "env": env})
                continue
            # theorem-like node
            info = env_info(tenv)
            number = next_thm_number(info)
            title = None
            if topt is not None:
                kv = parse_kv(topt) if re.match(r"\s*(name|title|label)\s*=", topt) else None
                title = kv.get("name") or kv.get("title") if kv else topt
            frame = current_frame()
            node = {
                "env": tenv, "kind": info["kind"], "display": info["display"],
                "number": number, "title": (title or "").strip() or None,
                "label": None, "section": dict(last_section),
                "stmt_start": after, "stmt_end": None,
                "loc": src.locate(m.start()), "offset": m.start(),
                "parent_frame": frame, "proof_spans": [],
            }
            fr = {"type": "node", "env": env, "node": node, "start": after}
            nodes.append(node)
            stack.append(fr)
            continue

        if m.group("eenv") is not None:
            env = m.group("eenv").strip()
            for k in range(len(stack) - 1, -1, -1):
                fr = stack[k]
                if fr["env"] == env:
                    del stack[k:]
                    if fr["type"] == "node":
                        fr["node"]["stmt_end"] = m.start()
                        last_closed_node[0] = fr["node"]
                    elif fr["type"] == "proof":
                        fr["end"] = m.start()
                        proofs.append(fr)
                    break
            continue

        if m.group("sec"):
            level = m.group("sec")
            i = m.end()
            _, i = read_optional(text, i)
            title, i = read_group(text, i)
            if not m.group("secstar"):
                section_event(level)
                num = sec_number(level)
            else:
                num = ""
            last_section = {"number": num, "title": clean_text_snippet(title or "", 120),
                            "level": SECTION_LEVELS[level], "label": None}
            sections.append(last_section)
            last_sec_end[0] = i
            last_closed_node[0] = None if level in ("part", "chapter") else last_closed_node[0]
            pos = i
            continue

        if m.group("appendix"):
            appendix[0] = True
            sec_count[top_level] = 0
            continue

        if m.group("label") is not None:
            if m.start() in handled_labels:
                continue
            lab = m.group("label").strip()
            frame = current_frame()
            if text[last_sec_end[0]:m.start()].strip() == "" and last_sec_end[0] > 0:
                labels[lab] = {"type": "section", "number": last_section["number"],
                               "offset": m.start(), "section": dict(last_section)}
                last_section["label"] = lab
            elif frame and frame["type"] == "node" and frame["node"]["label"] is None and \
                    "\\item" not in text[frame["start"]:m.start()]:
                frame["node"]["label"] = lab
                labels[lab] = {"type": "node", "frame": frame, "offset": m.start()}
            else:
                is_item = frame is not None and "\\item" in text[max(frame["start"], m.start() - 200):m.start()]
                labels[lab] = {"type": "item" if is_item else ("inner" if frame else "prose"),
                               "frame": frame, "offset": m.start(), "number": None,
                               "section": dict(last_section)}
            continue

        # references
        frame = current_frame()
        if m.group("refcmd"):
            cmd = m.group("refcmd")
            for lab in m.group("refargs").split(","):
                lab = lab.strip()
                if lab:
                    refs.append({"label": lab, "cmd": cmd, "frame": frame, "offset": m.start()})
        elif m.group("rangecmd"):
            for g in ("r1", "r2"):
                refs.append({"label": m.group(g).strip(), "cmd": "cref", "frame": frame,
                             "offset": m.start()})
        elif m.group("citecmd"):
            for key in m.group("citekeys").split(","):
                if key.strip():
                    cites.append({"key": key.strip(), "frame": frame, "offset": m.start()})
        elif m.group("hlabel") is not None:
            refs.append({"label": m.group("hlabel").strip(), "cmd": "hyperref", "frame": frame,
                         "offset": m.start()})

    # Unclosed frames (missing \end): close at body end.
    for fr in stack:
        if fr["type"] == "node" and fr["node"]["stmt_end"] is None:
            fr["node"]["stmt_end"] = body_end
        elif fr["type"] == "proof" and "end" not in fr:
            fr["end"] = body_end
            proofs.append(fr)

    # ---- ids & numbers -----------------------------------------------------
    used_ids = set()
    for nd in nodes:
        if nd["label"] and nd["label"] in aux:
            nd["number"] = aux[nd["label"]]
        nid = nd["label"]
        if not nid or nid in used_ids:
            prefix = KIND_PREFIX.get(nd["kind"], nd["kind"][:4])
            nid = f"{prefix}:{nd['number']}" if nd["number"] else f"{prefix}:auto{auto_id[0]}"
            while nid in used_ids:
                auto_id[0] += 1
                nid = f"{prefix}:auto{auto_id[0]}"
            auto_id[0] += 1
        used_ids.add(nid)
        nd["id"] = nid
        by_id[nid] = nd
    for lab, info in labels.items():
        if lab in aux and info["type"] != "node":
            info["number"] = aux[lab]

    def frame_node(fr):
        if fr is None:
            return None, None
        if fr["type"] == "node":
            return fr["node"], "statement"
        return fr.get("target"), "proof"

    # ---- attach proofs ----------------------------------------------------
    num_index: dict[tuple[str, str], dict] = {}
    for nd in nodes:
        if nd["number"]:
            num_index[(nd["kind"], nd["number"])] = nd
            num_index.setdefault(("*", nd["number"]), nd)
    orphan_proofs = []
    for pf in sorted(proofs, key=lambda p: p["offset"]):
        target = None
        opt = pf.get("opt") or ""
        if opt:
            mref = re.search(r"\\(?:" + REF_CMDS + r")\*?\s*\{([^},]*)", opt)
            if mref and mref.group(1).strip() in labels and labels[mref.group(1).strip()]["type"] == "node":
                target = labels[mref.group(1).strip()]["frame"]["node"]
            if target is None:
                mnum = re.search(r"(?i)(" + "|".join(KIND_WORDS) + r")\w*\.?\s*~?\s*([A-Z]?\d+(?:\.\d+)*[a-z]?)", opt)
                if mnum:
                    target = num_index.get((mnum.group(1).lower(), mnum.group(2))) or \
                        num_index.get(("*", mnum.group(2)))
        if target is None and not re.search(r"\\(?:" + REF_CMDS + r")", opt):
            prev = pf.get("prev")
            if prev is not None:
                target = prev
        pf["target"] = target
        if target is None:
            orphan_proofs.append(pf)
            continue
        target["proof_spans"].append((pf["start"], pf["end"]))

    # parents of nested nodes (claims inside proofs, etc.)
    for nd in nodes:
        pnode, part = frame_node(nd["parent_frame"])
        nd["parent"] = pnode["id"] if pnode is not None and pnode is not nd else None
        nd["parent_part"] = part if nd["parent"] else None

    eq_lines.sort()
    eq_starts = [e[0] for e in eq_lines]

    def slice_with_tags(a: int, b: int) -> str:
        """text[a:b] with explicit \\tag{n} on numbered display lines."""
        s = text[a:b]
        i = bisect.bisect_left(eq_starts, a)
        ins = []
        while i < len(eq_lines) and eq_lines[i][0] < b:
            ls, le, num = eq_lines[i]
            if le <= b:
                ins.append((le - a, num))
            i += 1
        for at, num in reversed(ins):
            s = s[:at].rstrip() + " \\tag{" + num + "}" + s[at:]
        return s

    blank_re = re.compile(r"\n[ \t]*\n")

    def paragraph_bounds(o: int) -> tuple[int, int]:
        """Paragraph (blank-line delimited) around offset o; display math does not break it."""
        starts = [m.end() for m in blank_re.finditer(text, body_start, o)]
        a = starts[-1] if starts else body_start
        m = blank_re.search(text, o, body_end)
        b = m.start() if m else body_end
        return a, b

    # ---- resolve labels -----------------------------------------------------
    label_out: dict[str, dict] = {}
    for lab, info in labels.items():
        rec = {"type": info["type"]}
        if info["type"] == "node":
            nd = info["frame"]["node"]
            rec.update(node=nd["id"], number=nd["number"], kind=nd["kind"],
                       display=nd["display"])
        else:
            nd, part = frame_node(info.get("frame"))
            rec["number"] = info.get("number")
            if nd is not None:
                rec.update(node=nd["id"], part=part)
            else:
                rec["section"] = info.get("section", {}).get("number")
                if info["type"] in ("prose", "equation"):
                    o = info["offset"]
                    a, b = paragraph_bounds(o)
                    rec["context"] = text[max(a, o - 900):min(b, o + 600)].strip()
                    rec["paragraph"] = slice_with_tags(a, b).strip() if b - a < 4000 else rec["context"]
                    rec["para_pos"] = a
                    rec["loc"] = src.locate(o)
        label_out[lab] = rec

    # ---- refs per node --------------------------------------------------------
    prose_refs = []
    for r in refs:
        fr = r["frame"]
        nd, part = frame_node(fr)
        if fr is not None and fr["type"] == "proof" and nd is None:
            nd = None
        entry = {"label": r["label"], "cmd": r["cmd"]}
        if nd is None:
            o = r["offset"]
            entry["context"] = clean_text_snippet(text[max(body_start, o - 250):o + 200], 450)
            entry["loc"] = src.locate(o)
            prose_refs.append(entry)
            continue
        key = "explicit_" + part if r["cmd"] in ("uses", "proves") else part
        nd.setdefault("_refs", {}).setdefault(key, []).append(r["label"])

    for c in cites:
        nd_c, part_c = frame_node(c["frame"])
        if nd_c is not None:
            nd_c.setdefault("_cites", {}).setdefault(part_c, []).append(c["key"])

    # ---- assemble -------------------------------------------------------------
    referenced = set()
    for nd in nodes:
        for key, labs in nd.get("_refs", {}).items():
            for lab in labs:
                tgt = label_out.get(lab, {}).get("node")
                if tgt and tgt != nd["id"]:
                    referenced.add(tgt)
        if nd["parent"]:
            referenced.add(nd["id"])

    out_nodes = []
    for nd in nodes:
        statement = slice_with_tags(nd["stmt_start"], nd["stmt_end"])
        if nd["label"]:
            statement = re.sub(r"\\label\s*\{" + re.escape(nd["label"]) + r"\}", "", statement, count=1)
        proof_parts = [slice_with_tags(a, b) for a, b in nd["proof_spans"]]
        hidden = (nd["kind"] in HIDDEN_KINDS and nd["id"] not in referenced and not include_all)
        r = nd.get("_refs", {})
        out_nodes.append({
            "id": nd["id"],
            "env": nd["env"],
            "kind": nd["kind"],
            "display": nd["display"],
            "number": nd["number"],
            "title": nd["title"],
            "label": nd["label"],
            "section": nd["section"].get("number") or None,
            "section_title": nd["section"].get("title") or None,
            "statement": statement.strip(),
            "proof": "\n\n".join(p.strip() for p in proof_parts) or None,
            "statement_format": "latex",
            "refs": {"statement": dedup(r.get("statement", [])),
                     "proof": dedup(r.get("proof", []))},
            "cites": {"statement": dedup(nd.get("_cites", {}).get("statement", [])),
                      "proof": dedup(nd.get("_cites", {}).get("proof", []))},
            "explicit_uses": {"statement": dedup(r.get("explicit_statement", [])),
                              "proof": dedup(r.get("explicit_proof", []))},
            "parent": nd["parent"],
            "loc": nd["loc"],
            "pos": nd["offset"],
            "hidden": hidden,
            "shape": "box" if nd["kind"] in DEFINITION_KINDS else "ellipse",
        })

    # paragraphs of running text that look like they define something
    covered = []
    for nd in nodes:
        covered.append((nd["offset"], nd["stmt_end"] or nd["offset"]))
        covered += nd["proof_spans"]
    covered.sort()
    prose_defs = []
    pos2 = body_start
    for m in blank_re.finditer(text, body_start, body_end):
        a, b = pos2, m.start()
        pos2 = m.end()
        if b - a < 40 or any(x < b and a < y for x, y in covered):
            continue
        para = text[a:b]
        if DEF_CUE_RE.search(para) and not re.search(r"\\(section|subsection|begin\{(figure|table|abstract)\})", para):
            labs = re.findall(r"\\label\s*\{([^}]*)\}", para)
            prose_defs.append({"loc": src.locate(a), "labels": labs,
                               "text": clean_text_snippet(para, 500)})
    from symbols import build_index_tex
    owners = []
    for nd in nodes:
        owners.append((nd["stmt_start"], nd["stmt_end"] or nd["stmt_start"], nd["id"], "statement"))
        owners += [(a, b, nd["id"], "proof") for a, b in nd["proof_spans"]]
    symbol_index = build_index_tex(text, body_start, body_end, owners, macros, src.locate)
    title, authors, abstract = find_title(preamble, text[body_start:body_end])
    return {
        "format": "paper-blueprint/extracted@1",
        "source": {"type": "tex", "path": os.path.abspath(path), "main": main,
                   "files": [os.path.relpath(f, src.root) for f in src.files],
                   "aux_numbers": bool(aux)},
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "macros": macros,
        "bibliography": parse_bibliography(main, text),
        "references": {k: v for k, v in parse_references(main, text).items()
                       if k in {c["key"] for c in cites}},
        "arxiv_mentioned": sorted(set(ARXIV_ID_RE.findall(text[body_start:body_end]))),
        "mathjax_packages": mj_packages,
        "theorem_envs": {k: {kk: vv for kk, vv in v.items()} for k, v in envs.items()},
        "sections": sections,
        "nodes": out_nodes,
        "labels": label_out,
        "prose_refs": prose_refs,
        "prose_definitions": prose_defs[:80],
        "symbol_index": symbol_index,
        "numbering": "exact (.aux)" if aux else "reconstructed (no .aux file next to the main .tex)",
        "orphan_proofs": [{"opt": p.get("opt"), "loc": src.locate(p["offset"]),
                           "text": clean_text_snippet(text[p["start"]:p["end"]], 300)}
                          for p in orphan_proofs],
    }


DEF_CUE_RE = re.compile(
    r"(?i)\b(we\s+(define|denote|write|call|say|introduce|fix|put|set|use the notation)|"
    r"(is|are)\s+(called|said to be|defined\s+(as|by|to be))|define[sd]?\b|denote[sd]?\b|"
    r"throughout\s+(this|the)\s+(section|paper|subsection)|:=|\\coloneqq|\\eqqcolon|"
    r"for\s+(brevity|convenience|simplicity),?\s+(we\s+)?(write|set|put|denote|let))")


def dedup(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
