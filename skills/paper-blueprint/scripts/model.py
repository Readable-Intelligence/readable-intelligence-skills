"""Merge extracted skeleton + agent annotations into the final graph model."""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict

NODE_FIELDS = {
    "kind", "display", "number", "title", "short", "statement", "proof",
    "proof_sketch", "summary", "importance", "reason", "hidden", "drop", "main",
    "aliases", "uses", "proof_uses", "add_uses", "add_proof_uses", "remove_uses",
    "remove_proof_uses", "shape", "new", "section", "statement_format", "parent", "after",
    "used_by", "statement_from", "section_title", "page", "before", "context", "bound",
    "proof_format",
}


def load_annotations(path: str | None) -> dict:
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if path.endswith(".json"):
        return json.loads(text) or {}
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML is required for .yaml annotations: pip install pyyaml") from exc

    class Loader(yaml.SafeLoader):
        """YAML 1.2 booleans only: keys such as `off`, `on`, `no`, `y` stay strings."""

    Loader.yaml_implicit_resolvers = {
        k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:bool"]
        for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()}
    Loader.add_implicit_resolver("tag:yaml.org,2002:bool",
                                 re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))
    data = yaml.load(text, Loader=Loader) or {}
    for key in ("nodes", "macros"):
        if isinstance(data.get(key), dict):
            data[key] = {str(k): v for k, v in data[key].items()}
    return data


def _as_list(x) -> list:
    if x is None:
        return []
    if isinstance(x, str):
        return [s.strip() for s in x.split(",") if s.strip()]
    return list(x)


