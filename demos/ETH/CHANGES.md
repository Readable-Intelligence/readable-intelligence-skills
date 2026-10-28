# What changed in the Readable Version

This note compares the [Readable Version](readable.pdf) (72 pages) with the [original manuscript](original.pdf) (67 pages). Page numbers are written "readable p. X / original p. Y". Theorem 1.1 and Corollaries 1.2–1.4 keep their original bounds. What changed is mainly how the paper is arranged and explained; one change to the wording of the abstract is noted under "What is not better".

## Main improvements

### 1. The main theorem is proved in the main body, not in the last appendix

The original contains two algorithms. Its main body (Sections 2–6, original pp. 7–43) develops an algorithm based on polynomial interpolation over Q, which proves only the weaker exponent O<sub>k</sub>(ρ(n)). The proof of the stated Theorem 1.1, by Boolean tensor contraction, appears only in **Appendix D, "A sharper bound for exact counting"** (original pp. 53–63).

The Readable Version puts the proof of Theorem 1.1 first:

| Part | Readable | Original |
|---|---|---|
| Deduction of both bounds of Theorem 1.1 from the contraction theorem | Section 2, "Proof of the main theorem" (pp. 10–12) | Appendix D.1–D.3 (pp. 53–57) |
| Proof of the contraction theorem | Section 3 (pp. 13–21) | Appendix D.4 (pp. 57–63) |
| Encoding sparse polynomial systems | Section 4 (pp. 22–26) | Sections 5.1–5.2, inside the interpolation algorithm |
| Constructing the parity tests | Section 5 (pp. 27–29) | Sections 6.1–6.2, inside the interpolation algorithm |
| The weaker interpolation algorithm | Sections 6–10 (pp. 30–57) | Sections 2–6 (pp. 7–43) |

Appendix D no longer exists. Sections 4 and 5, which both algorithms use, now come before either one needs them.

### 2. The introduction explains the contraction proof and says where each part is

- **A sketch of the contraction algorithm** (readable pp. 2–3), right after Theorem 1.1. The original introduction mentions contraction once, in the sentence pointing to Appendix D (original p. 2). The sketch explains how the parameter T deforms the contraction, why the selected points are chosen by two-adic valuation, why Taylor data is needed, and why the exponent becomes O(s/√log s).
- **An "Organisation" paragraph** (Section 1.2, readable p. 9). It says that Sections 2–5, with Appendix A and Lemma B.1, contain the whole proof of Theorem 1.1, and that the proof does not use Sections 6–10. It also lists which parts of the main proof the interpolation algorithm reuses.

### 3. Each proof section states its plan and its results first

- Section 2 opens by saying which two reductions give the two bounds, and states the results it needs (Theorem 2.1 and the outputs of Sections 4 and 5) before the two deductions in Sections 2.4 and 2.5.
- Section 3 opens with a list of the five steps one recursive call performs (readable p. 13), with a pointer to the subsection for each step. Original Appendix D.4 starts directly with the coefficient ring and leaves the reader to put the recursion together from its subsections.

### 4. Names made up for this paper replaced by standard terms or plain descriptions

| Original | Readable Version |
|---|---|
| packets (of slots) | arrays |
| Cauchy kernel (for the polynomial matrix W(T)) | its formula, stated directly |
| tapered Hermite recovery | Hermite interpolation with decreasing multiplicities |
| rational interpolation | polynomial interpolation over Q |
| dummy clauses | constant-one factors |
| (r, τ, D)-design | partitions, factor assignments and measurement matrices, with the same four conditions |

Two letters that were used for two different objects were also separated: the auxiliary coordinate set is now 𝒰 instead of ℬ (ℬ is also the coefficient ring), and the sum of clause violations in a parity test is now Λ<sub>i</sub> instead of L<sub>i</sub>.

## What is not better

- **The paper is longer:** 72 pages against 67, mostly because of the new introduction material.
- **The abstract changed in form.** The running time in the abstract and in the definition of ρ(n) is now written 2<sup>n/(log n)<sup>1/2−o(1)</sup></sup> instead of 2<sup>n/(log n)<sup>1/2+o(1)</sup></sup>. The reviewers changed it to match the exponent n log log n/√log n of Theorem 1.1. Both forms are correct because o(1) has no fixed sign, but this is a change to the paper's headline claim that the author has not approved.
- **Some standard terms became longer descriptions.** In the related-work section, "dynamic time warping" and the "Orthogonal Vectors Conjecture (OVC)" were replaced by descriptions in words. In a blind comparison, the GPT reviewer preferred the Readable Version overall, but found the original better where the new version delays consequences, repeats navigation, or uses a longer description in place of an established term.
- **Problems that remain in the final review.**
  - Two steps that the rewrite added are rated gaps that do not block the proof. Both are in the interpolation algorithm (Sections 6–8), not in the proof of Theorem 1.1. Section 8 cites a lemma for a restricted-kernel implication that the lemma does not state, and Section 6 uses three parameter bounds as special cases of general lemmas without writing the special case out.
  - On readable p. 14, the sentence beginning "Indeed" proves that v<sub>2</sub> is additive, not that O mod 2 is the field F<sub>2<sup>e</sup></sub>.
  - On readable p. 28, Hoeffding's inequality is cited from a one-sided statement ([AW15, Lemma 3.3]) but used for a two-sided bound.
  - The introduction's sketch repeats some material in Sections 1.1.4–1.1.5, and Section 6 derives some steps more than once.
- **One claim could not be checked.** The motivation for Corollary 1.2 credits [Ope26] with Unique Games hardness for Max-k-SAT. That source was not available to the reviewers. The claim is not used in any proof.

## How the changes were checked

Every rewritten proof passage was checked against the original by a separate model. During the rewrite one added bound was found to be false (a counterexample was given), and it was removed before the next version was accepted. A final check of all 57 rewritten passages in the delivered version found no blocking problem; the gaps it did find are listed above. As the [README](README.md) says, none of this is an independent verification of the mathematical claims.
