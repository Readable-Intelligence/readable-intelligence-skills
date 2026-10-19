"""Mechanical extraction of a dependency skeleton from a PDF.

Works best on LaTeX-generated PDFs.  Signals used, in order of reliability:
  * hyperref link annotations and named destinations (theorem.3.1, equation.12 …)
  * bold / small-caps headers "Lemma 3.2 (Title)." and italic "Proof." heads
  * amsthm QED boxes (drawn as four short strokes) to end proofs
  * textual references "Lemma 3.2", "Theorems 1.1 and 1.2", "(3.4)"
Statements come out as plain text with Unicode math; the agent is expected to
rewrite them in LaTeX (annotation `statement:`).
"""
from __future__ import annotations

import os
import re
import statistics

try:
    import pymupdf  # PyMuPDF >= 1.24
except ImportError:  # pragma: no cover
    try:
        import fitz as pymupdf  # type: ignore
    except ImportError as exc:
        raise SystemExit("PyMuPDF is required for PDF input: pip install pymupdf") from exc

from texparse import DEFINITION_KINDS, HIDDEN_KINDS, KIND_PREFIX

HEAD_KINDS = ("Theorem", "Lemma", "Task", "Proposition", "Corollary", "Definition", "Claim",
              "Conjecture", "Assumption", "Hypothesis", "Fact", "Observation", "Remark",
              "Example", "Notation", "Problem", "Question", "Exercise", "Axiom",
              "Construction", "Condition", "Convention", "Setting", "Property", "Principle",
              "Main Theorem", "Key Lemma")
NUM = r"(?:[A-Z]?\d+(?:\.\d+)*[a-z]?|[A-Z](?:\.\d+)*)"
HEAD_RE = re.compile(
    r"^(?P<kind>" + "|".join(sorted(HEAD_KINDS, key=len, reverse=True)) + r")"
    r"(?:\s+(?P<num>" + NUM + r"))?\s*(?P<rest>.*)$")
PROOF_RE = re.compile(r"^(?P<head>(?:(?:Completion|Conclusion|End|Continuation|Remainder|Rest|Second part)"
                      r"\s+of\s+the\s+)?[Pp]roof(?:\s+sketch)?|Sketch of (?:the )?proof)"
                      r"(?:\s+of\s+(?P<target>(?:[^.]|\.(?=\d)){1,80}?))?\s*(?:\(continued\))?\s*[.:](?!\d)")
TEXT_REF_RE = re.compile(
    r"\b(?P<kind>Theorem|Thm\.|Lemma|Lem\.|Proposition|Prop\.|Corollary|Cor\.|Definition|"
    r"Def\.|Defn\.|Claim|Conjecture|Assumption|Hypothesis|Fact|Observation|Remark|Example)"
    r"(?P<plural>s|ta)?\s+(?P<nums>" + NUM + r"(?:\s*(?:,|and|&|–|-|to)\s*" + NUM + r")*)")
QED_GLYPHS = {"\u25a1", "\u220e", "\u25a0", "\u25fb", "\u25fc", "\u2b1c", "\u2610", "\u2293"}
EQ_TAG_RE = re.compile(r"^\((" + NUM + r")\)$")
ABBR_KIND = {"thm.": "theorem", "lem.": "lemma", "prop.": "proposition", "cor.": "corollary",
             "def.": "definition", "defn.": "definition"}
MATH_FONT_HINTS = ("math", "cmmi", "cmsy", "cmex", "msam", "msbm", "rsfs", "eufm", "eusm",
                   "symbol", "stix", "cmbsy", "cmmib", "wasy", "dsrom", "bbm")
NONTHM_DEST = ("equation", "AMS", "cite", "page", "Doc-Start", "section", "subsection",
               "subsubsection", "chapter", "appendix", "part", "figure", "table", "Item",
               "Hfootnote", "footnote", "algorithm", "algocf", "lstlisting", "paragraph",
               "subfigure", "subtable", "enumi", "enumii", "enumiii", "mpfootnote")


def _font_class(span) -> str:
    f = span["font"].lower()
    if any(h in f for h in MATH_FONT_HINTS):
        return "math"
    if "bold" in f or "cmbx" in f or "black" in f or "heavy" in f or "semibold" in f or span["flags"] & 16:
        return "bold"
    if "csc" in f or "smallcaps" in f or "caps" in f:
        return "sc"
    if "ital" in f or "oblique" in f or "cmti" in f or "cmsl" in f or "slant" in f or span["flags"] & 2:
        return "italic"
    return "roman"


