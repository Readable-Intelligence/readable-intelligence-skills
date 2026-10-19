---
name: paper-blueprint
description: Turn a natural-language math / theoretical-CS paper (LaTeX source, a directory or archive of .tex files, or a PDF) into a Lean-blueprint-style interactive dependency graph — one HTML page where every definition/lemma/theorem is a node, dashed/solid arrows show statement/proof dependencies, clicking a node shows its statement, proof and role, and node colour encodes how crucial the result is to the paper's main argument (darker = more crucial), judged by you. Everything it writes — explanations, notation table, page labels — is in English. No formalization involved. Use this whenever the user wants a blueprint, dependency graph, proof map, lemma tree, "logical structure" or roadmap of a paper, or asks which lemmas are the key steps — even if they never say "blueprint".
---

# Paper blueprint

You produce `index.html`, a page that looks and behaves like the Lean blueprint
dependency graph (leanblueprint / plastexdepgraph):
- Graphviz layout via d3-graphviz;
- boxes for definitions, ellipses for results;
- dashed arrows for statement dependencies, solid arrows for proof dependencies;
- transitive reduction;
- a modal with the statement when a node is clicked.

The Lean colours for formalization status are replaced by one judgement: the
**importance** of each node, shown as a light-to-dark fill.

The work is split in two:
- **Scripts do the mechanical part**: theorem environments, proofs, labels, `\ref`s and
  hyperref links, numbering, the graph and the rendering.
- **You do what needs understanding**: repair the skeleton where mechanical extraction
  falls short, judge importance, and write the short explanations a reader sees. For
  PDFs you also rewrite statements in LaTeX.

The importance judgement is the point of the exercise. Colours assigned by degree counts
or proof length would point readers at the wrong steps.

## Setup

```bash
S=<absolute path of the directory containing this SKILL.md>/scripts/blueprint.py
python3 -c "import yaml" 2>/dev/null || pip install pyyaml       # always needed
python3 -c "import pymupdf" 2>/dev/null || pip install pymupdf   # only for PDF input
```

The work directory (default `<paper-name>-blueprint/` next to the paper) holds:
- `extracted.json`: machine output; do not edit it.
- `annotations.yaml`: your input; the durable artifact.
- `digest.md`: an overview for you, refreshed by `digest` and `build`.
- `index.html`: the result.

## Workflow

### 0. Only a PDF? Ask for the LaTeX source first
TeX input is far better than PDF input:
- statements, proofs, labels, numbering and macros come out exact;
- from a PDF you must retype every statement in LaTeX, proofs are unreadable raw text, and
  dependency and proof boundaries are heuristic.

So when the user gives only a PDF, do this before extracting:

1. Run `python3 $S probe paper.pdf`. It takes a second and reports:
   - whether the PDF was made by LaTeX, and whether it has hyperref links;
   - whether page 1 carries the paper's **own** arXiv stamp. An id that is only cited in
     the text does not count.
   - a LaTeX source that already sits next to the PDF (same name, or a folder whose
     `\title` matches);
   - an existing blueprint work directory for it. If one exists, continue that one
     (keep its `annotations.yaml`) rather than starting over.
2. **Ask the user once**, unless the probe says the PDF was not made by LaTeX, in which case
   a source is unlikely: just proceed. Use the AskUserQuestion tool if you have it,
   otherwise a short message, and wait for the answer.
   - Write the question and the options in English. Say in one sentence why (exact
     statements and proofs, far less retyping).
   - Name what the probe found (the arXiv id, or the source file next to the PDF).
   - Put the TeX route first and mark it recommended. The user can type a path into the
     tool's free-text "Other" field, or reply with it.
   - Options:
     - **source found next to the PDF**: "use it" / "continue with the PDF";
     - **own arXiv id**: "fetch the arXiv source" / "I'll provide my own .tex (path)" /
       "continue with the PDF";
     - **made by LaTeX**: "I'll provide the .tex, a source folder, or a .zip/.tar.gz, for
       example an Overleaf download (path)" / "continue with the PDF".
3. If the user provides or approves a source, extract that. If they decline, carry on with
   the PDF and say in the hand-over that a TeX source would improve fidelity.

Further rules:
- Download from arXiv only after the user agrees. Do not search the web for a source unless
  asked.
