# `annotations.yaml` reference

`extract` writes a skeleton with one entry per extracted node. You fill it in. `build`
merges it with `extracted.json`. Re-running `extract` never touches an existing
annotations file unless you pass `--force`, so your work survives a re-extraction after
the paper changes.

Use YAML block scalars (`|`) for anything containing LaTeX. Then backslashes need no
escaping:

```yaml
statement: |
  For every $R>0$ there is a measure $\mu$ with $\|\mu\|_{\mathrm{TV}}\le\lambda$ and
  \[ \mathcal E(\mu)\le V_R(\lambda). \]
```

## Top level

```yaml
title: "Optional override of the page title"
main: [thm:main]                 # main result(s): double border, drives the "main-cone" metric
notation:                        # paper-wide notation; each modal lists the entries it uses
  - symbol: "B"                  # LaTeX of the symbol (matched by letter, e.g. B, \\mathcal{D})
    meaning: "$B=2^n$, an upper bound on the input"
    where: "eq. (1)"             # where the paper fixes it (shown to the reader)
  - term: "good output"          # a word notion, matched as a phrase in the node's text
    meaning: "a transition output that …"
    where: "§4"
    # optional on any entry: nodes: [ids] (list only there), skip: [ids],
    #   exact: true (match the symbol text literally, e.g. "D(w)", instead of by letter)
macros:                          # extra MathJax macros (PDF inputs have none extracted)
  R: "\\mathbb{R}"               # in YAML double quotes a backslash must be doubled…
  ip: ['\langle #1,#2\rangle', 2]   # …in single quotes it must not
render:                          # defaults for `build` (CLI flags override)
  palette: blues                 # blues | reds | oranges | greens | purples | greys | viridis
  labels: both                   # both ("Lem 2.1" + title) | number | title | id (leanblueprint style)
  reduction: typed               # typed (per edge type) | plain (leanblueprint's tred) | none
  rankdir: TB                    # TB | BT | LR | RL
  raw_pdf_proofs: auto           # PDF only: auto = hide extracted proof text when a proof_sketch exists
novelty_date: 2026-10-26         # date of the literature search for the novelty borders (novelty.md)
novelty_skipped: "no internet"   # only if the user chose to skip the novelty assessment; `check` stops asking
nodes:
  <id>: { ...fields below... }
```

## Node fields

All fields are optional. Empty values in the skeleton, such as `importance:` or
`reason: ""`, count as "not set".

