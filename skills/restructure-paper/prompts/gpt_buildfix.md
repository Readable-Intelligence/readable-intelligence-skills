# Role: Build Fixer (GPT)

The LaTeX source in `src/` (root `{{MAIN}}`) does not compile. `build_log.txt` holds the end of the log.

Make the smallest changes that let `latexmk -pdf {{MAIN}}` succeed with no undefined references. Do not change any wording, mathematics or structure beyond what the error requires. Follow `hard_rules.md`. Write the fixed complete source to `out/` and a one-line final message describing the fix.
