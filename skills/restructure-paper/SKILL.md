---
name: restructure-paper
description: Fully automated two-model rewrite of a proof-based mathematics or theoretical CS paper (LaTeX) for readability. One written editorial standard (terminology, statements, architecture, local proofs, contribution) defines what a good version is; an independent acceptance review judges every version against each of its conditions. GPT (Codex CLI) retrieves the literature, writes the baseline revision, and does the well-defined checking (fidelity to the original, an independent check of every rewritten proof passage). Claude (Claude Code CLI) does the judgement: calibrating against comparable papers, the acceptance review, the repair sheets, and a blind vote that guards against regressions. Each round's revision is written by a cross review in which both models review the writing against the paper's literature and judge each other's findings; it also decides every problem the checks found. Statements are preserved exactly; incomplete arguments are completed and checked; what the reader does not need is cut. Use when the user asks to make a math/TCS manuscript readable with Claude and GPT working together.
---

# restructure-paper

Turns a LaTeX manuscript into a version that researchers in its field can read and check as easily as the best human-written papers on neighbouring problems. The model throughout is a careful expert editor working on a colleague's paper:
- understand the mathematics;
- arrange the paper as strong papers of its kind are arranged;
- make every nonstandard step checkable from the page;
- remove what the reader does not need;
- say plainly what could not be settled.

**Statements keep exactly their original strength; arguments do not keep their original gaps.** A missing step is written in and independently checked, using only the original's assumptions and cited results as their sources state them. A gap that needs more goes to the author in the report; the paper gets no prose about it, neither to hide it nor to disclose it.