| field | meaning |
|---|---|
| `importance` | 1–5 (see importance.md). Half steps such as 4.5 are allowed. Required for every shown node. |
| `reason` | One sentence justifying the importance and citing evidence. |
| `summary` | Role in the argument, in plain language. Inline LaTeX is allowed. |
| `proof_sketch` | 2–5 sentences on how the proof goes, shown above the proof. For results only, not definitions. |
| `novelty` | 1–5, for nodes rated importance ≥ 4 only, set after a literature search (see novelty.md). It is drawn as the node's border, from white (1, known) to deep red (5). Half steps are allowed. |
| `novelty_note` | Two short paragraphs separated by a blank line: "Statement: …" (at most 70 words) and "Technique: …" (at most 50 words). Write the labels as plain text; the page sets them in italics. Give the verdict and the 1–3 most relevant works, no technical details. Each citation is an inline link, `\href{url}{Author Year, locator}`; no `\cite`. LaTeX allowed. Required with `novelty`. |
| `novelty_refs` | The record behind the note's links; it is not shown on the page. A list of `{cite, where, url, verified}`, one entry per linked work, with the same `url`. `where` is the theorem / lemma / section number in the cited work, required when `verified: true`. Use `verified: false` when the full text was not accessible; the page then marks that link "(locator not verified)". |
| `statement` | Replaces the extracted statement (LaTeX). Mandatory for PDF inputs. Keep the paper's mathematics; put added explanations in `context`. |
| `context` | "Notation in force" note (LaTeX), shown below the statement in a box labelled as added by the blueprint. Use it for section-local setup the statement relies on, for example "As in §3, $m=2^k$ with $k=\lceil\log_2 n\rceil$." Its symbols count as explained for the self-containedness check. |
| `bound: [sym, …]` | Symbols this node introduces in words that the checker missed ("of order $r$"), or standard notation you judge needs no explanation. They silence the self-containedness check for this node. |
| `statement_from: <label>` | Copies the running-text paragraph that contains `<label>` as the statement. Exact LaTeX for TeX inputs; trim it afterwards if it is too long. |
| `proof` | Replaces the extracted proof. LaTeX by default; set `proof_format: text` for plain text. |
| `title`, `number`, `display`, `kind` | Fix extraction mistakes. `kind` sets the shape: definition-like kinds (`definition`, `assumption`, `notation`, `construction`, `hypothesis`, `axiom`, `condition`, `convention`, `setting`, `algorithm`) are boxes. A custom `display` (for example `Equation` or `Construction`) appears verbatim in labels. |
| `section`, `page` | Location shown in the modal and digest. New nodes inherit both from their first alias when it can be found; a new node without aliases shows "§-" until you set `section`. |
| `short` | Exact graph label. Plain text, `$…$` allowed (it is flattened to Unicode), `\n` for line breaks. It replaces the whole label, number included, so write e.g. `"Def (4.1)\nKernel"`. |
| `shape` | `box` or `ellipse`, to force a shape. |
| `main: true` | Same as listing the id under top-level `main`. |
| `hidden: true/false` | Hide a node, or show a remark or example that is hidden by default. |
| `drop: true` | Remove a node. Its edges are contracted, so A→X→B becomes A→B. |
| `add_uses` / `add_proof_uses` | Extra dependencies, by node id **or** label. `add_uses` gives a dashed edge (the statement needs it); `add_proof_uses` gives a solid edge (the proof needs it). |
| `remove_uses` / `remove_proof_uses` | Delete extracted dependencies, for example "compare with Lemma 2". |
| `uses` / `proof_uses` | Replace the extracted list entirely. Rarely needed. |
| `used_by: [a, b]` | Shorthand: adds this node to `add_uses` of `a` and `b`. Handy for new definition nodes. |
| `aliases: [eq:foo, …]` | Labels or keys that resolve to this node, so every reference to them becomes an edge from it. For a new node they also give the default `number` "(3.1)" and the section. |
| `new: true` | Create a node the extractor did not find. Give it `kind`, `title`, a `statement` (or `statement_from`), and `aliases` or `used_by`. |
| `before: <id>` / `after: <id>` | Position of a new node in document order. Default: just before the first node that cites one of its aliases. |

## How edges are formed

- **Where edges come from.** Edges come only from the extracted references (`\ref`,
  `\cref`, `\eqref`, `\uses`, hyperref links, "Lemma 3.2" in PDF text) and from your
  `add_*` / `used_by` entries. A `\ref` you write inside a rewritten `statement`,
  `summary` or `proof_sketch` becomes a clickable link but **not** an edge.
- **Dashed or solid.**
  - Your annotation decides: `add_uses` is dashed, `add_proof_uses` is solid.
  - When extraction saw the same target in a statement *and* in the proof, the edge is
    solid. The exception is a definition-like target, which stays dashed, because "Φ as in
    Theorem 5.1" in a statement borrows a setting and the proof is the real use.
  - To force the other style, remove the extracted one (for example `remove_uses: [X]`)
    and add the one you want.
- **Transitive reduction** (default, as in leanblueprint) works per edge type. A solid
  edge is dropped only when an all-solid detour exists; a dashed edge only when an
  all-dashed detour exists. `reduction: plain` gives leanblueprint's sparser plain `tred`,
  which may hide a theorem's hypotheses. The page's "all edges" checkbox and
  `--all-edges` show everything.
