---
name: restructure-paper
description: Rewrite a proof-based mathematics or theoretical computer science paper with source-verified terminology, economical precise statements, a brief gap-and-mechanism introduction, and understandable global and local proofs. Use for full manuscript restructuring or inherited AI-written exposition problems. Includes independent checking and repair during execution, followed by separate acceptance; preserves complete mathematical content while changing its presentation.
---

# Rewrite a mathematical paper

Use this package as the complete editorial workflow. Its six stage prompts replace earlier rewrite checklists. Do not concatenate obsolete versions or require a separate older terminology workflow afterward.

## Execution

1. Preserve the supplied original as `author_original`. Identify its authoritative source, target audience and available build command. Read the whole paper. Use the supplied source rather than an earlier rewrite. The stage editor fixes harmless build defects in its own candidate and records them; the original stays unchanged.
2. Execute stages 01–05 in order on the current manuscript. For each pass name the current input `stage_input`; the editor initially receives only that input and its generated prompt. Generate it with `python scripts/render_prompt.py STAGE --output PROMPT.md`. This self-contained prompt governs the independent editing pass, including examples and acceptance conditions. Supply it without ad hoc coaching or competing rules. Produce a complete revised candidate, with `changes.md` mapping the immediate input to the candidate.
3. Before finalizing any execution, including retries and stage06, perform the [independent execution check](review/execution-check.md) using the [general checklist](review/general-checklist.md). A fresh subagent first saves manuscript-only reader observations, then receives the criteria and checks necessary sources against that frozen account. It derives concerns anew from the current candidate. Return its findings to this execution's own editor, which makes justified repairs and records its responses; the checker verifies the affected text and dependencies. This is a staged permission to read the current execution's checker report after the independent editing pass, not access to previous diagnoses or other executions. Freeze `stage_output` only after this checkpoint is completed, with unresolved limitations explicit. Professional terminology, precise same-strength claims and complete arguments remain hard constraints; optional preferences do not require edits.
4. Submit the checked output to a different fresh independent reviewer using [review/independent.md](review/independent.md), [the reader-centered application](review/application.md), the exact stage prompt, `author_original`, `stage_input` and `stage_output`. Neither the editor nor its execution checker can supply this acceptance. Withhold editor notes and execution-check findings until the reviewer's own discovery is saved. Reconcile every failure against the actual paper, checking cumulative preservation against `author_original` and stage scope against `stage_input`.

   The coordinator verifies defects but does not patch manuscript content. Distinguish an inadequate general instruction from failure to apply an existing one; revise the skill only when evidence justifies a general correction, then regenerate affected prompts and check package consistency. A new execution starts from the designated original or last accepted skill-generated checkpoint, with only its stage input and generated prompt. Its own execution checker may later provide freshly derived findings under step3; never supply a hand-corrected ancestor, cached diagnosis list, another execution's findings or a precomputed repair recipe. Preserve rejected outputs and reviews, label retries, and obtain independent acceptance before advancing. A report cannot replace an actual manuscript repair.
5. Execute stage06 on the integrated draft. Its prompt includes all earlier specifications and requires complete-paper repair. Complete the execution checkpoint before submission, then obtain a fresh final acceptance reviewer who has never edited, checked or reviewed this integrated manuscript. It receives all three named manuscripts and does not inherit earlier PASS decisions. After any final-review repair, obtain a new eligible fresh final reviewer.
6. Check the final source and rendered output, references, original mathematical obligations and final reviewer findings. Deliver the revised source/PDF and a concise record of actual changes and unresolved limitations. Do not claim full acceptance with a FAIL or UNVERIFIED required condition.

| Stage | Prompt source | Accepted output |
|---|---|---|
| 01 | [Terminology and notation](stages/01-terminology.md) | Definition-based literature checks and consistent manuscript terms/symbols |
| 02 | [Statements](stages/02-statements.md) | Exact useful claims without dispensable notation or proof-driven packaging |
| 03 | [Architecture](stages/03-architecture.md) | Main deductions and construction purposes accessible at the point of need |
| 04 | [Local proofs](stages/04-local-proofs.md) | Nonstandard mechanisms and necessary intermediate reasoning on the page |
| 05 | [Contribution](stages/05-contribution.md) | Brief, source-supported gap → author action → resolving mechanism |
| 06 | [Complete repair](stages/06-complete-repair.md) | All preceding conditions satisfied together in the final paper |

The [common editing contract](stages/common.md) is included by the renderer. The examples in `examples/` are included with their stage; learn their reasoning and apply it to the manuscript. Keep audit artifacts outside the manuscript.

## Reviewer configuration

Use a fresh context for each independent reviewer. In a GPT-family environment request **GPT 6.1 Sol, xhigh**; in an Opus-family environment request **Opus 5.5, xhigh**. Record the actual invocation. If that configuration cannot be invoked, report the limitation and do not silently substitute or claim that the specified review occurred. The user may explicitly authorize another configuration. Editors may use the current model; independent acceptance cannot be performed by the editor itself.

## Conflicts and reopening

- **Preservation versus revision:** preserve mathematical meaning and full arguments, not wording, witness names, theorem environments, section order or proof locations. A problem inherited from the original still requires repair.
- **Economy versus explanation:** shorten introductory routine material and redundant statement packaging; expand difficult reasoning when its mechanism is missing. Global word/page reduction is not an acceptance objective.
- **Direct statements versus strict structure:** an object may admit a structured model without its given presentation having that structure. Compare equivalent formulations at the same mathematical strength.
- **Literature versus novelty:** established terminology does not establish that a result is already known; absence of a phrase does not establish novelty. Verify definitions and closest actual results separately.
- **Architecture versus local clarity:** moving complete proofs does not remove their obligation; adding headings does not explain a missing mechanism. Keep an exact statement and sufficient mechanism in the reading path.
- **Later changes versus earlier acceptance:** a new term reopens 01; a changed claim reopens 02 and its proof; moving material reopens 03 and references; changed reasoning reopens 04; changed attribution reopens 05. Recheck the actual affected scope, not every unrelated stage automatically.
- **Independent judgment versus prior reports:** reports can locate evidence after discovery; they never substitute for independent reading. Reviewer reconstruction that is absent from the manuscript is a repair request, not acceptance evidence.

Do not add an exception that contradicts a stage requirement. Resolve a genuine mathematical or access limitation explicitly and leave the affected condition unverified. Continue all independent authorized work that remains possible.
