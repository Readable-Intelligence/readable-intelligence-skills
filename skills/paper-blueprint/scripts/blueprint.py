#!/usr/bin/env python3
"""paper-blueprint (English edition): turn a math paper into a Lean-blueprint-style dependency graph.

  probe   PAPER.pdf            LaTeX origin / hyperref / own arXiv id: should we ask for the .tex?
  extract PAPER [-o WORKDIR]   mechanical skeleton  -> WORKDIR/extracted.json,
                               annotations.yaml (skeleton), digest.md
  digest  WORKDIR              re-write digest.md with annotations applied
  check   WORKDIR              list problems (missing importance, unknown ids …)
  build   WORKDIR [options]    write WORKDIR/index.html (+ graph.dot, refreshed digest.md)
  reader  WORKDIR              write reader.md: only what the page shows, for a blind review
  fetch-arxiv ID -o DIR        download a cited paper's arXiv source (to import definitions it supplies)
  pages   PDF [3-5,9]          render PDF pages to PNG + text (to read a PDF as images)

novelty assessment of the key results (references/novelty.md; needs internet):
  net-check                    can this machine reach arXiv / OpenAlex?
  novelty WORKDIR              write novelty-brief.md: the nodes rated >= 4 and what the paper says about them
  lit-search QUERY …           search arXiv and OpenAlex for prior work
  ref-index SOURCE -o DIR      list a cited work's numbered results (exact theorem numbers)

PAPER may be a .tex file, a directory of LaTeX sources, a source archive (.tar.gz/.zip,
e.g. an arXiv e-print), or a .pdf.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import latex2html  # noqa: E402
from model import DEF_KINDS, Model, load_annotations, short_preview  # noqa: E402

HERE_SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACTED = "extracted.json"
ANNOTATIONS = "annotations.yaml"
DIGEST = "digest.md"


def default_workdir(paper: str) -> str:
    """<paper's directory>/<paper name>-blueprint (never inside the skill itself)."""
    p = os.path.abspath(os.path.normpath(paper))
    stem = os.path.basename(p)
    for suf in ARCHIVE_SUFFIXES + (".pdf", ".tex"):
        if stem.lower().endswith(suf):
            stem = stem[: -len(suf)]
            break
    base = os.path.dirname(p) if os.path.isfile(p) else os.path.dirname(p.rstrip(os.sep))
    if os.path.abspath(HERE_SKILL) in os.path.abspath(base) or not os.access(base, os.W_OK):
        base = os.getcwd()
    return os.path.join(base, f"{stem}-blueprint")


def ann_path(workdir: str) -> str:
    for fn in (ANNOTATIONS, "annotations.yml", "annotations.json"):
        p = os.path.join(workdir, fn)
        if os.path.exists(p):
            return p
    return os.path.join(workdir, ANNOTATIONS)


def load(workdir: str) -> tuple[dict, dict]:
    p = os.path.join(workdir, EXTRACTED)
    if not os.path.exists(p):
        raise SystemExit(f"{p} not found; run `extract` first")
    with open(p, encoding="utf-8") as fh:
        ex = json.load(fh)
    return ex, load_annotations(ann_path(workdir))


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------

ARCHIVE_SUFFIXES = (".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tar.xz", ".zip", ".gz")


def unpack_source(archive: str, dest: str) -> str:
    """Unpack a LaTeX source archive (arXiv e-print, .zip, …) into a fresh directory, safely."""
    import gzip
    import shutil
    import tarfile
    import zipfile
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    root = os.path.realpath(dest)

    def safe(name):
        target = os.path.realpath(os.path.join(dest, name))
        return target == root or target.startswith(root + os.sep)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                if safe(info.filename):
                    z.extract(info, dest)
    elif tarfile.is_tarfile(archive):
        with tarfile.open(archive) as t:
            members = [mb for mb in t.getmembers() if safe(mb.name) and (mb.isfile() or mb.isdir())]
            try:
                t.extractall(dest, members=members, filter="data")
            except TypeError:  # Python < 3.12
                t.extractall(dest, members=members)
    elif archive.endswith(".gz"):  # arXiv sometimes serves a single gzipped .tex
        with gzip.open(archive, "rb") as fin, open(os.path.join(dest, "main.tex"), "wb") as fout:
            shutil.copyfileobj(fin, fout)
    else:
        raise SystemExit(f"{archive}: not a zip/tar/gzip archive")
    return dest


