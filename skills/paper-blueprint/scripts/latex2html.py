"""Convert a LaTeX snippet (theorem statement, proof) to HTML for MathJax.

Math is left as TeX (wrapped in \\( \\) / \\[ \\] or kept as an environment)
for MathJax to typeset; text-mode markup is turned into HTML.  This is a
display aid, not a full TeX engine: unknown commands are dropped and their
arguments kept.
"""
from __future__ import annotations

import html
import re
import unicodedata

from texparse import read_group, read_optional

MATH_ENVS = {
    "equation", "equation*", "align", "align*", "gather", "gather*",
    "multline", "multline*", "flalign", "flalign*", "alignat", "alignat*",
    "eqnarray", "eqnarray*", "displaymath", "math", "dmath", "dmath*",
    "xalignat", "xalignat*",
}
PH_OPEN, PH_CLOSE = "\ue000", "\ue001"

FORMAT_CMDS = {
    "emph": ("<em>", "</em>"), "textit": ("<em>", "</em>"), "textsl": ("<em>", "</em>"),
    "textbf": ("<strong>", "</strong>"), "textsc": ('<span class="sc">', "</span>"),
    "texttt": ("<code>", "</code>"), "textsf": ("<span class=\"sf\">", "</span>"),
    "underline": ("<u>", "</u>"), "uline": ("<u>", "</u>"),
    "textsuperscript": ("<sup>", "</sup>"), "textsubscript": ("<sub>", "</sub>"),
    "hl": ("<mark>", "</mark>"), "textrm": ("", ""), "textup": ("", ""),
    "textnormal": ("", ""), "mbox": ("", ""), "hbox": ("", ""), "text": ("", ""),
    "textmd": ("", ""), "makebox": ("", ""), "fbox": ("", ""),
}
DECL_CMDS = {"em": ("<em>", "</em>"), "it": ("<em>", "</em>"), "itshape": ("<em>", "</em>"),
             "sl": ("<em>", "</em>"), "bf": ("<strong>", "</strong>"),
             "bfseries": ("<strong>", "</strong>"), "sc": ('<span class="sc">', "</span>"),
             "scshape": ('<span class="sc">', "</span>"), "tt": ("<code>", "</code>"),
             "ttfamily": ("<code>", "</code>"), "rm": ("", ""), "upshape": ("", ""),
             "normalfont": ("", ""), "small": ("", ""), "footnotesize": ("", ""),
             "large": ("", ""), "Large": ("", ""), "normalsize": ("", "")}
SYMBOLS = {
    "ldots": "…", "dots": "…", "textellipsis": "…", "S": "§", "P": "¶",
    "textendash": "–", "textemdash": "—", "LaTeX": "LaTeX", "TeX": "TeX",
    "copyright": "©", "dag": "†", "ddag": "‡", "textbackslash": "\\",
    "i": "ı", "j": "ȷ", "ss": "ß", "o": "ø", "O": "Ø", "ae": "æ", "AE": "Æ",
    "oe": "œ", "OE": "Œ", "aa": "å", "AA": "Å", "l": "ł", "L": "Ł",
    "quad": "\u2003", "qquad": "\u2003\u2003", "enspace": "\u2002",
    "textquoteleft": "‘", "textquoteright": "’", "textquotedblleft": "“",
    "textquotedblright": "”", "textbullet": "•", "textasciitilde": "~",
    "textdegree": "°", "checkmark": "✓", "qed": "", "qedhere": "", "today": "",
}
SKIP_CMDS_0 = {
    "noindent", "indent", "smallskip", "medskip", "bigskip", "hfill", "vfill",
    "linebreak", "pagebreak", "newpage", "clearpage", "centering", "raggedright",
    "raggedleft", "leavevmode", "relax", "ignorespaces", "nopagebreak",
    "allowbreak", "protect", "phantomsection", "maketitle", "unskip", "null",
    "displaybreak", "allowdisplaybreaks", "break", "nolinebreak", "sloppy",
    "fussy", "selectfont", "boldmath", "unboldmath", "item@", "strut", "par@",
}
SKIP_CMDS_1 = {"label", "index", "vspace", "hspace", "vspace*", "hspace*",
               "color", "pagestyle", "thispagestyle", "enlargethispage",
               "addcontentsline", "setcounter", "addtocounter", "glossary",
               "nocite", "bibliographystyle", "bibliography", "input", "include",
               "pdfbookmark", "hypertarget", "phantom", "hphantom", "vphantom"}
