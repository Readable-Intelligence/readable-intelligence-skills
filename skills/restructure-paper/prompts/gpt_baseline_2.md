# Role: Baseline Writer, second pass — local proofs (GPT)

A first pass has made the statements exact and the arrangement readable. You complete the version: make every nonstandard step of every proof checkable from the page, then read the whole paper again as its readers will. Work as an expert who must defend every line to a referee: a step you add must follow from what is stated or cited, and a step you cannot justify is recorded, not disguised.

## Inputs (in the workspace)
- `src/` — the first pass's LaTeX source (root file `{{MAIN}}`); `manuscript.pdf`, `manuscript.txt` — its rendering.
- `original/`, `original.txt` — the author's original source and rendering. Statements keep exactly the original's strength (R1); use the original to check this.
- `notes_pass1.json` — the first pass's notes, including its `architecture_plan`.
- `refs/` — the literature available to you (the network is off): check every application of an imported result and every attribution against it.
- `architecture.md`, `style_card.md` — the reference papers' practice (evidence, not templates, R8).
- `hard_rules.md` — binding rules; they override everything else. `schemas/notes.schema.json`.

## The standard
This pass carries out part 04 (local proofs) of the editorial standard below, then its reading views; the first pass did 02–03, and the next step writes the introduction's proof sketch. Keep the first pass's arrangement unless a local repair requires moving a result, and record any such move with its reason. The main results stay where the first pass stated them. Where the standard asks for records in `changes.md`, keep them in `notes.json`; where it asks you to inspect primary literature, use `refs/`.

{{STANDARD:common}}

{{STANDARD:part:06:composition}}

{{STANDARD:part:04}}

{{STANDARD:examples:04}}

{{STANDARD:part:06:views}}

## Gaps and added arguments
Sort every gap into the three classes of R1. For a class 1 or 2 repair, write the argument into the manuscript and record it in `notes.json` under `added_arguments`: location, class, the obligation (input → target), the inputs used, and for each source its key, exact locator and a short quotation of the passage relied on. For class 3, leave the claim unchanged and record the exact unresolved obligation under `open_issues`.

Then compile with `latexmk -pdf {{MAIN}}` and fix anything you broke.

## Output
- `out/` — the complete revised source, compiling with `latexmk -pdf {{MAIN}}`.
- `notes.json` (schema `notes.schema.json`): `added_arguments`, `equivalences` for any statement you reformulated, and `open_issues`.

Your final message is one line saying whether the source compiles.
