# Judging importance

The node fill colour encodes one number per result: **how crucial it is to the paper's
main argument**. A reader who opens the graph should be able to look only at the dark
nodes and understand the skeleton of the paper: what is proved, and which steps carry
the weight. Everything else in the blueprint is mechanical. This judgement is not, and it is
why the skill exists. Spend your effort here.

## Contents
1. The scale
2. Evidence to collect
3. Procedure
4. Calibration rules
5. Writing `reason` and `summary`
6. Worked example

## 1. The scale

| level | name | what belongs here |
|---|---|---|
| **5** | main result / central idea | The theorem(s) the paper exists to prove. Also, rarely, the one new ingredient without which the paper would not exist: the result the abstract singles out, which the authors call "the key", "the heart of the proof", "our main technical contribution". |
| **4** | key step | Major milestones of the main proof: each half of a two-sided bound, the reduction that turns the problem into a tractable one, the hardest or most original lemma, a new central definition the main theorem is phrased in. If you removed it, a reader would lose the shape of the proof. |
| **3** | supporting | Lemmas with real content that the main path needs: non-trivial, but neither surprising nor architecturally central. A competent reader could reconstruct them once told they are needed. |
| **2** | technical / routine | Standard estimates, computations, bookkeeping, glue lemmas, easy consequences, results used only to tidy a special case. |
| **1** | background / peripheral | Classical facts restated or reproved "for completeness", notation, results used only in remarks, examples or side applications, anything off the main path. |

Half-steps (3.5) are allowed when you are torn; the colour is interpolated. Prefer integers.

## 2. Evidence to collect

Look at four kinds of evidence. No single kind decides on its own.

**A. What the authors say.** This is the strongest evidence. Read the abstract, the
introduction, any "overview", "proof strategy", "techniques" or "organisation" section,
and the sentences right before and after each statement. Cue phrases:
- *Up:* "main result", "key lemma", "crucial", "the heart of the matter", "main technical
  contribution", "new ingredient", "the main difficulty is", "the novelty", a
  named result ("Realization lemma"), a result restated in the introduction, or a result
  given its own section.
- *Down:* "standard", "well known", "classical", "folklore", "routine", "straightforward",
  "for completeness", "we recall", "elementary", "by a direct computation", a result with
  a citation and no proof, or a result placed in an appendix.

**B. Position in the graph** (the `digest.md` metrics):
- Is it in the *main cone*, i.e. an ancestor of a main result? If not, it is usually 1–2,
  unless it is itself a headline application that the abstract advertises.
- Is it a *bottleneck*? Check whether many prerequisites funnel through it to the main
  theorem, or whether the main proof cites it directly. The direct inputs to the main
  proof are the candidates for 4.
- A large `desc` count means the result is infrastructure. A lemma used everywhere, such
  as a contraction bound or a norm inequality, is useful but rarely *crucial*. Do not
  promote it for reach alone.

**C. Difficulty and originality of the proof.** A long, delicate, new proof suggests 4.
A three-line proof can still be 4–5 if it is the idea, for example a clever choice of
test function. A long proof can be 2 if it is a routine computation. Proof length is a
weak signal. Use it only to break ties.

**D. Kind.** A definition is important when the main theorem cannot be stated without
it, or when it is the paper's new concept (3–4). Notation and conventions are 1–2. An
assumption the main theorem rests on is 2–3, or 4 if it is the crux, as with a
non-standard hypothesis that the paper is about.

## 3. Procedure

1. **Read the architecture first, then the details.** Read the abstract, introduction and
   overview in full before you rate anything. Write down, for yourself, the main
   result(s) and a one-paragraph proof outline in the authors' terms, for example "upper
   bound by an explicit kernel; lower bound by duality, which needs a realization lemma;
   the realization lemma via polynomial approximation, QSP and a finite clock".
2. **Mark `main`.** Usually 1–3 nodes. Corollaries that merely restate the main theorem in
   another form are not main; rate them 3–4.
3. **Trace the main proof downwards.** Take the direct inputs of the main proof(s): these
   are 4s or strong 3s. Then take their inputs, and so on. Importance usually, but not
   always, decays with distance from the main result. Watch for a deep lemma that is the
   real novelty.