- Don't ask in these cases:
  - the user already said there is no source;
  - the user gave both a PDF and a TeX source (use the TeX).
- If you cannot reach the user yourself (you are a subagent, or the run is
  non-interactive), don't silently fall back. Stop and hand the question to whoever called
  you, unless your instructions say to proceed without asking. In that case use the PDF and
  note it.

### 1. Extract
```bash
python3 $S extract <paper.tex | source-dir | source.tar.gz/.zip | paper.pdf> -o <workdir>
```
For a source directory or archive, the main file (the one with `\documentclass`) is found
automatically, and archives are unpacked into `<workdir>/src`. Without `-o`, the work
directory is `<paper-name>-blueprint/` next to the paper. Give a readable `-o` when the
file name is generic (`paper.pdf`, `main.tex`), for example `-o 2505.12615-blueprint`. For a PDF, also read
`references/pdf.md`, which explains how to view pages if the Read tool cannot render
PDFs.

The command prints:
- node and edge counts;
- results with no proof attached;
- whether numbering is exact (a `.aux` file is present) or reconstructed.

`digest.md` lists:
- every node, with its location, uses / used-by, graph metrics and a statement preview;
- labelled displays in running text;
- running-text paragraphs that look like definitions;
- references made from running text.

### 2. Understand the paper before touching the annotations
Read `digest.md`. Then read the paper itself:
1. the abstract, introduction and any overview or proof-strategy section;
2. every statement and proof.

Before you write anything, be able to state in a few sentences:
- what the main result is;
- what the proof architecture is;
- where the new idea lies.

The digest is a map, not a substitute for reading.

### 3. Repair the skeleton
Edit `annotations.yaml`, which has one entry per node; for a PDF, rewriting it whole with
Write is fine. Field reference: `references/annotations.md`. Check each of the following.
These are exactly what mechanical extraction misses.

- **Implicit dependencies.**
  - Look for "by the previous lemma", "as above", "similarly to …", and named results or
    notions used without `\ref`.
  - Add them with `add_proof_uses` / `add_uses`.
  - A statement that needs a notion defined elsewhere has a *statement* dependency, drawn
    dashed.
- **Definitions living in running text.** Promote the ones later statements or proofs rely
  on: the paper's central objects, standing assumptions, and named constructions ("the
  preparation just described"). Use `new: true`, `aliases: [label]` and `used_by:`;
  `statement_from: label` copies the paragraph for TeX inputs. The digest lists
  candidates, including labels nobody `\ref`s.

  Do **not** promote:
  - mere notation;
  - intermediate computations;
  - "Throughout this section, K and Φ are as in Theorem 5.1"-style restatements of an
    existing node's hypotheses (point at that node instead).
- **A notion defined inside a theorem statement** (`V_R(λ) := …`) that other statements use.
  Either split it into its own definition node, or leave it. Do not draw edges from the
  theorem to those statements, which would create a cycle.
- **"Under the hypotheses of Theorem X".** A lemma used to prove Theorem X often says this,
  which creates a cycle. Point the edge at a setting/assumption node, or
  `remove_uses: [X]`. `check` reports cycles with their edges.
- **Proofs that are a whole section, and results showing `proof none found`.** Connect the
  results the proof really uses, and add a `proof_sketch`.
- **Spurious edges.** "Compare with Lemma 2" is not a use. `remove_uses` /
  `remove_proof_uses` it.
- **Extraction mistakes.** A wrong title, number or kind, a false node (`drop: true`), or a
  hidden remark that matters (`hidden: false`).

