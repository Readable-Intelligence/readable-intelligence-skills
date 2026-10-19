"""Math-symbol bookkeeping for the self-containedness check.

A *symbol* is a normalised piece of notation: a Latin letter ("Q"), a Greek letter
("\\varphi"), a decorated letter ("\\mathcal{D}", "\\mathbb{F}", "\\hat{\\gamma}").
`symbols_in(tex)` lists the symbols of a LaTeX snippet; `introduced_in(tex)` the ones the
snippet itself introduces ("Let $Q=2^b$", "for every $x$", "$\\sum_{j}$", "$y := …$").
The rest must come from somewhere the reader can see: a node it depends on, a `context`
note, or the paper-wide `notation` table.
"""
from __future__ import annotations

import re
import unicodedata

GREEK = ("alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa "
         "varkappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi "
         "chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega").split()
GREEK_SET = set(GREEK)
GREEK_UNICODE = dict(zip(
    "α β γ δ ϵ ε ζ η θ ϑ ι κ ϰ λ μ ν ξ π ϖ ρ ϱ σ ς τ υ ϕ φ χ ψ ω Γ Δ Θ Λ Ξ Π Σ Υ Φ Ψ Ω".split(),
    GREEK))
FONT_CMDS = ("mathcal", "mathbb", "mathfrak", "mathscr", "mathsf", "mathbf", "boldsymbol", "bm",
             "mathbbm", "mathds", "symbf", "symcal", "mathit")
ACCENT_CMDS = ("hat", "tilde", "bar", "overline", "widehat", "widetilde", "vec", "dot", "ddot",
               "check", "breve", "underline", "mathring")
SKIP_ARG_CMDS = ("text", "textrm", "textit", "textbf", "mathrm", "operatorname", "operatorname*",
                 "mbox", "label", "tag", "ref", "eqref", "cref", "Cref", "textup", "textsf", "texttt",
                 "mathtt", "hspace", "vspace", "color", "textcolor", "begin", "end", "cite", "emph")
BINDERS = ("sum", "prod", "bigcup", "bigcap", "bigoplus", "bigotimes", "coprod", "bigvee",
           "bigwedge", "max", "min", "sup", "inf", "lim", "limsup", "liminf", "argmax", "argmin",
           "esssup", "bigsqcup", "int", "iint", "oint")
RELATIONS = r"(?:=|<|>|\\le(?:q|qslant)?\b|\\ge(?:q|qslant)?\b|\\in\b|\\subset(?:eq)?\b|\\subseteq\b|" \
            r"\\supset(?:eq)?\b|\\ne(?:q)?\b|\\sim\b|\\approx\b|\\equiv\b|\\to\b|\\mapsto\b|:(?!=)|" \
            r"\\colon\b|\\coloneqq\b|\\eqqcolon\b|:=|\\le\b|\\ll\b|\\gg\b|\\mid\b|\\notin\b|\\cong\b|\\simeq\b)"
# Notation every reader is assumed to know.
STANDARD = {"\\pi", "\\mathbb{N}", "\\mathbb{Z}", "\\mathbb{Q}", "\\mathbb{R}", "\\mathbb{C}",
            "\\mathbb{T}", "\\mathbb{F}", "\\mathbb{E}", "\\mathbb{P}", "\\infty", "\\emptyset",
            "\\mathcal{O}", "\\mathbb{S}",
            "\\varnothing", "\\mathbb{D}", "\\mathbb{H}"}