class Model:
    def __init__(self, extracted: dict, ann: dict | None = None):
        self.ex = extracted
        self.ann = ann or {}
        self.warnings: list[str] = []
        self.nodes: dict[str, dict] = {}
        self.order: list[str] = []
        self._merge()
        self._labels()
        self._edges()
        self._metrics()

    # ------------------------------------------------------------------
    def _merge(self):
        for nd in self.ex.get("nodes", []):
            n = dict(nd)
            n.setdefault("refs", {"statement": [], "proof": []})
            n.setdefault("explicit_uses", {"statement": [], "proof": []})
            self.nodes[n["id"]] = n
            self.order.append(n["id"])
        ann_nodes = self.ann.get("nodes") or {}
        for nid, a in ann_nodes.items():
            nid = str(nid)
            a = a or {}
            unknown = set(a) - NODE_FIELDS
            if unknown:
                self.warnings.append(f"{nid}: unknown annotation field(s) {sorted(unknown)}")
            if nid not in self.nodes:
                if not (a.get("new") or a.get("statement") or a.get("kind")):
                    self.warnings.append(f"annotation for unknown node id '{nid}' ignored "
                                         "(add `new: true` and a statement to create a node)")
                    continue
                self.nodes[nid] = {
                    "id": nid, "kind": a.get("kind", "definition"), "display": None,
                    "number": None, "title": None, "label": None, "section": None,
                    "statement": "", "proof": None, "statement_format": "latex",
                    "refs": {"statement": [], "proof": []},
                    "explicit_uses": {"statement": [], "proof": []},
                    "parent": None, "loc": None, "hidden": False, "new": True,
                }
                self._insert_in_order(nid, a)
            n = self.nodes[nid]
            for k, v in a.items():
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue  # unfilled skeleton field
                if k == "used_by":
                    continue
                if k in ("aliases", "uses", "proof_uses", "add_uses", "add_proof_uses",
                         "remove_uses", "remove_proof_uses"):
                    n["ann_" + k] = [str(x) for x in _as_list(v)]
                elif k == "statement":
                    n["statement"] = v
                    n["statement_format"] = a.get("statement_format", "latex")
                elif k == "proof":
                    n["proof"] = v
                    n["proof_format"] = a.get("proof_format", "latex")
                elif k == "page":
                    n["loc"] = {"page": v, "pages": [v]}
                elif k != "new":
                    n[k] = v
            if "display" not in a and a.get("kind") and n.get("new"):
                n["display"] = a["kind"].capitalize()
        # used_by: [x, y] on a node is sugar for add_uses on x, y
        for nid, a in ann_nodes.items():
            for user in _as_list((a or {}).get("used_by")):
                if user in self.nodes:
                    self.nodes[user].setdefault("ann_add_uses", []).append(str(nid))
                else:
                    self.warnings.append(f"{nid}: used_by refers to unknown id '{user}'")
        self.macros = dict(self.ex.get("macros") or {})
        self.macros.update(self.ann.get("macros") or {})
        # defaults for nodes created in annotations: section / number / statement from an alias
        labels = self.ex.get("labels", {})
        sec_titles = {str(x.get("number")): x.get("title") for x in self.ex.get("sections", []) if x.get("number")}
        for nid, n in self.nodes.items():
            a = ann_nodes.get(nid) or {}
            src_lab = a.get("statement_from")
            if src_lab:
                info = labels.get(src_lab, {})
                para = info.get("paragraph") or info.get("context")
                if para and not a.get("statement"):
                    n["statement"] = para
                    n["statement_format"] = "latex" if self.ex["source"]["type"] == "tex" else "text"
                elif not para:
                    self.warnings.append(f"{nid}: statement_from label '{src_lab}' has no stored paragraph")
            if n.get("new"):
                first = next((labels[x] for x in _as_list(a.get("aliases")) + ([src_lab] if src_lab else [])
                              if x in labels), None)
                if first:
                    if not n.get("section") and first.get("section"):
                        n["section"] = first["section"]
                    if not n.get("number") and first.get("number") and first.get("type") == "equation":
                        n["number"] = f"({first['number']})"
                    if not n.get("loc") and first.get("loc"):
                        n["loc"] = first["loc"]
            if n.get("section") and not n.get("section_title"):
                n["section_title"] = sec_titles.get(str(n["section"]))
        main = [str(x) for x in _as_list(self.ann.get("main"))]
        for nid in main:
            if nid in self.nodes:
                self.nodes[nid]["main"] = True
            else:
                self.warnings.append(f"main: unknown node id '{nid}'")
        for n in self.nodes.values():
            if not n.get("display"):
                n["display"] = (n.get("kind") or "statement").capitalize()
            if n.get("shape") is None:
                n["shape"] = "box" if n.get("kind") in DEF_KINDS else "ellipse"

    def _insert_in_order(self, nid: str, a: dict):
        """Place a new node after `after:`, else before the first node citing one of its aliases."""
        before = a.get("before")
        if before and before in self.order:
            self.order.insert(self.order.index(before), nid)
            return
        after = a.get("after")
        if after and after in self.order:
            self.order.insert(self.order.index(after) + 1, nid)
            return
        aliases = set(_as_list(a.get("aliases")))
        users = set(_as_list(a.get("used_by")))
        for i, other in enumerate(self.order):
            o = self.nodes.get(other, {})
            labs = set(o.get("refs", {}).get("statement", []) + o.get("refs", {}).get("proof", []))
            if aliases & labs or other in users:
                self.order.insert(i, nid)
                return
        self.order.append(nid)

    # ------------------------------------------------------------------
    def _labels(self):
        self.label_to_node: dict[str, str] = {}
        self.label_info: dict[str, dict] = self.ex.get("labels", {})
        for lab, info in self.label_info.items():
            if info.get("node"):
                self.label_to_node[lab] = info["node"]
        for nid in self.nodes:
            self.label_to_node.setdefault(nid, nid)
            lab = self.nodes[nid].get("label")
            if lab:
                self.label_to_node[lab] = nid
        for nid, n in self.nodes.items():
            for lab in n.get("ann_aliases", []):
                self.label_to_node[lab] = nid

    def resolve(self, label: str) -> str | None:
        nid = self.label_to_node.get(label)
        if nid in self.nodes:
            return nid
        return None

    # ------------------------------------------------------------------
    def _edges(self):
        # (dependency, user) -> {"ext": set of parts from extraction, "ann": set of parts from annotations}
        seen: dict[tuple[str, str], dict[str, set]] = {}
        self.unresolved: dict[str, list[tuple[str, str]]] = defaultdict(list)

        def add(src, dst, part, source="ext"):
            if src == dst or src not in self.nodes or dst not in self.nodes:
                return
            seen.setdefault((src, dst), {"ext": set(), "ann": set()})[source].add(part)

        def enclosing(nid):
            """Nodes whose proof contains nid (a claim inside a proof refers to its host freely)."""
            out, p = set(), self.nodes[nid].get("parent")
            while p and p in self.nodes and p not in out:
                out.add(p)
                p = self.nodes[p].get("parent")
            return out

        for nid, n in self.nodes.items():
            hosts = enclosing(nid)
            for part in ("statement", "proof"):
                if part == "statement" and "ann_uses" in n:
                    labs = n["ann_uses"]
                elif part == "proof" and "ann_proof_uses" in n:
                    labs = n["ann_proof_uses"]
                else:
                    labs = n["refs"].get(part, []) + n["explicit_uses"].get(part, [])
                ann_labs = set(n.get("ann_add_" + ("uses" if part == "statement" else "proof_uses"), []))
                if "ann_uses" in n and part == "statement" or "ann_proof_uses" in n and part == "proof":
                    ann_labs |= set(labs)
                labs = labs + [x for x in ann_labs if x not in labs]
                removed = set(n.get("ann_remove_" + ("uses" if part == "statement" else "proof_uses"), []))
                removed_ids = {self.resolve(x) or x for x in removed}
                for lab in labs:
                    tgt = self.resolve(lab)
                    if tgt is None:
                        info = self.label_info.get(lab, {})
                        if info.get("type") not in ("section",):
                            self.unresolved[lab].append((nid, part))
                        continue
                    if lab in removed or tgt in removed_ids or tgt in hosts:
                        continue
                    add(tgt, nid, part, "ann" if lab in ann_labs else "ext")
            par = n.get("parent")
            if par and par in self.nodes and "parent" not in n.get("ann_remove_proof_uses", []):
                if par not in {self.resolve(x) or x for x in n.get("ann_remove_proof_uses", [])}:
                    add(nid, par, "proof")
        for nid, n in self.nodes.items():
            for key in ("ann_add_uses", "ann_add_proof_uses", "ann_uses", "ann_proof_uses",
                        "ann_remove_uses", "ann_remove_proof_uses"):
                for lab in n.get(key, []):
                    if self.resolve(lab) is None:
                        self.warnings.append(f"{nid}: {key[4:]} refers to unknown id/label '{lab}'")

        # Edge kind.  Annotations win.  When extraction saw the target both in the statement
        # and in the proof, the edge is dashed only if the target is definition-like: a
        # statement saying "Φ as in Theorem 5.1" borrows a setting, the proof is the real use.
        raw: dict[tuple[str, str], str] = {}
        for (a, b), src in seen.items():
            parts = src["ann"] or src["ext"]
            if len(parts) == 1:
                raw[(a, b)] = next(iter(parts))
            else:
                raw[(a, b)] = "statement" if self.nodes[a].get("kind") in DEF_KINDS else "proof"

        # visibility: hidden (default for unreferenced remarks) and dropped nodes
        self.visible = [nid for nid in self.order
                        if nid in self.nodes and not self.nodes[nid].get("drop")
                        and not self.nodes[nid].get("hidden")]
        vis = set(self.visible)
        # contract invisible nodes so that A -> X -> B becomes A -> B
        succ = defaultdict(dict)
        for (a, b), part in raw.items():
            succ[a][b] = part
        edges: dict[tuple[str, str], str] = {}
        for a in vis:
            stack = [(b, p) for b, p in succ[a].items()]
            seen = set()
            while stack:
                b, p = stack.pop()
                if b in seen:
                    continue
                seen.add(b)
                if b in vis:
                    if a != b and edges.get((a, b)) != "statement":
                        edges[(a, b)] = p
                else:
                    stack.extend((c, "proof") for c in succ[b])
        self.edges = edges  # (dependency, user) -> 'statement' | 'proof'

    # ------------------------------------------------------------------
    def _metrics(self):
        vis = self.visible
        self.uses = {n: [] for n in vis}
        self.used_by = {n: [] for n in vis}
        for (a, b), part in sorted(self.edges.items(), key=lambda e: (vis.index(e[0][1]), vis.index(e[0][0]))):
            self.uses[b].append((a, part))
            self.used_by[a].append((b, part))
        self.ancestors = {n: self._closure(n, self.uses) for n in vis}
        self.descendants = {n: self._closure(n, self.used_by) for n in vis}
        self.main = [n for n in vis if self.nodes[n].get("main")]
        self.main_cone = set()
        self.main_guessed = not self.main
        for m in (self.main or self.suggested_main()[:2]):
            self.main_cone |= self.ancestors[m] | {m}
        self.cycles = self._find_cycles()
        # depth = longest chain of prerequisites (ignoring cycles)
        depth: dict[str, int] = {}

        def d(n, stack=()):
            if n in depth:
                return depth[n]
            if n in stack:
                return 0
            depth[n] = 0
            depth[n] = 1 + max((d(a, stack + (n,)) for a, _ in self.uses[n]), default=-1)
            return depth[n]
        for n in vis:
            d(n)
        self.depth = depth

    @staticmethod
    def _closure(n, adj):
        seen, stack = set(), [a for a, _ in adj[n]]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend(a for a, _ in adj.get(x, []))
        seen.discard(n)
        return seen

    def _find_cycles(self):
        cyc = []
        for n in self.visible:
            if n in self.descendants[n] or any(n in self.ancestors[a] and a in self.ancestors[n]
                                                for a, _ in self.uses[n]):
                cyc.append(n)
        return cyc

    def suggested_main(self) -> list[str]:
        """Heuristic guess at main results: theorem-like sinks with many ancestors."""
        cands = []
        for n in self.visible:
            nd = self.nodes[n]
            if nd.get("kind") in ("theorem", "corollary", "proposition") and not self.used_by[n]:
                cands.append((nd.get("kind") == "theorem", len(self.ancestors[n]), n))
        cands.sort(reverse=True)
        return [c[2] for c in cands[:4]]

    def reduced_edges(self, mode: str = "typed") -> dict:
        """Transitive reduction.  mode: "typed" (default), "plain" (leanblueprint's tred), "none".

        "typed" is done separately for each edge type.

        leanblueprint runs a plain `tred`; we only drop a solid (proof) edge a->b when an
        all-solid path a->...->b exists, and a dashed (statement) edge only along an
        all-dashed path, so a theorem never loses its visible hypotheses and a proof never
        loses a cited input to a path through a definition.
        """
        if mode == "none":
            return dict(self.edges)
        out = {}
        for kind in (("statement", "proof") if mode == "typed" else ("any",)):
            adj = defaultdict(set)
            for (a, b), part in self.edges.items():
                if part == kind or kind == "any":
                    adj[a].add(b)
            for a in list(adj):
                for b in adj[a]:
                    # another path a -> c -> ... -> b with only this edge type?
                    stack, seen, redundant = [c for c in adj[a] if c != b], set(), False
                    while stack and not redundant:
                        x = stack.pop()
                        if x in seen or x == a:
                            continue
                        seen.add(x)
                        if b in adj.get(x, ()):
                            redundant = True
                        stack.extend(adj.get(x, ()))
                    if not redundant:
                        out[(a, b)] = self.edges[(a, b)]
        return out

    def cycle_edges(self) -> list[tuple[str, str, str]]:
        """Edges that lie on a dependency cycle."""
        return [(a, b, p) for (a, b), p in self.edges.items() if a in self.descendants.get(b, set())]

    # ------------------------------------------------------------------
    def label_text(self, nid: str) -> str:
        n = self.nodes[nid]
        if n.get("number"):
            return f"{n['display']} {n['number']}"
        name = n.get("short") or n.get("title")
        if name:
            import latex2html
            name = latex2html.plain(str(name).replace("\\n", " "), self.macros)
            name = name if len(name) <= 40 else name[:38] + "…"
            disp = n.get("display") or "Statement"
            first = name.split()[0].rstrip(".:").lower() if name.split() else ""
            if first and (disp.lower().startswith(first) or first in ("def", "defn", "lem", "thm", "prop", "cor")):
                return name
            return f"{disp}: {name}"
        return n.get("display") or nid

    def check(self) -> list[str]:
        """Problems that should be fixed before handing over."""
        probs = list(self.warnings)
        for nid in self.visible:
            n = self.nodes[nid]
            imp = n.get("importance")
            if imp is None:
                probs.append(f"{nid}: no importance")
            else:
                try:
                    v = float(imp)
                    if not 1 <= v <= 5:
                        probs.append(f"{nid}: importance {imp} outside 1..5")
                except (TypeError, ValueError):
                    probs.append(f"{nid}: importance '{imp}' is not a number")
            if imp is not None and not n.get("reason"):
                probs.append(f"{nid}: importance given without `reason`")
            if n.get("statement_format") == "text":
                probs.append(f"{nid}: statement is raw PDF text; rewrite it in LaTeX (annotation `statement:`)")
            if not self.uses[nid] and not self.used_by[nid] and len(self.visible) > 1:
                probs.append(f"{nid}: isolated node (no dependencies either way) — check edges or hide it")
        if not self.main:
            probs.append("no main result marked (top-level `main: [...]` in annotations)")
        cyc = self.cycle_edges()
        if cyc:
            probs.append("dependency cycle; edges on it: " + ", ".join(
                f"{a} -> {b} ({p})" for a, b, p in cyc) +
                ". Typical cause: a statement saying 'under the hypotheses of Theorem X' — point that "
                "edge at a setting/assumption node or remove it with remove_uses.")
        for nid, issues in self.scope_report().items():
            for part in ("statement", "context", "proof_sketch", "summary", "proof"):
                items = [i for i in issues if i["part"] == part]
                if not items:
                    continue
                desc = "; ".join(f"${i['symbol']}$ (seen earlier: {_where(i['hint'])})" for i in items)
                probs.append(f"{nid}: not self-contained — {part} uses {desc}. Fix: add_uses/add_proof_uses "
                             "to the node that defines it, a `context:` note, a top-level `notation:` "
                             "entry, or `bound:` if the statement does introduce it")
        for k, v in (self.ann.get("macros") or {}).items():
            if not re.fullmatch(r"[A-Za-z]+", str(k)):
                probs.append(f"macros: '{k}' is not a valid macro name (letters only, no backslash)")
            if not isinstance(v, (str, list)):
                probs.append(f"macros: value of '{k}' should be a string or [body, nargs]")
        return probs

    # ------------------------------------------------------------------
    # self-containedness
    # ------------------------------------------------------------------
    def notation_entries(self) -> list[dict]:
        """Top-level `notation:` as [{symbol, meaning, where, syms}]."""
        import symbols as S
        raw = self.ann.get("notation") or []
        if isinstance(raw, dict):
            raw = [{"symbol": k, "meaning": v} for k, v in raw.items()]
        out = []
        for e in raw:
            if not isinstance(e, dict) or not (e.get("symbol") or e.get("term")):
                self.warnings.append(f"notation: entry {e!r} needs `symbol` (or `term`) and `meaning`")
                continue
            if e.get("term"):  # a word notion ("good output"), matched as a phrase
                out.append({"symbol": None, "term": str(e["term"]), "meaning": str(e.get("meaning") or ""),
                            "where": e.get("where"), "syms": set()})
                continue
            tex = str(e["symbol"])
            syms = _head_symbols(tex, self.macros) - S.STANDARD
            out.append({"symbol": tex, "term": None, "meaning": str(e.get("meaning") or ""),
                        "where": e.get("where"), "syms": syms,
                        "match_syms": _head_symbols(tex, self.macros),
                        "literal": re.sub(r"\s+", "", tex.strip("$")),
                        "macros_used": {m for m in re.findall(r"\\([A-Za-z]+)", tex) if m in self.macros},
                        "exact": bool(e.get("exact")),
                        "only": [str(x) for x in _as_list(e.get("nodes"))],
                        "skip": [str(x) for x in _as_list(e.get("skip"))]})
        for e in out:
            e.setdefault("only", [])
            e.setdefault("skip", [])
        return out

    def notation_for(self, nid: str) -> list[int]:
        """Indices of notation entries that the node's displayed text uses."""
        import symbols as S
        n = self.nodes[nid]
        text = " ".join(str(n.get(f) or "") for f in ("statement", "proof_sketch", "context", "summary"))
        syms = S.symbols_in(text, self.macros, with_index=True, keep_standard=True)
        low, flat = text.lower(), re.sub(r"\s+", "", text)
        out = []
        for k, e in enumerate(self.notation_entries()):
            if e["only"] and nid not in e["only"] or nid in e["skip"]:
                continue
            if e["term"]:
                hit = e["term"].lower() in low
            else:
                letter_hit = bool(e["match_syms"] & syms)
                if letter_hit and re.search(r"[_^]", e["literal"]):
                    # "c_\eta" or "M_d": only uses that carry a script too, not every bare c / M
                    base = re.split(r"[_^]", e["literal"])[0]
                    letter_hit = base in flat and bool(re.search(re.escape(base) + r"\}?\s*[_^]", flat))
                lit = e["literal"]
                lit_hit = len(lit) > 1 and re.search(
                    (r"(?<![A-Za-z\\])" if lit[:1].isalpha() else "") + re.escape(lit) +
                    (r"(?![A-Za-z])" if lit[-1:].isalpha() else ""), flat) is not None
                macro_hit = any(re.search(r"\\" + m + r"(?![A-Za-z])", text) for m in e["macros_used"])
                hit = lit_hit or macro_hit or (not e.get("exact") and not e["macros_used"] and letter_hit)
            if hit:
                out.append(k)
        return out

    def scope_report(self) -> dict:
        """nid -> list of {part, symbol, kind, hint}: notation a reader of this node cannot resolve.

        A symbol in a node's statement (or proof sketch / LaTeX proof) is resolved when it is
        introduced there, mentioned in the node's `context`, listed in `bound`, a `notation`
        entry, or used in a node it depends on.  Unresolved symbols that the paper used or
        defined *before* this node (running text, another statement) are the dangerous ones:
        the paper's reader saw them earlier, the blueprint's reader did not.
        """
        import symbols as S
        if hasattr(self, "_scope"):
            return self._scope
        index = self.ex.get("symbol_index") or {}
        notation = set().union(*[e["syms"] for e in self.notation_entries()]) if self.notation_entries() else set()
        mac = self.macros

        def latex_of(nid, field):
            n = self.nodes[nid]
            v = n.get(field)
            if not v:
                return ""
            if field == "statement" and n.get("statement_format") == "text":
                return ""
            if field == "proof" and n.get("proof_format", "latex" if self.ex["source"]["type"] == "tex" else "text") != "latex":
                return ""
            return str(v)

        def bound_of(nid):
            out = set()
            for b in _as_list(self.nodes[nid].get("bound")):
                b = str(b)
                out |= S.symbols_in(b if "$" in b else f"${b}$", mac, with_index=True)
            return out

        mentioned, provides = {}, {}
        for nid in self.visible:
            mentioned[nid] = S.symbols_in(latex_of(nid, "statement") + " " + latex_of(nid, "context"),
                                          mac, with_index=True)
            # what a node makes available to the nodes that depend on it
            provides[nid] = S.introduced_in(latex_of(nid, "statement"), mac) | \
                S.symbols_in(latex_of(nid, "context"), mac, with_index=True) | bound_of(nid)
        report = {}
        for nid in self.visible:
            n = self.nodes[nid]
            stmt = latex_of(nid, "statement")
            base = set(notation) | S.introduced_in(stmt, mac) | bound_of(nid)
            for a in self.ancestors[nid]:
                base |= provides.get(a, set())
            avail = base | S.symbols_in(latex_of(nid, "context"), mac, with_index=True)
            issues = []
            pos = n.get("pos")
            if pos is None and n.get("new"):
                # a node promoted from running text sits where its first alias sits
                for lab in n.get("ann_aliases", []) + ([n["statement_from"]] if n.get("statement_from") else []):
                    info = self.label_info.get(lab, {})
                    if info.get("para_pos") is not None:
                        pos = info["para_pos"]
                        break
            ctx_avail = base
            # context notes and role texts may lean on results that use this node (they are
            # one click away under "Used by"); statements and proof sketches may not
            later = set().union(*[provides.get(d, set()) for d in self.descendants[nid]]) \
                if self.descendants[nid] else set()
            for part in ("statement", "context", "proof_sketch", "summary", "proof"):
                text = latex_of(nid, part)
                if not text:
                    continue
                used = S.symbols_in(text, mac)
                if part == "context":
                    # a context note must itself rest on the notation table / dependencies;
                    # what the node's own statement introduces or mentions is fine
                    used = used - S.introduced_in(text, mac, generous=True) - \
                        S.symbols_in(stmt, mac, with_index=True)
                    for sym in sorted(used - ctx_avail - later):
                        rec = index.get(sym)
                        if rec and rec.get("def") and rec["def"].get("owner") != nid:
                            issues.append({"part": part, "symbol": sym, "hint": rec["def"], "defined": True})
                    continue
                if part != "statement":
                    used -= S.introduced_in(text, mac, generous=True) | mentioned[nid]
                agent_text = part in ("proof_sketch", "summary") or (part == "statement" and n.get("new"))
                # \bar x (conjugate) is explained once x is
                pool = avail | (later if part == "summary" else set())
                if part == "summary":  # the role text shares the modal with the proof sketch
                    pool |= S.introduced_in(latex_of(nid, "proof_sketch"), mac, generous=True)
                pool |= {f"\\bar{{{x}}}" for x in pool}
                if part != "statement":
                    pool |= {f"\\bar{{{x}}}" for x in mentioned[nid]}
                for sym in sorted(used - pool):
                    rec = index.get(sym)
                    if agent_text and part != "statement":
                        # text written for the blueprint must introduce what it uses
                        issues.append({"part": part, "symbol": sym, "hint": (rec or {}).get("def") or
                                       (rec or {}).get("first") or {"owner": None, "part": "nowhere", "loc": {},
                                                                    "snippet": "not used elsewhere in the paper"},
                                       "defined": bool(rec and rec.get("def"))})
                        continue
                    if not rec:
                        continue
                    def earlier(occ):
                        return occ and occ.get("owner") != nid and (
                            pos is None or occ.get("pos") is None or _before(occ["pos"], pos))
                    # notation the paper defines before this node, or uses freely in other nodes
                    free_elsewhere = [o for o in rec.get("free_owners", []) if o != nid]
                    if earlier(rec.get("def")):
                        hint = rec["def"]
                    elif earlier(rec.get("first")) and len(free_elsewhere) >= 2:
                        hint = rec["first"]
                    else:
                        continue  # a local name, or first seen in this node
                    if part == "proof" and not rec.get("def"):
                        continue  # proofs: only flag notation the paper actually defines somewhere
                    issues.append({"part": part, "symbol": sym, "hint": hint,
                                   "defined": rec.get("def") is not None})
            if issues:
                report[nid] = issues
        self._scope = report
        return report

    def suggestions(self) -> list[str]:
        """Optional improvements (do not block a hand-over)."""
        out = []
        pdf = self.ex["source"]["type"] == "pdf"
        for nid in self.visible:
            n = self.nodes[nid]
            result = n.get("kind") not in DEF_KINDS and n.get("kind") not in ("remark", "example", "notation")
            try:
                imp = float(n.get("importance") or 0)
            except (TypeError, ValueError):
                imp = 0
            if result and not n.get("proof_sketch") and (imp >= 4 or pdf and n.get("proof")):
                out.append(f"{nid}: no proof_sketch" + (" (PDF proofs are shown as raw text)" if pdf else ""))
            if not n.get("summary"):
                out.append(f"{nid}: no summary")
            orig = next((x.get("statement") for x in self.ex.get("nodes", []) if x["id"] == nid), None)
            if self.ex["source"]["type"] == "tex" and orig and n.get("statement") and \
                    re.sub(r"\s+", "", orig) != re.sub(r"\s+", "", str(n["statement"])):
                out.append(f"{nid}: statement differs from the paper's; keep the mathematics, move "
                           "added explanations to `context`")
        return out

def _head_symbols(tex: str, macros: dict) -> set:
    """Head symbol of each comma-separated part: "D(w)" -> {D}, "\\C_-, \\overline{\\C}_-" -> both C's."""
    import symbols as S
    out = set()
    body = tex.strip().strip("$")
    for part in S._top_level_split(S.expand_macros(body, macros)):
        toks = [t for t, k in S._tokens(part) if k == "base"]
        if toks:
            out.add(toks[0])
    return out


def _before(a, b) -> bool:
    try:
        return a < b
    except TypeError:
        return True


def _where(occ: dict) -> str:
    loc = occ.get("loc") or {}
    place = f"p.{loc['page']}" if loc.get("page") else (f"line {loc.get('line')}" if loc.get("line") else "?")
    owner = occ.get("owner")
    what = f"{owner} {occ.get('part')}" if owner else "running text"
    snip = (occ.get("snippet") or "")[:70].replace("\n", " ")
    return f"{what}, {place}: “{snip}…”"


DEF_KINDS = {"definition", "notation", "assumption", "hypothesis", "axiom", "construction",
             "condition", "convention", "setting", "algorithm"}


def short_preview(s: str | None, n: int = 260) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " …"
