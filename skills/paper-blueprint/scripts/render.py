"""Render the merged model as a Lean-blueprint-style dependency graph page."""
from __future__ import annotations

import html
import json
import os
import re
import textwrap
import urllib.request

import latex2html
from model import Model

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")

CDN = {
    "d3": "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js",
    "d3-graphviz": "https://cdn.jsdelivr.net/npm/d3-graphviz@5.6.0/build/d3-graphviz.min.js",
    "mathjax": "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg.js",
    "mathjax-full": "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg-full.js",
}

# Sequential palettes, light -> dark; index 0 = importance 1, index 4 = importance 5.
PALETTES = {
    "blues": ["#eef4fb", "#c6dbef", "#6baed6", "#2171b5", "#08306b"],
    "reds": ["#fff0e8", "#fcbba1", "#fb6a4a", "#cb181d", "#67000d"],
    "oranges": ["#fff3e6", "#fdd0a2", "#fd8d3c", "#d94801", "#7f2704"],
    "greens": ["#f0f9ec", "#c7e9c0", "#74c476", "#238b45", "#00441b"],
    "purples": ["#f6f4fa", "#dadaeb", "#9e9ac8", "#6a51a3", "#3f007d"],
    "greys": ["#f7f7f7", "#d9d9d9", "#969696", "#525252", "#141414"],
    "viridis": ["#fde725", "#5ec962", "#21918c", "#3b528b", "#440154"],
}
LEVEL_NAMES = {1: "background / routine", 2: "technical", 3: "supporting",
               4: "key step", 5: "main result / central idea"}
# Novelty border of the key results (importance >= 4): white (known) -> deep red; index 0 = novelty 1.
NOVELTY_REDS = ["#ffffff", "#f8b4b4", "#ef6461", "#d01c1f", "#860010"]
NOVELTY_PENWIDTH = "4"
NOVELTY_NAMES = {1: "known", 2: "routine variant", 3: "new combination",
                 4: "substantially new", 5: "no close precedent"}
UI = {
    "en": {
        "page": "dependency graph", "search": "Find a result…", "edges": "all edges",
        "edges_tip": "leanblueprint shows the transitive reduction; tick to show every recorded dependency",
        "fit": "fit", "fit_tip": "Reset zoom", "loading": "Laying out the graph…", "close": "Close (Esc)",
        "legend": "Legend", "boxes": "Boxes", "boxes_dd": "definitions (and assumptions, notation)",
        "ellipses": "Ellipses", "ellipses_dd": "theorems, lemmas, propositions, corollaries, claims",
        "double": "Double border", "double_dd": "main result(s) of the paper",
        "dashed": "Dashed arrow", "dashed_dd": "used in the <em>statement</em>",
        "solid": "Solid arrow", "solid_dd": "used in the <em>proof</em>",
        "fill": "Fill colour", "fill_dd": "importance for the paper's main argument, as judged by the "
                                       "reading agent (darker = more crucial):",
        "click": "Click", "click_dd": "a node to read its statement; drag to pan, scroll to zoom",
        "results": "results", "importance": "Importance", "not_rated": "importance not rated",
        "used_stmt": "used in the statement", "used_proof": "used in the proof", "main": "main result",
        "no_statement": "(no statement)", "why": "Why this matters", "role": "Role in the argument",
        "sketch": "Proof sketch", "proof": "Proof", "proof_pdf": "Proof (text extracted from the PDF)",
        "uses": "Uses", "used_by": "Used by", "nothing": "nothing in this graph",
        "cone": "show dependency cone", "cone_on": "showing dependency cone", "up": "up", "down": "down",
        "centre": "centre in graph", "unrated": "not rated",
        "context": "Notation in force (added by the blueprint)", "notation_here": "Notation used here",
        "glossary": "Notation", "glossary_tip": "Paper-wide notation", "glossary_empty": "No notation table.",
        "novelty": "Novelty", "novelty_hd": "Novelty (literature search)",
        "unverified": "locator not verified",
        "border": "Border colour", "border_dd": "novelty of a key result (importance 4–5) relative to the "
                                                "literature, in its statement and its proof technique, judged "
                                                "from a literature search (white = known, deeper red = more "
                                                "novel):",
        "searched": "literature searched",
        "levels": LEVEL_NAMES, "novelty_levels": NOVELTY_NAMES,
    },
}