- **Notation fixed in running text** ("Throughout, $u$ denotes unit roundoff"; "we fix
  $m=2^k$"). Statements use such notation silently. Collect it in the top-level
  `notation:` table, or in a node's `context:` note when it is section-local, so that each
  node can be read on its own (step 5).

Keep the graph faithful: add an edge only when the text supports it. After editing, run
`python3 $S digest <workdir>` and re-read the merged uses / used-by lists.

### 4. Judge importance
Read `references/importance.md` (the 1–5 scale, the evidence, calibration). Then, for
**every** shown node, fill in:
- `importance`;
- `reason`: one sentence of evidence;
- `summary`: the node's role in the argument, in plain language.

Mark the main result(s) under top-level `main:`. Add a `proof_sketch` to every result
rated 4–5, and to every result of a PDF paper, whose extracted proofs are raw text. Do not
add one to definitions.

Write every explanation in English: `reason`, `summary`, `proof_sketch`, `context` notes
and `notation` meanings. This edition always produces an English blueprint, even when the
conversation is in another language. Keep mathematics in LaTeX.

### 5. Make every node self-contained
A reader opens one node at a time. Every symbol and notion in its statement and proof
sketch must be explained by one of:
- the node itself;
- its `context` note;
- the `notation` table;
- a node it depends on.

The paper's running text does not count: the blueprint reader never sees it. Read
`references/self-contained.md`, then:
1. **Run `python3 $S check <workdir>`.** It reports, per node, the symbols seen earlier in
   the paper but not explained (for example "statement uses $Q$, seen earlier: running
   text p.5 …"). Fix each with an edge, a `notation` entry, a `context` note, or a new
   definition node, or mark it `bound` when the statement does introduce it.
2. **Blind-reader review.** Run `python3 $S reader <workdir>` to write `reader.md`, which
   holds only what the page shows. Give it to a fresh subagent that has not seen the paper
   and must not open it, and ask for every symbol or notion it cannot resolve. Run that
   subagent in the foreground (`run_in_background: false`) and wait for its report. This catches
   undefined *words* ("good output", "Step 3") as well. Without subagents, do it yourself,
   strictly.
3. Repeat until both are clean. Report any gap you deliberately keep, such as the paper
   itself never defining something.

Never edit the mathematics of a statement to make it self-contained; add `context`,
`notation` or edges instead.

Cited works: a black-box or marginal citation only needs to stay visible. Look a cited
paper up (`$S fetch-arxiv <id> -o <workdir>/refs` for arXiv) only when a node cannot be
read without a specific definition or equation from it. Then import just that piece,
marked with its source (self-contained.md, "Cited works").

### 6. Check, build, look
```bash
python3 $S check <workdir>      # repeat until "ok"; suggestions are optional
python3 $S build <workdir>      # writes index.html, graph.dot, refreshes digest.md
```
Fix the cause of a `check` problem, not the symptom:
- an isolated node usually means a missed dependency;
- a cycle usually means a spurious or hypothesis-borrowing edge;
- a self-containedness finding means a missing edge, notation entry or context note.

If Playwright is available (`python3 -c "import playwright"`), look at the page and
check the LaTeX:
```bash
python3 <skill-dir>/scripts/screenshot.py <workdir>/index.html <workdir>/shot.png [node-id ...] --expand --check-math
```
- `--check-math` typesets every modal and lists MathJax errors (undefined macros,
  unbalanced braces). Nothing else will tell you about a red formula; always run it after
  writing LaTeX.
- Modal shots are full length.

Then look at the screenshots:
- Do the dark nodes form a readable spine?
- Are the labels legible? Use `short:` (plain text, `$…$` allowed) for long titles.

Build options (or `render:` in annotations):
- `--palette reds|greens|purples|greys|viridis`
- `--labels id` (leanblueprint-style labels)
- `--reduction plain` (leanblueprint's sparser plain `tred`; the default `typed` keeps each
  statement's hypotheses visible)
- `--all-edges` (no reduction)
- `--offline`: a self-contained ~4 MB file; without it d3 and MathJax load from a CDN.

### 7. Hand over
Tell the user:
- **Where the page is** (`<workdir>/index.html`) and how to open it. A double-click
  works, with internet unless built `--offline`. Remotely or in Codespaces, use
  `python3 -m http.server 8000 -d <workdir>` and open the forwarded port.
- **The spine**: the main result(s) and the 4–5 rated steps, one line each.
- **What you changed by hand**: nodes added or dropped, notable edges.
- **Caveats**: reconstructed numbering, judgement calls you were unsure about, and any
  remaining self-containedness gaps (for example notation the paper never defines).

When the user disagrees with a rating or an edge, edit `annotations.yaml` and `build`.
Re-running `extract` keeps the annotations. Never pass `--force` unless you mean to
discard them.

## Notes
- Remarks and examples are hidden unless something refers to them. `extract
  --include-all` shows all of them; `hidden: false` shows one.
- Sources that already use leanblueprint's `\uses{…}` are respected.
- For 60+ nodes, work section by section in steps 2–4, but calibrate importance globally
  at the end.
