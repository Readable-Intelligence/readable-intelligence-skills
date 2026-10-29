# What changed in the Readable Version

This note compares the [Readable Version](readable.pdf) (57 pages) with the [original manuscript](original.pdf) (53 pages). Page numbers are written "readable p. X / original p. Y". Theorem 1.1 and the other results keep their original statements. What changed is how the paper is arranged and explained.

## Main improvements

### 1. The plan of the proof is given at the start, and the proof of Theorem 1.1 comes right after the last input

In the original, the incidence construction that starts the argument is Proposition 2.4, stated in the middle of Section 2 (original p. 6). The proof of Theorem 1.1 is the last thing in the paper (original p. 51), after all the algebra of Section 8.

The Readable Version opens Section 2 with this construction as **Proposition 2.1** (readable p. 5). It then explains the role of each of its parameters and lists the five results that carry it to a contradiction: Propositions 4.3, 6.1, 6.2, 7.1 and 8.1. The proof of Theorem 1.1 now follows directly after the statement of the last of them, Proposition 8.1 (readable p. 46). It no longer waits for the proof of Proposition 8.1.

### 2. Each section states its main result first

| Result | Readable | Original |
|---|---|---|
| Bit disagreement on 𝒞 (formerly "common variation") | Proposition 6.1, opening of Section 6 (p. 31) | Proposition 6.3 (p. 32) |
| Positive exception mass on 𝒢 (formerly "positive rare mass") | Proposition 6.2, opening of Section 6 (p. 31) | Proposition 6.5 (p. 34) |
| The pair graph with large ratio heights and small alternating-product heights (formerly "organized pair graph") | Proposition 7.1, opening of Section 7 (p. 39) | Proposition 7.6, end of Section 7 (p. 41) |

In Section 5, the upper score bound (Proposition 5.4) and the lower bound outside 𝒞 (Proposition 5.6) now each have their own subsection.

### 3. Names made up for this paper replaced by standard terms or plain descriptions

| Original | Readable Version |
|---|---|
| incidence piece | incidence subgraph |
| rectangle (maximizing rectangle) | induced bipartite subgraph |
| complete rectangle | 4-cycle |
| wedge | edge pair at a center |
| strict cross | the set of states agreeing with a state in exactly one coordinate |
| total variation (of the thresholds) | integrated minority-bit probability |
| budget | bound |
| rare levels, common levels | levels with f < ε, levels in 𝒞 |
| rare mass, common variation | exception mass on 𝒢, bit disagreement on 𝒞 |
| organized pair graph | pair graph with large ratio heights and small alternating-product heights |
| multiplicative rectangles | small alternating-product heights |
| template | history list |
| popular circle | circle containing at least t<sup>9/10</sup> points |
| profile | point function |
| generic grid, surviving generic point | complete bipartite subgraph with algebraically independent coordinates, point retaining its transcendence degree |

Letters that were used for two different objects were also separated. For example, the score coefficient is now ϖ instead of λ (λ also denotes the edge ratios), and the logarithmic derivatives are now 𝖺<sub>i</sub> instead of A<sub>i</sub> (A also labels coordinates).

### 4. Less text the reader does not need

Seventeen sentences or clauses that only said what the argument does *not* assume or use were deleted, for example "No assertion of mutual independence of these coordinate differences is needed".


## How the changes were checked

Every rewritten proof passage was checked against the original by a separate model. During the rewrite two versions were rejected because the checks found blocking problems; both were repaired before the next version was accepted. A final check of all 76 rewritten passages in the delivered version found no blocking problem. The 17 deletions in item 4 were made last and were not checked again. In a blind comparison, both reviewers preferred the Readable Version with high confidence.

The final reviewers raised one mathematical point, a step the original leaves out. In the proof of Lemma 8.3, the count (8.6) of complete bipartite configurations allows repeated vertices, but the selection that follows needs a subgraph with distinct vertices. The proof now bounds the tuples with a repeated vertex by O(t<sub>n</sub><sup>N+j−1+o(1)</sup>) and discards them (readable p. 49). This change was written by one model and checked step by step against the paper by the other. As the [README](README.md) says, none of this is an independent verification of the mathematical claims.