def legend_html(ui: dict, pal: list[str], novelty: bool = False, novelty_date: str = "") -> str:
    rows = [("boxes", "boxes_dd"), ("ellipses", "ellipses_dd"), ("double", "double_dd"),
            ("dashed", "dashed_dd"), ("solid", "solid_dd"), ("fill", "fill_dd")]
    out = [f'    <span id="legend_title" class="title">{html.escape(ui["legend"])}',
           '      <div class="btn"><div class="bar"></div><div class="bar"></div><div class="bar"></div></div>',
           '    </span>', '    <dl class="legend">']
    for k, v in rows:
        out.append(f"      <dt>{html.escape(ui[k])}</dt><dd>{ui[v]}</dd>")
    scale = "".join(
        f'<span class="swatch" style="background:{pal[i - 1]}"></span>'
        f'<span class="swatch-label">{i} – {html.escape(ui["levels"][i])}</span><br>' for i in range(5, 0, -1))
    out.append(f'      <div class="scale">{scale}<span class="swatch" style="background:#fff;border-style:dashed">'
               f'</span><span class="swatch-label">{html.escape(ui["unrated"])}</span></div>')
    if novelty:
        dd = ui["border_dd"]
        if novelty_date:  # "… (deeper red = more novel; literature searched 2026-10-26):"
            dd = dd.rstrip(":").rstrip(")") + f"; {html.escape(ui['searched'])} {html.escape(novelty_date)}):"
        out.append(f"      <dt>{html.escape(ui['border'])}</dt><dd>{dd}</dd>")
        # drawn on a key-result fill, as in the graph, so that the white border of level 1 shows
        scale = "".join(
            f'<span class="swatch" style="background:{pal[3]};border:3px solid {NOVELTY_REDS[i - 1]}"></span>'
            f'<span class="swatch-label">{i} – {html.escape(ui["novelty_levels"][i])}</span><br>'
            for i in range(5, 0, -1))
        out.append(f'      <div class="scale">{scale}</div>')
    out.append(f"      <dt>{html.escape(ui['click'])}</dt><dd>{ui['click_dd']}</dd>")
    out.append("    </dl>")
    return "\n".join(out)
ABBREV = {"theorem": "Thm", "lemma": "Lem", "proposition": "Prop", "corollary": "Cor",
          "definition": "Def", "claim": "Claim", "conjecture": "Conj", "assumption": "Asm",
          "remark": "Rem", "example": "Ex", "notation": "Not", "observation": "Obs",
          "fact": "Fact", "hypothesis": "Hyp"}


# ---------------------------------------------------------------------------
# colours
# ---------------------------------------------------------------------------

def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _mix(a: str, b: str, t: float) -> str:
    ra, ga, ba = _hex(a)
    rb, gb, bb = _hex(b)
    return "#%02x%02x%02x" % (round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t))


