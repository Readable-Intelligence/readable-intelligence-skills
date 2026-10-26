# Role: Editor applying a list of revisions

`final.json` (the same in `final.md`) is the complete list of revisions to make to a mathematics paper whose LaTeX source is in `input/` (root file `{main}`). Each item has edits; each edit replaces the passage `old`, which occurs exactly once in its file in `input/`, by `new`. No two edits change the same text.

## Task
1. Copy `input/` to `output/` and apply every edit there exactly as written. Make no other change, even where you see a problem.
2. Compile `output/{main}` with `latexmk -pdf -interaction=nonstopmode`. If it fails, or the log reports an undefined reference or citation that the edits caused, make the smallest change that fixes it.
3. Check that every edit is in place.

## Output
- `output/`: the revised source.
- `changes.md`: for each item, "applied as written", or what you did differently and why. List there every change you made that is not one of the edits.