_CTRL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ufffd]")
_LIGATURES = {"\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi", "\ufb04": "ffl",
              "\ufb05": "ft", "\ufb06": "st", "\u00ad": ""}


def _norm(s: str) -> str:
    s = _CTRL.sub("", s)
    for a, b in _LIGATURES.items():
        s = s.replace(a, b)
    return s


class Line:
    __slots__ = ("page", "x0", "y0", "x1", "y1", "text", "spans", "classes", "size", "idx")

    def __init__(self, page, bbox, spans):
        self.page = page
        self.x0, self.y0, self.x1, self.y1 = bbox
        self.spans = spans
        self.text = _norm("".join(s["text"] for s in spans)).strip()
        self.classes = [(_font_class(s), len(s["text"].strip())) for s in spans]
        self.size = max((s["size"] for s in spans if s["text"].strip()), default=0)
        self.idx = -1

    def share(self, cls: str) -> float:
        tot = sum(n for _, n in self.classes) or 1
        return sum(n for c, n in self.classes if c == cls) / tot

    def first_class(self) -> str:
        for c, n in self.classes:
            if n:
                return c
        return "roman"


def _qed_boxes(page) -> list[tuple[float, float]]:
    """Positions (x, y) of amsthm-style QED squares (four short strokes or one small square)."""
    try:
        drawings = page.get_drawings()
    except Exception:  # pragma: no cover
        return []
    segs = [tuple(d["rect"]) for d in drawings if d["rect"].width <= 11 and d["rect"].height <= 11]
    boxes, used = [], [False] * len(segs)
    for i, (x0, y0, x1, y1) in enumerate(segs):
        if used[i]:
            continue
        used[i] = True
        members = 1
        for j in range(i + 1, len(segs)):
            a0, b0, a1, b1 = segs[j]
            if used[j]:
                continue
            nx0, ny0, nx1, ny1 = min(x0, a0), min(y0, b0), max(x1, a1), max(y1, b1)
            if nx1 - nx0 <= 11 and ny1 - ny0 <= 11:
                x0, y0, x1, y1 = nx0, ny0, nx1, ny1
                used[j] = True
                members += 1
        if 4 <= x1 - x0 <= 11 and 4 <= y1 - y0 <= 11:
            boxes.append((x1, (y0 + y1) / 2))
    return boxes