def _luminance(c: str) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _hex(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def importance_colors(imp, palette: list[str]) -> tuple[str, str, str]:
    """(fill, font colour, border) for an importance value in [1, 5] or None."""
    if imp is None:
        return "#ffffff", "#24292e", "#9a9a9a"
    v = min(5.0, max(1.0, float(imp)))
    lo = int(v) - 1
    t = v - int(v)
    fill = palette[lo] if lo >= 4 else _mix(palette[lo], palette[lo + 1], t)
    font = "#ffffff" if _luminance(fill) < 0.25 else "#1b1f23"
    return fill, font, palette[4] if v < 4 else "#1b1f23"


def _num(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def novelty_color(nov) -> str | None:
    """Border colour for a novelty value in [1, 5] (deeper red = more novel); None if not assessed."""
    v = _num(nov)
    if v is None:
        return None
    v = min(5.0, max(1.0, v))
    lo = int(v) - 1
    return NOVELTY_REDS[lo] if lo >= 4 else _mix(NOVELTY_REDS[lo], NOVELTY_REDS[lo + 1], v - int(v))


def novelty_note_html(note, refs, conv, ui: dict) -> str:
    """The note as HTML, with the paragraph labels "Statement" and "Technique" in italics; its inline
    \\href citations whose `novelty_refs` entry is unverified get a mark."""
    if not note:
        return ""
    out = re.sub(r'(^|<div class="para">)\s*(Statement|Technique):', r"\1<em>\2</em>:", conv(note))
    for r in refs if isinstance(refs, list) else []:
        if isinstance(r, dict) and r.get("verified") is False and r.get("url"):
            link = r'(<a href="' + re.escape(html.escape(str(r["url"]))) + r'"[^>]*>.*?</a>)'
            out = re.sub(link, r'\1<span class="unverified"> (' + html.escape(ui["unverified"]) + ")</span>", out)
    return out


# ---------------------------------------------------------------------------
# DOT
# ---------------------------------------------------------------------------

def _dot_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def node_label(m: Model, nid: str, style: str, macros: dict) -> str:
    n = m.nodes[nid]
    if n.get("short"):  # plain text; $...$ math is flattened to Unicode
        return "\n".join(latex2html.plain(x, macros) for x in str(n["short"]).replace("\\n", "\n").split("\n"))
    if style == "id":  # exactly what leanblueprint shows
        return nid.split(":")[-1]
    kind = n.get("kind") or ""
    display = n.get("display") or kind.capitalize()
    # abbreviate the standard names only; an explicit custom `display` is kept as written
    name = ABBREV.get(kind, display) if display.lower() == kind else display
    head = f"{name} {n['number']}" if n.get("number") else display
    title = latex2html.plain(n.get("title") or "", macros)
    if style == "number" or not title:
        return head if (n.get("number") or not title) else title
    if style == "title":
        return "\n".join(textwrap.wrap(title, 22)[:3])
    lines = textwrap.wrap(title, 24)
    if len(lines) > 2:
        lines = lines[:2]
        lines[1] = lines[1].rstrip(" ,.;:") + "…"
    return head + "\n" + "\n".join(lines)


def build_dot(m: Model, edges: dict, palette: list[str], label_style: str, macros: dict,
              rankdir: str = "TB") -> str:
    out = ['strict digraph "" {',
           f'  graph [bgcolor=transparent, rankdir={rankdir}, nodesep=0.35, ranksep=0.55];',
           '  node [penwidth=1.8, style=filled, fontsize=13, margin="0.12,0.06"];',
           '  edge [arrowhead=vee, color="#4b5563", penwidth=1.1];']
    for nid in m.visible:
        n = m.nodes[nid]
        fill, font, border = importance_colors(n.get("importance"), palette)
        attrs = {
            "label": node_label(m, nid, label_style, macros),
            "shape": n.get("shape") or "ellipse",
            "fillcolor": fill, "fontcolor": font, "color": border,
        }
        if n.get("main"):
            attrs["peripheries"] = "2"
        nov = novelty_color(n.get("novelty"))
        if nov:
            attrs["color"] = nov
            attrs["penwidth"] = NOVELTY_PENWIDTH
        if n.get("importance") is None:
            attrs["style"] = "filled,dashed"
        out.append(f"  {_dot_str(nid)} [" + ", ".join(f"{k}={_dot_str(str(v))}" for k, v in attrs.items()) + "];")
    order = {nid: i for i, nid in enumerate(m.visible)}
    for (a, b), part in sorted(edges.items(), key=lambda e: (order[e[0][1]], order[e[0][0]])):
        style = " [style=dashed]" if part == "statement" else ""
        out.append(f"  {_dot_str(a)} -> {_dot_str(b)}{style};")
    out.append("}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def _bib_map(ex: dict) -> dict:
    return ex.get("bibliography") or {}


def make_converter_factory(m: Model):
    ex = m.ex
    macros = m.macros
    bib = _bib_map(ex)
    visible = set(m.visible)

    def ref(label: str, cmd: str) -> str:
        nid = m.resolve(label)
        info = m.label_info.get(label, {})
        own = nid is not None and (label == nid or info.get("type", "node") == "node"
                                   or label in m.nodes[nid].get("ann_aliases", []))
        if own and info.get("type") not in ("equation", "item", "inner"):
            n = m.nodes[nid]
            num = n.get("number")
            if cmd in ("ref", "eqnum", "subref") and num:
                txt = num
            elif cmd.startswith("hyperref:"):
                txt = cmd.split(":", 1)[1] or m.label_text(nid)
            elif cmd in ("nameref", "Nameref") and n.get("title"):
                txt = latex2html.plain(n["title"], macros)
            else:
                txt = m.label_text(nid)
        else:
            num = info.get("number")
            typ = info.get("type")
            if typ == "equation":
                txt = f"({num})" if cmd in ("eqref", "cref", "Cref", "autoref", "Autoref") and num else (num or "??")
                if cmd == "eqnum":
                    txt = num or "??"
            elif typ == "section":
                txt = (f"Section {num}" if cmd in ("cref", "Cref", "autoref", "Autoref") else num) or "??"
            else:
                txt = num or "??"
        txt = html.escape(txt)
        if nid in visible:
            return f'<a class="bp-ref" data-node="{html.escape(nid)}">{txt}</a>'
        return f'<span class="bp-ref-plain" title="{html.escape(label)}">{txt}</span>'

    def cite(keys, note):
        labs = [str(bib.get(k, k)) for k in keys]
        return "[" + ", ".join(labs) + (", " + note if note else "") + "]"

    def conv(src: str | None) -> str:
        if not src:
            return ""
        c = latex2html.Converter(macros=macros, ref=ref, cite=cite,
                                 theorem_envs=ex.get("theorem_envs") or {})
        return c.convert(src)

    def conv_inline(src: str | None) -> str:
        if not src:
            return ""
        return latex2html.inline(src, macros=macros, ref=ref)

    return conv, conv_inline


def text_to_html(s: str) -> str:
    paras = [p.strip() for p in re.split(r"\n\s*\n", s or "") if p.strip()]
    return "".join(f'<div class="para raw-text">{html.escape(p)}</div>' for p in paras)


def mathjax_config(ex: dict, macros: dict, inline_assets: bool) -> str:
    pk = [p for p in ex.get("mathjax_packages") or [] if p]
    cfg = {
        "tex": {
            "inlineMath": [["\\(", "\\)"]],
            "displayMath": [["\\[", "\\]"]],
            "processEscapes": True,
            "processEnvironments": True,
            "tags": "none",
            "macros": macros,
        },
        "svg": {"fontCache": "global"},
        "startup": {"typeset": False},
        "options": {"enableMenu": False},
    }
    if pk:
        cfg["tex"]["packages"] = {"[+]": pk}
        if not inline_assets:
            cfg["loader"] = {"load": ["[tex]/" + p for p in pk]}
    return "window.MathJax = " + json.dumps(cfg) + ";"


_ASSET_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "paper-blueprint")


def fetch_asset(url: str) -> str:
    os.makedirs(_ASSET_CACHE, exist_ok=True)
    fn = os.path.join(_ASSET_CACHE, re.sub(r"[^A-Za-z0-9.]+", "_", url))
    if not os.path.exists(fn):
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
        with open(fn, "wb") as fh:
            fh.write(data)
    with open(fn, encoding="utf-8") as fh:
        return fh.read()


def render(m: Model, out_dir: str, palette: str = "blues", label_style: str = "both",
           reduction: str = "typed", inline_assets: bool = False, rankdir: str = "TB",
           title: str | None = None, lang: str = "en", raw_pdf_proofs: str = "auto") -> str:
    ex = m.ex
    ui = UI.get(lang)
    if ui is None:
        raise SystemExit(f"unknown lang {lang}; choose from {', '.join(UI)}")
    pal = PALETTES.get(palette)
    if pal is None:
        raise SystemExit(f"unknown palette {palette}; choose from {', '.join(PALETTES)}")
    macros = m.macros
    conv, conv_inline = make_converter_factory(m)
    reduce = reduction != "none"
    reduced = m.reduced_edges(reduction)
    dot_main = build_dot(m, reduced, pal, label_style, macros, rankdir)
    dot_full = build_dot(m, m.edges, pal, label_style, macros, rankdir) if reduce else None

    notation = m.notation_entries()
    nodes = {}
    for nid in m.visible:
        n = m.nodes[nid]
        fill, font, border = importance_colors(n.get("importance"), pal)
        loc = n.get("loc") or {}
        if "page" in loc:
            loc_s = f"page {loc['page']}"
        elif "file" in loc:
            loc_s = f"{loc['file']}:{loc.get('line', '?')}"
        else:
            loc_s = ""
        stmt_fmt = n.get("statement_format", "latex")
        statement_html = conv(n.get("statement")) if stmt_fmt == "latex" else text_to_html(n.get("statement"))
        proof = n.get("proof")
        proof_fmt = n.get("proof_format", "latex" if ex["source"]["type"] == "tex" else "text")
        raw_proof = isinstance(proof, str) and proof_fmt == "text"
        if raw_proof and (raw_pdf_proofs == "never" or raw_pdf_proofs == "auto" and n.get("proof_sketch")):
            proof, raw_proof = None, False  # the sketch replaces unreadable PDF text
        if raw_proof:
            proof_html = text_to_html(proof)
        else:
            proof_html = conv(proof) if proof else ""
        nodes[nid] = {
            "id": nid,
            "kind": n.get("kind"),
            "display": n.get("display"),
            "number": n.get("number"),
            "label": m.label_text(nid),
            "title": conv_inline(n.get("title")) if n.get("title") else "",
            "title_plain": latex2html.plain(n.get("title") or "", macros),
            "section": n.get("section"),
            "section_title": latex2html.plain(n.get("section_title") or ""),
            "statement": statement_html,
            "statement_raw": stmt_fmt != "latex",
            "proof": proof_html,
            "proof_raw": raw_proof,
            "proof_sketch": conv(n.get("proof_sketch")) if n.get("proof_sketch") else "",
            "summary": conv(n.get("summary")) if n.get("summary") else "",
            "summary_plain": latex2html.plain(n.get("summary") or "", macros),
            "reason": conv(n.get("reason")) if n.get("reason") else "",
            "context": conv(n.get("context")) if n.get("context") else "",
            "notation": m.notation_for(nid),
            "importance": float(n["importance"]) if n.get("importance") is not None else None,
            "novelty": _num(n.get("novelty")),
            "novelty_color": novelty_color(n.get("novelty")),
            "novelty_note": novelty_note_html(n.get("novelty_note"), n.get("novelty_refs"), conv, ui),
            "main": bool(n.get("main")),
            "fill": fill, "font": font, "border": border,
            "uses": m.uses[nid], "used_by": m.used_by[nid],
            "ancestors": sorted(m.ancestors[nid]), "descendants": sorted(m.descendants[nid]),
            "loc": loc_s,
        }
    paper_title = title or latex2html.plain(ex.get("title") or "") or "Blueprint"
    data = {
        "title": paper_title,
        "authors": latex2html.plain(ex.get("authors") or ""),
        "order": m.visible,
        "nodes": nodes,
        "dot": dot_main,
        "dot_full": dot_full,
        "notation": [{"symbol": conv_inline("$" + e["symbol"].strip("$") + "$") if e["symbol"]
                      else "<em>" + html.escape(e["term"]) + "</em>",
                      "meaning": conv_inline(e["meaning"]),
                      "where": html.escape(str(e["where"])) if e.get("where") else ""} for e in notation],
        "palette": pal,
        "levels": ui["levels"],
        "novelty_palette": NOVELTY_REDS,
        "novelty_levels": ui["novelty_levels"],
        "novelty_date": str(m.ann.get("novelty_date") or ""),
        "ui": {k: v for k, v in ui.items() if k not in ("levels", "novelty_levels")},
        "reduced": reduce,
        "source": os.path.basename(ex["source"].get("main") or ex["source"].get("path") or ""),
    }
    with open(os.path.join(ASSETS, "template.html"), encoding="utf-8") as fh:
        tpl = fh.read()
    if inline_assets:
        scripts = "".join(f"<script>{fetch_asset(CDN[k])}</script>\n" for k in ("d3", "d3-graphviz"))
        mj = f"<script>{fetch_asset(CDN['mathjax-full'])}</script>"
    else:
        scripts = "".join(f'<script src="{CDN[k]}"></script>\n' for k in ("d3", "d3-graphviz"))
        mj = f'<script async src="{CDN["mathjax"]}"></script>'
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = (tpl.replace("__TITLE__", html.escape(paper_title))
               .replace("__MATHJAX_CONFIG__", mathjax_config(ex, m.macros, inline_assets))
               .replace("__MATHJAX__", mj)
               .replace("__LEGEND__", legend_html(ui, pal, any(nd["novelty"] is not None for nd in nodes.values()),
                                                  str(m.ann.get("novelty_date") or "")))
               .replace("__UI_PAGE__", html.escape(ui["page"]))
               .replace("__UI_SEARCH__", html.escape(ui["search"]))
               .replace("__UI_EDGES_TIP__", html.escape(ui["edges_tip"]))
               .replace("__UI_EDGES__", html.escape(ui["edges"]))
               .replace("__UI_FIT_TIP__", html.escape(ui["fit_tip"]))
               .replace("__UI_FIT__", html.escape(ui["fit"]))
               .replace("__GLOSSARY_COLOR__", "#2171b5" if palette in ("reds", "oranges") else "#d94801")
               .replace("__GLOSSARY_DARK__", "#08519c" if palette in ("reds", "oranges") else "#a63603")
               .replace("__UI_GLOSSARY_TIP__", html.escape(ui["glossary_tip"]))
               .replace("__UI_GLOSSARY__", html.escape(ui["glossary"]))
               .replace("__UI_LOADING__", html.escape(ui["loading"]))
               .replace("__UI_CLOSE__", html.escape(ui["close"]))
               .replace("__DATA_JSON__", payload)
               .replace("__SCRIPTS__", scripts))
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    with open(os.path.join(out_dir, "graph.dot"), "w", encoding="utf-8") as fh:
        fh.write(dot_main + "\n")
    return out
