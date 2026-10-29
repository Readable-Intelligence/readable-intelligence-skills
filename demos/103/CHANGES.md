# What changed in the Readable Version

This note compares the [Readable Version](readable.pdf) (118 pages) with the [original manuscript](original.pdf) (108 pages). Page numbers are written "readable p. X / original p. Y". Theorems 1.1 and 1.2 and the other results keep their original statements, except for the corrections listed under "How the changes were checked". What changed is how the paper is arranged and explained.

## Main improvements

### 1. The main theorems are deduced near the start

In the original, the intermediate result that everything rests on, fixed inverse-polynomial accuracy, is stated only as Theorem 12.1 (original p. 92). The class equality L = RL = BPL, the promise version and the variable-precision Theorem 1.2 are deduced after it (original pp. 96–97), 90 pages after the introduction.

The Readable Version adds a new **Section 3, "Reduction to fixed-precision approximation"** (readable pp. 10–12). It states the intermediate result as Theorem 3.1 and immediately deduces Theorem 1.1, the promise-problem equality prBPL = prL (Corollary 3.2), and Theorem 1.2 by padding. It also says which three results the proof of Theorem 3.1 combines. The proof itself stays at the end, in Section 13 (readable pp. 104–108).

| Part | Readable | Original |
|---|---|---|
| Fixed inverse-polynomial accuracy | Theorem 3.1 (p. 11) | Theorem 12.1 (p. 92) |
| Deduction of L = RL = BPL and prBPL = prL | Section 3.1 (p. 11) | Section 12.3 (p. 96) |
| Accuracy supplied as part of the input (Theorem 1.2) | Section 3.2 (pp. 11–12) | Section 12.4 (pp. 96–97) |
| Proof of the fixed-accuracy theorem | Section 13 (pp. 104–108) | Sections 12.1–12.2 (pp. 92–96) |

### 2. Long sections state their main result first

| Result | Readable | Original |
|---|---|---|
| Error bounds for the actual estimators | Theorem 10.2, Section 10.3, near the start of Section 10 (p. 64) | Theorem 9.8, end of Section 9 (p. 61) |
| Uniform block coupling | Proposition 10.3 (p. 65), right after the theorem it serves | Proposition 9.7 (p. 60), before that theorem |
| Uniform numerical interface | Theorem 11.2, Section 11.2, near the start of Section 11 (p. 74) | Theorem 10.9, end of Section 10 (p. 72) |

The catalytic comparison of fingerprints, which is part of the space-bounded implementation, moved from the fingerprint section (original Section 9.6, p. 62) to the implementation section (readable Section 12.5, p. 94).

### 3. A fuller proof sketch in the introduction

Section 1.2, "Proof strategy" (readable pp. 5–8 / original pp. 4–6), grew from about 1,200 to about 1,900 words. It now:

- opens by naming Theorem 3.1 as the core result;
- compares the approach with the resource costs of the two best earlier methods, Nisan's generator (O(log² n) seed bits) and Saks and Zhou's matrix powering;
- gives one paragraph to each decisive idea, with the section that carries it out: transferring transitions into rewards, estimating in one shared random environment, differences and row compression, fingerprints for adaptive endpoints, total evaluation in logarithmic space, and the median.

### 4. Names made up for this paper replaced by standard terms or plain descriptions

| Original | Readable Version |
|---|---|
| rank channels | sampling matrices |
| stochastic atoms | random sparse tables |
| numerical clock t | digit position ν |
| rank (of a list of values) | order statistic |
| clean calculation | comparison calculation |
| gate (incoming gate) | cutoff (incoming cutoff) |
| salt | seed |
| key (catalytic key equality) | fingerprint |
| contour, tour | depth-first traversal |
| density (of a matrix stage) | entry bound |
| baseline | default |
| structural leaf | discrete operand |
| buffered test | comparison with a fixed margin |
| envelope | candidate endpoint set |
| strictly forward (matrix) | with transitions only to later times |

Letters that were used for two different objects were also separated. For example, the space coefficients A, D are now A<sub>space</sub>, D<sub>space</sub> (A and D also denote the sampling matrix and the residual), and the digit alphabet is now 𝒜<sub>dig</sub> (𝒜 also denotes the active-vertex set).

### 5. Less text the reader does not need

Forty-nine sentences or clauses that only said what the argument does *not* assume or use were deleted, for example "No independence of estimated inputs is required".


## How the changes were checked

Every rewritten proof passage was checked against the original by a separate model. During the rewrite one version was rejected because the fidelity check found a serious difference from the original; it was repaired before the next version was accepted. A final check of all 83 rewritten passages in the delivered version found no blocking problem. The 49 deletions in item 5 were made last and were not checked again. In a blind comparison, both reviewers preferred the Readable Version with high confidence.

The final reviewers raised five points. Four were fixed after the automated run by sentence-level corrections, which were not checked again by a separate model:

- the name Bertrand's postulate is restored for the existence of the primes used in Lemma 10.1 and Section 13.1 (readable pp. 63 and 105); the run had replaced it with an unnamed statement;
- the Cheng–Hoza hitting-set result (readable p. 5) now names the binary alphabet, H<sub>n</sub> ⊆ {0,1}<sup>n</sup>, and cites their Theorem 1.3;
- Lemma 12.4(3) (readable p. 88) now states the upper bound "has length at most" that its proof establishes and its only use requires;
- the proof of Lemma 8.3 (readable p. 43) now says that O(b/a)/N is a factor multiplying the displayed sums.

The fifth point was a step the original leaves to the reader: the bound (9.10) for the case with no overflow, used in Proposition 9.5, was justified by "the same proof" as Lemma 9.2. It is now proved in full (readable p. 55), including how the order statistic that sets each row cutoff is controlled. This proof was written by one model and checked step by step against the paper by the other. As the [README](README.md) says, none of this is an independent verification of the mathematical claims.
