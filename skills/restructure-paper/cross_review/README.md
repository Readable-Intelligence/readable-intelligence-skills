# Cross review

Two reviewers find the issues in a paper's writing, each judges the other's findings, and the findings that pass are merged and applied.

In restructure-paper (`../README.md`), each round runs `review.py` once on the round's base version, from `scripts/duo.py`, with the problems its checks found in that version (`--reported`). This folder is the maintained copy; it was taken on 2026-10-24 from the standalone tool in `rewrite_v11/cross_review/`, which keeps the batch tool (`batch.py`, `prompts/extract.md`) and the records of its tests.

1. **Review.** Claude (Opus 5.5, xhigh) and GPT (6 Astra, max) work independently. Each reads the whole draft and the literature it relies on, and writes notes on both. The notes include how that literature writes: the patterns its works share, with examples. Each reviewer then compares the draft with those patterns and lists the places where the draft departs from them at a cost to its reader. Each issue comes with a fix written as exact edits to the LaTeX source. The list also gives the problems the reviewer leaves open for the author, and every place it noted and decided is not an issue, with its reason. Each reviewer saves the works it obtains online in `sources/`, one file per work, saying at the top what the work is, where it came from, and whether the file is the exact text. Claude's list is A and GPT's list is B.
2. **Cross review.** Each reviewer gets its own notes back, and the works both reviewers saved (`sources/yours/`, `sources/other/`), and judges every item on the other's list, with a reason: it accepts or rejects each issue and each open problem, and agrees or disagrees with each decision that a place is not an issue. Where it finds an issue's fix wrong, finds an issue at a place the other decided is not one, or can fix an open problem, it writes the fix; the item's author then accepts or rejects that fix, with the same saved works, and only an accepted fix is applied. Open problems go to the author only if the other reviewer confirmed them, or if the fix it wrote was rejected.
3. **Merge.** A script collects the items one reviewer proposed and the other accepted. GPT merges the overlapping ones into one list. It also gets the rejected fixes with their reasons. Where a reason given for accepting or rejecting any fix names a fault that an accepted fix shares, the merge leaves that part out, or the whole finding.
4. **Revise.** GPT applies that list to the draft, and nothing else. A script compares the result with the list applied exactly.

```
python3 review.py run --name NAME --draft PATH [--literature PATH ...] [--prompts DIR ...] [--reported FILE] [--config FILE] [--mock]
python3 review.py resume --name NAME          # continue after a stop; finished steps are not rerun
python3 review.py status --name NAME          # print the report
python3 review.py unlock --name NAME          # restore the records' permissions after a crash
```

- `--draft`: the paper's LaTeX source, either a directory or a single `.tex` file. It must compile.
- `--literature`: optional files or directories of works the reviewers should read. A PDF also gets a text version. The reviewers find any other works online. Claude's web reader returns processed page content rather than the exact text, so supply the works whose exact statements matter.
- `--prompts`: optional folders of prompt files to use in place of those in `prompts/`; the first folder that has a file wins. The run keeps a copy of the prompts it uses in `prompts/` of the run, so a resumed run uses the same ones.
- `--reported`: optional problems that other checks of the paper found, as `{"about": "...", "problems": [{"id", "check", "location", "quote", "problem"}]}`; `about` (optional) says where they come from. Both reviewers get them (`reported.md`, read after their first reading) and decide each one, as an issue, an open problem or a place that is not an issue, naming its id in that item's `reported`. The judges see them too; for a place decided not to be an issue, the reason holds only if the problem the check found is not there. A fix of a step the paper does not justify is the shortest complete justification.
- In `--config`, `avoid` lists strings that identify the paper itself (title, slug): the reviewers are told never to open, download or search for it, and the audit flags any search or download naming one. `sensitive` lists further paths that no agent may touch (`scripts/duo.py` gives its run directory and package).

## Rounds

```
python3 rounds.py run --name NAME --draft PATH [--literature PATH ...] [--prompts DIR ...] [--rounds N] [--config FILE] [--mock]
python3 rounds.py resume --name NAME          # continue where the rounds stopped
```

One run finds only some of a paper's problems, and a different set each time. `rounds.py` runs the whole process again on the paper as the last round left it, with fresh reviewers, up to N rounds (default 3), and stops early when a round changes nothing. Each round is a run of `review.py` in `runs.nosync/NAME/roundK/`, with the prompts of round 1. Its reviewers do not see the earlier rounds' notes or lists. They get the supplied literature and the works that the earlier rounds' reviewers saved (`NAME/obtained/roundK_A/`, `roundK_B/`, given to them under `literature/obtained/`). A saved file identical to one already passed on, or supplied, is not passed on again, nor are the files saved with it under the same name; these stay in the round's records. Outputs in `runs.nosync/NAME/`:
- `report.md`: what each round applied, and where it stopped;
- `revised/`, `revised.pdf`: the paper after the last round that changed it;
- `revised_vs_draft.md`: every passage changed since the draft;
- `open_questions.md`: the problems every round left for the author (a later round may have fixed some).

