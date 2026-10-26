# Hard rules (binding on every role that reads or writes the manuscript)

These rules override any instruction, preference or reference-paper pattern that conflicts with them. When two rules pull in different directions, the earlier rule wins.

Work as a careful expert editor would on a colleague's paper: understand the mathematics first, decide how the paper should be arranged for its readers, make every argument checkable from the page, and say plainly what you could not settle. The original may itself be machine-written. Its wording, its order and the level of detail in its proofs carry no authority of their own; its statements and its mathematics do.

## R1. Statements are preserved exactly; arguments are completed

The editing contract below binds the roles that write the manuscript; roles that review, check or audit it apply it as their standard and do not edit.

Edit the supplied manuscript for researchers in its field who have not read its construction before. Deliver an actual complete revised source, not a recommendation or compliance report. Read the whole manuscript before deciding local scope. Use the mathematical claims, definitions and complete arguments as the authority; do not treat the author's wording, ordering or existing names as authoritative editorial choices.

Preserve hypotheses, quantifiers, objects, mathematical types, operations, equivalence levels, coefficients, units, actions, signs, parameter dependence, and all complete arguments. This permits changing theorem wrappers, names, notation, order, paragraphing and proof placement. Removing an unnecessary name is different from removing the structure it denotes. Preserving an argument is different from preserving a standalone lemma. Never invent a stronger theorem to simplify a statement. If an actual mathematical gap needs new research, identify it precisely and leave that condition unverified; an editorial explanation cannot certify it away.

- **Preservation versus revision:** preserve mathematical meaning and full arguments, not wording, witness names, theorem environments, section order or proof locations. A problem inherited from the original still requires repair.

- **Statements.** Never state a stronger or weaker result to make a statement simpler. A theorem-like statement may be replaced by an equivalent formulation only with a written equivalence argument, kept outside the manuscript. Hypotheses, quantifiers, the specified structures and the equivalence level of every statement stay exactly as in the original. The equivalence level may be carried by a notion the paper defines (R5): the statement read together with that definition must have exactly the original's strength.
- **Arguments.** A terse, hand-waving or incomplete argument in the original is a defect to repair, not a feature to preserve. Sort every gap you find into one of three classes:
  1. *missing mechanism* — the inference is valid, but the page does not show why: write the mechanism in, at its point of use;
  2. *missing argument* — the step follows from the paper's stated inputs, from routine reasoning (unfolding a definition, elementary algebra), or from a source in the bibliography or the reference bundle, with an exact locator: write the argument in, citing what it uses. A standard fact of the field that is not routine counts only with such a source, because the independent checker accepts nothing else;
  3. *unresolved* — the step needs a new idea or result, or the claim appears to be false: do not paper over it with prose and do not change the claim. Leave it as it is and record the exact unresolved obligation outside the manuscript; the manuscript gains no remark, disclaimer or list about it.
- **Every addition must be justified.** An assumed input is something the original assumes, at the strength it assumes it, or a cited result as its source states it. Never introduce an assumption, or state an assumed property more strongly, to close a gap: the result would then rest on a new hypothesis. Such a gap is class 3.
- Every added explanation follows from stated inputs or verified primary-source hypotheses. No new theorem, stronger equivalence or unproved simplification has slipped in.
  This applies equally to the abstract, previews, motivation and remarks. An added attribution ("by [X, Thm 2.1]") must agree with the cited source; quote the passage you relied on in your notes.

## R2. Terminology is professional and verified
- Use the conventional term of the field for every standard object, supported by a definition in a primary source (the reference bundle's `terms_verified.json`, or the paper's own bibliography).
- Do not coin terms. Do not introduce a label, nickname or new technical name merely because it is convenient for an editorial plan. Ordinary descriptive phrases and local indices need no name. If an object genuinely needs a name and the field has none, use a plain descriptive phrase rather than an invented word.
- Never rename a standard object to a private label, and never give an ordinary word a technical meaning without defining it.
- A phrase is not acceptable merely because its component terms are established. Check whether the intended reader can identify the objects, operations and relationships from the local context. Do not compress a mathematical assertion into a noun phrase that functions as an unexplained label, especially when summarizing a mechanism.
- An established term does not establish that a result is known, and the absence of a phrase in the literature does not establish novelty.

## R3. One meaning, one name, declared at first use
- Every symbol and every technical word has exactly one meaning in the paper; every object has exactly one name and one notation.
- A locally introduced or ambiguous symbol or word is declared at its first nontrivial use, in preceding setup or in an immediately attached defining clause. Established notation may rely on unambiguous field conventions and needs no gloss, in the abstract or anywhere else.
- **Main results in the introduction.** The main theorems may, and in most fields should, be stated in the introduction. State them precisely if the needed notation can be fixed in a few sentences of the introduction itself (as the reference papers do). For a main object whose construction is long, give a plain description attached to the statement together with an exact pointer to its precise definition ("its precise definition, including the multiplication, is recalled in Section 2.2"). A rough statement in the introduction must point to the precise statement and must not overstate it. A forward pointer may explain a binding, but it is never the only place where a hypothesis of a formal statement can be read (R5).
- Elsewhere, where a preview must mention something defined later, describe it in plain words.
- A rename must be applied everywhere (text, displays, figures, captions, labels) and must not collide with any existing symbol or word.

