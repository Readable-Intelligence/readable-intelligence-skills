# Stage 03 — Proof architecture

Reorganize the proof-bearing body of the entire paper. Preserve complete arguments, not the original list of theorem environments or proof locations. Do not rewrite the introductory novelty discussion in this stage; update its navigation references if necessary.

## Procedure

1. Read all proofs, including unnumbered arguments and appendices. Build a private dependency graph of results, constructions and imported inputs. Record the usable output and actual consumers of every node. Track temporary bootstrap assumptions separately from proved conclusions. The graph is a reasoning aid, not manuscript prose.
2. Find the shortest intelligible route from the problem to each main result. Identify where the reader must understand a new mechanism and where a routine verification only certifies it. Assess each formal result by the new inference it enables, not by proof length or citation count.
3. For every result choose a presentation: main-route statement, local supporting statement, unnumbered consequence integrated into its consumer, or optional material. Independently choose the complete proof's location: adjacent, a later dedicated subsection, or appendix. Even a retained location requires comparison with the plausible alternatives. Mathematical necessity alone does not justify a numbered lemma or main-text proof. Do not require an appendix or a merge when neither improves the reading path.
4. Before a long construction or sequence of supporting proofs, make its usable output and its contribution to the main proof accessible. For a main result with several substantial inputs, provide an early actual deduction from precise statements, or an equally explicit local explanation of their composition with exact statement/proof pointers. “We prove several lemmas and then the theorem” is not such an explanation. If an exact deduction fits in a short paragraph, prefer giving it over another itinerary. Forward-stated inputs are allowed when their assumptions and conclusions are available and proofs have named destinations.
5. Keep each branch contiguous until its promised output is reached. A return to an earlier branch must have a mathematical reason, not merely inherit the original order. Group sections by a coherent question/output. Introduce a construction's purpose before its machinery, and explain what the next section can now use at the transition. Do not add a redundant preview to every short proof.
6. Keep the decisive mechanism in the main reading path, even when its detailed verification is deferred. Retain all complete proofs at reachable locations. Implement the architecture in the manuscript, fix definitions and references after movement, and write a compact result-to-statement/proof/consumer map in `changes.md`.

## Acceptance — all required

- A reader can reconstruct each main theorem's deduction from accessible statements and the written assembly before inspecting all supporting proofs. The actual deduction is present, not reconstructed only in an audit report.
- At the entrance to each substantial construction the needed output, reason for introducing it and next mathematical use are clear without looking ahead into its proof.
- Every numbered and unnumbered result has a reasoned presentation and proof-placement decision. “All arguments must survive” does not settle either decision. “No move proposed” cannot make the placement check inapplicable.
- Distinct proof branches do not interrupt each other without an explained dependency. Definitions appear before their use, including in moved previews.
- The main text explains each decisive mechanism. Deferred material retains its exact scope and full proof; every original mathematical obligation has a reachable destination.
