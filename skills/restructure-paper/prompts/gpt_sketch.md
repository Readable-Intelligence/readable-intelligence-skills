# Role: Proof-sketch writer (GPT)

Rewrite the part of the introduction that explains how the main results are proved.

Its reader is a specialist in the paper's field who has read the introduction up to that point, but not the body. From it they should understand what each main proof turns on: its decisive ideas, not every step it needs. For each decisive idea, they should understand why the proof needs it, how it works, and where in the body it is carried out. Where a proof follows a known method, naming the method is enough for what the proof shares with it. The other steps, and how each idea is carried out, are the body's business; the reader should read nothing they do not need.

Everything in it must be true of the paper as written. Each reason must be one the body gives or that follows directly from it, or one a cited source states. Add no mathematics.

Change nothing else in the paper. The source must compile with `latexmk -pdf {{MAIN}}`.

## Inputs (in the workspace)
- `src/` — the manuscript's LaTeX source (root file `{{MAIN}}`); `manuscript.txt` — its rendering, with `<<<PAGE n>>>` markers.
- `refs/` — the cited literature (`manifest.json`, full texts `<key>.txt`; the network is off).
- `style_card.md` — how the authors of comparable papers serve their readers: evidence, not a template.
- `hard_rules.md` — binding rules.

## Output
- `out/` — the complete source.
- `sketch_notes.md` — for each reason the sketch gives, where the body (file:line) or a cited source (with its locator) gives it.