4. **Rate everything else**, using the table and the evidence. Every shown node needs a
   rating.
5. **Calibrate** with the rules below. Then sort your ratings and re-read the 4s and 5s
   together, and the 1s and 2s together. Ask: "Would the authors agree with this
   ordering?"

## 4. Calibration rules

- **Ratings are relative within the paper.** Even a paper made only of hard lemmas has
  routine glue. Even a survey has a main point. Use the whole scale.
- **Rough distribution** for a paper with 15–40 nodes: 5 → 1–2 nodes (main results, at
  most one more); 4 → about 10–25%; 3 → about 25–40%; 1–2 → the rest. Deviate when the
  paper clearly warrants it, and say why in `reason`.
- **Short, tightly knit papers.** In a 10–15 page paper where the abstract lists five
  steps and each step is one lemma, more than 25% at level 4 is correct. Say so in the
  hand-over rather than demoting real milestones to fit the quota.
- **Two co-equal ingredients.** When the introduction presents two main ingredients, both
  may be 5 alongside the main theorem. Use 4.5 only for a genuine "between".
- **3 is not a default.** If you are tempted to give 3 everywhere, go back to step 1. You
  have not yet understood the proof architecture.
- **Dark should form a readable spine.** Follow the 4s and 5s through the graph. They
  should connect, possibly through a few 3s, and tell the story of the proof. Isolated
  dark nodes deserve a second look.
- **Do not inherit importance mechanically.** A 5 can rest on 2s; that just means the
  prerequisites are routine.
- **Cited black boxes** stay modest (1–3) even when they are load-bearing, because they
  are not this paper's contribution. Example: "By the Fejér–Riesz theorem". If the paper's
  point is precisely to apply a deep external result in a new way, the new application
  is the important node, not the black box.
- **Constructions and figures.** A construction or algorithm that a statement refers to
  ("the preparation just described") is a node: kind `construction`, rated like the step
  it enables. An argument that lives inside a proof (a figure, or "the crucial
  observation") does not get its own node. Credit it in the host's `reason` and
  `proof_sketch`, and rate the host accordingly.
- **Off-path material** (remarks, examples, alternative proofs, extensions mentioned
  "for completeness") gets 1–2. It is often hidden anyway.

## 5. Writing `reason` and `summary`

- `reason` justifies the number in one sentence that points at evidence. The modal shows
  it under "Why this matters".
  - Good: "Authors' key new ingredient (abstract, §1.2); every lower-bound argument goes through it."
  - Good: "Classical Fejér–Riesz factorization, reproved for completeness."
  - Bad: "Important lemma." / "Used in the proof."
- `summary` is the result's *role in the argument*, in plain language, one or two
  sentences. A reader who skips the formula should still understand why the step is
  there.
  - Example: "Turns the analytic test function into an actual matrix element of
    e^{-i(zX+Y)}, so the duality bound applies to matrices."
  - It may contain inline LaTeX (`$...$`). It must not just restate the statement.
- `proof_sketch` is 2–5 sentences on *how* the proof goes, naming the results it uses.
  Write one for every result rated 4–5, and for every result in a PDF paper. Definitions
  need none.

## 6. Worked example (sketch)

Take a hypothetical combinatorics paper: *"every planar graph with property X has a
Y of size at most f(n)"*.
- `thm:main` → **5**, main.
- `lem:decomposition`, a new structural decomposition that the introduction calls "the
  key insight", used by every later section → **5** if the authors present it as the
  main idea, otherwise **4**.
- `lem:discharging`, a long and delicate discharging argument that the authors call "the
  main technical part" → **4**.
- `def:good-partition`, the new notion that the decomposition lemma is phrased in →
  **3–4**.
- `lem:reducible`, a list of reducible configurations, each checked by a short case
  analysis → **3**.
- `prop:separator`, the planar separator theorem, cited and used once → **1–2**: it is a
  classical black box.
- `lem:small-cases`, small n checked by computer → **2**.
- `cor:algorithm`, a linear-time algorithm advertised in the abstract but downstream of
  the main theorem → **3**. Rate it 4 only if the paper treats it as a second headline
  result.
- `rem:tightness`, an example showing f(n) is tight → hidden, or 1–2 if shown.
