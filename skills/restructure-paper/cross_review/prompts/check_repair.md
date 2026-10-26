# Role: Checking the fixes another reviewer wrote for your list

You reviewed the writing of a mathematics paper by comparing it with its literature; your notes from that review are in `notes/`. Another reviewer, who reviewed the same paper independently, then judged everything on your list, and for each item in `items.json` (the same in `items.md`) it disagreed with you and wrote a fix. Each item has a `kind`:
- `issue`: one of your findings. The other reviewer agreed that the problem is real and worth fixing, but found your fix wrong; the item gives your fix (`original_fix`, `original_edits`), its reason (`judge_reason`) and its corrected fix (`fix`, `edits`);
- `not_issue`: a place you noted and decided is not an issue. The other reviewer found it an issue; the item gives what you noted and your reason, its reason (`judge_reason`) and its fix (`fix`, `edits`);
- `open`: a problem you left open for the author. The other reviewer found a fix; the item gives the problem, its reason (`judge_reason`) and its fix (`fix`, `edits`).

A fix is applied to the paper only if you accept it. You are the only check between it and the paper.

## Inputs (in the workspace)
- `paper/` (root file `{main}`), `paper.pdf`, `paper.txt` (with `<<<PAGE n>>>` page markers) and `literature/`, as in your review.
- `notes/`: your notes on the paper (`paper.md`), its literature (`literature.md`) and how that literature writes (`patterns.md`).
- `sources/`: the works that the two reviewers obtained online during their reviews, where they saved any: `sources/yours/` from your review, `sources/other/` from the other reviewer's. Each file says at its top what it is and whether it is the work's exact text.
- `items.json`, `items.md`: the items, as described above.

## Task
For each item, check the other reviewer's reason against the paper and the works it relies on, in their exact text where `literature/` or `sources/` has it, and judge the fix by the standard below. Your earlier decision on the item does not settle the question: judge the reason on its merits. Accept the fix only if:
1. the problem it addresses is real, and the paper is better for its reader with the fix than without it, at the place where the reader meets the passage. For a corrected fix of your own finding, you have already said so;
2. the fix is a fix by the standard below: it is correct, it resolves the problem at every place where the reader meets it, it changes no more than the problem requires, and every other passage of the paper that states, restates or relies on what it changes is still correct with it. Look for those passages in the whole paper, not only near the edits.

Otherwise reject it, and say why. Do not reject a fix because you would have worded it differently.

{standard}

## Output
`verdicts.json` (schema `schemas/verdicts.schema.json`): for each item, its `id`, the `verdict` (`accept` or `reject`) and the `reason`.
