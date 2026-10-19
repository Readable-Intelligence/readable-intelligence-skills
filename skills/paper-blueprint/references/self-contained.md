# Making every node self-contained

A blueprint reader opens one node at a time. Everything that node's statement and proof
sketch use must be explained by one of the following:

1. the node itself: its statement introduces the symbol ("Let $m=2^k$", "for every
   $x$", "$y:=\dots$");
2. its `context` note: a short "notation in force" paragraph shown above the statement;
3. the paper-wide `notation` table, which the modal lists automatically under "Notation
   used here";
4. a node it depends on, directly or transitively, through a visible arrow.

Papers routinely break this, and usually not because the paper is wrong. Papers are read
linearly: §1 fixes $n=|V(G)|$ in running text, §3 sets $\varepsilon=1/(100\Delta)$, and every
later statement silently uses them. A blueprint is read non-linearly, so these symbols
must be made explicit. The author of a blueprint is the worst person to notice: you have
read the paper, so $\varepsilon$ "obviously" means $1/(100\Delta)$ to you.

## The two checks

**1. The mechanical symbol check** is built into `check`.

For every shown node, `check` lists the math symbols that are:
- used in its statement or proof sketch (or in its LaTeX proof, for notation the paper
  defines);
- not resolved by 1–4 above;
- **seen earlier in the paper**: defined in running text or in another node, or used
  freely elsewhere.

Each finding cites where the symbol was seen. Example:

```
lem:3.2: not self-contained — statement uses $t$ (seen earlier: running text, p.6:
         "… we fix ε = 1/(100Δ) and t = ⌈ε^{-2} log n⌉ …"); $\Delta$ (seen earlier: …)
```

It knows letters, Greek letters and decorated letters ($\mathcal D$, $\hat\gamma$,
$\mathbb F$). It checks the following parts of each node.

| part | what is checked |
|---|---|
| statement | Must not use notation the paper fixed earlier. A symbol whose first use in the paper is this statement counts as introduced here. |
| `context` | Must itself rest on the notation table, on dependencies, or on results that use the node. |
| `proof_sketch`, `summary` (text you write) | **Every** symbol must be introduced in the text itself, by the statement, by the notation table, or by a dependency; summaries may also use results that use the node. |
| LaTeX proof | Only notation the paper defines somewhere. |

A dependency contributes only what it *introduces* (or its `context`/`bound`), not every
letter it happens to mention, so an undefined symbol does not "spread" downstream.

It does **not** know:
- *words*: "good output", "canonical encoding", "Step 3", "the trial", "admissible
  measure";
- *letter clashes*: a node whose $S$ is not the notation table's $S$. Symbols are compared
  by their letter, ignoring subscripts, so $M_d$ and $M_r$ count as one symbol. A hint that
  cites the wrong one ("seen earlier: Möbius map $M_r$") still points at a real gap.

The blind reader catches these.

Write introductions so the checker can see them: "let / fix / define / write / set / for
every / where $x$ …", "fix a mesh $\delta>0$", "$x$ denotes …". A symbol introduced in
some other phrasing ("from $p-1=h2^\ell$ one gets …") is reported, and then needs a
rephrase or `bound`.

**2. The blind-reader review** catches what the symbol check cannot.

```bash
python3 $S reader <workdir>        # writes <workdir>/reader.md: only what the page shows
                                   # (statements, notes, sketches, roles, uses / used by,
                                   #  notation table; the paper's macros expanded)
```

If you can launch a subagent (Agent tool), give a **fresh** one only `reader.md`, and tell
it not to open the paper or anything else. Run it in the foreground
(`run_in_background: false`), or wait for its report before going on: the next step
depends on its findings. The point is a reader who does not know the
paper. Prompt it along these lines:

> You are a mathematician reading a blueprint of a paper you have never seen. The file
> `<workdir>/reader.md` is all you have; do not open any other file. For every entry,
> list each symbol, term or notion that its statement, context note, proof sketch or role
> text uses without defining it, and that is also not defined by the notation table or by
> an entry it lists under "Uses" (follow those transitively). Ignore standard mathematics
> a graduate student knows (O(·), gcd, unitary, Hadamard gate…). Name the
> paper-specific ones. Sort your findings into two lists:
> - **GAP**: something whose meaning you cannot work out;
> - **POINTER**: a reference such as "eq. (28)" or "Figure 1" whose content is not shown,
>   but where the text around it still makes sense.
>
> Check only whether things are *defined*, not whether the mathematics is correct (if
> you notice a likely error, list it separately at the end). Output:
> `node-id: GAP|POINTER: item — why it is unclear`. Be strict; say "none" for clean
> entries.

Without a subagent, do the review yourself on `reader.md`, entry by entry, pretending you
have not read the paper. This is weaker, so be strict.

Repeat build → check → reader review until both come back clean, or until every remaining
item is a deliberate decision you mention in the hand-over.

A definition node that the blueprint *assembles* from several places in the paper (a
procedure described across §2–§5, or the conventions behind "exact layer stripping")
works like this:
- `statement`: a faithful transcription of what the paper says, in the paper's
  notation;
- `context`: a note that the node was assembled, and from where.

Mark anything you inferred rather than read ("by context").

## Fixing a finding

Pick the remedy by **where the notion lives in the paper**:

| situation | remedy |
|---|---|
| Defined in another node's statement, and this node really depends on it | `add_uses: [that-node]` (dashed edge) |
| Defined inside a theorem statement but used by its own prerequisites (for example a value $V(\lambda):=\dots$ set in the main theorem and also used by the lemmas that prove it) | Split it out as a definition node (`new: true`, `kind: definition`). The theorem and the propositions then `add_uses` it. This avoids a cycle. |
| Defined in running text and used across the paper (a global parameter, standing notation, a fixed gate set, unit roundoff $u$) | Add a top-level `notation:` entry. It is listed in every modal that uses it. |
| A substantive object defined in running text (a construction, a function family, a named quantity with properties) | Promote it to a definition node and draw edges to it (see the main workflow). |
| Section-local setup ("Throughout this section, $K$, $\Omega$, $\Phi$ are as in Theorem 5.1"; "fix $k=\lceil\log_2 n\rceil$ and $m=2^k$") used by a few nodes | A `context:` note on those nodes, or a small definition node if several nodes share it. |
| A *word* the paper defines in running text ("good output", "transition", "admissible") | `notation:` entry with `term:` instead of `symbol:`. It is listed in every modal whose text contains the phrase. A cluster of related words may deserve a definition node instead. |
| A `notation` entry is listed in modals where it does not apply (same letter, other meaning) | Restrict it with `nodes: [...]` or `skip: [...]`, or match it literally with `exact: true`. |
| The paper reuses a letter (Hadamard $H$ and a subgroup $H$) | Keep the paper's names, and add a one-line remark in that node's `context`. |
| The statement does introduce it, in words the heuristic missed ("of order $r$", "the trial returns an integer $d$") | `bound: [r, d]` on that node. |
| Standard notation of the field that a reader is expected to know | `bound: [...]` on the node, or a `notation:` entry if a one-line reminder helps |
| The node relies on a **cited work** (see "Cited works" below) | Usually nothing: keep the citation visible. Import a piece only when the node cannot be read without it. |

## Cited works

Most citations need no work. A black-box result ("by [Hig02, Thm 3.5]"), a historical
or related-work mention, or a standard fact used in a proof is fine as it is, as long as
the citation stays visible in the statement, sketch or `context`, so the reader knows
where it comes from. In the blind review such items are POINTERs, not GAPs.

Look a cited work up only when a node **cannot be understood without a specific piece of
it**. Typical case: the statement computes "the matrix (39) of [1]", or is phrased in a
notion that only the cited paper defines. Then:
1. fetch it from a public source. For arXiv, run
   `python3 $S fetch-arxiv <id> -o <workdir>/refs`, which downloads and safely unpacks the
   source (or keeps the PDF if there is no source). `digest.md` lists the works cited
   inside statements and proofs, with their arXiv ids and DOIs.
2. import just that piece into the node's `context` (or a `notation` entry), transcribed
   faithfully and marked with its origin, e.g. "(from [1] = arXiv:2505.12615, eq. (39))".

Don't build nodes for the cited paper's own results, and don't chase every reference. If
a work is not openly available, leave the citation and mention it in the hand-over.

Rules that keep the blueprint faithful:

- **Never alter a statement to make it self-contained, not even by appending a
  "Notation: …" line.** Put the missing pieces in `context`, `notation` or edges. The
  `context` box is labelled as added by the blueprint, so readers can tell it apart from
  the paper's text. For TeX inputs, `check` lists statements that differ from the paper's
  text.
- **Point at the paper.** A `context` or `notation` entry says where the notion comes from
  ("§3.1", "eq. (1)"), so the reader can check it.
- **Close definitions under their own prerequisites.** When you add
  $t=\lceil\varepsilon^{-2}\log n\rceil$, $\varepsilon$ and $n$ need explaining too, and
  whatever they rest on, until everything is grounded in the problem's input. Definition
  nodes need the same care.
- **Write proof sketches against the node's own context.** Use only what the statement,
  its `context`, the notation table and the nodes it uses provide. Introduce anything else
  in the sketch itself ("write $m=\lfloor n/2\rfloor$ …").

## Example

A hypothetical graph-theory paper. Its §1 fixes $G$, $n=|V(G)|$ and the maximum degree
$\Delta$; its §3 fixes $\varepsilon=1/(100\Delta)$ and $t=\lceil\varepsilon^{-2}\log n\rceil$
in running text before Lemmas 3.1–3.4.

```yaml
notation:
  - symbol: "G"
    meaning: "the input graph, simple and connected"
    where: "§1"
  - symbol: "n"
    meaning: "$n=|V(G)|$"
    where: "§1"
  - symbol: "\\Delta"
    meaning: "the maximum degree of $G$"
    where: "§1"
nodes:
  lem:3.2:
    context: |
      As in §3, $\varepsilon=1/(100\Delta)$ and $t=\lceil\varepsilon^{-2}\log n\rceil$.
  lem:3.4:
    add_uses: [def:3.3]       # its statement speaks of "good walks", defined in Def. 3.3
    bound: [k]                # "a walk of length $k$": introduced in words
```