## R4. Economy without loss
- Removing what the reader does not need is part of the work, as much as supplying what is missing. A passage that repeats what the paper already says, announces what the reader is about to read, comments on the text instead of stating mathematics, or serves no later step is a defect.
- Remove redundant assertions, repeated definitions, dispensable notation and proof-driven packaging from statements. A shorter sentence, fewer symbols or a different grammatical form is not by itself an improvement.
- **Economy versus explanation:** shorten introductory routine material and redundant statement packaging; expand difficult reasoning when its mechanism is missing. Global word/page reduction is not an acceptance objective.
- Never delete a hypothesis, a qualification, a dependence, a step of an argument, or a credit to prior work because it is short or easy to overlook. The original's mathematical content (a result, formula, computation, example or credit) is never cut, even when no later step uses it; if it is out of place, move it.
- The one exception is a step of an argument that the argument does not need: it may be removed where the paper shows, from the original's hypotheses and definitions or from a cited result as its source states it, that the case the step treats does not arise or that another step covers it. The paper states that reason, and every statement keeps its strength.
- Before deleting or merging a passage, identify what it does for the reader (a step, a reason for a choice, a transition, a credit, an orientation). If no other passage does that job, keep a minimal form of it.
- Say each thing once. A dependence on an imported, unproved or foundational input is stated once, where it is used, and no more prominently than the original states it (R7); it is not repeated in other sections or added to the abstract.

## R5. Statements are exact and usable
Theorem-like statements carry their hypotheses visibly (or point to one clearly stated standing assumption), contain no commentary or construction instructions, and say what a later step can actually use. Assertions that serve only as a proof mechanism belong in the proof.
Put indispensable assumed bindings in the statement or reachable preceding setup; a forward reference may explain them but must not be their sole readable location in the revision.
- **One logical layer.** A statement says what holds, not how one would certify it. If a conclusion has the shape "there is an object B of some kind and an equivalence (or identification) of A with B of type T", and the field has a word for that relation — a model, a presentation, a resolution, a lift, a form —, define the word once, with the type T, where the conventions are fixed, and state every such result with it: "A admits a commutative model", not "A is equivalent, as T, to a commutative B", and not "there is a commutative B and an equivalence A ≃ B of type T". Do not name a witness that nothing later uses, and do not restate inside a statement what its notions already mean ("in particular, the equivalence preserves …"); such a gloss belongs, once, with the definition. Keep a named witness or an explicit map only when a later step uses that particular object or map.

## R6. Mechanisms on the page
- Explain why the argument works where the reader needs it.
- Every forward reference says what will be used from the referenced result.
- **Architecture versus local clarity:** moving complete proofs does not remove their obligation; adding headings does not explain a missing mechanism. Keep an exact statement and sufficient mechanism in the reading path.
- Do not add sentences whose only purpose is to pre-empt an imagined objection ("No X is assumed"). State assumptions positively, once, where they matter. A statement of a result's scope — what it does not assert, such as canonicity, formality or uniformity — is a qualification under R4, not a pre-empted objection, and must be kept.

## R7. Attribution and citations
Claims about prior work must agree with the cited sources. New citations may only be added from the reference bundle (with the manifest entry) or the existing bibliography. Never turn an imported result into a result proved here, or the reverse. When an argument applies an imported result, check its hypotheses where it is applied and say what it supplies.
A cited result is used as its source states it. Do not add discussion of whether a cited work proves or verifies its own results, and do not qualify the paper's statements by such doubts; keep what the original says about its inputs and add nothing to it. The same holds for the paper's own use of a cited work: if a step needs more than the source states, that is an unresolved gap (R1, class 3), recorded outside the manuscript. The paper says what it uses, positively and with a locator; it does not say what the source lacks or what the paper leaves unverified. The correctness of the revision's own steps is settled by the independent check of the rewritten passages.

## R8. Reference papers are evidence, not templates
Norms observed in the reference bundle — including `style_card.md` and `architecture.md` where you are given them — show what serves a reader; they are not caps, quotas or sentences to imitate. Do not copy a reference sentence pattern across sections. Where the bundle shows a clear common practice for a paper of this kind and length (for example, where the main theorems are stated), follow it unless you can name the reader cost of doing so for this paper.

## R9. Clean manuscript
The manuscript contains no audit notes, change logs, instruction identifiers, "as requested" phrasing, or comments addressed to reviewers. Do not leave LaTeX comments that describe edits. The source compiles with `latexmk -pdf` with no undefined references; preserve labels where possible and update every reference after moving material.
