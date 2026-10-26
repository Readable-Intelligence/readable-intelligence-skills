# Tests of restructure-paper

The skill was built and tested as `readable-duo` v12; the records below call it v12.

**Naming.** Records before 2026-10-22 use the names of the time: "stage" for a part of the standard, condition ids `S…` (now `P…`), and "the account" for the proof sketch.

## 1. Control flow (stub agents, `--mock`)

The stub agents run with `MOCK_PAIRWISE=longer`, one job at a time. They check the control flow, the staging (every input a prompt names exists), the schemas and the report.

| Scenario | Setting | Path | Result |
|---|---|---|---|
| V1 | failed conditions 5, 3, 1, 0 | rounds; final sheet; confirmation; final acceptance by both families; delivery | passes |
| V2 | failed conditions 5, 5, 5 | stop: no progress in two accepted rounds | passes |
| V3 | round-1 debt | repair loop clears the debt; rounds continue | passes |
| V4 | the confirmation check finds a defect | discovery charged to every version sharing the text; repair; repaired version delivered | passes |
| V5 | repair and revert fail every round | open base each round; original delivered; `deliverable_open/` written | passes |

## 2. Real test on a paper with known exposition problems

**Setup.**
- **Paper:** a 23-page paper on Plancherel algebras, rewritten to 37 pages (M8) by v11 with ad-hoc patches.
- **What an outside comparison with an earlier rewrite had found in M8:**
  - an introduction sketch that lists facts without reasons;
  - proof openings that announce the paragraphs that follow;
  - phrases used before their meaning is given, and compressed labels;
  - commentary on whether a cited proposition is proved;
  - redundancy.
- **Its advantages, to be kept:** main results stated in the introduction; flatness reduced to multiplicities first; commutativity deduced early from stated inputs.
- **The test:** one round of v12 from M8, on an isolated copy, with no hints (no reader reports), using Claude Opus 5.5 at `xhigh` and GPT-6-Astra at `max`. The round consists of:
  - a full panel on M8;
  - one sheet and its execution;
  - the gate;
  - the confirmation check;
  - the final acceptance by both families;
  - the final comparison with the original.

**Evaluation of the result.**
- **Script measurements** of each known issue.
- **E1:** a blind comparison with the earlier rewrite, by a fresh GPT session and a fresh Claude session.
- **E2:** a targeted check of each known issue and each advantage, by a fresh GPT session, against M8.

### First test (v12 as first built)

**Detection.** The acceptance review of M8 failed 16 of 30 conditions. Among them were three of the known problems, found without hints:
- the sketch as an itinerary (S05.3);
- the announcing proof openings (S04.4);
- the commentary on the cited work (S02.4);

plus an unattested term (S01.1) and an undefined hypothesis (S02.1). It did not flag the phrases used before their meaning is given, although the registrar listed them; the compiler was not told to act on the registrar's lists.

**The sheet.**
- **Items:** 19, of kinds edit 15, cut 3, mechanism 1.
- **Execution:** all executed.
- **For the author:** nine problems were recorded, with no prose added. Among them is the reviewer's demand to establish the cited construction's unproved properties.

**Gate.** The vote preferred M9 over M8 (medium confidence). Debt 0, fidelity H 0. The confirmation check found 0 blocking findings in 60 rewritten passages. Both final judges prefer M9 to the original with high confidence.

**Outcome (E2, script):**

| Item | M8 | M9 |
|---|---|---|
| Proof openings announce what follows | fails | **fixed** (6 → 0 announcement sentences) |
| Verbatim commentary on the cited work | present | **removed** (gap phrases 9 → 6) |
| Sketch gives the reason for each step | fails | fails: shorter (319 → 226 words), but two reasons were lost |
| Phrases explained at first use | fails | fails ("closed coordinate diagonal" p. 5 vs p. 16) |
| No commentary on the cited work's status | fails | fails (abstract clause; one sentence in Remark 1.3) |
| Theorems in the introduction; reduction first; early deduction | holds | **holds** |

