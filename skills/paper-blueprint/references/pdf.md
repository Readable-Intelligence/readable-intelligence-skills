# PDF inputs

The PDF extractor reliably recovers the node list (kind, number, title, page), the
proof each node belongs to, and the dependency edges. For LaTeX-generated PDFs it reads
these from hyperref links. Statements come out as plain text with Unicode math, which
reads badly. Rewriting them is part of your job.

## 1. Prefer the LaTeX source when it exists

SKILL.md step 0 asks the user for the source before anything else; `probe` tells you
what to offer. Only the paper's **own** arXiv id counts: the vertical stamp on page 1, such
as `arXiv:2501.01234v2 [math.CA] 3 Jan 2025`. An id that appears only in the references
or the text, a cited earlier version for instance, is not this paper's source.

When the user agrees to fetch the arXiv source:
```bash
curl -L -A 'Mozilla/5.0' -o <workdir>/src.tar.gz https://arxiv.org/e-print/<id>
python3 $S extract <workdir>/src.tar.gz -o <workdir>   # unpacks into <workdir>/src, finds the main .tex
```
This gives exact statements, labels, numbering and macros. Do not run any build scripts
that ship with the source.

When the user has no source, everything below applies.

## 2. What to check in the skeleton

`extract` prints counts. `digest.md` lists every node with its page. Compare them with
the paper:

- **Missed headers.** The extractor needs a bold or small-caps head ("**Lemma 3.2**") or a
  hyperref anchor. Unusual styles, such as an italic head or "Theorem A", may be missed.
  Add any missing node with `new: true`, `kind`, `number`, `title` and `statement`.
- **False headers.** A bold "Theorem 1.1" inside running text can be mistaken for a node.
  `drop: true` it.
- **Proofs.** "Proof of Theorem 1.1" or "Completion of the proof of …" anywhere in the
  paper is attached to that result, and a plain "Proof." to the preceding node. A result
  proved by a whole section, with no proof environment, shows `proof none found` in the
  digest. Add `add_proof_uses` and a `proof_sketch`.
- **Edges.**
  - *With hyperref*, links give precise references, and textual "(3.4)" equation references
    are ignored to avoid noise.
  - *Without hyperref*, references come from text patterns ("Lemma 3.2", "(3.4)"). Expect
    some noise there, and review edges more carefully.

## 3. Rewriting statements

For each shown node:
1. Look at the page(s). The digest and `loc.pages` give the page numbers.
   - Use the Read tool on the PDF (`pages: "5-6"`). Reading 2–5 pages at a time is
     efficient.
   - If that fails (for example "pdftoppm is not installed"), render the pages yourself
     and Read the PNGs:
     ```bash
     python3 $S pages paper.pdf 5-6 -o <workdir>/pages   # writes p005.png + p005.txt …
     ```
     Keep renders inside the workdir. A shared scratch directory can collide with other
     sessions.
2. Write the statement faithfully in LaTeX under `statement: |`. Keep the authors'
   wording and structure, including enumerated items. Do not paraphrase or shorten the
   mathematics. Display formulas go in `\[ … \]`. An equation that the paper numbers gets
   `\tag{3.4}`.
3. Put repeated notation in top-level `macros:`. For example `R: "\\mathbb{R}"` lets you
   write `\R`. That is a typing aid. Notation a *reader* needs explained belongs in
   `notation:` or `context:` (see self-contained.md).
4. Run `screenshot.py … --check-math` once all statements are written. It lists every
   formula MathJax could not typeset.

Extracted PDF proofs are raw text with garbled formulas. Give every result a
`proof_sketch` in LaTeX. With the default `render: {raw_pdf_proofs: auto}`, the raw text
is then hidden for that node. Where the full proof matters, for example a short key
argument, you may transcribe it under `proof: |`; it is LaTeX by default.

Budget: a 20-page paper with ~20 nodes takes about two passes through the PDF. The first
pass is for architecture and importance; the second is for statements, done page range
by page range.