ACCENTS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
           "=": "\u0304", ".": "\u0307", "u": "\u0306", "v": "\u030c", "H": "\u030b",
           "c": "\u0327", "k": "\u0328", "r": "\u030a", "b": "\u0331", "d": "\u0323"}
CITE_RE = re.compile(r"(?:cite|citep|citet|citealp|citealt|Cite|Citep|Citet|parencite|"
                     r"textcite|autocite|footcite|citeauthor|citeyear|cites)\*?")
REF_LIKE = {"ref", "eqref", "cref", "Cref", "autoref", "Autoref", "vref", "Vref",
            "cpageref", "Cpageref", "labelcref", "nameref", "Nameref", "pageref",
            "vpageref", "thmref", "Thmref", "subref", "crefrange", "Crefrange"}
ENUM_DEFAULT = ["arabic", "alph", "roman", "Alph"]


def _to_roman(n: int) -> str:
    vals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
            (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


def _counter(style: str, n: int) -> str:
    if style == "alph":
        return chr(96 + n) if n <= 26 else str(n)
    if style == "Alph":
        return chr(64 + n) if n <= 26 else str(n)
    if style == "roman":
        return _to_roman(n)
    if style == "Roman":
        return _to_roman(n).upper()
    return str(n)


class Converter:
    """Stateful converter; `ref` is a callback (label, cmd) -> html string."""

    def __init__(self, macros: dict | None = None, ref=None, cite=None,
                 theorem_envs: dict | None = None):
        self.macros = macros or {}
        self.ref = ref or (lambda label, cmd: html.escape(label))
        self.cite = cite or (lambda keys, note: "[" + ", ".join(keys) + (", " + note if note else "") + "]")
        self.theorem_envs = theorem_envs or {}
        self.math: list[str] = []
        self.enum_depth = 0
        self.expansions = 0

    # -- math protection ---------------------------------------------------
    def protect(self, s: str) -> str:
        out, i, n = [], 0, len(s)
        while i < n:
            c = s[i]
            if c == "\\" and i + 1 < n:
                nxt = s[i + 1]
                if nxt in "([":
                    close = "\\)" if nxt == "(" else "\\]"
                    j = s.find(close, i + 2)
                    if j >= 0:
                        out.append(self._ph(s[i + 2:j], "display" if nxt == "[" else "inline"))
                        i = j + 2
                        continue
                m = re.match(r"\\begin\s*\{([^}]+)\}", s[i:])
                if m and m.group(1).strip() in MATH_ENVS:
                    env = m.group(1).strip()
                    endm = re.compile(r"\\end\s*\{" + re.escape(env) + r"\}").search(s, i + m.end())
                    if endm:
                        out.append(self._ph(s[i + m.end():endm.start()], env))
                        i = endm.end()
                        continue
                out.append(s[i:i + 2])
                i += 2
                continue
            if c == "$":
                if s.startswith("$$", i):
                    j = s.find("$$", i + 2)
                    if j >= 0:
                        out.append(self._ph(s[i + 2:j], "display"))
                        i = j + 2
                        continue
                else:
                    j = i + 1
                    while j < n:
                        if s[j] == "\\":
                            j += 2
                            continue
                        if s[j] == "$":
                            break
                        j += 1
                    if j < n:
                        out.append(self._ph(s[i + 1:j], "inline"))
                        i = j + 1
                        continue
            out.append(c)
            i += 1
        return "".join(out)

    def _ph(self, body: str, mode: str) -> str:
        self.math.append((body, mode))
        return f"{PH_OPEN}{len(self.math) - 1}{PH_CLOSE}"

    def _math_html(self, idx: int) -> str:
        body, mode = self.math[idx]
        body = self._clean_math(body)
        if mode == "inline":
            return '<span class="math">\\(' + html.escape(body, quote=False) + "\\)</span>"
        if mode == "display":
            return '<div class="math display">\\[' + html.escape(body, quote=False) + "\\]</div>"
        env = {"dmath": "equation", "dmath*": "equation*", "displaymath": "equation*",
               "math": None, "xalignat": "alignat", "xalignat*": "alignat*"}.get(mode, mode)
        if env is None:
            return '<span class="math">\\(' + html.escape(body, quote=False) + "\\)</span>"
        return ('<div class="math display">\\begin{' + env + "}" +
                html.escape(body, quote=False) + "\\end{" + env + "}</div>")

    def _clean_math(self, body: str) -> str:
        body = re.sub(r"\\label\s*\{[^}]*\}", "", body)
        body = re.sub(r"\\(qedhere|displaybreak(\[\d\])?|allowdisplaybreaks|nonumber\b(?=\s*\\tag))", "", body)

        def mref(m):
            cmd, labs = m.group(1), m.group(2)
            parts = []
            for lab in labs.split(","):
                txt = re.sub(r"<[^>]+>", "", self.ref(lab.strip(), "ref" if cmd != "eqref" else "eqnum"))
                parts.append(html.unescape(txt))
            s = ", ".join(parts)
            return "\\text{(" + s + ")}" if cmd == "eqref" else "\\text{" + s + "}"
        body = re.sub(r"\\(eqref|ref|cref|Cref|autoref)\*?\s*\{([^}]*)\}", mref, body)
        body = re.sub(r"\\intertext\s*\{([^}]*)\}", r"\\text{\1}\\\\", body)
        body = body.replace("\\hdots", "\\ldots").replace("\\mathbbm", "\\mathbb")
        body = body.replace("\\textup", "\\textrm")
        return body

    # -- text conversion -----------------------------------------------------
    def convert(self, src: str) -> str:
        if not src:
            return ""
        s = self.protect(src)
        out = self._text(s)
        # paragraphs
        paras = [p.strip() for p in re.split(r"\n\s*\n|\ue002", out) if p.strip()]
        out = "".join(f'<div class="para">{p}</div>' for p in paras)
        out = re.sub(PH_OPEN + r"(\d+)" + PH_CLOSE, lambda m: self._math_html(int(m.group(1))), out)
        return out

    def _text(self, s: str) -> str:
        out: list[str] = []
        i, n = 0, len(s)
        while i < n:
            c = s[i]
            if c == PH_OPEN:
                j = s.find(PH_CLOSE, i)
                out.append(s[i:j + 1])
                i = j + 1
                continue
            if c == "\\":
                i = self._command(s, i, out)
                continue
            if c == "{":
                inner, j = read_group(s, i)
                if inner is None:
                    i += 1
                    continue
                m = re.match(r"\s*\\([A-Za-z]+)(?![A-Za-z])", inner)
                if m and m.group(1) in DECL_CMDS:
                    a, b = DECL_CMDS[m.group(1)]
                    out.append(a + self._text(inner[m.end():]) + b)
                else:
                    out.append(self._text(inner))
                i = j
                continue
            if c == "}":
                i += 1
                continue
            if c == "~":
                out.append("\u00a0")
            elif c == "-" and s.startswith("---", i):
                out.append("—")
                i += 3
                continue
            elif c == "-" and s.startswith("--", i):
                out.append("–")
                i += 2
                continue
            elif c == "`":
                if s.startswith("``", i):
                    out.append("“")
                    i += 2
                    continue
                out.append("‘")
            elif c == "'":
                if s.startswith("''", i):
                    out.append("”")
                    i += 2
                    continue
                out.append("’")
            elif c in "<>&":
                out.append(html.escape(c))
            else:
                out.append(c)
            i += 1
        return "".join(out)

    def _args(self, s: str, i: int, k: int) -> tuple[list[str], int]:
        args = []
        for _ in range(k):
            a, j = read_group(s, i)
            if a is None:
                m = re.match(r"\s*(\\[A-Za-z]+|\S)", s[i:])
                if not m:
                    break
                a, j = m.group(1), i + m.end()
            args.append(a)
            i = j
        return args, i

    def _command(self, s: str, i: int, out: list) -> int:
        m = re.match(r"\\([A-Za-z@]+\*?|.)", s[i:])
        if not m:
            return i + 1
        name = m.group(1)
        j = i + m.end()
        base = name.rstrip("*")
        # single-character commands
        if len(name) == 1 and not name.isalpha():
            if name == "\\":
                _, j = read_optional(s, j)
                out.append("<br>")
            elif name in ACCENTS:
                arg, j2 = read_group(s, j)
                if arg is None:
                    arg, j2 = s[j:j + 1], j + 1
                arg = {"\\i": "ı", "\\j": "ȷ"}.get(arg.strip(), arg.strip())
                out.append(unicodedata.normalize("NFC", (arg[:1] or " ") + ACCENTS[name]) + arg[1:])
                j = j2
            elif name in ",;:! ":
                out.append({",": "\u2009", ";": "\u2004", ":": "\u2005", "!": "", " ": " "}[name])
            elif name in "%&#$_{}":
                out.append(html.escape(name))
            elif name == "/":
                pass
            elif name == "-":
                pass
            else:
                out.append(html.escape(name))
            return j
        if base in ACCENTS and base.isalpha() and len(base) == 1:
            arg, j2 = read_group(s, j)
            if arg is not None:
                out.append(unicodedata.normalize("NFC", (arg.strip()[:1] or " ") + ACCENTS[base]) + arg.strip()[1:])
                return j2
        if base == "begin":
            return self._environment(s, i, out)
        if base == "end":
            _, j = read_group(s, j)
            return j
        if base in FORMAT_CMDS:
            a, b = FORMAT_CMDS[base]
            arg, j2 = read_group(s, j)
            if arg is None:
                return j
            out.append(a + self._text(arg) + b)
            return j2
        if base in DECL_CMDS:
            return j
        if base in SYMBOLS:
            out.append(SYMBOLS[base])
            if base.isalpha() and s.startswith("{}", j):
                j += 2
            return j
        if base in REF_LIKE:
            if base in ("crefrange", "Crefrange"):
                (a, b), j = self._args(s, j, 2)
                out.append(self.ref(a.strip(), "cref") + "–" + self.ref(b.strip(), "ref"))
                return j
            arg, j = read_group(s, j)
            if arg is None:
                return j
            labs = [x.strip() for x in arg.split(",") if x.strip()]
            out.append(", ".join(self.ref(lab, base) for lab in labs))
            return j
        if base == "hyperref":
            lab, j = read_optional(s, j)
            txt, j = read_group(s, j)
            out.append(self._text(txt or "") if lab is None else self.ref(lab, "hyperref:" + (txt or "")))
            return j
        if CITE_RE.fullmatch(name):
            opt1, j = read_optional(s, j)
            opt2, j2 = read_optional(s, j)
            if opt2 is not None:
                j = j2
            keys, j = read_group(s, j)
            note = opt2 if opt2 is not None else opt1
            out.append(html.escape(self.cite([k.strip() for k in (keys or "").split(",") if k.strip()],
                                             re.sub(r"[{}~\\]", " ", note or "").strip())))
            return j
        if base in ("url", "nolinkurl"):
            arg, j = read_group(s, j)
            out.append(f'<a href="{html.escape(arg or "")}" target="_blank">{html.escape(arg or "")}</a>')
            return j
        if base == "href":
            (u, t), j = self._args(s, j, 2)
            out.append(f'<a href="{html.escape(u)}" target="_blank">{self._text(t)}</a>')
            return j
        if base in ("footnote", "footnotetext", "thanks"):
            _, j = read_optional(s, j)
            arg, j = read_group(s, j)
            out.append(f'<span class="footnote">{self._text(arg or "")}</span>')
            return j
        if base in ("paragraph", "subparagraph", "subsection", "subsubsection", "section"):
            _, j = read_optional(s, j)
            arg, j = read_group(s, j)
            out.append(f"<strong>{self._text(arg or '')}.</strong> ")
            return j
        if base in ("textcolor", "colorbox"):
            (_, t), j = self._args(s, j, 2)
            out.append(self._text(t))
            return j
        if base == "ensuremath":
            arg, j = read_group(s, j)
            out.append(self._ph(arg or "", "inline"))
            return j
        if base == "verb":
            if j < len(s):
                d = s[j]
                k = s.find(d, j + 1)
                if k > 0:
                    out.append("<code>" + html.escape(s[j + 1:k]) + "</code>")
                    return k + 1
            return j
        if base == "item":
            opt, j = read_optional(s, j)
            out.append("\ue002• " if opt is None else "\ue002" + self._text(opt) + " ")
            return j
        if base == "par":
            out.append("\ue002")
            return j
        if base in ("newline",):
            out.append("<br>")
            return j
        if base in SKIP_CMDS_0:
            return j
        if base in SKIP_CMDS_1:
            _, j = read_optional(s, j)
            _, j = read_group(s, j)
            return j
        if base in ("setlength", "addtolength"):
            _, j = self._args(s, j, 2)
            return j
        if base == "vskip" or base == "hskip":
            mm = re.match(r"\s*-?[\d.]+\s*\w+(\s*(plus|minus)\s*-?[\d.]+\s*\w+)*", s[j:])
            return j + (mm.end() if mm else 0)
        if base in self.macros and self.expansions < 5000:
            self.expansions += 1
            spec = self.macros[base]
            body, nargs, default = (spec, 0, None) if isinstance(spec, str) else \
                (spec[0], spec[1], spec[2] if len(spec) > 2 else None)
            args = []
            if default is not None:
                opt, j2 = read_optional(s, j)
                args.append(opt if opt is not None else default)
                if opt is not None:
                    j = j2
                nargs -= 1
            more, j = self._args(s, j, nargs)
            args += more
            for k, a in enumerate(args, 1):
                body = body.replace(f"#{k}", a)
            if re.search(r"\\(math|operatorname|frac|sum|int|left|right|[A-Za-z]+sym)", body) \
                    or re.fullmatch(r"\\?[A-Za-z]*\{?[A-Za-z]\}?", body.strip()) and "\\math" in body:
                out.append(self._ph(body, "inline"))
            else:
                out.append(self._text(self.protect(body)))
            return j
        # unknown command: drop it, keep arguments as text
        return j

    def _environment(self, s: str, i: int, out: list) -> int:
        m = re.match(r"\\begin\s*\{([^}]+)\}", s[i:])
        env = m.group(1).strip()
        start = i + m.end()
        # find matching \end{env} (same-name nesting)
        pat = re.compile(r"\\(begin|end)\s*\{" + re.escape(env) + r"\}")
        depth, end, after = 1, len(s), len(s)
        for mm in pat.finditer(s, start):
            depth += 1 if mm.group(1) == "begin" else -1
            if depth == 0:
                end, after = mm.start(), mm.end()
                break
        body = s[start:end]
        base = env.rstrip("*")
        if base in ("itemize", "enumerate", "description", "compactenum", "compactitem",
                    "inparaenum", "asparaenum"):
            opt, b = read_optional(body, 0)
            if opt is not None:
                body = body[b:]
            items = self._split_items(body)
            tag = "ul" if base in ("itemize", "compactitem") else ("dl" if base == "description" else "ol")
            if tag == "ol":
                self.enum_depth += 1
                style = ENUM_DEFAULT[min(self.enum_depth - 1, 3)]
                tmpl = {"arabic": "{}.", "alph": "({})", "roman": "{}.", "Alph": "{}."}[style]
                if opt:
                    mm = re.search(r"label\s*=\s*(\{.*\}|[^,\]]*)", opt)
                    lab = (mm.group(1) if mm else opt).strip().strip("{}")
                    st = re.search(r"\\(alph|Alph|roman|Roman|arabic)\*?", lab)
                    if st:
                        style = st.group(1)
                        tmpl = lab[:st.start()] + "{}" + lab[st.end():]
                    elif re.fullmatch(r"\(?[aAiI1]\)?\.?", lab):
                        ch = re.search(r"[aAiI1]", lab).group(0)
                        style = {"a": "alph", "A": "Alph", "i": "roman", "I": "Roman", "1": "arabic"}[ch]
                        tmpl = lab.replace(ch, "{}")
                    tmpl = re.sub(r"[\\{}](?!\})", "", tmpl.replace("{}", "\0")).replace("\0", "{}")
                lis = []
                for n, (lab, txt) in enumerate(items, 1):
                    marker = self._text(lab) if lab is not None else html.escape(tmpl.format(_counter(style, n)))
                    lis.append(f'<li><span class="item-label">{marker}</span> {self._block(txt)}</li>')
                self.enum_depth -= 1
                out.append('<ol class="tex-enum">' + "".join(lis) + "</ol>")
            elif tag == "dl":
                out.append("<dl>" + "".join(
                    f"<dt>{self._text(lab or '')}</dt><dd>{self._block(txt)}</dd>" for lab, txt in items) + "</dl>")
            else:
                out.append("<ul>" + "".join(
                    (f'<li class="custom"><span class="item-label">{self._text(lab)}</span> {self._block(txt)}</li>'
                     if lab is not None else f"<li>{self._block(txt)}</li>") for lab, txt in items) + "</ul>")
            return after
        if base in ("center", "flushleft", "flushright"):
            out.append(f'<div class="{base}">{self._block(body)}</div>')
        elif base in ("quote", "quotation", "verse"):
            out.append(f"<blockquote>{self._block(body)}</blockquote>")
        elif base in ("proof", "pf"):
            opt, b = read_optional(body, 0)
            head = self._text(opt) if opt is not None else "Proof"
            out.append(f'<div class="nested-proof"><em>{head}.</em> {self._block(body[b:] if opt is not None else body)}</div>')
        elif base in self.theorem_envs or base in ("claim", "lemma", "theorem", "remark", "step", "case"):
            opt, b = read_optional(body, 0)
            disp = self.theorem_envs.get(base, {}).get("display", base.capitalize())
            title = f" ({self._text(opt)})" if opt is not None else ""
            content = body[b:] if opt is not None else body
            out.append(f'<div class="nested-thm"><strong>{html.escape(disp)}{title}.</strong> {self._block(content)}</div>')
        elif base in ("verbatim", "lstlisting", "minted", "algorithmic", "algorithm", "algorithm2e",
                      "tabular", "tabularx", "array", "tikzpicture", "tikzcd"):
            txt = re.sub(PH_OPEN + r"(\d+)" + PH_CLOSE, lambda mm: "$" + self.math[int(mm.group(1))][0] + "$", body)
            out.append(f'<pre class="raw">{html.escape(txt.strip())}</pre>')
        elif base in ("figure", "table", "comment", "thebibliography"):
            pass
        else:
            out.append(self._text(body))
        return after

    def _block(self, s: str) -> str:
        txt = self._text(s)
        paras = [p.strip() for p in re.split(r"\n\s*\n|\ue002", txt) if p.strip()]
        if len(paras) <= 1:
            return paras[0] if paras else ""
        return "".join(f'<div class="para">{p}</div>' for p in paras)

    def _split_items(self, body: str) -> list[tuple[str | None, str]]:
        """Split a list body at top-level \\item."""
        items, depth, env_depth, i, n = [], 0, 0, 0, len(body)
        starts = []
        while i < n:
            c = body[i]
            if c == "\\":
                if body.startswith("\\begin", i):
                    env_depth += 1
                elif body.startswith("\\end", i):
                    env_depth -= 1
                elif depth == 0 and env_depth == 0 and re.match(r"\\item(?![A-Za-z])", body[i:]):
                    starts.append(i)
                i += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        for k, st in enumerate(starts):
            en = starts[k + 1] if k + 1 < len(starts) else n
            chunk = body[st + 5:en]
            lab, b = read_optional(chunk, 0)
            items.append((lab, chunk[b:] if lab is not None else chunk))
        return items


def inline(src: str, macros=None, ref=None) -> str:
    """Convert a short snippet (titles) without paragraph wrappers."""
    c = Converter(macros=macros, ref=ref)
    s = c._text(c.protect(src or ""))
    s = s.replace("\ue002", " ")
    return re.sub(PH_OPEN + r"(\d+)" + PH_CLOSE, lambda m: c._math_html(int(m.group(1))), s).strip()


def plain(src: str, macros: dict | None = None) -> str:
    """Rough plain-text rendering (graph labels, tooltips)."""
    c = Converter(macros=macros)
    s = c._text(c.protect(src or "")).replace("\ue002", " ")
    s = re.sub(PH_OPEN + r"(\d+)" + PH_CLOSE, lambda m: _plain_math(c.math[int(m.group(1))][0], macros), s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


GREEK = {k: v for k, v in zip(
    "alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi rho sigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega".split(),
    "α β γ δ ϵ ε ζ η θ ϑ ι κ λ μ ν ξ π ρ σ τ υ ϕ φ χ ψ ω Γ Δ Θ Λ Ξ Π Σ Φ Ψ Ω".split())}
MATH_SYM = {"le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "neq": "≠", "ne": "≠", "infty": "∞",
            "in": "∈", "subset": "⊂", "subseteq": "⊆", "times": "×", "cdot": "·", "to": "→",
            "pm": "±", "approx": "≈", "sim": "∼", "ell": "ℓ", "partial": "∂", "nabla": "∇",
            "sum": "Σ", "prod": "Π", "int": "∫", "cup": "∪", "cap": "∩", "emptyset": "∅",
            "forall": "∀", "exists": "∃", "mid": "|", "ldots": "…", "cdots": "⋯"}


def _plain_math(tex: str, macros: dict | None = None) -> str:
    for _ in range(3):  # expand argument-free user macros (\\ii -> \\mathrm{i})
        tex = re.sub(r"\\([A-Za-z]+)", lambda m: macros[m.group(1)] if isinstance((macros or {}).get(m.group(1)), str)
                     else m.group(0), tex)
    t = re.sub(r"\\(mathrm|mathbf|mathcal|mathbb|operatorname|text|mathsf|mathit|boldsymbol)\s*\{([^}]*)\}", r"\2", tex)
    t = re.sub(r"\\([A-Za-z]+)", lambda m: GREEK.get(m.group(1), MATH_SYM.get(m.group(1), "")), t)
    t = re.sub(r"_\{([^{}]*)\}|_(\w)", lambda m: _script(m.group(1) if m.group(1) is not None else m.group(2), True), t)
    t = re.sub(r"\^\{([^{}]*)\}|\^(\w|\*)", lambda m: _script(m.group(1) if m.group(1) is not None else m.group(2), False), t)
    t = t.replace("{", "").replace("}", "").replace("\\", "")
    return re.sub(r"\s+", " ", t).strip()


_SUB = dict(zip("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"))
_SUP = dict(zip("0123456789+-=()in*T", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁱⁿ*ᵀ"))


def _script(content: str, sub: bool) -> str:
    """x_{12} -> x₁₂ when Unicode has the glyphs, else x_12 / x^ab."""
    table = _SUB if sub else _SUP
    content = content.replace(" ", "")
    if content and all(c in table or c == "," for c in content):
        return "".join(table.get(c, c) for c in content)
    return ("_" if sub else "^") + content