**Regressions** (E2, and GPT's final acceptance):
- the original's rank formula was cut as "unused";
- the index of where each dependence is used moved into the introduction;
- one sentence was repeated.

The blind comparisons (E1) with the earlier rewrite agree:
- the new version is better in organization, local proofs and redundancy;
- the earlier one is better in the introduction's sketch and in terminology;
- both would revise from the new version.

**What this showed about the skill, and the general fixes made:**

| Gap | Fix |
|---|---|
| The registrar's lists of terms used before their meaning, of clashes and of private names reached the compiler but were not among the problems it must answer | Compiler rule 1 includes every entry of those lists |
| The reviewer did not check whether the introduction gives the reason for each step | The reader's account records, for each step of the route from the introduction, whether its reason is given |
| R4 asked for the dependence "in the abstract if it limits the main result", contradicting R7 | R4: stated once, where it is used, no more prominently than the original states it |
| A `cut` removed original mathematics; the fidelity check did not notice | R4 and the compiler: original mathematical content is moved, never cut. A script detector lists labelled formulas of the original whose label and content are both gone; each needs a fidelity ruling, and a lost one is H (blocking) |

The detector flags exactly the lost rank formula in M9 and nothing in M8. The stub scenarios pass after the fixes.

### Retest (v12 after the first-test fixes)

**Setup.** Same paper, starting point (M8), models and evaluation as the first test.
- **Isolation, part one:** the steps up to the first repair sheet (the review and checks of M8, the sheet, its execution, the checks of M9) ran before the separate Codex home existed. Their GPT steps could therefore see the user's global Codex instructions. The audit caught one step reading a user-installed Codex skill; that attempt was discarded.
- **Isolation, part two:** every later step ran with the separate Codex home, from the repair onwards.

**Detection.** The acceptance review of M8 failed 15 conditions.

**The sheet.**
- **Items:** 13, of kinds edit 9, mechanism 3, cut 1.
- **Origins:** several items came from the registrar's lists, as the fix intended.

**Gate and repair.**
- **M9 rejected:** the vote preferred M9 (medium confidence), but M9 had debt 2:
  - the cut deleted a normalization remark of the original, which the fidelity check ruled lost (H);
  - one added step was rated unsupported.
- **The repair:** M10 restored the remark. It made the unsupported step supported by restating the assumed input it needed more strongly (see below). Debt went 2 → 0, and the vote against the deliverable M8 was newer/medium. The confirmation check found 0 blocking findings in 64 rewritten passages.
- **Final acceptance of M10:** Claude 16 FAIL, GPT 11 FAIL. Both final judges prefer M10 to the original with high confidence.

**Outcome (E2, script):**

| Item | M8 | M10 |
|---|---|---|
| Proof openings announce what follows | fails | **fixed** (6 → 0) |
| Commentary on the cited work | fails | fails: the abstract clause and the verbatim quotations are gone (gap phrases 9 → 3), but Remark 1.3 still says what the cited proposition does not contain and that the paper does not verify it |
| Sketch gives the reason for each step | fails | fails: 319 → 206 words. The reasons for duality and for the opposite algebra are given; the reasons for internal endomorphisms and for E3 rather than E2 are not |
| Phrases explained at first use | fails | fails ("closed coordinate diagonal" p. 5 vs p. 17) |
| Other redundancy | fails | fails: the §9 summaries are gone; the two parallel lists of imported properties and one repeated sentence remain |
| Theorems in the introduction; reduction first; early deduction | holds | **holds** |

**New problems (E2, and the final acceptance by both families):**
- **The assumed input was strengthened.** To repair a step the proof check had rated unsupported, the repair sheet restated one of the unverified imported properties in a stronger form: "at each point" became a full-faithfulness statement for families. It then derived the step from it. The proof check then rated the step verified, because it took the stated property as given; the fidelity check did not compare assumptions with the original's.
- **Reasons were lost.** The shortened sketch dropped the reason for working in Lysenko's categories, because the body states it.
- **Inherited from M8, not yet repaired:**
  - local definitions dropped when material moved;
  - symbol clashes;
  - announcements at section level.

**E1** (blind, against the earlier rewrite): both judges would revise from M10 rather than from the earlier rewrite.
- **Better in M10:** statements, both proof organizations, and local proofs.
- **Better in the earlier rewrite:** the sketch's reasons, and local definitions.

**What this showed about the skill, and the general fixes made:**

| Gap | Fix |
|---|---|
| R7 forbade discussing whether a cited work proves its results, but not discussing whether the paper's *use* of it goes beyond what it states; the compiler kept that discussion as honest disclosure | R1 (class 3) and R7: such a gap is recorded outside the manuscript; the paper says what it uses, positively and with a locator, and never what the source lacks or what the paper leaves unverified. Compiler rule 4: an open problem is neither hidden nor written into the paper; text a revision added about one is cut. The reviewer's required repair never asks for disclosure, and the vote does not count its removal as a regression |
| An unsupported step was repaired by strengthening an assumed input, and both checks accepted it | R1: an assumed input is one the original assumes at that strength, or a cited result as its source states it; closing a gap by a new or stronger assumption is class 3. The compiler may name only such inputs, in a `mechanism` and in a repair. The proof check rates a step resting on a revision-made assumption `unsupported`. The fidelity check rules a new or stronger assumption a change of strength (H, blocking) |
| The registrar listed "closed coordinate diagonal" (used p. 5, defined p. 17), as it had in every registry since the original. The compiler, asked to decide whether each reported problem is real, dismissed it with a group of entries ("the methods vocabulary, reduced by" the sketch item), and that item prescribed the phrase, unexplained, in the new sketch | The registrar (GPT, its own session, max effort) now fixes every problem it finds, directly in each newly written version; the compiler issues no terminology items. Compiler rule 1: every other reported problem is fixed, unless the page is shown, by quotation, not to have it, or the fix would change a statement or need a new argument |

The stub scenarios pass after the fixes. The evaluation's own GPT sessions now also run with a separate Codex home (`tests_v12.nosync/eval/cdx_isolated.py`).

### Third test (v12 after the retest fixes, one more round from M10)

Delivered **M11**. The cited-work gap remark is gone; only the original's own dependence sentences remain. The strengthened input was replaced by an argument (the confirmation check found no blocking finding). Proof openings still hold. Still failing: the sketch's reasons for E3 and for coinduction, and "closed coordinate diagonal" (p. 4, explained p. 17). New problems: glosses and section pointers in the abstract, one definition repeated three times, and two explanations lost from the introduction. The in-run registrar (judging prompt, medium effort) changed 366 lines, mostly glosses of standard notions, and did not fix the phrase.

### Registrar step tests (pages 1–10 of M11's executor output, isolated, `tests_v12.nosync/registrar_test.py`)

| Registrar prompt | "closed coordinate diagonal" | Abstract and introduction | Other | Time |
|---|---|---|---|---|
| Judging ("is this a problem?"), medium and max | missed ("plain description") | +88 words at max | | |
| Old inventory prompt plus "fix", max | fixed | +106 words | glosses of standard notation | |
| Listing, "only what the paper defines", max | fixed | +183 words, 30 insertions | | |
| The old skill's stage 01, verbatim, max | fixed | +161 words, 17 insertions; abstract glossed ℏ and added ℓ ≠ p; k[ℏ], H_O, Rep_k(Ǧ) replaced by words | added a category type, attributions, a convention and an action formula; 229 changed lines | ~50 min |
| One rule, first version, max | fixed (replaced by its description) | +17 words, 4 insertions; abstract unchanged; no standard notation touched | 100 changed lines: "finite" corrected to "of finite type" throughout, a coined "one-sided correspondence" removed; source names kept with locators (e.g. "diagonal strata", Lysenko §7.3); builds | 14.5 min |

The one-rule test also showed two faults: it renamed letters bound in a single sentence or definition to avoid clashes with other uses (`GL_{n_0}`, `G_{0,\mathcal O}`, `D_0`), and its report listed a mathematical "problem" that came from the text extraction of a source (an isomorphism sign lost above an arrow).

Both were fixed by one line each: rule 3 now says that a letter bound inside one sentence, formula or definition clashes with nothing elsewhere, and the registry no longer reports mathematical problems (the checks do).

| Registrar prompt | "closed coordinate diagonal" | Abstract and introduction | Other | Time |
|---|---|---|---|---|
| **One rule, current** (`prompts/registrar.md`), max | **fixed**: replaced by the field's name, "partial diagonals" (BFN 2019, §3(ii)) | +5 words, 2 insertions; abstract unchanged; no standard notation touched | 50 changed lines: "finite" → "of finite type" throughout; two names for one object merged ("purity classes" → "fundamental classes", the alias "finite labels" removed); no bound letter renamed; builds, 38 pages | 17 min |

In this 10-page test the registrar left later pages unchanged, so the renamed terms still occur in their old form there; in a real run it applies each change to every occurrence.

### Agent input closed (2026-10-21)
A GPT step started from a process whose input stays open waits for that input and never starts: an isolated max-effort test sat for 34 minutes at "Reading additional input from stdin…". Every agent call in `scripts/duo.py` now starts with its input closed (`stdin=subprocess.DEVNULL`; 7 calls). Check, with a real GPT call under an input pipe that never closes: without the fix, still waiting after 90 s; with it, "OK" in 4 s.

### Stage 05 replaced: the introduction's account of the proofs (2026-10-22, `tests_v12.nosync/sketch_*`)
Each version of the goal was given, as a single step, to a GPT writer (gpt-6-astra). The writer rewrote only the account of the proofs in M11, with the bundle, style card and hard rules. v1 and v2 were judged against a list of this paper's problems. From v3 on, each version was judged blind:
- two judges, Claude (opus-5-5, xhigh) and GPT (max), each first calibrated on how the reference papers outline their own proofs;
- four versions per round, under random labels: the new one, v3, M11 and the old skill's draft;
- in parallel, a GPT fidelity check of every sentence against the body and the sources.

| Goal given to the writer | Words | Result |
|---|---|---|
| v1: the goal plus rules drawn from this paper's problems | 533 | Rules misapplied: "one pointer is enough" deleted the theorem pointers; lemma-level detail |
| v2: the goal only, first wording | 634 | The route without the reasons |
| **v3** (now stage 05), high effort | 742 | Ranked first by both judges in round 1 and by GPT in round 2 ("as good as the good field examples"). Claude placed it a close second in round 2, behind the old draft ("the best 'how' account") |
| v3 with a separate literature analyst's report (4,458 words) as input | 721 | No better: the report was a survey plus another itinerary |
| v4: the obstacle and key idea, the route at the level of sections, max | 417 | Accurate (fidelity 24/24) but too compressed: says the steps succeed without what makes them work. 2nd (GPT), 3rd (Claude) |
| v5: v3 plus "the idea that drives each proof, stated first", max | 746 | Fidelity 39/39; 2nd (GPT), 3rd (Claude): "essentially [v3]'s content" but less readable |

M11's account, written under the old stage 05, ranked last or third in all four judgements.

The acceptance review was run once with this stage 05 and nothing else changed (`review_test.py`, Claude opus-5-5, xhigh), on v3's version. It wrote `reading.json` before opening `criteria/`. S05.2–S05.4 passed. S05.1 failed for one missing reason, why contravariant duality yields the opposite algebra. It noted, but passed, that the reason for E₃ rather than E₂ was left implicit.

After the change, scenarios V1 and V2 of §1 were rerun with stub agents (`tests_v12.nosync/mock_stage05/`):
- **Prompts:** the pass-2 prompt carries the new stage 05 once and neither the old examples nor "gap-and-mechanism". The review's criteria list 23 conditions, S05.1–S05.4.
- **V1:** five, three, one, then zero conditions fail; M5 is delivered after the confirmation check and the final acceptance.
- **V2:** stops after two accepted rounds without progress.

### The registrar once, after the last structural change (2026-10-22)
Changes:
- **Registrar timing:** it no longer runs after the baseline and after every sheet. `terms()` runs it once in the final phase, on a copy of the version that would be delivered. The copy passes the light gate, with the repair loop on rejection, before the confirmation check.
- **Stage 05 and R6:** S05.1 now says "can find in the account", and R6 keeps only its first sentence.

Stub-agent scenarios (`tests_v12.nosync/mock_registrar_last/`, `MOCK_PAIRWISE=longer`, one job at a time):

| Scenario | Setting | Path | Result |
|---|---|---|---|
| V1 | failed conditions 5, 3, 1, 0 | rounds; final sheet; one registrar job; gate accepts; confirmation on the registrar's version; delivery | passes |
| V2 | failed conditions 5, 5, 5 | stop for no progress; one registrar job; gate; delivery | passes |
| V3 | round-1 debt | repair loop in round 1; rounds; one registrar job; delivery | passes |
| V7 | the gate's fidelity check reports a blocking finding (`MOCK_FAIL=terms_fidelity_lost`); the stub's repair does not build | repair and revert fail; the original is delivered with `deliverable_open/` (the existing fail-safe) | passes |
| V8 | as V7, with the stub's repair anchored to the fidelity finding | gate rejects; repair accepted (debt 1 → 0); confirmation; repaired version delivered | passes |

Every scenario runs exactly one registrar job. Stub changes: the stub registrar leaves a marker; `terms_fidelity_lost` makes the first fidelity check after it blocking; the stub compiler anchors a repair to the first blocking fidelity finding when there is no proof-check finding.

### Renaming, the optional-versus-FAIL rule, and the calibration prompt (2026-10-22)
Changes:
- **Renaming.** The standard's "stages" became parts (`standard/parts/`, `{{STANDARD:part:NN}}`, condition ids `P02.1` … `P06.4`). The introduction's account of the proofs became the proof sketch (`parts/05-proof-sketch.md`), and the reviewer's notes became the reading record.
- **Review.** `accept.md` now says an improvement is optional only if no condition requires it.
- **Calibration.** The calibration prompt's style card and rubric no longer ask for "the barrier or gap" or a "roadmap as a chain of reasons". They now ask what the reference introductions explain about the proofs, what they leave to the body, and the words they spend per idea.

Checks:
- **Conditions:** 23, P02.1 … P06.4.
- **Rendered prompts and the reviewer's criteria:** no remaining "stage" or "account".
- **Stub scenarios** (`tests_v12.nosync/mock_rename/`, one registrar job each): V1 (steady progress), V3 (round-1 debt) and V8 (terminology gate rejects, repair accepted) pass.

### The proof sketch as its own step (2026-10-22)
Changes:
- **New step** after pass 2: `gpt_sketch.md` (v6's prompt verbatim) rewrites only the introduction's proof sketch on pass 2's version B2 and writes `sketch_notes.md`; its output is M1. Pass 2 no longer quotes part 05.
- **Part 05 and `accept.md`** are back to the text under which v6 was written and reviewed (the counterfactual sentence and its bound are set aside, kept in `_superseded/counterfactual_bound/`).

Checks:
- **Stub scenarios** (`tests_v12.nosync/mock_v6_step/`): V1, V3 and V8 run `r0_baseline`, `r0_baseline_2`, `r0_sketch` in order and deliver the same versions as `mock_rename/`; every input the sketch prompt names is staged.
- **With models:** the step itself is the v6 test (`tests_v12.nosync/sketch_t7/`, on M11); not yet run on a pass-2 version.

### Cross-review rounds replace the review-and-fix rounds (2026-10-24)
Changes (decided by the user after the CR3 vs M6 comparison, `tests_v12.nosync/cross_vs_v12/`):
- **Rounds.** After the soundness checks and the repair loop of each round, `cross_review/review.py` (the maintained copy, `cross_review/`) revises the round's base version. v12's checks pass it the problems they found in that version (`reported.json`): unjustified or unsupported steps, failed proof conditions, lost content, copied phrases, bibliography entries and reader reports. The cross review decides each one. The instruction compiler's review mode, the verifier, the final sheet and the stop for no progress are gone. A round that changes nothing ends the rounds.
- **R4 and the fidelity check.** A step of the original may be removed when the paper shows, from the original's hypotheses and definitions or from a cited result as its source states it, that the case it treats does not arise or that another step covers it. The paper states the reason, and every statement keeps its strength.

Stub-agent scenarios (`tests_v12.nosync/cross_in_v12/`, `MOCK_PAIRWISE=longer`, one job at a time; the cross review's own stub agents):

| Scenario | Setting | Path | Result |
|---|---|---|---|
| t1 | the cross review alone, with three reported problems (`cr_runs/t1`) | every reported problem decided and listed in `reported_decisions.md`; the isolation sentence in each network job's prompt | passes |
| V1 | failed conditions 5, 3, 1, 0 | three cross rounds on M1, M2, M3 (1, 4, 4 problems reported); saved works passed on, repeated files skipped; round limit; one registrar job (M5); confirmation; final acceptance; M5 delivered | passes |
| V3 | round-1 debt | repair loop in round 1 (M2 accepted repaired); cross rounds on M2, M3, M4; registrar M6 delivered | passes |
| V8 | the terminology gate's fidelity check reports a blocking finding | gate rejects the registrar's M5; repair M6 accepted and delivered | passes |
| V9 | the cross review's judges reject every item | "a cross-review round changed nothing"; final phase; M2 delivered | passes |
| V11 | debt in the third proof-check job | the debt falls in the confirmation check (the cross review's edits leave no rewritten proof passages earlier); repair; M6 delivered | passes |
| V11b | one script-flagged check ruled lost | not reached: the script checks listed no changed statement in this paper, so the stub had nothing to mark | not exercised (rejection is covered by V8 and V11c) |
| V11c | round-1 debt with `repair_on_reject` false | M1 rejected; the cross review runs on M0 with 0 problems reported; rounds continue; M5 delivered | passes |
| V10 | first stop test | the stop was not sent (the process match was ambiguous); the run finished normally | not a stop test (replaced by V10s) |
| V10s | `stop_test.py`: SIGTERM while the cross review's first judge runs | during the run the vault and the cross review's records are closed (mode 0); v12 exits 1; afterwards nothing is left running, no lock remains, records are back to 0755; `resume` finishes the round and delivers M5 | passes |
| Vfinal | as V1, after the last code change | the same job sequence and report as V1; M5 delivered | passes |

Other checks:
- **Locks** (`lock_probe/`): a stand-in `review.py` sees the vault closed while it runs, and open afterwards; a v12 GPT job also closes `out/cross`.
- **Tool-call audit** (unit test): a Claude WebSearch naming the paper's title, a `curl` with the paper's identifier and a read of the run directory are flagged; the agent's own messages are not.
- **Consistency:** every schema a job names exists and every schema is used; every key of `config.default.json` is used and every key the code reads is defined; every prompt has a stub role and renders with no placeholder left; the files the documentation names exist (or are run outputs); all scripts compile.

## Defensive-sentence pass (2026-10-26)

The final acceptance reviews of the positive-scalar-curvature run still found about 30 defensive sentences ("No principal-curvature bound for the boundary is assumed.") that no step had been asked to remove. A last GPT step now deletes the ones the reader does not need (`prompts/gpt_defensive.md`); the script keeps its output only if it builds and only deletes text (`texutil.deletions_only`).

- **Unit test** (copies of that run's M8 source): two deleted sentences, one across a line break, are accepted and listed; a changed word, a missing file and an identical copy give `None`, `None` and no deletions.
- **Stub scenarios** (toy paper, `MOCK_PAIRWISE=longer`): with the stub deleting the paper's two "No … is assumed/needed." sentences, M6 (M5 minus them) is delivered and the report lists both deletions and keeps M5's proof-check table; with `MOCK_FAIL=defensive_adds` the output adds a word, is rejected, and M5 is delivered.
- **Real pass on the positive-scalar-curvature run's M8** (GPT-6-Astra, max):
  - First instruction ("…or answers an objection nobody raised…; keep… every statement of a result's scope"): 56 deletions in 12 minutes; 7 of them removed a reason, a case or a conclusion, and the defensive sentences inside statements of results were kept (13 left by the pattern scan).
  - Current instruction: 39 deletions in 7 minutes; the 7 passages are kept and the defensive sentences inside statements are gone (10 sentences left by the scan, most of them content: strength, non-circularity, definitions). Two deletions are judgement calls: the last statement of the directed-versus-undirected incidence point (Section 6), and the list of hypotheses the main theorem does not need (after Theorem 1.1).