## The prompts

- `prompts/review.md`: the reviewers' task, step 1.
- `prompts/standard.md`: what counts as an issue (a departure from the literature's patterns, as the reviewers found them, that costs the reader) and what a fix must be. It is included in `review.md`, `cross_review.md` and `check_repair.md`, so every step judges by the same rules.
- `prompts/cross_review.md`: step 2.
- `prompts/check_repair.md`: step 2, the author's check of a fix the other reviewer wrote for its list.
- `prompts/merge.md`: step 3.
- `prompts/revise.md`: step 4.

## What the script checks

Before a run starts, the tool's own files, prompts, schemas and prompt folders must all be on this disk. iCloud moves the content of little-used files to the cloud when the disk is short of space, and reading such a file can return nothing, so a step would run with an empty prompt; the run stops instead and names the files.

When an output fails a check, the step reruns in a fresh session. That session starts from the failed attempt's outputs and is told what failed, so a long review gets corrected rather than redone. A step is rerun at most twice.

- **Review.** Every edit's `old` occurs exactly once in its file, and `new` differs from it. No two edits change the same text. Every reported problem is decided by an item that names its id, and every id named is a reported one.
- **Cross review.** Every item gets exactly one verdict; a place decided not to be an issue is agreed with or given a fix, not rejected. A fix written by the judge applies to the draft, under the same rules as a review's edits. The author's check gives each such fix exactly one verdict, accept or reject.
- **Merge.** Every accepted finding is covered by exactly one item, or is listed as left out with the reason. A finding that is not merged with another keeps its edits unchanged, unless the item's merge note says what was left out. The whole list applies to the draft at once: every `old` is found, and no two edits overlap.
- **Revise.** The revised source compiles and has no undefined reference or citation that the draft lacked. `deviations.md` lists every passage where the result differs from the list applied exactly.

Each agent runs in its own workspace, with the run's records locked while it works, and its tool calls are audited afterwards; see `agents.py`. Each finished job's record has `_activity.md`: the time and tokens it used, its messages, and its tool calls in order. If Claude Code refuses any tool call for lack of permission, the run stops with a message. That is a setup fault, which a retry cannot fix; without the check the step would pass while the reviewer worked without the literature. The reviewers can use the network, but the merge and revise steps cannot.

## Outputs of one run of `review.py` (`runs.nosync/NAME/`; within rounds, `runs.nosync/NAME/roundK/`)

- `report.md`: counts and pointers.
- `list_A.md`, `list_B.md`: everything each reviewer decided (issues, open problems, places decided not to be issues), with the other reviewer's verdict, and any fix it wrote with the author's check of it.
- `open_questions.md`: problems the reviewers found but could not fix correctly, as the cross review left them. They are for the author and are not applied.
- `final_list.md`: the merged list, and the accepted findings the merge left out, with the reasons.
- `revised/`, `revised.pdf`: the revised paper.
- `changes.md`: the editor's account of the revision.
- `deviations.md`: where the revised paper differs from the list applied exactly.
- `revised_vs_draft.md`: every changed passage.
- `reported_decisions.md` (when problems were reported): for each, the items that decided it, with the verdicts; the problems themselves are in `records/reported.md`.
- `records/`: the copied draft and literature, and every step's workspace (`records/jobs/`). The reviewers' notes, including the patterns each found (`patterns.md`), are in `records/jobs/review.A/notes/` and `records/jobs/review.B/notes/`, and the works each saved in `records/jobs/review.A/sources/` and `records/jobs/review.B/sources/`.

## Files

- `review.py`: the pipeline, one round.
- `rounds.py`: runs the pipeline in rounds.
- `agents.py`, `tex.py`: the agent runner and LaTeX helpers, first copied from `readability_lab/` so that the tool stands alone. The runner adds web access for Claude, and lets a retry start from the failed attempt's outputs.
- `config.json`: models, timeouts and parallelism.
- `schemas/`: the output formats.
- `mock_agent.py`: stub agents for `--mock`, which test the tool itself without any model.

Standard library only. Needs `claude`, `codex`, `latexmk` and `pdftotext` on PATH.