def extract_pdf(path: str, include_all: bool = False) -> dict:
    doc = pymupdf.open(path)
    try:
        names = doc.resolve_names()
    except Exception:  # pragma: no cover
        names = {}
    lines: list[Line] = []
    qed: list[tuple[int, float]] = []
    page_h = {}
    for pno, page in enumerate(doc):
        page_h[pno] = page.rect.height
        d = page.get_text("dict")
        for b in d["blocks"]:
            for l in b.get("lines", []):
                spans = [s for s in l["spans"] if s["text"]]
                if not spans or not "".join(s["text"] for s in spans).strip():
                    continue
                lines.append(Line(pno, l["bbox"], spans))
                for sp in spans:  # QED as a glyph (msam \square, \blacksquare, …)
                    if sp["text"].strip() in QED_GLYPHS:
                        qed.append((pno, (sp["bbox"][1] + sp["bbox"][3]) / 2))
        qed += [(pno, y) for _, y in _qed_boxes(page)]

    # merge visually identical-baseline fragments (PyMuPDF splits lines at math)
    merged: list[Line] = []
    for ln in lines:
        prev = merged[-1] if merged else None
        if prev and prev.page == ln.page and abs(prev.y1 - ln.y1) < 2.5 and ln.x0 >= prev.x1 - 1 \
                and ln.x0 - prev.x1 < 60:
            prev.spans += [{"text": " ", "font": "x", "flags": 0, "size": 0}] + ln.spans
            prev.text = _norm("".join(s["text"] for s in prev.spans)).strip()
            prev.classes += ln.classes
            prev.x1 = max(prev.x1, ln.x1)
            prev.y0 = min(prev.y0, ln.y0)
            continue
        merged.append(ln)
    lines = merged

    sizes = [s["size"] for ln in lines for s in ln.spans if s["text"].strip()]
    body = statistics.median(sizes) if sizes else 10
    # running heads / page numbers: identical short text on many pages at top/bottom
    edge_text: dict[str, int] = {}
    for ln in lines:
        if ln.y0 < 70 or ln.y1 > page_h[ln.page] - 60:
            key = re.sub(r"\d+", "#", ln.text)
            edge_text[key] = edge_text.get(key, 0) + 1
    def is_furniture(ln):
        if not (ln.y0 < 70 or ln.y1 > page_h[ln.page] - 60):
            return False
        key = re.sub(r"\d+", "#", ln.text)
        return re.fullmatch(r"[#\s–-]*", key) is not None or (edge_text.get(key, 0) >= 3 and len(ln.text) < 120)
    lines = [ln for ln in lines if not is_furniture(ln)]
    for i, ln in enumerate(lines):
        ln.idx = i

    # ---- theorem destinations (hyperref) ------------------------------------
    def dest_pos(info):
        p = info.get("page")
        to = info.get("to")
        if p is None or p < 0 or to is None:
            return None
        y = page_h.get(p, 792) - to[1]
        return p, y
    thm_dests = []
    eq_dests = {}
    for name, info in names.items():
        prefix = name.split(".", 1)[0]
        pos = dest_pos(info)
        if pos is None:
            continue
        if prefix in ("equation", "AMS"):
            eq_dests[name] = pos
        elif prefix.rstrip("*") not in NONTHM_DEST and "." in name:
            thm_dests.append((pos, name))

    # ---- classify lines ---------------------------------------------------------
    heads = {}  # line idx -> dict
    for i, ln in enumerate(lines):
        m = HEAD_RE.match(ln.text)
        if not m:
            continue
        fc = ln.first_class()
        near_dest = any(p == ln.page and -4 <= ln.y0 - y <= 30 for (p, y), _ in thm_dests)
        if fc not in ("bold", "sc") and not near_dest:
            continue
        rest = m.group("rest")
        title = None
        text_after = rest
        rest_full = rest
        j = i
        if rest.startswith("("):
            while rest_full.count("(") > rest_full.count(")") and j + 1 < len(lines) and j - i < 3:
                j += 1
                rest_full += " " + lines[j].text
            depth, k = 0, 0
            for k, ch in enumerate(rest_full):
                depth += ch == "("
                depth -= ch == ")"
                if depth == 0:
                    break
            title = rest_full[1:k].strip()
            text_after = rest_full[k + 1:]
        mm = re.match(r"\s*[.:]\s*", text_after)
        if not mm and not (m.group("num") and text_after.strip() == ""):
            # "Lemma 3.4 lets us ..." in running text that happens to be bold: reject
            if not (near_dest and fc in ("bold", "sc")):
                continue
        text_after = text_after[mm.end():] if mm else text_after
        kind = m.group("kind").split()[-1].lower()
        heads[i] = {"kind": kind, "display": m.group("kind"), "num": m.group("num"),
                    "title": title, "first_text": text_after.strip(), "span_to": j}

    proof_heads = {}
    for i, ln in enumerate(lines):
        m = PROOF_RE.match(ln.text)
        if m and ln.first_class() in ("italic", "bold", "sc"):
            proof_heads[i] = {"target": m.group("target"), "first_text": ln.text[m.end():].strip()}

    sec_heads = {}
    for i, ln in enumerate(lines):
        if i in heads or i in proof_heads:
            continue
        if ln.first_class() == "bold" and ln.share("bold") > 0.6 and ln.size >= body * 1.05 and len(ln.text) < 120:
            m = re.match(r"^((?:\d+|[A-Z])(?:\.\d+)*)\.?\s+(.*)$", ln.text)
            if m:
                sec_heads[i] = {"number": m.group(1), "title": m.group(2)}
            elif re.fullmatch(r"(?:\d+|[A-Z])(?:\.\d+)*", ln.text) and i + 1 < len(lines):
                sec_heads[i] = {"number": ln.text, "title": lines[i + 1].text}
            elif re.match(r"^(Appendix|References|Bibliography|Acknowledg)", ln.text):
                sec_heads[i] = {"number": "", "title": ln.text}
    # absorb the title line of split section headings
    for i in list(sec_heads):
        if sec_heads[i]["title"] == (lines[i + 1].text if i + 1 < len(lines) else None) and \
                re.fullmatch(r"(?:\d+|[A-Z])(?:\.\d+)*", lines[i].text):
            sec_heads.pop(i + 1, None)

    # equation tags at the margins
    eq_tags = []  # (page, y, number, line idx)
    left_tags = []
    for i, ln in enumerate(lines):
        w = doc[ln.page].rect.width
        for s in ln.spans:
            t = s["text"].strip()
            mm = EQ_TAG_RE.match(t)
            if mm and "bbox" in s:
                tag = (ln.page, (s["bbox"][1] + s["bbox"][3]) / 2, mm.group(1), i)
                if s["bbox"][0] > 0.72 * w:
                    eq_tags.append(tag)
                elif s["bbox"][2] < 0.28 * w:
                    left_tags.append(tag)
    # left-margin tags only for leqno documents; otherwise they are list items "(1) …"
    if not eq_tags:
        eq_tags = left_tags
    eq_tags = sorted(set(eq_tags))

    # ---- segmentation -------------------------------------------------------------
    nodes: list[dict] = []
    regions: list[dict] = []  # {node, part, start, end}
    state = None  # current region
    section = {"number": "", "title": ""}
    line_gaps = [lines[i + 1].y0 - lines[i].y0 for i in range(len(lines) - 1)
                 if lines[i + 1].page == lines[i].page and 0 < lines[i + 1].y0 - lines[i].y0 < 3 * body]
    normal_gap = statistics.median(line_gaps) if line_gaps else body * 1.25
    qed_set = sorted(qed)

    def close(i):
        nonlocal state
        if state is not None:
            state["end"] = i
            regions.append(state)
            state = None

    # A QED box ends the proof on the line it sits on, or, when the proof ends with a
    # display, it sits alone between this line and the next one.
    qed_after = [False] * len(lines)
    for i, ln in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        hi = nxt.y0 - 1 if nxt is not None and nxt.page == ln.page else page_h[ln.page]
        qed_after[i] = any(p == ln.page and ln.y0 - 3 <= y <= max(hi, ln.y1 + 3) for p, y in qed_set)

    def has_qed(ln):
        return qed_after[ln.idx]

    def math_heavy(ln):
        return ln.share("math") > 0.35 or len(re.sub(r"[\W\d_]", "", ln.text)) < 0.4 * max(len(ln.text), 1)

    last_node = None
    for i, ln in enumerate(lines):
        if i in sec_heads:
            close(i)
            section = sec_heads[i]
            continue
        if i in heads:
            close(i)
            h = heads[i]
            node = {"kind": h["kind"], "display": h["display"], "number": h["num"],
                    "title": h["title"], "page": ln.page + 1, "line": i,
                    "section": section.get("number") or None,
                    "section_title": section.get("title") or None, "y": ln.y0,
                    "first_text": h["first_text"], "skip_to": h["span_to"]}
            nodes.append(node)
            last_node = node
            state = {"node": node, "part": "statement", "start": i, "italic": None}
            continue
        if i in proof_heads:
            close(i)
            ph = proof_heads[i]
            target = None
            if ph["target"]:
                mm = re.search(r"(" + "|".join(HEAD_KINDS) + r")\s+(" + NUM + r")", ph["target"])
                if mm:
                    for nd in nodes:
                        if nd["number"] == mm.group(2) and nd["kind"] == mm.group(1).split()[-1].lower():
                            target = nd
                    if target is None:
                        target = {"pending": (mm.group(1).split()[-1].lower(), mm.group(2))}
            if target is None:
                target = last_node
            state = {"node": target, "part": "proof", "start": i, "first_text": ph["first_text"]}
            if has_qed(ln):
                close(i + 1)
            continue
        if state is None:
            continue
        if state["part"] == "proof":
            if has_qed(ln):
                close(i + 1)
            continue
        # statement: decide where it ends
        if i <= state["node"]["skip_to"]:
            continue
        prev = lines[i - 1]
        if state["italic"] is None:
            it, ro = ln.share("italic"), ln.share("roman")
            state["italic"] = it > ro
        if state["italic"]:
            if ln.share("roman") > 0.55 and ln.share("italic") < 0.15 and not math_heavy(ln):
                close(i)
                continue
        else:
            gap = ln.y0 - prev.y0 if ln.page == prev.page else 0
            if gap > 1.6 * normal_gap and not math_heavy(ln) and not math_heavy(prev):
                close(i)
                continue
    close(len(lines))

    # resolve pending proof targets
    by_kn = {(nd["kind"], nd["number"]): nd for nd in nodes if nd["number"]}
    by_n = {}
    for nd in nodes:
        if nd["number"]:
            by_n.setdefault(nd["number"], nd)
    for r in regions:
        if isinstance(r["node"], dict) and "pending" in r["node"]:
            k, n = r["node"]["pending"]
            r["node"] = by_kn.get((k, n)) or by_n.get(n)

    # ---- ids --------------------------------------------------------------------
    used = set()
    for k, nd in enumerate(nodes):
        pre = KIND_PREFIX.get(nd["kind"], nd["kind"][:4])
        nid = f"{pre}:{nd['number']}" if nd["number"] else f"{pre}:p{nd['page']}"
        base, c = nid, 2
        while nid in used:
            nid = f"{base}-{c}"
            c += 1
        used.add(nid)
        nd["id"] = nid

    # map line idx -> region
    line_region = {}
    for r in regions:
        if r["node"] is None:
            continue
        for i in range(r["start"], r["end"]):
            line_region[i] = r

    def region_at(page, y):
        """Region containing a point; falls back to the nearest preceding line."""
        best = None
        for ln in lines:
            if ln.page == page and ln.y0 - 2 <= y <= ln.y1 + 2:
                best = ln
                break
        if best is None:
            cands = [ln for ln in lines if ln.page == page and ln.y0 <= y + 2]
            best = cands[-1] if cands else None
        return (line_region.get(best.idx), best) if best else (None, None)

    # theorem destination name -> node
    dest_node = {}
    for (p, y), name in thm_dests:
        cands = [nd for nd in nodes if nd["page"] - 1 == p and -4 <= nd["y"] - y <= 40]
        if cands:
            dest_node[name] = min(cands, key=lambda nd: abs(nd["y"] - y))["id"]

    labels: dict[str, dict] = {}
    for nd in nodes:
        labels[nd["id"]] = {"type": "node", "node": nd["id"], "number": nd["number"],
                            "kind": nd["kind"], "display": nd["display"]}
    for name, nid in dest_node.items():
        labels[name] = {"type": "node", "node": nid}
    # equations: from tags and from named dests
    eq_index = {}
    for p, y, num, li in eq_tags:
        r = line_region.get(li)
        key = f"eq:({num})"
        rec = {"type": "equation", "number": num, "page": p + 1, "para_pos": [p, round(y - 80, 1)]}
        if r is not None and r["node"] is not None:
            rec.update(node=r["node"]["id"], part=r["part"])
        else:
            rec["context"] = " ".join(lines[k].text for k in range(max(0, li - 3), min(len(lines), li + 2)))
        labels[key] = rec
        eq_index[(p, round(y))] = key
    # hyperref puts the anchor above the display (by up to ~70pt); match anchors to tags in
    # reading order: each anchor takes the first unused tag below it on the same page.
    dest_tag, used_tags, pos_tag = {}, set(), {}
    for name, (p, y) in sorted(eq_dests.items(), key=lambda kv: (kv[1][0], kv[1][1])):
        key = (p, round(y))
        if key in pos_tag:
            dest_tag[name] = pos_tag[key]
            continue
        tag = next((t for t in eq_tags if t[0] == p and t[1] >= y - 5 and t not in used_tags), None)
        if tag is not None:
            used_tags.add(tag)
        dest_tag[name] = pos_tag[key] = tag
    for name, (p, y) in eq_dests.items():
        tag = dest_tag.get(name)
        r, ln = region_at(p, tag[1]) if tag else region_at(p, y + 6)
        rec = {"type": "equation", "number": tag[2] if tag else None, "page": p + 1,
               "para_pos": [p, round((tag[1] if tag else y) - 80, 1)]}
        if r is not None and r["node"] is not None:
            rec.update(node=r["node"]["id"], part=r["part"])
        elif ln is not None:
            rec["context"] = " ".join(lines[k].text for k in range(max(0, ln.idx - 3), min(len(lines), ln.idx + 2)))
        labels[name] = rec

    # ---- references ----------------------------------------------------------------
    refs = {nd["id"]: {"statement": [], "proof": []} for nd in nodes}
    prose_refs = []
    n_internal_links = 0
    cites = {nd["id"]: {"statement": [], "proof": []} for nd in nodes}
    cite_dest: dict[str, dict] = {}
    for pno, page in enumerate(doc):
        for lk in page.get_links():
            name = lk.get("nameddest") or lk.get("name")
            if lk.get("kind") not in (pymupdf.LINK_NAMED, pymupdf.LINK_GOTO):
                continue
            if not name and lk.get("kind") == pymupdf.LINK_GOTO:
                to = lk.get("to")
                tp = lk.get("page")
                if to is None or tp is None:
                    continue
                r2, _ = region_at(tp, to.y if hasattr(to, "y") else to[1])
                name = None
                target_node = r2["node"]["id"] if r2 and r2["node"] else None
            elif name and name.startswith("cite."):
                rect = lk["from"]
                r, _ln = region_at(pno, (rect.y0 + rect.y1) / 2)
                ckey = name[5:]
                cite_dest[ckey] = names.get(name, {})
                if r is not None and r["node"] is not None:
                    cites[r["node"]["id"]][r["part"]].append(ckey)
                continue
            else:
                if not name or name.split(".", 1)[0] in ("cite", "page", "Doc-Start", "section",
                                                          "subsection", "subsubsection", "chapter",
                                                          "appendix", "figure", "table", "Hfootnote"):
                    continue
                target_node = None
            n_internal_links += 1
            rect = lk["from"]
            r, ln = region_at(pno, (rect.y0 + rect.y1) / 2)
            key = name or (target_node and target_node)
            if not key:
                continue
            if name and name not in labels:
                # e.g. Item.3 destinations: attribute to whatever region holds them
                pos = dest_pos(names.get(name, {}))
                if pos:
                    r3, ln3 = region_at(*pos)
                    if r3 is not None and r3["node"] is not None:
                        labels[name] = {"type": "inner", "node": r3["node"]["id"], "part": r3["part"]}
                    else:
                        labels[name] = {"type": "prose"}
            if r is not None and r["node"] is not None:
                refs[r["node"]["id"]][r["part"]].append(key)
            elif ln is not None:
                prose_refs.append({"label": key, "cmd": "link", "loc": {"page": pno + 1},
                                   "context": ln.text[:300]})

    def region_text(r):
        out = []
        for i in range(r["start"], r["end"]):
            out.append(lines[i].text)
        return out

    def textual_refs(text):
        found = []
        for m in TEXT_REF_RE.finditer(text):
            kind = m.group("kind").lower()
            kind = ABBR_KIND.get(kind, kind)
            for num in re.findall(NUM, m.group("nums")):
                nd = by_kn.get((kind, num)) or by_n.get(num)
                if nd:
                    found.append(nd["id"])
        if n_internal_links < 5:  # no hyperref: fall back to "(3.4)"-style equation refs
            for m in re.finditer(r"\((" + NUM + r")\)", text):
                key = f"eq:({m.group(1)})"
                if key in labels:
                    found.append(key)
        return found

    for r in regions:
        if r["node"] is None:
            continue
        txt = " ".join(region_text(r)[1:] if r["part"] == "statement" else region_text(r))
        if r["part"] == "statement":
            txt = (r["node"].get("first_text") or "") + " " + txt
        refs[r["node"]["id"]][r["part"]] += [x for x in textual_refs(txt) if x != r["node"]["id"]]

    # ---- references: entry text at each cite destination (hyperref), else "[12]" parsing ----
    references: dict[str, dict] = {}

    def entry_text_at(p, y):
        cand = [ln for ln in lines if ln.page == p and ln.y1 >= y - 2]
        cand.sort(key=lambda ln: ln.y0)
        txt = []
        for k, ln in enumerate(cand[:6]):
            if k and (REF_ENTRY_START.match(ln.text) or ln.x0 < cand[0].x0 - 2):
                break
            txt.append(ln.text)
        return " ".join(txt)
    for ckey, info in cite_dest.items():
        pos = dest_pos(info) if info else None
        text = entry_text_at(*pos) if pos else ""
        references[ckey] = _pdf_ref_record(ckey, text)
    if not cite_dest:
        ref_start = next((i for i in sorted(sec_heads) if re.match(r"(?i)(references|bibliography)",
                                                                   sec_heads[i]["title"] or "")), None)
        if ref_start is not None:
            cur, buf = None, []
            for ln in lines[ref_start + 1:]:
                m = REF_ENTRY_START.match(ln.text)
                if m:
                    if cur:
                        references[cur] = _pdf_ref_record(cur, " ".join(buf))
                    cur, buf = m.group(1), [ln.text[m.end():]]
                elif cur:
                    buf.append(ln.text)
            if cur:
                references[cur] = _pdf_ref_record(cur, " ".join(buf))
        if references:
            for r in regions:
                if r["node"] is None:
                    continue
                txt = " ".join(region_text(r))
                for m in re.finditer(r"\[([^\[\]]{1,40})\]", txt):
                    for key in re.split(r"\s*[,;]\s*", m.group(1)):
                        key = re.sub(r",?\s*(Thm|Theorem|Lemma|Sec|Section|Prop|Cor|Eq|p)\.?.*$", "", key).strip()
                        if key in references:
                            cites[r["node"]["id"]][r["part"]].append(key)

    # ---- assemble ---------------------------------------------------------------
    def join_lines(ls):
        out = ""
        for t in ls:
            if out.endswith("-") and t[:1].islower():
                out = out[:-1] + t
            elif out:
                out += "\n" + t
            else:
                out = t
        return out

    stmt_text = {nd["id"]: "" for nd in nodes}
    proof_text: dict[str, list[str]] = {nd["id"]: [] for nd in nodes}
    proof_pages: dict[str, list[int]] = {nd["id"]: [] for nd in nodes}
    for r in regions:
        nd = r["node"]
        if nd is None:
            continue
        ls = region_text(r)
        if r["part"] == "statement":
            first = nd.get("first_text") or ""
            body_lines = ls[nd["skip_to"] - r["start"] + 1:]
            stmt_text[nd["id"]] = join_lines(([first] if first else []) + body_lines)
        else:
            first = r.get("first_text") or ""
            proof_text[nd["id"]].append(join_lines(([first] if first else []) + ls[1:]))
            proof_pages[nd["id"]] += sorted({lines[i].page + 1 for i in range(r["start"], r["end"])})

    referenced = set()
    for nid, rr in refs.items():
        for part in rr.values():
            for key in part:
                tgt = labels.get(key, {}).get("node")
                if tgt and tgt != nid:
                    referenced.add(tgt)

    out_nodes = []
    for nd in nodes:
        nid = nd["id"]
        pages = sorted(set([nd["page"]] + proof_pages[nid]))
        out_nodes.append({
            "id": nid, "env": nd["kind"], "kind": nd["kind"], "display": nd["display"].split()[-1]
            if nd["display"] not in ("Main Theorem", "Key Lemma") else nd["display"],
            "number": nd["number"], "title": nd["title"], "label": None,
            "section": nd["section"], "section_title": nd["section_title"],
            "statement": stmt_text[nid], "statement_format": "text",
            "proof": "\n\n".join(p for p in proof_text[nid] if p) or None, "proof_format": "text",
            "refs": {"statement": _dedup(refs[nid]["statement"]), "proof": _dedup(refs[nid]["proof"])},
            "explicit_uses": {"statement": [], "proof": []},
            "cites": {"statement": _dedup(cites[nid]["statement"]), "proof": _dedup(cites[nid]["proof"])},
            "parent": None, "loc": {"page": nd["page"], "pages": pages},
            "pos": [nd["page"] - 1, round(nd["y"], 1)],
            "hidden": nd["kind"] in HIDDEN_KINDS and nid not in referenced and not include_all,
            "shape": "box" if nd["kind"] in DEFINITION_KINDS else "ellipse",
        })

    from symbols import build_index_pdf

    def line_owner(i):
        r = line_region.get(i)
        return (r["node"]["id"], r["part"]) if r is not None and r["node"] is not None else None
    symbol_index = build_index_pdf(lines, line_owner)

    meta = doc.metadata or {}
    title = (meta.get("title") or "").strip()
    if not title and lines:
        first_page = [ln for ln in lines if ln.page == 0]
        if first_page:
            big = max(ln.size for ln in first_page)
            title = " ".join(ln.text for ln in first_page if ln.size >= big - 0.5)
    abstract = ""
    for i, ln in enumerate(lines[:400]):
        if re.match(r"^\s*Abstract\b", ln.text):
            buf = [ln.text[len("Abstract"):].lstrip(" .:—")]
            for ln2 in lines[i + 1:i + 60]:
                if ln2.idx in sec_heads or ln2.idx in heads:
                    break
                buf.append(ln2.text)
            abstract = join_lines([b for b in buf if b]).replace("\n", " ")
            break
    sections = []
    for i in sorted(sec_heads):
        sections.append({"number": sec_heads[i]["number"], "title": sec_heads[i]["title"],
                         "page": lines[i].page + 1})

    return {
        "format": "paper-blueprint/extracted@1",
        "source": {"type": "pdf", "path": os.path.abspath(path), "main": os.path.abspath(path),
                   "pages": doc.page_count, "hyperref": bool(thm_dests),
                   "qed_boxes": len(qed)},
        "title": title,
        "authors": (meta.get("author") or "").strip(),
        "abstract": abstract,
        "macros": {},
        "mathjax_packages": [],
        "theorem_envs": {},
        "sections": sections,
        "nodes": out_nodes,
        "labels": labels,
        "prose_refs": prose_refs[:400],
        "references": references,
        "bibliography": {k: v["label"] for k, v in references.items()},
        "arxiv_mentioned": sorted({m.group(1) for ln in lines for m in ARXIV_ANY_RE.finditer(ln.text)}),
        "symbol_index": symbol_index,
        "orphan_proofs": [],
    }