def cmd_fetch_arxiv(args):
    """Download a (cited) paper's arXiv e-print into OUT/<id>/ and unpack it; PDF-only e-prints are kept as PDF."""
    import urllib.request
    aid = re.sub(r"^(?:arxiv:|https?://arxiv\.org/(?:abs|pdf|e-print)/)", "", args.id.strip(), flags=re.I)
    aid = aid.removesuffix(".pdf")
    out = os.path.join(args.out, aid.replace("/", "_"))
    os.makedirs(out, exist_ok=True)
    req = urllib.request.Request(f"https://arxiv.org/e-print/{aid}", headers={"User-Agent": "Mozilla/5.0 paper-blueprint"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    raw = os.path.join(out, "e-print")
    with open(raw, "wb") as fh:
        fh.write(data)
    if data[:4] == b"%PDF":
        os.replace(raw, os.path.join(out, f"{aid.replace('/', '_')}.pdf"))
        print(f"{out}: the e-print is a PDF only ({len(data)} bytes); read it with the Read tool or `pages`")
        return 0
    src = unpack_source(raw if not data[:2] == b"\x1f\x8b" else _with_suffix(raw, ".gz"), os.path.join(out, "src"))
    try:
        from texparse import find_main_tex
        main = find_main_tex(src)
        print(f"{out}: source unpacked; main file {main}")
    except SystemExit:
        print(f"{out}: unpacked into {src} (no main .tex found)")
    return 0


def _with_suffix(path: str, suffix: str) -> str:
    """unpack_source decides by content, but a bare gzip needs a .gz name for its fallback branch."""
    new = path + suffix
    os.replace(path, new)
    return new


def cmd_probe(args):
    """Facts about a PDF, to decide whether to ask the user for the LaTeX source."""
    from pdfparse import probe_pdf
    info = probe_pdf(args.pdf)
    print(f"title      : {info['title'] or '(no metadata title)'}")
    print(f"pages      : {info['pages']}")
    print(f"producer   : {info['producer'] or '?'}")
    print(f"from LaTeX : {'yes' if info['latex'] else 'no / unknown'}")
    print(f"hyperref   : {'yes (internal links and anchors)' if info['hyperref'] else 'no'}")
    print(f"arXiv id   : {info['arxiv_id'] or 'none found (no arXiv stamp on page 1)'}")
    if info["arxiv_cited"]:
        print(f"cited ids  : {', '.join(info['arxiv_cited'])}  (mentioned in the text; NOT this paper's own id)")
    nearby = find_nearby_sources(args.pdf, info.get("title") or "")
    existing = [d for d in (default_workdir(args.pdf), os.path.join(os.getcwd(), os.path.basename(default_workdir(args.pdf))))
                if os.path.exists(os.path.join(d, ANNOTATIONS))]
    for d in dict.fromkeys(existing):
        print(f"existing   : {d} already has {ANNOTATIONS} — continue that blueprint instead of starting over")
    for f in nearby:
        print(f"nearby src : {f}")
    print()
    if nearby:
        print("advice: a LaTeX source for this paper seems to be right here. Ask the user whether to use it.")
    elif info["arxiv_id"]:
        aid = info["arxiv_id"]
        print(f"advice: this is arXiv:{aid}. Its LaTeX source is public: https://arxiv.org/e-print/{aid}")
        print("        Ask the user whether to use it (or whether they have their own .tex), then:")
        print(f"        curl -L -A 'Mozilla/5.0' -o <workdir>/src.tar.gz https://arxiv.org/e-print/{aid}")
        print("        python3 blueprint.py extract <workdir>/src.tar.gz -o <workdir>")
    elif info["latex"]:
        print("advice: the PDF was produced by LaTeX, so a .tex source exists somewhere. Ask the user for it")
        print("        (a .tex file, a source folder, or an arXiv/Overleaf source archive) before extracting.")
    else:
        print("advice: not produced by LaTeX as far as the metadata tells; a .tex source is unlikely.")
        print("        Do not ask; proceed with the PDF.")
    return 0


def find_nearby_sources(pdf: str, title: str) -> list[str]:
    """Same-name .tex/.zip/.tar.gz next to the PDF, or .tex files there whose \\title matches."""
    folder = os.path.dirname(os.path.abspath(pdf))
    stem = os.path.splitext(os.path.basename(pdf))[0]
    out = []
    for suf in (".tex",) + ARCHIVE_SUFFIXES:
        cand = os.path.join(folder, stem + suf)
        if os.path.isfile(cand):
            out.append(cand)
    words = {w for w in re.findall(r"[a-z]{4,}", title.lower())}
    places = [folder] + [os.path.join(folder, d) for d in sorted(os.listdir(folder))
                         if os.path.isdir(os.path.join(folder, d)) and not d.startswith(".")][:40]
    if os.path.dirname(folder) != folder:
        parent = os.path.dirname(folder)
        places += [os.path.join(parent, d) for d in sorted(os.listdir(parent))
                   if os.path.isdir(os.path.join(parent, d)) and not d.startswith(".")][:40]
    for place in places:
        try:
            names = os.listdir(place)
        except OSError:
            continue
        for fn in names:
            if not fn.endswith(".tex"):
                continue
            path = os.path.join(place, fn)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    head = fh.read(20000)
            except OSError:
                continue
            m = re.search(r"\\title\s*(?:\[[^\]]*\])?\s*\{([^}]*)", head)
            if ("\\documentclass" in head or "\\documentstyle" in head) and m and words:
                tw = set(re.findall(r"[a-z]{4,}", m.group(1).lower()))
                if len(words & tw) >= max(2, int(0.6 * len(words))):
                    out.append(place if place != folder else path)
    return list(dict.fromkeys(out))


def cmd_extract(args):
    paper = args.paper
    wd = args.out or default_workdir(paper)
    if os.path.isfile(paper) and paper.lower().endswith(ARCHIVE_SUFFIXES):
        paper = unpack_source(paper, os.path.join(wd, "src"))
        print(f"unpacked   : source archive into {paper}")
    if paper.lower().endswith(".pdf"):
        from pdfparse import extract_pdf
        ex = extract_pdf(paper, include_all=args.include_all)
    else:
        from texparse import extract_tex
        ex = extract_tex(paper, include_all=args.include_all)
    os.makedirs(wd, exist_ok=True)
    with open(os.path.join(wd, EXTRACTED), "w", encoding="utf-8") as fh:
        json.dump(ex, fh, ensure_ascii=False, indent=1)
    ap = ann_path(wd)
    if not os.path.exists(ap) or args.force:
        with open(ap, "w", encoding="utf-8") as fh:
            fh.write(annotation_skeleton(ex))
        made = "written"
    else:
        made = "kept (exists; use --force to overwrite)"
    m = Model(ex, load_annotations(ap))
    write_digest(wd, m)
    vis = set(m.visible)
    found = [n["id"] for n in ex["nodes"]]
    hidden = sum(1 for n in found if n not in vis)
    added = sum(1 for n in vis if m.nodes[n].get("new"))
    print(f"source      : {ex['source']['type']}  {ex['source'].get('main')}")
    print(f"title       : {latex2html.plain(ex.get('title') or '')}")
    print(f"nodes       : {len(found)} found, {len(vis)} shown"
          f" ({hidden} hidden or dropped" + (f", {added} added in annotations)" if added else ")"))
    print(f"edges       : {len(m.edges)} ({sum(1 for p in m.edges.values() if p == 'statement')} statement, "
          f"{sum(1 for p in m.edges.values() if p == 'proof')} proof)")
    nopf = [n for n in m.visible if not m.nodes[n].get("proof") and m.nodes[n]["kind"] not in
            DEF_KINDS | {"conjecture", "remark", "example", "question", "problem"}]
    print(f"no proof    : {len(nopf)} {' '.join(nopf[:12])}{' …' if len(nopf) > 12 else ''}")
    print(f"unresolved  : {len(m.unresolved)} labels referenced by nodes but defined in running text")
    if ex.get("numbering"):
        print(f"numbering   : {ex['numbering']}")
    if ex.get("prose_definitions"):
        print(f"prose defs  : {len(ex['prose_definitions'])} running-text paragraphs that look like definitions (see digest)")
    print(f"workdir     : {wd}")
    print(f"  {EXTRACTED}, {DIGEST} written; {os.path.basename(ap)} {made}")


def _yaml_key(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _yaml_block(text: str, indent: int) -> str:
    pad = " " * indent
    return "|\n" + "\n".join(pad + ln if ln.strip() else "" for ln in text.strip("\n").split("\n"))


def annotation_skeleton(ex: dict) -> str:
    is_pdf = ex["source"]["type"] == "pdf"
    import latex2html
    out = [
        f"# Annotations for: {latex2html.plain(ex.get('title') or '') or ex['source'].get('main')}",
        "# Written by the agent (see references/annotations.md in the paper-blueprint skill).",
        "# Every shown node needs `importance` (1-5) and a one-sentence `reason`;",
        "# `summary` (role in the argument) is strongly recommended.",
        "# Once nodes and importance are final, nodes rated >= 4 get `novelty` (1-5), `novelty_note`",
        "# and `novelty_refs` from a literature search (references/novelty.md).",
        "",
        "main: []            # ids of the paper's main result(s)",
        "",
        "nodes:",
    ]
    for n in ex["nodes"]:
        head = f"{n.get('display') or n['kind']} {n.get('number') or ''}".strip()
        if n.get("title"):
            head += f" ({n['title']})"
        where = f"p.{n['loc']['page']}" if n.get("loc", {}).get("page") else \
            (f"{n['loc']['file']}:{n['loc']['line']}" if n.get("loc") else "")
        flag = "   [hidden: unreferenced remark/example; no rating needed unless you unhide it]" \
            if n.get("hidden") else ""
        out.append(f"  {_yaml_key(n['id'])}:   # {head} — {where}{flag}".rstrip())
        if is_pdf:
            raw = (n.get("statement") or "").strip()
            out.append("    # PDF text of the statement — rewrite it in LaTeX under `statement: |`:")
            for ln in raw.split("\n")[:40]:
                out.append("    #   " + re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", ln))
            out.append("    statement:")
        if n.get("hidden"):
            out.append("    # hidden: false   # uncomment to show it (then rate it)")
            continue
        out.append("    importance:")
        out.append('    reason: ""')
        out.append('    summary: ""')
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# digest
# ---------------------------------------------------------------------------

def write_digest(wd: str, m: Model) -> str:
    ex = m.ex
    L = []
    import latex2html
    L.append(f"# Blueprint digest — {latex2html.plain(ex.get('title') or '')}")
    L.append("")
    L.append(f"Source: {ex['source']['type']} `{ex['source'].get('main')}`"
             + (f" ({ex['source'].get('pages')} pages)" if ex['source'].get('pages') else ""))
    L.append(f"Shown nodes: {len(m.visible)} · edges: {len(m.edges)} · "
             f"after transitive reduction: {len(m.reduced_edges())}")
    if ex.get("numbering"):
        L.append(f"Numbering: {ex['numbering']}")
    if ex.get("abstract"):
        L.append("")
        L.append("## Abstract")
        L.append(short_preview(ex["abstract"], 1500))
    if ex.get("sections"):
        L.append("")
        L.append("## Sections")
        for s in ex["sections"]:
            L.append(f"- {s.get('number') or ''} {s.get('title') or ''}".rstrip())
    L.append("")
    L.append("## Main results")
    if m.main:
        L.append("Marked: " + ", ".join(m.main))
    else:
        L.append("None marked yet. Heuristic candidates (theorem-like sinks with many prerequisites): "
                 + (", ".join(m.suggested_main()) or "—"))
    L.append("")
    L.append("## Nodes (document order)")
    L.append("Metrics: `anc` = results it transitively relies on, `desc` = results that transitively "
             "rely on it, `main-cone` = it is a prerequisite of a marked main result, `proof` = proof length "
             "in characters. These are hints for the importance judgement, not the judgement itself.")
    for nid in m.visible:
        n = m.nodes[nid]
        head = f"{m.label_text(nid)}" + (f" ({n['title']})" if n.get("title") else "")
        loc = n.get("loc") or {}
        where = f"p.{loc['page']}" if loc.get("page") else (f"{loc.get('file')}:{loc.get('line')}" if loc else "")
        L.append("")
        meta = ", ".join(x for x in (n.get("kind"), f"§{n.get('section') or '-'}", where) if x)
        L.append(f"### `{nid}` — {head} [{meta}]")
        uses = ", ".join(f"{a}{'(S)' if p == 'statement' else ''}" for a, p in m.uses[nid]) or "—"
        users = ", ".join(f"{b}{'(S)' if p == 'statement' else ''}" for b, p in m.used_by[nid]) or "—"
        L.append(f"- uses: {uses}")
        L.append(f"- used by: {users}")
        plen = len(n.get("proof") or "")
        L.append(f"- anc {len(m.ancestors[nid])} · desc {len(m.descendants[nid])} · depth {m.depth[nid]}"
                 f" · main-cone{'(guess)' if m.main_guessed else ''} {'yes' if nid in m.main_cone else 'no'}"
                 f" · proof {plen if plen else 'none found'}"
                 + (f" · parent {n['parent']}" if n.get("parent") else ""))
        if n.get("importance") is not None:
            L.append(f"- importance {n['importance']}: {n.get('reason') or ''}")
        if n.get("novelty") is not None:
            L.append(f"- novelty {n['novelty']}: {short_preview(n.get('novelty_note'), 200)}")
        L.append(f"- statement: {short_preview(n.get('statement'), 420)}")
    hidden = [n for n in m.order if n in m.nodes and n not in m.visible]
    if hidden:
        L.append("")
        L.append("## Hidden nodes")
        for nid in hidden:
            n = m.nodes[nid]
            why = "dropped" if n.get("drop") else "hidden"
            L.append(f"- `{nid}` {m.label_text(nid)} ({n.get('title') or ''}) — {why}: "
                     f"{short_preview(n.get('statement'), 160)}")
    prose_labels = {lab: info for lab, info in m.label_info.items()
                    if info.get("type") in ("prose", "equation") and not info.get("node")
                    and m.resolve(lab) is None}
    if prose_labels:
        L.append("")
        L.append("## Labels defined in running text (not inside any node)")
        L.append("No edge is drawn for these. If one is a real definition or standing assumption, "
                 "create a node (`new: true`, `aliases: [label]`, optionally `statement_from: label` "
                 "to copy its paragraph); references to the label then become edges automatically. "
                 "Unreferenced ones can still be central definitions — read them.")
        order = sorted(prose_labels, key=lambda l: (not m.unresolved.get(l), str(prose_labels[l].get("loc"))))
        for lab in order:
            info = prose_labels[lab]
            users = m.unresolved.get(lab, [])
            us = ", ".join(sorted({u for u, _ in users})) if users else "not referenced by any node"
            num = f" ({info.get('number')})" if info.get("number") else ""
            sec = f" §{info.get('section')}" if info.get("section") else ""
            ctx = short_preview(info.get("context"), 380)
            L.append(f"- `{lab}`{num}{sec} — {us}" + (f"\n  > {ctx}" if ctx else ""))
    refs = ex.get("references") or {}
    users: dict[str, list[str]] = {}
    for nid in m.visible:
        for part, keys in (m.nodes[nid].get("cites") or {}).items():
            for k in keys:
                users.setdefault(k, []).append(f"{nid}{'(S)' if part == 'statement' else ''}")
    if users or ex.get("arxiv_mentioned"):
        L.append("")
        L.append("## Cited works used inside statements and proofs")
        L.append("For information. Black-box or marginal citations need nothing beyond staying visible. "
                 "Look a work up only if a node cannot be read without a specific definition or equation "
                 "from it (`python3 blueprint.py fetch-arxiv <id> -o <workdir>/refs`), and import just "
                 "that piece with its citation (references/self-contained.md, \"Cited works\").")
        for k, us in sorted(users.items(), key=lambda kv: -len(kv[1])):
            r = refs.get(k, {})
            ids = ", ".join(x for x in (f"arXiv:{r['arxiv']}" if r.get("arxiv") else "",
                                        f"doi:{r['doi']}" if r.get("doi") else "") if x)
            L.append(f"- [{r.get('label') or k}] used by {', '.join(us)}" + (f" — {ids}" if ids else "")
                     + (f"\n  > {short_preview(r.get('text'), 240)}" if r.get("text") else ""))
        if ex.get("arxiv_mentioned"):
            L.append(f"- arXiv ids mentioned in the text: {', '.join(ex['arxiv_mentioned'])} "
                     "(cited works, not this paper's own id)")
    if ex.get("prose_definitions"):
        L.append("")
        L.append("## Running-text paragraphs that look like definitions")
        L.append("Matched by cue words (define, denote, we write, throughout this section, :=, …). "
                 "Promote the ones that introduce notions later statements rely on; skip mere notation "
                 "and restated hypotheses of an existing node.")
        for p in ex["prose_definitions"]:
            loc = p.get("loc") or {}
            where = f"p.{loc['page']}" if loc.get("page") else f"{loc.get('file', '')}:{loc.get('line', '')}"
            labs = f" [labels: {', '.join(p['labels'])}]" if p.get("labels") else ""
            L.append(f"- {where}{labs}: {short_preview(p.get('text'), 300)}")
    pr, seen_pr = [], set()
    for r in ex.get("prose_refs", []):
        key = (m.resolve(r["label"]), (r.get("context") or "")[:120])
        if key[0] in m.visible and key not in seen_pr:
            seen_pr.add(key)
            pr.append(r)
    if pr:
        L.append("")
        L.append("## References from running text (hints about the proof architecture)")
        for r in pr[:80]:
            loc = r.get("loc") or {}
            where = f"p.{loc['page']}" if loc.get("page") else f"{loc.get('file', '')}:{loc.get('line', '')}"
            L.append(f"- {where} → `{m.resolve(r['label'])}`: {short_preview(r.get('context'), 260)}")
    if ex.get("orphan_proofs"):
        L.append("")
        L.append("## Proofs not attached to any node")
        for p in ex["orphan_proofs"]:
            L.append(f"- {p['loc']}: [{p.get('opt') or ''}] {p['text']}")
    probs = m.check()
    L.append("")
    L.append("## Open problems (from `check`)")
    L.extend(f"- {p}" for p in probs) if probs else L.append("- none")
    path = os.path.join(wd, DIGEST)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return path


def cmd_digest(args):
    ex, ann = load(args.workdir)
    m = Model(ex, ann)
    p = write_digest(args.workdir, m)
    if args.print:
        with open(p, encoding="utf-8") as fh:
            print(fh.read())
    else:
        print(f"wrote {p}")


def cmd_check(args):
    ex, ann = load(args.workdir)
    m = Model(ex, ann)
    probs = m.check()
    sugg = m.suggestions()
    if sugg:
        print(f"{len(sugg)} suggestion(s) (optional):")
        for p in sugg:
            print("  - " + p)
    if probs:
        scope = [p for p in probs if "not self-contained" in p]
        nov = [p for p in probs if "no novelty assessment" in p]
        print(f"{len(probs)} problem(s) to fix" + (f" ({len(scope)} self-containedness)" if scope else "")
              + (f" ({len(nov)} novelty pending)" if nov else "") + ":")
        for p in [p for p in probs if p not in scope and p not in nov] + scope + nov:
            print("  - " + p)
        if scope:
            print("  (see references/self-contained.md for how to resolve self-containedness problems)")
        if nov:
            print("  (novelty is assessed in SKILL.md step 6, after nodes and importance are final; "
                  "expected to be pending before then)")
        return 1
    assessed = sum(1 for nid in m.visible if m.nodes[nid].get("novelty") is not None)
    print(f"ok: {len(m.visible)} nodes, {len(m.edges)} edges, all rated"
          + (f", novelty assessed for {assessed} key result(s)" if assessed else "")
          + (" (novelty assessment skipped)" if ann.get("novelty_skipped") else ""))
    return 0


def cmd_reader(args):
    """Write reader.md: exactly what the blueprint tells a reader, for a blind self-containedness review."""
    ex, ann = load(args.workdir)
    m = Model(ex, ann)
    L = [f"# Reader view — {latex2html.plain(ann.get('title') or ex.get('title') or '')}", "",
         "This file is everything the blueprint page shows about each result (statement, notes, ",
         "dependencies), without the paper; the paper's macros are expanded as the page renders them. ",
         "A reader may follow `Uses` links (transitively) and consult the notation table; `Used by` ",
         "lists later results that rely on the entry, which role texts may mention.", ""]
    entries = m.notation_entries()
    import symbols as S

    def ref_text(mm):  # \ref{lem:x} -> "Lemma 2.1 [`lem:x`]", \eqref{eq:y} -> "(4.2)", as on the page
        cmd, labs = mm.group(1), mm.group(2)
        parts = []
        for lab in [x.strip() for x in labs.split(",") if x.strip()]:
            info = m.label_info.get(lab, {})
            nid = m.resolve(lab)
            if info.get("type") in ("equation", "item") or (nid is None and info.get("number")):
                num = info.get("number") or "??"
                parts.append(f"({num})" if cmd in ("eqref", "cref", "Cref") else num)
            elif nid:
                parts.append(f"{m.label_text(nid)} [`{nid}`]")
            else:
                parts.append("??")
        return ", ".join(parts)

    def x(tex):  # show what the page renders: expand the paper's own macros, resolve refs, drop \label
        t = re.sub(r"\\label\s*\{[^}]*\}", "", str(tex or ""))
        t = re.sub(r"(?:Theorem|Lemma|Proposition|Corollary|Definition|Section|Remark)~?\s*(?=\\(?:ref|cref|Cref)\b)",
                   "", t)
        t = re.sub(r"\\(eqref|ref|cref|Cref|autoref)\*?\s*\{([^}]*)\}", ref_text, t)
        return S.expand_macros(t, m.macros).strip()
    L.append("## Notation table")
    L.extend((f"- ${x(e['symbol'].strip('$'))}$" if e["symbol"] else f"- *{e['term']}*") + f": {x(e['meaning'])}"
             + (f" ({e['where']})" if e.get("where") else "") for e in entries) if entries else L.append("(none)")
    for nid in m.visible:
        n = m.nodes[nid]
        head = m.label_text(nid) + (f" ({latex2html.plain(n['title'], m.macros)})" if n.get("title") else "")
        L += ["", f"## `{nid}` — {head}"]
        uses = [f"`{a}` {m.label_text(a)}" + (" [statement]" if p == "statement" else "") for a, p in m.uses[nid]]
        L.append("Uses: " + (", ".join(uses) if uses else "nothing"))
        deeper = sorted(m.ancestors[nid] - {a for a, _ in m.uses[nid]}, key=m.visible.index)
        if deeper:
            L.append("Uses, indirectly: " + ", ".join(f"`{a}`" for a in deeper))
        users = [f"`{b}` {m.label_text(b)}" for b, _ in m.used_by[nid]]
        L.append("Used by: " + (", ".join(users) if users else "nothing"))
        if n.get("context"):
            L += ["", "Context note:", x(n["context"])]
        L += ["", "Statement:", x(n.get("statement"))]
        if n.get("proof_sketch"):
            L += ["", "Proof sketch:", x(n["proof_sketch"])]
        if not args.no_summary and n.get("summary"):
            L += ["", "Role:", x(n["summary"])]
    out = args.out or os.path.join(args.workdir, "reader.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"wrote {out} ({len(m.visible)} nodes, {len(entries)} notation entries)")
    return 0


NOVELTY_BRIEF = "novelty-brief.md"


def _safe_stdout():
    """Titles and abstracts of cited works carry arbitrary Unicode; never crash on a narrow console encoding."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def _loc_text(loc: dict | None) -> str:
    loc = loc or {}
    return f"p.{loc['page']}" if loc.get("page") else f"{loc.get('file', '')}:{loc.get('line', '')}"


def cmd_novelty(args):
    """Write novelty-brief.md: the key results to assess, with what the paper itself says and cites about them."""
    ex, ann = load(args.workdir)
    m = Model(ex, ann)
    targets = [nid for nid in m.visible if m.needs_novelty(nid)]
    unrated = [nid for nid in m.visible if m.nodes[nid].get("importance") is None]
    refs, bib = ex.get("references") or {}, ex.get("bibliography") or {}

    def ref_line(k):
        r = refs.get(k, {})
        ids = ", ".join(x for x in (f"arXiv:{r['arxiv']}" if r.get("arxiv") else "",
                                    f"doi:{r['doi']}" if r.get("doi") else "") if x)
        return f"[{r.get('label') or bib.get(k) or k}] `{k}` {short_preview(r.get('text'), 260)}" + \
            (f" — {ids}" if ids else "")
    L = [f"# Novelty brief — {latex2html.plain(ann.get('title') or ex.get('title') or '')}", "",
         "The key results (importance >= 4). For each, assess its novelty against the literature, for the "
         "statement and for the proof technique: one rating 1-5, a `novelty_note`, and `novelty_refs` with "
         "exact theorem numbers (references/novelty.md). Below is what the blueprint says about each node, what "
         "the paper cites inside it and what its running text says about it. These are leads only: verify them, "
         "and search beyond the paper's bibliography.", ""]
    if unrated:
        L += [f"**Warning:** {len(unrated)} shown node(s) have no importance yet ({', '.join(unrated[:10])}). "
              "Finish SKILL.md steps 4-5 first; the set of key results is not final.", ""]
    if ann.get("novelty_skipped"):
        L += [f"**Note:** top-level `novelty_skipped` is set ({ann['novelty_skipped']}).", ""]
    L += ["## Paper", f"- title: {latex2html.plain(ex.get('title') or '')}",
          f"- authors: {latex2html.plain(ex.get('authors') or '') or '?'}",
          f"- source: {ex['source']['type']} `{ex['source'].get('main') or ex['source'].get('path')}`"]
    if ex.get("abstract"):
        L += ["", "Abstract: " + short_preview(ex["abstract"], 2000)]
    for nid in targets:
        n = m.nodes[nid]
        L += ["", f"## `{nid}` — {m.label_text(nid)}"
              + (f" ({latex2html.plain(n['title'], m.macros)})" if n.get("title") else "")]
        L.append(f"- importance {n['importance']}" + (" · **main result**" if n.get("main") else "")
                 + f" · {n.get('kind')} · §{n.get('section') or '-'} · {_loc_text(n.get('loc'))}")
        L.append("- status: " + (f"assessed, novelty {n['novelty']}" if n.get("novelty") is not None else "pending"))
        if n.get("reason"):
            L.append(f"- why it matters: {n['reason']}")
        if n.get("summary"):
            L.append(f"- role: {short_preview(n['summary'], 600)}")
        uses = ", ".join(f"`{a}`{' (statement)' if p == 'statement' else ''}" for a, p in m.uses[nid])
        L.append(f"- uses: {uses or 'nothing'}")
        if n.get("context"):
            L += ["", "Context note:", "", str(n["context"]).strip()]
        L += ["", "Statement:", "", str(n.get("statement") or "(none)").strip()]
        if n.get("proof_sketch"):
            L += ["", "Proof sketch:", "", str(n["proof_sketch"]).strip()]
        if n.get("proof"):
            L += ["", f"Proof (first {args.proof_chars} characters):", "",
                  short_preview(str(n["proof"]), args.proof_chars)]
        cites = n.get("cites") or {}
        keys = list(dict.fromkeys((cites.get("statement") or []) + (cites.get("proof") or [])))
        if keys:
            L += ["", "Cited inside this node:"] + [f"- {ref_line(k)}" for k in keys]
        mentions = [r for r in ex.get("prose_refs", []) if m.resolve(r["label"]) == nid]
        if mentions:
            L += ["", "What the running text says around references to it:"]
            L += [f"- {_loc_text(r.get('loc'))}: {short_preview(r.get('context'), 400)}" for r in mentions[:10]]
        if n.get("novelty_note"):
            L += ["", f"Current assessment (novelty {n.get('novelty')}):", "", str(n["novelty_note"]).strip()]
    if refs:
        L += ["", "## The paper's bibliography (leads, not conclusions)"]
        L += [f"- {ref_line(k)}" for k in refs]
    path = os.path.join(args.workdir, NOVELTY_BRIEF)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"wrote {path}: {len(targets)} key result(s) to assess")
    for nid in targets:
        n = m.nodes[nid]
        print(f"  {nid:28s} importance {n['importance']:<4} " +
              (f"novelty {n['novelty']}" if n.get("novelty") is not None else "pending"))
    if unrated:
        print(f"  warning: {len(unrated)} node(s) not rated yet; the list of key results is not final")
    return 0


def cmd_net_check(args):
    """Can this shell reach the literature services?  (A web-search tool of the agent is a separate route.)"""
    from literature import net_check
    _safe_stdout()
    res = net_check()
    for name, ok, info in res:
        print(f"{name:12s}: {'ok' if ok else 'FAILED'}  {info}")
    if any(ok for _, ok, _ in res):
        print("network: available — the novelty assessment can run (`lit-search`, `ref-index`, your web tools)")
        return 0
    print("network: not reachable from this shell. Unless you have another web route (a web search / fetch "
          "tool that works), ask the user before going on (SKILL.md step 6).")
    return 1


def cmd_lit_search(args):
    """Prior-work search on arXiv and OpenAlex: authors, year, title, venue, link, abstract."""
    from literature import search_arxiv, search_openalex
    _safe_stdout()
    q = " ".join(args.query)
    for name, fn in (("arXiv", search_arxiv), ("OpenAlex", search_openalex)):
        if args.source not in ("both", name.lower()):
            continue
        try:
            hits = fn(q, args.n, args.before)
        except Exception as exc:
            print(f"## {name}: failed ({str(exc).splitlines()[0][:160]})\n")
            continue
        print(f"## {name}: {len(hits)} result(s) for {q!r}" + (f" up to {args.before}" if args.before else ""))
        for h in hits:
            print(f"- {h['authors']} ({h['year']}). {h['title']}. {h['venue']}")
            print(f"  {h['url']}   {h['ids']}")
            if h["abstract"] and args.abstract:
                print("  > " + short_preview(h["abstract"], args.abstract))
        print()
    return 0


def cmd_ref_index(args):
    """Numbered results of a cited work (Theorem 3.2, Lemma 4.1, …) so that a citation names the right one."""
    from literature import fetch_text, numbered_results
    _safe_stdout()
    text, origin = fetch_text(args.source)
    os.makedirs(args.out, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9.]+", "_", args.source.split("://")[-1]).strip("_")[:80] or "source"
    path = os.path.join(args.out, slug + ".txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"source: {origin}\n\n{text}")
    res = numbered_results(text)
    words = [w.lower() for w in args.grep or []]
    shown = [r for r in res if all(w in " ".join((r["kind"], r["number"], r["title"], r["text"])).lower()
                                   for w in words)]
    print(f"source : {origin}")
    print(f"text   : {path} ({len(text)} characters)")
    print(f"results: {len(res)} numbered heads" + (f"; {len(shown)} contain {' '.join(args.grep)!r}" if words else ""))
    for r in shown:
        head = f"{r['kind']} {r['number']}" + (f" ({r['title']})" if r["title"] else "") + \
            (f" [p.{r['page']}]" if r["page"] else "")
        print(f"- {head}: {short_preview(r['text'], args.chars)}")
    if not res:
        print("  no numbered heads recognised; search the saved text, or read the PDF with your own tools")
    return 0


def cmd_pages(args):
    """Render PDF pages to PNG (+ text) so they can be looked at with an image viewer / Read."""
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf  # type: ignore
    doc = pymupdf.open(args.pdf)
    pages = set()
    for part in (args.pages or f"1-{doc.page_count}").split(","):
        a, _, b = part.partition("-")
        lo, hi = int(a), int(b or a)
        pages.update(range(max(1, lo), min(doc.page_count, hi) + 1))
    out = args.out or os.path.join(default_workdir(args.pdf), "pages")
    os.makedirs(out, exist_ok=True)
    for pno in sorted(pages):
        page = doc[pno - 1]
        png = os.path.join(out, f"p{pno:03d}.png")
        page.get_pixmap(dpi=args.dpi).save(png)
        with open(os.path.join(out, f"p{pno:03d}.txt"), "w", encoding="utf-8") as fh:
            fh.write(page.get_text())
        print(png)
    return 0


def cmd_build(args):
    from render import render
    ex, ann = load(args.workdir)
    m = Model(ex, ann)
    opts = ann.get("render") or {}
    out = render(m, args.out or args.workdir,
                 palette=args.palette or opts.get("palette", "blues"),
                 label_style=args.labels or opts.get("labels", "both"),
                 reduction="none" if args.all_edges or opts.get("all_edges") else
                 (args.reduction or opts.get("reduction", "typed")),
                 inline_assets=args.offline,
                 rankdir=args.rankdir or opts.get("rankdir", "TB"),
                 title=ann.get("title"),
                 lang="en",
                 raw_pdf_proofs=opts.get("raw_pdf_proofs", "auto"))
    probs = m.check()
    write_digest(args.workdir, m)
    print(f"wrote {out} (and refreshed {DIGEST})")
    print(f"  {len(m.visible)} nodes, {len(m.edges)} edges "
          f"({len(m.reduced_edges(args.reduction or opts.get('reduction', 'typed')))} drawn after transitive reduction)")
    if probs:
        print(f"  {len(probs)} open problem(s) — run `check` for the list")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fetch-arxiv", help="download a cited paper's arXiv source into OUT/<id>/")
    p.add_argument("id", help="arXiv id, e.g. 2505.12615 or quant-ph/9508027")
    p.add_argument("-o", "--out", required=True, help="e.g. <workdir>/refs")
    p.set_defaults(fn=cmd_fetch_arxiv)
    p = sub.add_parser("probe", help="facts about a PDF (LaTeX origin, hyperref, arXiv id) before extracting")
    p.add_argument("pdf")
    p.set_defaults(fn=cmd_probe)
    p = sub.add_parser("extract", help="mechanical extraction from .tex / directory / source archive / .pdf")
    p.add_argument("paper")
    p.add_argument("-o", "--out", help="work directory (default: ./<paper>-blueprint)")
    p.add_argument("--force", action="store_true", help="overwrite an existing annotations.yaml")
    p.add_argument("--include-all", action="store_true", help="also show unreferenced remarks/examples")
    p.set_defaults(fn=cmd_extract)
    p = sub.add_parser("digest", help="rewrite digest.md with annotations applied")
    p.add_argument("workdir")
    p.add_argument("--print", action="store_true", help="also print it")
    p.set_defaults(fn=cmd_digest)
    p = sub.add_parser("check", help="list problems before building")
    p.add_argument("workdir")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("reader", help="write reader.md (blueprint content only) for a blind review")
    p.add_argument("workdir")
    p.add_argument("-o", "--out")
    p.add_argument("--no-summary", action="store_true", help="leave out the `summary` (role) texts")
    p.set_defaults(fn=cmd_reader)
    p = sub.add_parser("pages", help="render PDF pages to PNG + text (fallback for reading PDFs)")
    p.add_argument("pdf")
    p.add_argument("pages", nargs="?", help="e.g. 3-5,9 (default: all)")
    p.add_argument("-o", "--out", help="output dir (default: ./<paper>-blueprint/pages)")
    p.add_argument("--dpi", type=int, default=110)
    p.set_defaults(fn=cmd_pages)
    p = sub.add_parser("net-check", help="can this machine reach arXiv / OpenAlex (novelty assessment)?")
    p.set_defaults(fn=cmd_net_check)
    p = sub.add_parser("novelty", help="write novelty-brief.md: the key results (importance >= 4) to assess")
    p.add_argument("workdir")
    p.add_argument("--proof-chars", type=int, default=1500, help="how much of each extracted proof to include")
    p.set_defaults(fn=cmd_novelty)
    p = sub.add_parser("lit-search", help="search arXiv and OpenAlex for prior work")
    p.add_argument("query", nargs="+", help="search words; quote a phrase inside the query: '\"exact phrase\" word'")
    p.add_argument("--source", choices=["both", "arxiv", "openalex"], default="both")
    p.add_argument("-n", type=int, default=8, help="results per source (default 8)")
    p.add_argument("--before", help="only work up to this date (YYYY, YYYY-MM or YYYY-MM-DD), e.g. the paper's date")
    p.add_argument("--abstract", type=int, default=300, help="characters of each abstract to show (0: none)")
    p.set_defaults(fn=cmd_lit_search)
    p = sub.add_parser("ref-index", help="list a cited work's numbered results, for exact theorem numbers")
    p.add_argument("source", help="arXiv id, URL (HTML or PDF), or a local .pdf/.html/.txt")
    p.add_argument("-o", "--out", required=True, help="e.g. <workdir>/refs (the full text is saved there)")
    p.add_argument("--grep", nargs="+", help="only results whose head or text contains all these words")
    p.add_argument("--chars", type=int, default=220, help="characters of each result's text to show")
    p.set_defaults(fn=cmd_ref_index)
    p = sub.add_parser("build", help="write index.html")
    p.add_argument("workdir")
    p.add_argument("--out", help="output directory (default: the work directory)")
    p.add_argument("--palette", help="blues (default) | reds | oranges | greens | purples | greys | viridis")
    p.add_argument("--labels", choices=["both", "number", "title", "id"],
                   help="node label style; `id` mimics leanblueprint exactly")
    p.add_argument("--all-edges", action="store_true", help="no transitive reduction by default")
    p.add_argument("--reduction", choices=["typed", "plain", "none"],
                   help="typed (default): per edge type; plain: leanblueprint's tred; none")
    p.add_argument("--rankdir", choices=["TB", "BT", "LR", "RL"])
    p.add_argument("--offline", action="store_true",
                   help="inline d3/d3-graphviz/MathJax so the page works without network (~4 MB)")
    p.set_defaults(fn=cmd_build)
    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