# Text cues after which the first math chunk introduces its leading symbols.
CUE_RE = re.compile(
    r"(?i)(?:\b(?:let|fix|take|choose|consider|given|pick)\b(?:\s+(?:an?|the|some|any|each|every)\b)?"
    r"(?:\s+[\w-]+){0,3}?|\bfor\b(?:\s+(?:all|every|each|any|some|an?|the|fixed))?|"
    r"\bsuppose\b|\bassume\b|\bwhere\b|\bwith\b|\btake\b|\bchoose\b|"
    r"\bthere\s+(?:is|are|exists?)\b(?:\s+[\w-]+){0,6}|\bconsider\b|\bnamely\b|\bsay\b|"
    r"\bof\s+(?:order|degree|size|length|dimension|rank)(?:\s+at\s+(?:most|least))?|\bexists?\b|"
    r"\bsome\b|\bevery\b|\beach\b|\bany\b|\bwhenever\b|\bif\b|\bunless\b|"
    r"\b(?:define[sd]?|defining|denoted?(?:\s+by)?|denoting|write|writing|set|setting|put|putting|"
    r"call(?:ed|ing)?|introduce|introducing|letting|taking|choosing|fixing)\b(?:\s+[\w-]+){0,8}|"
    r"\b(?:integers?|numbers?|matri(?:x|ces)|vectors?|functions?|polynomials?|sequences?|parameters?|"
    r"constants?|operators?|maps?|sets?|points?|states?|registers?|elements?|reals?|primes?|"
    r"measures?|circuits?|graphs?|subsets?|kernels?|families|family|variables?|coefficients?|"
    r"probability|probabilities|quantity|quantities|values?|index|indices|exponents?|degrees?|"
    r"lengths?|sizes?|costs?|errors?|rates?|factors?|outcomes?|labels?|strings?|bits?|qubits?|"
    r"gates?|transforms?|density|densities|distributions?|norms?|weights?|polynomial|spaces?|"
    r"groups?|rings?|fields?|algorithms?|events?|unitar(?:y|ies)|projections?|densit(?:y|ies)|"
    r"intervals?|domains?|curves?|paths?|trees?|nodes?|edges?|vertices|vertex|words?|codes?)\b)[\s,:~]*$")
# "X is $A = …$": a copula introduces the left side of an equation that follows it
COPULA_RE = re.compile(r"(?i)\b(?:is|are|be|equals?)\s*$")
# text between two math chunks that continues an enumeration ("$a$, $b$ and $c$")
CONTINUE_RE = re.compile(r"(?i)^[\s,;~]*(?:(?:and|or|as\s+well\s+as)\b[\s,~]*)?$")
STRIP_STANDARD = [
    re.compile(r"\\\\\s*\[[^\]]*\]"),                                   # \\[1mm]
    re.compile(r"(?<![A-Za-z\\])C\s*\^\s*(?:\{\s*(?:\d+|\\infty)\s*\}|\d|\\infty)"),  # C^1, C^\infty
    re.compile(r"(?<![A-Za-z\\])(?:S?U|S?O|GL|SL|Sp|PSL)\s*\(\s*(?:\d+|[nNdmk])\s*\)"),  # U(2), SU(n)
    re.compile(r"(?<![A-Za-z\\])O\s*\("),                                     # big-O
    re.compile(r"(?<![A-Za-z\\])e(?=\s*\^)"),                                  # e^{x}: Euler's number
    re.compile(r"(?<=\\pi)\s*i(?![A-Za-z])|(?<![A-Za-z\\])i(?=\s*\\pi)"),         # 2\pi i
    re.compile(r"\\[,!;]\s*d(?=\s*[A-Za-z\\])"),                                # \,dx  (differential d)
]


def _strip_braces(s: str) -> str:
    return s.strip().strip("{}").strip()


def expand_macros(tex: str, macros: dict | None, rounds: int = 4) -> str:
    """Expand user macros (MathJax format: str or [body, nargs(, default)])."""
    if not macros:
        return tex
    from texparse import read_group, read_optional
    for _ in range(rounds):
        changed = False
        out, i = [], 0
        for m in re.finditer(r"\\([A-Za-z]+)", tex):
            name = m.group(1)
            if name not in macros or m.start() < i:
                continue
            spec = macros[name]
            body, nargs, default = (spec, 0, None) if isinstance(spec, str) else \
                (spec[0], int(spec[1]) if len(spec) > 1 else 0, spec[2] if len(spec) > 2 else None)
            j = m.end()
            args = []
            if default is not None:
                opt, j2 = read_optional(tex, j)
                args.append(opt if opt is not None else default)
                j = j2 if opt is not None else j
                nargs -= 1
            for _k in range(max(nargs, 0)):
                a, j2 = read_group(tex, j)
                if a is None:
                    mm = re.match(r"\s*(\\[A-Za-z]+|\S)", tex[j:])
                    if not mm:
                        break
                    a, j2 = mm.group(1), j + mm.end()
                args.append(a)
                j = j2
            for k, a in enumerate(args, 1):
                body = body.replace(f"#{k}", a)
            out.append(tex[i:m.start()])
            out.append("{" + body + "}" if nargs else " " + body + " ")
            i = j
            changed = True
        out.append(tex[i:])
        tex = "".join(out)
        if not changed:
            break
    return tex


POST_CUE_RE = re.compile(r"(?i)^\s*(?:denotes?|stands?\s+for|is\s+(?:called|defined|said|the\s+\w+\s+of)|"
                         r"are\s+(?:called|defined)|will\s+denote)")


