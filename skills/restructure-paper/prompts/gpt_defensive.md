# Role: Defensive-Sentence Pass (GPT)

Delete each sentence or clause whose only content is what the paper does not assume, need, require, impose, use or aim at, wherever it stands, including inside statements of results. Keep every sentence that gives a reason, covers a case, or states a conclusion or property that a later step uses, and change nothing else.

## Inputs
- `src/` — the LaTeX source of the manuscript (root `{{MAIN}}`).

## Output
Write the complete source to `out/`; it must compile with `latexmk -pdf {{MAIN}}`. Finish with one line giving the number of deletions.
