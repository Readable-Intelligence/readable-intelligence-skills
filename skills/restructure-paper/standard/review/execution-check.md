# Independent checking during skill execution

This checkpoint belongs to the editing execution, before the final output is delivered. It is additional to the later independent acceptance review. The checklist contains general questions; each checker discovers concrete concerns from this execution's actual candidate. No previous manuscript diagnosis or expected repair is an input.

The checking subagent does not execute the editor assignment. The editing prompt defines the obligations it inspects; this protocol defines its role, permitted inputs and stepwise access. Only the executing agent changes the manuscript.

## Candidate and independent checker

The executing agent first performs its assigned editing pass and saves a complete candidate with identifiable source and rendered-output versions. This is a candidate checkpoint, not a declaration of acceptance. Preserve the input and previous candidate snapshots.

Invoke a fresh subagent independent of the editor. The coordinator may schedule it on the executing agent's behalf. For independent repetitions, use a separate checker context for each repetition; do not give it another repetition's manuscript or findings. Its initial inputs are the current candidate, its input, an authorized author baseline when available, and integrity metadata. Withhold editor notes, old findings, detailed editing criteria and external source content.

First ask the checker to read as an intended researcher and save located observations about claims, argument flow and understanding. For consequential external inputs, ask what conclusion the manuscript supplies, which relevant conditions need to match, and what later step uses it. Distinguish explicit text, ordinary disciplinary knowledge, and inferred or unclear connections. State the assumed expertise without assuming recall of a source-specific statement. Freeze this reading record before the next phase.

Then provide the exact editing prompt, the [reader-centered application](application.md) and the [general checklist](general-checklist.md). Permit independent inspection of the necessary primary evidence. Apply G01–G07 to the assigned scope, compare the needed source conclusions and conditions with the frozen reading record, and assess whether the criteria support the observed readability. Keep scholarly precision and complete arguments mandatory. A background citation or a familiar applicable result does not require an expanded explanation solely because it is cited.

Write findings with actual manuscript locations and evidence. Separate mathematical or evidential defects, a missing explanation needed by the intended reader, unresolved evidence and optional preferences. Describe the missing property or information; do not prescribe one sentence, formula or proof order. A checklist assertion, count or build cannot establish substantive correctness. Do not edit the candidate or read the editor's private rationale to fill a missing public argument.

## Feedback and repair within the same execution

Return the checker's frozen findings to the executing agent. This is a stepwise input permission for reconciliation after the independent editing pass: the editor may now read this execution's own checker report and evidence. The independent-work whitelist in the generated prompt continues to exclude previous rewrites, other executions' findings, acceptance reports and surrounding workspace material. The permission does not authorize coordinator-written manuscript patches or a precomputed repair list.

The executing agent reconciles each required finding against the actual manuscript and evidence, makes justified repairs itself, and records its disposition. A checker is fallible: a proposed repair may be rejected with located evidence, and optional preferences need not cause edits. An unresolved source, mathematical gap or conflict with an existing requirement remains explicit; neither agent may waive it to obtain a passing record.

The checker then inspects the repaired passages and affected dependencies. Reuse its already inspected evidence when still applicable; repeat a source audit only when the change or unresolved concern requires it. Preserve withdrawn findings and the reason for withdrawing them. Continue until required findings are resolved or a concrete limitation is recorded. Recheck the final interacting manuscript, then freeze the complete output, the check records and the executing agent's responses. The recorded final source must be the one actually checked.

Concrete findings and fixes remain artifacts of this execution. They never become reusable checklist entries or hints for a later fresh execution. General skill changes require a separately justified general correction.

## Later independent acceptance

Only after this execution checkpoint is complete does the output enter the ordinary independent acceptance review. Use a different fresh reviewer who has neither edited nor performed this execution check. It receives the actual manuscripts and assigned criteria, without the execution findings or editor notes until its own discovery is saved. Its judgment must come from the final text and independent evidence, not from the internal check's status.

This checkpoint changes when defects can be detected and repaired; it does not add a citation quota, require complete theorem restatements, impose a prose template or replace the assigned acceptance conditions.