This version joins two earlier skills: the editorial standard of the previous, single-model `restructure-paper` (kept verbatim in `standard/`, except part 05, part 06's two references to it, and the renaming of its "stages" to parts) and the two-model machinery of `readable-duo` v11. It was built and tested as `readable-duo` v12, the name its records use. Why each part is there is in `docs/DESIGN.md`.

## Run it

**Prerequisites:** `claude` (Claude Code, logged in with a Claude subscription), `codex` (Codex CLI, logged in with a ChatGPT subscription), `latexmk`, `pdftotext`, Python ≥ 3.9.

Run as an ordinary user. **Neither the run directory nor this package may sit in a folder a sync service mirrors** (iCloud Drive including Desktop & Documents, Dropbox, OneDrive, Google Drive): those services reset directory permissions, which disables the isolation lock, and evict files when the disk fills, which makes steps fail. The script refuses both. With iCloud Drive, a folder whose name ends in `.nosync` is safe.

```bash
python3 scripts/duo.py run    --src path/to/paper_source --out path/to/run.nosync [--config my.json]
python3 scripts/duo.py status --out path/to/run.nosync
python3 scripts/duo.py resume --out path/to/run.nosync [--config my.json]   # pass the same --config again
python3 scripts/duo.py unlock --out path/to/run.nosync                      # only after a kill -9
```

**Models** go in `--config`, for example `{"claude": {"model": "claude-opus-5-5", "effort": "xhigh"}, "gpt": {"model": "gpt-6-astra", "effort": "max"}}`. Per-role overrides: `"role_model": {"check.md": "<model>"}`, `"role_effort": {...}`; preflight tests each.

**Inside Claude Code:** start the command in the background and report the run directory; do not read anything under `run_dir/vault` while the run is in progress.

**Optional input:** reports from other readers can be placed in `run_dir/vault/reader_reports.json` (`{"reports": [{"id", "page", "location", "quote", "problem"}]}`); each cross-review round decides each one whose passage is still in its base, like any other reported problem.

**Results:** `run_dir/deliverable/` (source and `paper.pdf`) and `run_dir/report.md`. If a later working version still carries an unresolved finding, it is handed over separately in `deliverable_open/` with its findings.

`--mock` replaces both models with a stub to test the control flow (and checks that every input a prompt names is staged).

## The standard

`standard/` holds the editorial standard: the contract shared by all editing work, six parts (01 terminology and notation, 02 statements, 03 architecture, 04 local proofs, 05 the proof sketch in the introduction, 06 complete repair). The parts are areas of the standard, not steps of the workflow: a step carries out or reviews some of them, their examples, and the reviewer's protocol, application rules and checklist. It is the single source: prompts quote it through `{{STANDARD:…}}` placeholders (`scripts/standard.py`), and the acceptance conditions of parts 02–06 are numbered `P02.1` … `P06.4` (23 conditions). Part 01 stays in `standard/` for reference but is not run: names and symbols follow the registrar's rule (`prompts/registrar.md`). Part 05 is this skill's own: one goal, what a specialist should understand from the proof sketch in the introduction about what each main proof turns on (its decisive ideas), in place of the old procedure and its examples. It is general; nothing in it is about a particular paper.

`prompts/hard_rules.md` (R1–R9) binds every role that reads or writes the manuscript: exact statements and completed arguments (R1); professional, verified terminology with no compressed labels (R2); one meaning per symbol (R3); removal of what the reader does not need (R4); exact, usable statements (R5); mechanisms on the page (R6); correct attribution, cited results used as stated (R7); references as evidence, not templates (R8); a clean, compiling manuscript (R9).

## Who does what

| Step | Model | Writes |
|---|---|---|
| Literature retrieval (web on) | GPT | `refs/`: texts, manifest, term table, including comparable papers and the sources of imported results |
| Calibration | **Claude** | how comparable papers are arranged and written (`architecture.*`, `style_card.md`, rubric for the vote), gaps in the bundle |
| Terminology verification | GPT | verified terms (quotations checked by script) |
| Baseline, pass 1: parts 02–03 | GPT | an arranged version with exact statements; the arrangement plan (script: every labelled result placed) |
| Baseline, pass 2: part 04 and the reading views | GPT | local proofs completed; notes on added arguments and open gaps |
| Proof sketch: part 05 (`gpt_sketch.md`) | GPT | the introduction's proof sketch, rewritten on pass 2's version and nothing else changed; `sketch_notes.md`, where the body or a cited source gives each reason |
| **Each round:** | | |
| · Acceptance review | **Claude** | `reading.json` (the reading record, written before the standard is opened; the tool log proves the order), then `acceptance.json`: PASS / FAIL / UNVERIFIED on every condition, with located evidence and, for each FAIL, the required repair; math issues |
| · Vote (regression guard) | **Claude** | blind vote between the candidate and its predecessor, with each side's regressions |
| · Fidelity check | GPT | statements, lost steps and qualifications against the original, with a ruling on every place a script flags |
| · Independent proof check | GPT | a verdict on every rewritten proof passage and every added step |
| · Planted defects (round 1) | GPT | whether the checkers find three planted defects; a miss adds Claude checkers to every later round |
| · Cross review (`cross_review/`, its own process) | **Claude and GPT** | the next version. Each reviews the writing against the paper's literature (finding online what the bundle lacks, never the paper itself) and decides every problem the checks found in the base; each judges every item of the other's list and checks any fix the other wrote for its own; GPT merges the accepted fixes and revises the paper. Records in `run_dir/cross/round<k>/` |
| Registrar | GPT, its own session (max effort) | once, after the last structural change (after the rounds, before the confirmation check), on a copy of the version that would be delivered, which then passes the light gate: one rule for every name and symbol, applied directly in the source: what the field uses for this object stays as it is, abstract included; anything else gets the field's name or a short explanation at its first use; one name per object; nothing but names and symbols changes. The version is rebuilt from its output |
| Repair loop | Claude → GPT | repair sheets (`instructions.json`: items of kind `edit`, `mechanism` or `cut`, each anchored to source lines) for exactly the findings that block a version, executed by GPT with a receipt; then a revert sheet if needed |
| Confirmation check | GPT | a fresh check of every rewritten proof passage of the version to be delivered |
| Final acceptance review | **Claude and GPT, separately** | the delivered version against every condition, for the report |
| Final comparison | **Claude and GPT, separately** | final version vs original, blind |
| Defensive-sentence pass | GPT | last, on the version to be delivered (not on the original): one instruction deletes each sentence or clause whose only content is what the paper does not assume, need, require, impose, use or aim at (also inside statements), keeping anything that gives a reason, covers a case, or states a conclusion or property used later. Kept only if it builds and only deletes text (script); not checked again; every deletion listed in the report |

## Keeping the two models independent

Every step is a fresh process in a freshly staged workspace with an opaque name, containing only its listed inputs. The models communicate only through typed files: references (GPT → Claude, with GPT's commentary stripped), the calibrated standard (Claude → GPT), manuscript versions (GPT → Claude, blind, comments stripped), repair sheets (Claude → GPT), check results (GPT → the Claude compiler), and, for each cross-review round, the base version with the problems the checks found in it. Claude runs with `--restricted --safe-mode --no-session-persistence` and file tools only; GPT runs `codex exec --ephemeral --ignore-user-config` in a `workspace-write` sandbox with the network off except during retrieval, and with its own Codex home inside the run directory (only the login is shared), so the user's global Codex instructions, skills, memories and history never reach a step. If Codex refreshes the login during a step, the refreshed login is carried back to `~/.codex/auth.json`. While steps run, the vault and the other CLI's session stores are made unreadable, a watcher stops the run if the lock is undone, and every step's tool calls are audited. The cross review runs as its own process on copies staged in `run_dir/cross/`, with the vault locked; its own steps lock its records and are audited too (any read of this run directory or package, any search or download of the paper itself). Its steps use the same CLIs and the run's models, with the cross review's own timeouts and limits (`cross_review/config.json`, overridable through `"cross_review"` in `--config`). While the skill's own steps run, `run_dir/cross/` is locked.

## Decisions made by the script

- **Soundness debt.** Blocking findings are fidelity items of severity H and added steps the proof check rates `unsupported` or `false`. The debt of a version is every blocking finding of every check so far whose text is still in it, unchanged. All versions are measured on this same evidence, so a defect found late in shared text counts against every version containing it.
- **Acceptance of a candidate:** it builds, it has no debt, and the vote does not find it worse than its predecessor (overall with medium confidence or more, or for one reader with high confidence). The vote only guards against regressions; what is still wrong is the acceptance review's business.
- **Repair instead of discard:** a candidate rejected only for debt goes to the repair loop: local repair sheets for exactly its findings, each checked locally and accepted when the debt strictly falls and the vote against the current deliverable does not find it worse; at most `max_repairs` attempts, then one sheet restoring the original's wording where the findings sit. If debt still remains and the round's vote preferred the candidate strongly, it becomes the working base; only debt-free versions are delivered.
- **What the next round decides:** the cross review finds the writing problems itself, against the paper's literature. It also gets every problem the checks found in its base: fidelity findings of severity H and M, added steps the proof check did not confirm and gaps it found (class 1–2), failed proof conditions (P04) and math issues of the acceptance review, false or unsupported claims the vote found, copied passages, added references that match no paper of the bundle, and reader reports. Both reviewers decide each one; a fix of it is the shortest correct one, and one that would need a statement changed or an argument nobody can supply goes to the author. The other failed conditions of the acceptance review are not passed on: readability is the cross review's own judgement. Terminology and notation are the registrar's, once, at the end.
- **Stopping:** every condition passes with clean checks; a cross-review round changes nothing; two rejections in a row; or the round limit (`rounds`, default 3).
- **Before delivery:** a fresh proof check of every rewritten passage of the version to be delivered (findings go through the repair loop), the final acceptance review by both families, and the blind comparison with the original by both. The delivered version is the last accepted version without debt, unless both final judges prefer the original; the defensive-sentence pass then runs on it (`"defensive_pass": false` turns it off).
- **Coverage is enforced by script:** an output is rejected and the step retried if a condition, a proof passage, a flagged place or a labelled result of the original lacks its verdict or placement.
- **Usage limits** pause the run with growing back-off; `resume` continues where it stopped.

## Report

`report.md` opens with added proof steps the independent check did not confirm, then the final acceptance table (every condition, by Claude and by GPT, with what still fails), the mathematical issues and the questions for the author, the soundness debt of every accepted version, the defences that ran and whether they were shown to work, the arrangement against comparable papers, every round, the cross-review rounds (problems reported and given a fix, items applied, passages changed), the final comparison and step times. The questions for the author include the problems each cross-review round's reviewers left open (`cross/round<k>/open_questions.md`).

## Files

```
SKILL.md                this file
README.md               overview with workflow diagrams (Mermaid)
config.default.json     models (with per-role overrides), rounds, repair loop, checks, limits, isolation
standard/               the editorial standard (parts, examples, reviewer protocol), single source
prompts/                one prompt per role, plus hard_rules.md
schemas/                JSON schemas for every structured output (validated by script; invalid output → retry)
scripts/duo.py          orchestrator (standard library only)
scripts/standard.py     renders the standard into prompts; numbers its acceptance conditions
scripts/texutil.py      LaTeX build, statement extraction, diffs, anchors, structure measurements, detectors
scripts/mock_agent.py   stub for --mock
cross_review/           the cross review run by each round (README, review.py, prompts, schemas, its own stub)
docs/DESIGN.md          why the skill is built this way, the evidence, and the residual risks
docs/TESTS.md           the tests run on this version and their results
```
