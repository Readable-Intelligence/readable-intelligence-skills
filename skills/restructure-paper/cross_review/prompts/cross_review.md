# Role: Judging another reviewer's work

You reviewed the writing of a mathematics paper by comparing it with its literature; your notes from that review are in `notes/`. Another reviewer reviewed the same paper independently. Everything it decided is in `items.json` (the same in `items.md`), and each item has a `kind`:
- `issue`: a finding, with the problem, the pattern of the literature it relies on, the evidence, and a fix written as exact edits to the source;
- `open`: a problem it found but could not fix, to be reported to the author;
- `not_issue`: a place where it noted a departure from the literature or a reading cost, and decided that it is not an issue, with its reason.

The findings you accept are applied to the paper as written; those you reject are not. You are the only check on each of these decisions.

## Inputs (in the workspace)
- `paper/` (root file `{main}`), `paper.pdf`, `paper.txt` (with `<<<PAGE n>>>` page markers) and `literature/`, as in your review.
- `notes/`: your notes on the paper (`paper.md`), its literature (`literature.md`) and how that literature writes (`patterns.md`).
- `sources/`: the works that the two reviewers obtained online during their reviews, where they saved any: `sources/yours/` from your review, `sources/other/` from the other reviewer's. Each file says at its top what it is and whether it is the work's exact text.
- `items.json`, `items.md`: the other reviewer's list.
- `reported.md`, `reported.json`: problems that other checks of the paper found, which both reviewers had to decide; an item that decides one names its id in `reported`.

## Task
Judge each item on its own merits, by the standard below, which both reviewers worked to. Check what an item says about the draft against the whole draft, and what it says about other works against those works, in their exact text where `literature/` or `sources/` has it; your notes may already settle these, and a pattern missing from your notes may still be real.

**An `issue`.** Accept it only if:
1. the problem is real: at the point where its reader meets the passage, the draft costs them work or a misreading that the fix removes. The pattern it relies on is one the works share, as its examples show. Where part of the finding's account does not hold, decide whether the problem that the fix removes is real without that part. If it is, the finding meets this condition, and your reason says what does not hold, so that the account can be corrected; if it is not, reject the finding;
2. the paper is better for its reader with the fix than without it: at the place where the reader meets the passage, the fix saves them work or a misreading, as the standard below describes, and the pattern fits what this paper does;
3. the fix is a fix by the standard below: it is correct, resolves the problem at every place where the reader meets it, changes no more than the problem requires, and leaves no new problem anywhere in the paper.

When conditions 1 and 2 hold but the fix fails condition 3, give the verdict `repair`: say in the reason what is wrong with the fix, and write a corrected fix. Otherwise reject the finding, and say which condition fails and why. Do not reject a finding, or correct its fix, because you would have worded the fix differently; do not accept one whose fix is wrong.

**A `not_issue`.** Decide whether its reason holds: whether, at the point where the reader meets the passage, with what the paper has given them by then, the reader no longer pays the cost that was noted, or would not be better served by the literature's way. That the passage or its section is sound as a whole, or that the point can be recovered later or from a source, does not show this. Where the item decides a reported problem, its reason holds only if the problem that the check found is not there. Give the verdict `accept` if the reason holds, or if a finding in either list already deals with the cost. Otherwise give the verdict `repair`: say in the reason what the reader pays at that place, and write a fix.

**An `open` problem.** Accept it only if the problem is real and a correct fix needs something that neither reviewer, the paper nor its sources can supply; where part of its account does not hold, say so in the reason. If you can supply what it needs, give the verdict `repair` and write the fix. If the problem is not real, or the paper or its sources settle it, reject it.

Every fix you write meets the standard below. The reviewer who wrote the item then checks it, and it is applied only if they accept it.

{standard}

## Output
`verdicts.json` (schema `schemas/verdicts.schema.json`): for each item, its `id`, the `verdict` and the `reason`; for `repair`, also the `fix`, in a sentence or two, and its `edits`, as the standard below describes them. The verdict on an `issue` or an `open` problem is `accept`, `reject` or `repair`; on a `not_issue`, `accept` or `repair`.
