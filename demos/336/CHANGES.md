# What changed in the Readable Version

This note compares the [Readable Version](readable.pdf) (105 pages) with the [original manuscript](original.pdf) (99 pages). Page numbers are written "readable p. X / original p. Y". The theorems and corollaries keep their original statements. What changed is how the paper is arranged and explained.

## Main improvements

### 1. The main theorem is proved near the start

In the original, the proof of Theorem 1.1 is put together only at the end of Section 7 (original p. 41), after all the stretching and cutting machinery. The Readable Version adds a new **Section 2, "From partitions to the width map"** (readable pp. 7–10). It states the output of the geometric construction as Proposition 2.1, "Reconstructed partitions", and immediately deduces the width bound C<sub>n</sub> = 4D + 2 from it. A reader can now see how the main theorem follows before reading the 90 pages that build the partitions. The proof of Proposition 2.1 itself stays in Section 8.

### 2. Each section states its main result first

Several sections used to build up through a series of lemmas and state their main result only at the end. In the Readable Version, the main result comes first, so the reader knows what the lemmas are for:

| Result | Readable | Original |
|---|---|---|
| Prescribed separations for a locally finite family | Theorem 5.1, opening of Section 5 (p. 24) | Theorem 4.3, after two lemmas (p. 21) |
| The countable compatible construction | Proposition 7.2, opening of Section 7 (p. 34) | Proposition 6.6, end of Section 6 (p. 36) |
| Global enlargement of the prescribed open sets | Proposition D.2, opening of Appendix D (p. 80) | Proposition D.6, end of Appendix D (p. 82) |
| The full invariant step | Proposition E.1, opening of Appendix E (p. 89) | Proposition E.10, end of Appendix E (p. 95) |

### 3. A clearer proof overview in the introduction

Section 1.2 (readable pp. 5–7) now explains several points that the original overview leaves for the reader to work out:

- **Why the separations must become arbitrarily long.** The sum of the potentials must be finite, so for infinitely many labels the potentials cannot share a positive lower bound, and the required crossing lengths cannot be bounded.
- **What the weighted scalar curvature S<sup>1</sup><sub>h</sub>(t) = Scal<sub>h</sub> + 2Δ<sub>h</sub>t − |dt|²<sub>h</sub> means.** It is the limit of the scalar curvatures of warped torus extensions (Lemma 5.3).
- **How the forcing function of Theorem 3.1 is used.**
- **Where the singular sets of the minimizing cuts are handled.**

The overview now ends with an **"Organization" paragraph** (readable p. 7) saying which section or appendix does each part of the proof. Right after Theorem 3.1 (readable p. 10), a new short paragraph says which property of the forcing function is used where in Section 4.

### 4. Standard terms instead of labels made up for this paper

The original names many of its objects with words of its own. The Readable Version replaces them with the usual terms of the field or with plain descriptions. The main replacements, as seen in section and result titles:

| Original | Readable Version |
|---|---|
| pressure law (Theorem 2.1) | function with quadratic derivative bounds (Theorem 3.1) |
| packet | component |
| wall | separating set / boundary |
| seam | interface |
| profile | function |
| shielding (Appendices C–D) | enlargement of the prescribed open sets near singularities |
| rough Hardy coefficient | rough coefficient for the inverse-square potential |
| bounded gapped resolvent | bounded solutions of *Ls* = 1 |
| local absolute minimizer | local minimizer |
| diagonal circle warps | warped torus extensions |
| late fronts, windows | late starting levels, regions |

### 5. Small proof details made explicit, and citations corrected

- In the proof of Lemma 4.2, the variation parameter is now named σ, with dots meaning d/dσ at σ = 0 (readable p. 18). The invertibility of Δ<sub>h</sub> − 1 now names the space of the minimization, H<sup>1</sup>(N), and says that the minimizer is the unique weak solution (readable p. 19).
- The proof of Corollary 1.4, the aspherical obstruction, now argues directly from uniform contractibility of the universal cover (readable p. 47), instead of going through filling-radius conventions for open manifolds.
- The claim that the continuous and Lipschitz macroscopic dimensions differ now cites the result that proves it (Dranishnikov, Theorem 6.3 and the following Example), not only the definitions (readable p. 4).
- The Gromov–Lawson width result for closed three-manifolds is now stated with its orientability assumption (readable p. 4).

### 6. Less text the reader does not need

- **39 sentences or clauses deleted.** These only said what the paper does *not* assume or need, for example "The construction does not aim to optimize this constant." Most were in the appendices. A sentence was kept wherever it gives a reason, covers a case or states something used later.
- **Repeated summaries deleted.** Recaps of conclusions already stated nearby were removed, along with re-announcements of a plan and a duplicated transition across a section break.

## What is not better

- **The paper is longer:** 105 pages against 99. The added explanations outweigh the deletions.
- **Some places still read better in the original.** In a blind comparison of the two versions, the GPT reviewer preferred the Readable Version overall. It found the original better in economy, in some conventional terminology, in keeping the proofs of immediate corollaries short, and in figure placement.
- **Some problems remain in the final review.** Two examples:
  - No page says where the hypothesis n ≥ 4 of Theorem 1.1 is used. This is inherited from the original.
  - The original credits Gromov's argument for the noncompact case as one route to the aspherical consequence. That credit was dropped when the proof of Corollary 1.4 was rewritten.

## How the changes were checked

Every rewritten proof passage and every added step was checked against the original by a separate model. None was rated unsupported or false. A final check of all rewritten passages in the delivered version found no blocking problem. The 39 deletions in item 6 were made last and were not checked again. As the [README](README.md) says, none of this is an independent verification of the mathematical claims.