REF_ENTRY_START = re.compile(r"^\s*\[([A-Za-z0-9+\-]{1,14})\]\s*")


def _pdf_ref_record(key: str, text: str) -> dict:
    text = re.sub(r"\s+", " ", REF_ENTRY_START.sub("", text or "")).strip()[:300]
    a = ARXIV_ANY_RE.search(text)
    d = re.search(r"(?i)\b(10\.\d{4,9}/[^\s,;]+)", text)
    label = key if not key.isdigit() else key
    return {"label": label, "text": text, "arxiv": a.group(1) if a else None,
            "doi": d.group(1).rstrip(".") if d else None}


def _dedup(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


ARXIV_STAMP_RE = re.compile(r"arXiv:\s*((?:\d{4}\.\d{4,5})|(?:[a-z\-]+(?:\.[A-Z]{2})?/\d{7}))(v\d+)?\s+\[[^\]]+\]")
ARXIV_ANY_RE = re.compile(r"arXiv:\s*((?:\d{4}\.\d{4,5})|(?:[a-z\-]+(?:\.[A-Z]{2})?/\d{7}))(v\d+)?")


def probe_pdf(path: str) -> dict:
    """Cheap facts about a PDF that decide whether to ask for the LaTeX source."""
    doc = pymupdf.open(path)
    meta = doc.metadata or {}
    producer = f"{meta.get('producer') or ''} {meta.get('creator') or ''}".strip()
    latex = bool(re.search(r"(?i)tex|xdvipdfmx|dvipdf|arxiv genpdf|hyperref", producer))
    own_id = None
    if doc.page_count:
        page = doc[0]
        # the arXiv stamp is a rotated line in the left margin: "arXiv:2505.12615v1 [quant-ph] 19 May 2025"
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                text = "".join(s["text"] for s in ln["spans"])
                m = ARXIV_STAMP_RE.search(text)
                if m and (abs(ln["dir"][0]) < 0.5 or own_id is None):
                    own_id = m.group(1) + (m.group(2) or "")
    cited = []
    for pno in range(min(doc.page_count, 3)):
        for m in ARXIV_ANY_RE.finditer(doc[pno].get_text()):
            if own_id is None or not own_id.startswith(m.group(1)):
                cited.append(m.group(1))
    try:
        names = doc.resolve_names()
    except Exception:  # pragma: no cover
        names = {}
    hyperref = any(n.split(".", 1)[0] not in ("Doc-Start", "page", "cite", "section", "subsection")
                   for n in names)
    return {"pages": doc.page_count, "title": (meta.get("title") or "").strip(), "producer": producer,
            "latex": latex, "hyperref": hyperref, "arxiv_id": own_id,
            "arxiv_cited": sorted(set(cited))}
