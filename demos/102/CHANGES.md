# What changed in the Readable Version

This note compares the [Readable Version](readable.pdf) (62 pages) with the [original manuscript](original.pdf) (58 pages). Page numbers are written "readable p. X / original p. Y". Theorem 1.1 and the approximation consequences keep their original statements. What changed is how the paper is arranged and explained.

## Main improvements

### 1. The whole reduction is put together before the long constructions

In the original, the reader first goes through the 10-page construction of the "latent alphabet gadget" (Section 3) and the matrix extraction (Section 5) before the pieces are combined: the matrix-game gap is deduced on original p. 35 and Theorem 1.1 is proved on original p. 37.

The Readable Version states what each construction provides and assembles the proof first:

| Part | Readable | Original |
|---|---|---|
| The test, with the map it uses stated as Lemma 3.3 | Section 3 (pp. 9–14) | Section 4 (pp. 17–22), with the map stated as Lemma 3.1 (p. 7) |
| The two bounds on advice agreement and the deduction of the matrix-game gap | Section 4 (pp. 14–17) | Sections 5.1–5.2 (pp. 22–25) and 6 (pp. 33–36) |
| Proof of Theorem 1.1 | Section 5.2 (p. 19) | Section 7.2 (p. 37) |
| Construction of the map and its noise (proof of Lemma 3.3) | Section 6 (pp. 20–31) | Section 3 (pp. 7–17) |
| Matrix extraction and decoding (proof of Proposition 4.3) | Section 7 (pp. 31–41) | Section 5 (pp. 22–33) |
| The agreement upper bound (proof of Lemma 4.4) | Section 8 (pp. 41–43) | Section 6.2 (pp. 33–35) |

A reader can now check how Theorem 1.1 follows from three stated inputs by p. 19, and then read their proofs in any order.

### 2. Results that were only inside proofs are now stated

- **Proposition 4.5, "A fixed gap with adjustable completeness"** (readable p. 17), states the matrix-game gap with the order in which the parameters are fixed, and explains why that order allows any small completeness error.
- **Lemma 4.4** (readable p. 17) states the agreement upper bound before it is used, with the reason it holds and a pointer to its proof in Section 8.
- **Section 7.6, "Choosing the tuple length"** (readable p. 41), collects the parameter choices that the original makes along the way.
- **Appendix A.2, "Rational weights for the CSP consequence"** (readable pp. 50–51), gives the step from the fixed-instance form of Raghavendra's theorem to Corollary 9.2 in its own subsection. The original gives it inside the running text of Section 8.1 (original p. 40).

### 3. A longer abstract and a clearer introduction

- The abstract now says what the new ingredient is: a noise law for the degree-two matrix shortcode under which an equivariant nonlinear evaluation is almost unchanged, while every family of high-rank linear observations detects the noise.
- Section 1.4 (readable pp. 5–8) ends by saying which section states and which proves each input.

### 4. Names made up for this paper replaced by standard terms or plain descriptions

| Original | Readable Version |
|---|---|
| latent alphabet gadget | an equivariant map with additive noise |
| generic spaces of characters | spaces of linear functionals satisfying two stated conditions |
| linear lifts | linear extensions |
| inverse shortcode theorem | shortcode soundness theorem |
| homogeneous coordinate | the coordinate t<sub>0</sub> for the intercept |
| exact table keys | representing tables |
| latent matrix test | matrix equality test |
| clean coordinates | singleton coordinates with zero advice slopes |
| good row advice | row advice in the set ℛ (nonempty slice and α/2 agreement) |
| harmonic potential | the sum of reciprocals H<sub>r</sub> |
| strong-left form of Unique Games | Unique Games with completeness on left vertices |
| SDP<sub>R</sub> | LC, Raghavendra's own notation |

Several letters that were used for two different objects were also separated, for example the answer alphabet K and the pair count binom(k, 2) (now N<sub>2</sub>), and the game H and the matrix game (now 𝒢).

### 5. Less text the reader does not need

Ten sentences or clauses that only said what the argument does *not* assume or use were deleted, for example "It is not an input to this proof".


## How the changes were checked

Every rewritten proof passage was checked against the original by a separate model. None was rated unsupported or false, and a final check of all rewritten passages found no blocking problem. The ten deletions in item 5 were made last and were not checked again. In a blind comparison, both reviewers preferred the Readable Version with high confidence. After the automated run, a few sentence-level corrections were made by hand and were not checked again by a separate model: the original parameter condition 2<sup>−ℓ</sup> < η/4 is restored in equation (4.4); the name kernel clustering is restored; and the proof of Lemma A.3 now says that the explicit error comes from running the argument of [17, Lemma 10.5] with the stated invariance bound, not from the statement of that lemma. As the [README](README.md) says, none of this is an independent verification of the mathematical claims.
