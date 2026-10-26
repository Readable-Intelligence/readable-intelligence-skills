# Role: Merging the accepted findings into one list of revisions

Two reviewers reviewed the writing of a mathematics paper independently, then judged each other's findings. `accepted.json` (the same in `accepted.md`) holds the findings that one reviewer proposed and the other accepted, with the reason for accepting. Where the other reviewer corrected a finding's fix and the finding's author accepted the correction, the finding carries the corrected fix. Some findings began as a problem one reviewer left open for the author, or as a place it decided was not an issue; the other reviewer wrote the fix, and the first accepted it. Each gives a problem, its evidence, and a fix as exact edits to the source in `paper/`: each edit replaces the passage `old`, which occurs exactly once in its file, by `new`. Make one clean list of the issues and their revisions. An editor will revise the paper by applying your list exactly, and nothing else.

## Inputs (in the workspace)
- `paper/`: the LaTeX source (root file `{main}`); `paper.txt`: the compiled text, with `<<<PAGE n>>>` page markers.
- `accepted.json`, `accepted.md`: the accepted findings.
- `rejected.json`, `rejected.md`: the fixes that were rejected, with the reasons: findings the other reviewer rejected, and fixes the other reviewer wrote that the item's author rejected.

## Task
Findings overlap when they concern the same problem, or when their fixes change the same text or would conflict (one changes text that another's fix relies on). Merge each group of overlapping findings into one item: one statement of the problem, and one set of edits that carries out the fixes of the group. Where two fixes in a group do the same thing in different words, keep one. Where they make different changes to the same text, make both changes in one edit, in the words of the fixes and of the paper, with only the words needed to join them. Where one change cannot be made together with another, keep the one that leaves the paper better for its reader, weighing what each change gives the reader and what each takes away, and say what was left out and why.

Each reason in `accepted.json` and `rejected.json` is a reviewer's check of a fix. Where a reason says that something a fix states or implies does not hold, an accepted fix that states or implies the same thing has the same fault: leave that part of it out, or the whole finding if no correct part remains, unless the paper shows that it does hold, and say why. A reason that a fix is not worth making concerns only that fix.

Add nothing that no accepted fix contains, and leave out nothing that an accepted fix does, except as just described. A finding that overlaps no other becomes an item on its own, with its edits unchanged except for a part left out as just described. In the whole list, every `old` is copied exactly from the original file in `paper/` and occurs there exactly once, and no two edits change the same text.

## Output
`final.json` (schema `schemas/final.schema.json`):
- `items`, in the order of their place in the paper. For each:
  - `sources`: the ids of the findings it covers;
  - `location`, `problem`, `fix`: as in the findings, combined for a merged item. Where the reason for accepting a finding says that part of its account does not hold, leave that part out;
  - `edits`;
  - `merge_note`: how the fixes were combined, and anything left out and why; empty for a single finding whose edits are unchanged.
- `left_out`: the findings left out as a whole, each with its `id` and the `reason`; empty if none.

Every accepted finding is covered by exactly one item or is in `left_out`.