def math_chunks_after(tex: str) -> list[str]:
    """Text following each math segment (aligned with math_chunks)."""
    chunks = math_chunks(tex)
    afters = [b for b, _ in chunks[1:]]
    import latex2html
    c = latex2html.Converter()
    protected = c.protect(tex or "")
    tail = re.split(latex2html.PH_OPEN + r"\d+" + latex2html.PH_CLOSE, protected)[-1] if chunks else ""
    return afters + [tail]


def math_chunks(tex: str) -> list[tuple[str, str]]:
    """[(text_before, math_body), …] for every math segment of a LaTeX snippet."""
    import latex2html
    c = latex2html.Converter()
    protected = c.protect(tex or "")
    out, last = [], 0
    for m in re.finditer(latex2html.PH_OPEN + r"(\d+)" + latex2html.PH_CLOSE, protected):
        before = protected[last:m.start()]
        before = re.sub(latex2html.PH_OPEN + r"\d+" + latex2html.PH_CLOSE, " ", before)
        out.append((before, c.math[int(m.group(1))][0]))
        last = m.end()
    return out


def _clean_math(math: str) -> str:
    for rx in STRIP_STANDARD:
        math = rx.sub(" ", math)
    s = re.sub(r"\\(label|tag|ref|eqref|cref|Cref)\*?\s*\{[^}]*\}", " ", math)
    # text-like arguments carry no symbols (\mathrm{d}, \operatorname{Log}, \text{if})
    for _ in range(3):
        s = re.sub(r"\\(text|textrm|textit|textbf|mathrm|operatorname\*?|mbox|textup|textsf|texttt|"
                   r"mathtt|hspace|vspace|color|textcolor|begin|end|cite|emph)\s*\{[^{}]*\}", " ", s)
    return re.sub(r"\\(left|right|big|Big|bigg|Bigg)[lr]?(?![A-Za-z])", " ", s)


def _tokens(math: str):
    """Yield (symbol, kind); kind is 'base', or 'index' inside a sub/superscript."""
    s = _clean_math(math)
    i, n = 0, len(s)
    script_depths: list[int] = []
    depth = 0
    pending_script = False
    while i < n:
        c = s[i]
        in_script = bool(script_depths) or pending_script
        kind = "index" if in_script else "base"
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+)\*?", s[i:])
            if not m:
                i += 2
                pending_script = False
                continue
            name, j = m.group(1), i + m.end()
            if name in FONT_CMDS or name in ACCENT_CMDS:
                from texparse import read_group
                grp, j2 = read_group(s, j)  # balanced {…} argument, or a single token
                if grp is not None:
                    inner, consumed = grp.strip(), j2 - j
                else:
                    tok = re.match(r"\s*(\\[A-Za-z]+|[A-Za-z])", s[j:])
                    inner, consumed = (tok.group(1), tok.end()) if tok else ("", 0)
                if consumed and inner.lstrip("\\") in FONT_CMDS:
                    grp2, j3 = read_group(s, j + consumed)
                    if grp2 is not None and re.fullmatch(r"\s*(?:[A-Za-z]|\\[A-Za-z]+)\s*", grp2):
                        fname = {"mathbbm": "mathbb", "mathds": "mathbb", "bm": "boldsymbol"}.get(
                            inner.lstrip("\\"), inner.lstrip("\\"))
                        sym = f"\\{fname}{{{grp2.strip()}}}"
                        if name in ACCENT_CMDS:  # \widehat\mathbf{h} -> \hat{\mathbf{h}}
                            acc = {"overline": "bar", "widehat": "hat", "widetilde": "tilde"}.get(name, name)
                            sym = f"\\{acc}{{{sym}}}"
                        yield sym, kind
                        i = j3
                        pending_script = False
                        continue
                if consumed:
                    font = {"mathbbm": "mathbb", "mathds": "mathbb", "bm": "boldsymbol",
                            "symbf": "mathbf", "symcal": "mathcal", "overline": "bar",
                            "widehat": "hat", "widetilde": "tilde"}.get(name, name)
                    if name == "mathit":
                        for ch in re.findall(r"[A-Za-z]", inner):
                            yield ch, kind
                    elif re.fullmatch(r"\\[A-Za-z]+", inner):
                        if inner[1:] in GREEK_SET:
                            yield f"\\{font}{{{inner}}}", kind
                    elif re.fullmatch(r"[A-Za-z]", inner):
                        yield f"\\{font}{{{inner}}}", kind
                    elif name in ACCENT_CMDS or re.match(r"\s*\\[A-Za-z]", inner):
                        # \hat{x_1}, \overline{\gamma_k}, \widehat{\boldsymbol\gamma}: the first
                        # symbol inside carries the accent
                        inside = [t for t, k in _tokens(inner) if k == "base"]
                        if inside:
                            yield (f"\\{font}{{{inside[0]}}}" if name in ACCENT_CMDS else inside[0]), kind
                    else:  # \mathbf{ab}: one symbol per letter
                        for ch in re.findall(r"[A-Za-z]", re.sub(r"_.*", "", inner)):
                            yield f"\\{font}{{{ch}}}", kind
                    i = j + consumed
                    pending_script = False
                    continue
            if name in GREEK_SET:
                yield "\\" + name, kind
            i = j
            pending_script = False
            continue
        if c in "_^":
            pending_script = True
            i += 1
            continue
        if c == "{":
            depth += 1
            if pending_script:
                script_depths.append(depth)
                pending_script = False
            i += 1
            continue
        if c == "}":
            if script_depths and script_depths[-1] == depth:
                script_depths.pop()
            depth -= 1
            i += 1
            continue
        if c.isascii() and c.isalpha():
            yield c, kind
        elif c in GREEK_UNICODE:
            yield "\\" + GREEK_UNICODE[c], kind
        if not c.isspace():
            pending_script = False
        i += 1