- **Claims inside a proof.** A claim stated inside a proof is an extra node used by that
  proof. References from the claim back to its host are ignored.

## YAML and LaTeX gotchas

- Statements are LaTeX, not HTML. Use `\emph{…}`, `itemize`/`enumerate` and
  `\[ … \]`; raw `<em>` is escaped.
- Keys such as `off`, `on`, `yes` and `no` are read as plain strings. Still, quoting odd
  keys (`"off":`) is the safest habit.
- A `notation` entry is matched by its *head* symbol, the first symbol of each
  comma-separated part. So `"D(w)"` matches $D$, not every $w$; `"\\mathbb{C}_-, \\overline{\\mathbb{C}}_-"`
  matches both. An entry with a subscript (`"M_d"`) matches only subscripted uses of that
  letter ($M_2$, $M_r$, …). An entry written with one of the paper's macros (`"\\ip{u}{v}"`)
  matches wherever that macro is used. A literal match respects word boundaries, so
  `"\\T"` does not match `\TV`. Use `nodes:`, `skip:` or `exact: true` for the rest.
- Run `screenshot.py … --check-math` after writing LaTeX. Undefined macros and unbalanced
  braces are invisible to `check`.

## Ids and references

- **TeX input.** The id is the node's `\label` (`lem:contraction`). Unlabelled environments
  get `lem:2.3` or `thm:auto5`.
- **PDF input.** The id is `<prefix>:<number>`: `thm:1.1`, `lem:3.2`, `prop:4.1`,
  `cor:1.3`, `def:2.1`, `asm:1.1`, `claim:…`, `rem:…`, `task:…`.
- **Where references may point.** `add_uses` and the other edge lists accept node ids,
  LaTeX labels (`eq:kernel`, `thm:main`), hyperref destinations from PDFs
  (`theorem.3.1`, `equation.12`) and PDF equation keys (`eq:(3.4)`).
- **Equation labels.** A label on an equation inside a node's statement or proof already
  resolves to that node. Labels in running text resolve to nothing until a node claims
  them through `aliases`. `digest.md` lists these under "Labels defined in running text".

## Typical edits

Promote a definition made in running text into a node:
```yaml
  def:good-partition:
    new: true
    kind: definition
    title: Good partitions
    statement: |
      A partition $V=V_1\sqcup\dots\sqcup V_k$ of a plane graph $G$ is \emph{good} if every
      $G[V_i]$ is connected and
      \[ \sum_i |\partial V_i| \le C\sqrt{n}. \]
    aliases: [eq:good]                # every \eqref{eq:good} now points here
    used_by: [lem:decomposition]      # its statement uses the notion (dashed edge)
    importance: 3
    reason: "New notion in which the key decomposition lemma is phrased."
    summary: "Partitions with small total boundary: the objects the induction runs over."
```

Add an implicit dependency ("by the previous lemma", "as in the proof above"):
```yaml
  prop:clock:
    add_proof_uses: [lem:pulses]
```

The novelty assessment of a key result (step 6, novelty.md). The cited work below is a
placeholder:
```yaml
  lem:lifting:
    novelty: 3
    novelty_note: |
      Statement: new in this form, but a quantitative version of the classical lifting fact
      in \href{https://arxiv.org/abs/<id>}{Smith 2019, Lemma 2.4}.

      Technique: standard Hensel-type lifting, applied to … instead of … .
    novelty_refs:
      - cite: "A. Smith, Lifting lemmas, J. Number Theory 200 (2019)"
        where: "Lemma 2.4"
        url: "https://arxiv.org/abs/<id>"
        verified: true
```

A section-long proof with no `proof` environment, or one that extraction missed. Make
the theorem depend on the section's results:
```yaml
  prop:3.1:
    add_proof_uses: [lem:3.2, lem:3.3, lem:3.4]
    proof_sketch: |
      Section 3 assembles the order trial: Lemma 3.2 builds the phase function, …
```