def symbols_in(tex: str, macros: dict | None = None, with_index: bool = False,
               keep_standard: bool = False) -> set[str]:
    """Symbols used in a LaTeX snippet (outside sub/superscripts unless with_index)."""
    out = set()
    for _, body in math_chunks(tex):
        body = expand_macros(body, macros)
        for sym, kind in _tokens(body):
            if kind == "base" or with_index and kind == "index":
                out.add(sym)
    return out if keep_standard else out - STANDARD


def _split_relations(body: str) -> list[str]:
    return re.split(RELATIONS, body)


BINDER_RE = re.compile(r"\\(?:" + "|".join(BINDERS) + r")\*?\s*(?:\\limits|\\nolimits)?\s*_\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\\?[A-Za-z]+)")


def introduced_in(tex: str, macros: dict | None = None, generous: bool = False) -> set[str]:
    """Symbols the snippet binds or introduces itself (a deliberately generous heuristic).

    generous=True (proof sketches, proofs): every symbol of a cued chunk counts as introduced,
    so "write $q=A/2^T$" introduces A and T as well as q.
    """
    intro = set()

    def syms(fragment, kinds=("base", "index")):
        return {s for s, k in _tokens(fragment) if k in kinds}

    prev_cued = False
    chunks = math_chunks(tex)
    afters = math_chunks_after(tex) if chunks else []
    for idx, (before, body) in enumerate(chunks):
        body = expand_macros(body, macros)
        after = afters[idx] if idx < len(afters) else ""
        if POST_CUE_RE.match(after or ""):
            intro |= syms(re.split(RELATIONS, body)[0])
        if generous:
            # "$w=e^{-ihz}$", "$c_j\in\C$": a lone symbol on the left of = / \in is being introduced
            for clause in _top_level_split(body):
                mm = re.match(r"\s*((?:\\[A-Za-z]+\s*(?:\{[^{}]*\}|[A-Za-z](?![A-Za-z]))|\\[A-Za-z]+|[A-Za-z])(?:\s*[_^]\s*(?:\{[^{}]*\}|\w))*"
                              r"(?:\s*\([^()]*\))?)\s*(?:=|\\in\b|:=|\\coloneqq)", clause)
                if mm:
                    intro |= syms(mm.group(1), ("base",))
        # \sum_{j=0}^n, \max_{x \in S}, \bigcup_{k}
        for m in BINDER_RE.finditer(body):
            sub = m.group(1).strip("{}")
            intro |= syms(re.split(r"=|\\in\b|\\le|<|\\ge|>|\\subset|\\to", sub)[0])
        for m in re.finditer(r"\\(?:forall|exists|nexists)\s*(\\[A-Za-z]+|[A-Za-z](?:\s*,\s*[A-Za-z])*)", body):
            intro |= syms(m.group(1))
        # postfix quantifiers  "… < \varepsilon \qquad (z \in Z)"
        for m in re.finditer(r"\(\s*([A-Za-z](?:\s*,\s*[A-Za-z])*)\s*\\in\b", body):
            intro |= syms(m.group(1))
        # set-builder {x : …}, {x \in S : …}, {(d,j) : …}
        for m in re.finditer(r"\\\{\s*(.{1,40}?)\s*(?::|\\mid|\||\\colon)", body):
            intro |= syms(re.split(r"\\in\b", m.group(1))[0])
        for m in re.finditer(r"([A-Za-z(),\s]{1,12})\\mapsto", body):
            intro |= syms(m.group(1))
        # y := …   and   … =: y
        for m in re.finditer(r"([^=<>;]{1,60}?)\s*(?::=|\\coloneqq|\\triangleq|\\equiv)", body):
            lhs = _top_level_split(m.group(1))
            intro |= syms(lhs[-1] if lhs else m.group(1), ("base",))
        for m in re.finditer(r"(?:=:|\\eqqcolon)\s*([^=<>,;]{1,60})", body):
            intro |= syms(m.group(1), ("base",))
        # measures  d\mu(k), \mathrm{d}\nu(x): the argument is the integration variable
        for m in re.finditer(r"(?:\\mathrm\{d\}|\\dd|\\,d|\bd)\s*\\?[A-Za-z]+\s*\(\s*([A-Za-z])\s*\)", body):
            intro.add(m.group(1))
        # differentials  \,dx   \mathrm{d}x   \dd x
        for m in re.finditer(r"(?:\\,|\\!|\\;|\s|\})(?:d|\\mathrm\{d\}|\\dd|\\operatorname\{d\})\s*([A-Za-z]|\\[a-z]+)(?![A-Za-z])", body):
            intro |= syms(m.group(1)) if m.group(1).startswith("\\") else {m.group(1)}
        # a cue in the preceding text ("Let", "for every", "where", …): leading term(s);
        # after a defining cue every listed clause "F(x) = …, G = …" defines its left side
        tail = (before or "")[-80:]
        opening = not (before or "").strip() and bool(re.search(r"(?<![<>!])=|:=|\\coloneqq", body))
        cued = opening or bool(CUE_RE.search(tail)) or \
            (bool(COPULA_RE.search(tail)) and "=" in body) or \
            (prev_cued and bool(CONTINUE_RE.match(before or "")))
        prev_cued = cued
        if cued and generous:
            intro |= syms(body)
        elif cued:
            defining = DEFINING_CUE_RE.search(tail) or not tail.strip(" ,~")
            clauses = _top_level_split(body) if defining else [body]
            for clause in clauses:
                parts = re.split(RELATIONS, clause)
                lead = syms(parts[0]) if parts else set()
                if not lead and len(parts) > 1:  # "2 \le m < B" introduces the middle term m
                    lead = syms(parts[1], ("base",))
                intro |= lead
    return intro


DEFINING_CUE_RE = re.compile(r"(?i)\b(define[sd]?|let|set|put|where|write|denote[sd]?|with|call)\b[^.]*$")


def _top_level_split(body: str) -> list[str]:
    """Split at , ; \\quad \\qquad \\\\ that are outside (), [], {}."""
    out, depth, last, i = [], 0, 0, 0
    while i < len(body):
        c = body[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and (c in ",;" or body.startswith("\\qquad", i) or body.startswith("\\quad", i)
                             or body.startswith("\\\\", i)):
            out.append(body[last:i])
            step = 6 if body.startswith("\\qquad", i) else 5 if body.startswith("\\quad", i) else \
                2 if body.startswith("\\\\", i) else 1
            i += step
            last = i
            continue
        i += 1
    out.append(body[last:])
    return [x for x in out if x.strip()]


# ---------------------------------------------------------------------------
# PDF side: recover symbols from math fonts
# ---------------------------------------------------------------------------

def pdf_span_symbols(text: str, font: str) -> list[str]:
    """Symbols in one PDF text span, judged by its font (math italic, cal, bb …)."""
    f = font.lower()
    out = []
    for ch in text:
        if ch in GREEK_UNICODE:
            out.append("\\" + GREEK_UNICODE[ch])
            continue
        if ord(ch) > 0x1D400:
            name = unicodedata.name(ch, "")
            m = re.match(r"MATHEMATICAL (BOLD )?(ITALIC |SCRIPT |DOUBLE-STRUCK |FRAKTUR |SANS-SERIF )?"
                         r"(CAPITAL|SMALL) ([A-Z])$", name)
            if m:
                letter = m.group(4) if m.group(3) == "CAPITAL" else m.group(4).lower()
                style = (m.group(2) or "").strip()
                wrap = {"SCRIPT": "mathcal", "DOUBLE-STRUCK": "mathbb", "FRAKTUR": "mathfrak",
                        "SANS-SERIF": "mathsf"}.get(style)
                out.append(f"\\{wrap}{{{letter}}}" if wrap else letter)
            continue
        if not ch.isascii() or not ch.isalpha():
            continue
        if "msbm" in f or "bbold" in f or "dsrom" in f or "doublestruck" in f:
            out.append(f"\\mathbb{{{ch}}}")
        elif "eufm" in f or "fraktur" in f:
            out.append(f"\\mathfrak{{{ch}}}")
        elif "rsfs" in f or "script" in f:
            out.append(f"\\mathscr{{{ch}}}")
        elif ("cmsy" in f or "mathsymbols" in f) and ch.isupper():
            out.append(f"\\mathcal{{{ch}}}")
        elif "cmmi" in f or "mathitalic" in f or ("math" in f and "ital" in f):
            out.append(ch)
    return out


# ---------------------------------------------------------------------------
# Paper-wide index: where is each symbol first used / first defined?
# ---------------------------------------------------------------------------

def _occ(owner, part, loc, snippet, pos):
    return {"owner": owner, "part": part, "loc": loc, "snippet": snippet, "pos": pos}


def _add(index, sym, occ, defining):
    rec = index.setdefault(sym, {"first": None, "def": None, "defs": 0, "uses": 0, "free_owners": []})
    rec["uses"] += 1
    if not defining and occ["owner"] and occ["owner"] not in rec["free_owners"]:
        rec["free_owners"].append(occ["owner"])  # nodes that use it without introducing it
    if rec["first"] is None:
        rec["first"] = occ
    if defining:
        rec["defs"] += 1
        # a definition in running text or in a statement is notation the reader must be told about;
        # one inside a proof is usually a local variable
        if rec["def"] is None and occ["part"] != "proof":
            rec["def"] = occ


def build_index_tex(text: str, start: int, end: int, owners: list, macros: dict, locate) -> dict:
    """owners: list of (start, end, node_id, part) spans; the rest is running text."""
    paint = {}
    # proofs first, statements second, so a claim inside a proof owns its own statement
    for a, b, nid, part in sorted(owners, key=lambda o: (o[3] != "proof", o[0])):
        for k in range(max(a, start), min(b, end)):
            paint[k] = (nid, part)
    index: dict = {}
    blank = re.compile(r"\n[ \t]*\n")
    pos = start
    while pos < end:
        own = paint.get(pos)
        stop = pos + 1
        while stop < end and paint.get(stop) == own:
            stop += 1
        if own is None:
            bounds, last = [], pos
            for m in blank.finditer(text, pos, stop):
                bounds.append((last, m.start()))
                last = m.end()
            bounds.append((last, stop))
        else:
            bounds = [(pos, stop)]
        for a, b in bounds:
            piece = text[a:b]
            if not piece.strip():
                continue
            used = symbols_in(piece, macros, with_index=True)
            if not used:
                continue
            intro = introduced_in(piece, macros)
            occ = _occ(own[0] if own else None, own[1] if own else "prose", locate(a),
                       re.sub(r"\s+", " ", piece.strip())[:260], a)
            for sym in sorted(used):
                _add(index, sym, occ, sym in intro)
        pos = stop
    return index


PDF_DEF_CUE = re.compile(r"(?i)\b(let|define[sd]?|denote[sd]?|we write|write|where|set|put|call(ed)?|"
                         r"is called|stands for|abbreviate)\b|:=")


def build_index_pdf(lines: list, line_owner) -> dict:
    """lines: pdfparse.Line objects in reading order; line_owner(i) -> (node_id, part) or None."""
    index: dict = {}
    for i, ln in enumerate(lines):
        syms = []
        for sp in ln.spans:
            syms += pdf_span_symbols(sp.get("text", ""), sp.get("font", ""))
        if not syms:
            continue
        own = line_owner(i)
        ctx = " ".join(x.text for x in lines[max(0, i - 1):i + 2])
        occ = _occ(own[0] if own else None, own[1] if own else "prose",
                   {"page": ln.page + 1}, re.sub(r"\s+", " ", ctx)[:260], [ln.page, round(ln.y0, 1)])
        defining = bool(PDF_DEF_CUE.search(ln.text))
        for sym in sorted(set(syms) - STANDARD):
            _add(index, sym, occ, defining)
    return index
