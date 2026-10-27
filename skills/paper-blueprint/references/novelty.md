# Assessing novelty

The fill colour says how much a result matters **to this paper**. The border on the key
results (importance 4–5) says something else: how new the result is **relative to the
literature**. That covers both its statement and its proof technique. The border runs from
white (known) to deep red (no close precedent). A reader should be able to tell from the
graph which key steps are the paper's own new ideas and which are known results or
standard techniques put to use. The modal explains the rating in a short two-paragraph
note, Statement and Technique. It links the closest prior work inline, by exact theorem
number.

This judgement rests on a literature search, not on the paper's word. Authors' claims
("to our knowledge, the first …") are leads to check.

## Contents
1. When and what to assess
2. The scale
3. Internet access
4. Procedure for one node
5. Where to search
6. Exact citations
7. Writing `novelty_note` and `novelty_refs`
8. Calibration and honesty rules
9. Several nodes in parallel
10. Worked example

## 1. When and what to assess

- **When.** Only after the node set and every importance rating are final, which means
  after SKILL.md steps 3–5. If a later change raises a node to 4 or more, assess it. If a
  change lowers one below 4, remove its novelty fields.
- **Which nodes.** Every shown node with `importance >= 4`, including the main results
  and key definitions. `python3 $S novelty <workdir>` lists them. Until they are all
  assessed, `check` reports each one as "no novelty assessment".
- **What.** One rating that combines two aspects:
  - **Statement.** Is the result, or an equivalent one, already known? It may be known
    under another name, in another field, or as a special case or corollary of a known
    result. Or is it a generalisation, a sharpening, or a known result moved to a new
    setting?
  - **Technique.** Is the key step of the proof standard? Name it the way the literature
    does: "Hensel lifting", "a hybrid argument", "the Chinese remainder theorem", "amplitude
    amplification", "a compactness argument", "a direct calculus estimate". Or is it a
    known argument with modifications? Then say which ones. Or is there no precedent?
  - For a **definition** or construction, "technique" means the notion itself. Is it
    standard, equivalent to a known notion under another name, or new?
- **Relative to what.** Rate the result against work that appeared before the paper.
  Mention independent work from about the same time as concurrent, and later work as
  later. Neither lowers the rating.

## 2. The scale

| level | name | what belongs here |
|---|---|---|
| **5** | no close precedent | The statement is not in the literature in any equivalent form, **and** the key idea has no clear precedent: a new technique, or a known tool used where the literature gives no hint that it could work. Rare: at most one or two nodes in a paper, often none. |
| **4** | substantially new | A new statement whose proof needs an essential new ingredient, although it is built from known tools. The closest prior work is clearly weaker, or reaching it from that work takes a real idea. Also a known statement with a substantially new proof technique. |
| **3** | new combination | A new or sharper statement proved by combining known techniques in a way that is not obvious, or by adapting a known argument with changes that are not routine. Also a known statement with a genuinely different, but not deep, new proof. |
| **2** | routine variant | A known result in a new setting, a special case, explicit constants, or a variant with slightly different hypotheses. The proof is a known argument with routine changes. Also a new statement that follows by a standard technique once someone asks the question. |
| **1** | known | The statement, or an equivalent one, is in the literature or in textbooks, and so is its proof. Results recalled or reproved "for completeness" belong here. |

Half steps (3.5) are allowed. Prefer integers.

How to combine the two aspects:

| statement | technique | rating |
|---|---|---|
| known (or equivalent to a known one) | standard / the known proof | 1 |
| known, special case, or new setting | standard, routine changes | 2 |
| new, but it follows once posed | a standard technique, named | 2–3 |
| known | a genuinely different proof | 3 (4 if the new technique is the point) |
| new | non-obvious combination of known tools | 3–4 |
| new | an essentially new key idea | 4–5 |

A main result (importance 5) does **not** automatically get novelty 5. Many main theorems
assemble known ingredients in a new way, and that is a 3. A modest-looking lemma can be a
4 if it is where the new idea sits.

## 3. Internet access

Without the internet you cannot judge novelty, and you cannot check a single theorem
number. Check access before starting:

1. If you have a web search tool, run one test search. If you have a fetch tool, open
   `https://arxiv.org/abs/quant-ph/9508027`.
2. Run `python3 $S net-check`, which tests whether this shell can reach the arXiv API,
   OpenAlex and arxiv.org. `lit-search` and `ref-index` need that.

One working route is enough. If **neither** works, stop and ask the user, with the
AskUserQuestion tool if you have it and otherwise a short message, then wait for the
answer. Write the question in English and say in one sentence why you are asking: novelty
can only be judged, and theorem numbers checked, against the literature. Options:

- **"I'll enable internet / web access, then continue"** (recommended). Re-run the checks
  once the user says it is done.
- **"Skip the novelty assessment."** Set top-level `novelty_skipped: "<reason>"`. The page
  is built without novelty borders, and `check` no longer asks for them. Say so in the
  hand-over.
- **"Assess from the paper and your own knowledge, unverified."** Every entry in
  `novelty_refs` then gets `verified: false`, and every Technique paragraph ends with "(Not
  checked against the literature: no internet access.)". Never give a theorem number from
  memory, even here. Leave `where` empty unless the paper itself states the number, and
  then write "Theorem 3.1 (as cited in the paper)".

If you cannot reach the user (you are a subagent, or the run is non-interactive), do not
choose for them. Hand the question to whoever called you, as in SKILL.md step 0.

## 4. Procedure for one node

1. **Pin down the claim.** Read the node in `novelty-brief.md` and in the paper, including
   the full proof. Write down for yourself, in standard terminology and without the
   paper's notation:
   - (a) the mathematical content of the statement;
   - (b) the key step(s) of the proof;
   - (c) any equivalent formulation, including ones in other fields. A lemma about
     orders modulo $2^k$ may be a known fact in elementary number theory. A circuit
     identity may be a known identity in representation theory.
2. **Start from the paper.** Find out what the authors claim is new, and whom they compare
   with ("extends [7]", "following [3]", "a variant of the argument in [12, §4]"). The
   brief lists the works cited inside the node and the running text around references to
   it. The introduction and the related-work section usually say more. Treat all of this
   as leads: check every claimed precedent in the cited work itself, and search beyond
   the paper's bibliography, because papers under-cite.
3. **Search.** Run at least 3–5 queries per node, of three kinds:
   - *statement* queries: the result in standard words ("exact quantum order finding",
     "order of 3 modulo 2^k");
   - *technique* queries: the name of the method plus the object ("amplitude
     amplification exact", "Hensel lifting quantum circuit");
   - *equivalence* queries: the same content in the terms of another field.

   For a node whose content is classical, look for the textbook statement as well
   (§5).
4. **Read the closest sources.** Open the two to four most relevant hits and find the
   specific result. Compare precisely: are the hypotheses the same? Is the conclusion
   stronger or weaker? Is the proof idea the same, and if not, what differs? A title or
   an abstract is not enough to call something "the same result".
5. **Fix each locator** exactly (§6).
6. **Rate the node** (§2) and **write** `novelty_note` and `novelty_refs` (§7).
7. **Log the search** in `<workdir>/novelty-log.md`: per node, the queries you ran, the
   sources you opened, and what each showed, including the near misses. Someone can then
   audit or redo the assessment. The log is not shown on the page.

## 5. Where to search

| tool | good for |
|---|---|
| your web search tool | everything; the first stop. Add "arXiv", "theorem", "lemma" or a textbook name to a query |
| `python3 $S lit-search <words> [--before YYYY-MM-DD]` | arXiv and OpenAlex (journals, books, conference papers): authors, year, venue, link, abstract. `--before` limits it to work before the paper. Quote a phrase inside the query: `'"exact phrase" word'` |
| `python3 $S ref-index <arXiv id or URL> -o <workdir>/refs [--grep word …]` | a cited work's numbered results (Theorem 3.2, Lemma 4.1 …) with their statements, read from arXiv's HTML (with the version) or from a page or PDF. Saves the full text in `refs/` for further searching |
| `python3 $S fetch-arxiv <id> -o <workdir>/refs` | a cited paper's LaTeX source, when you need its exact statement |
| your fetch tool on `arxiv.org/abs/…`, `arxiv.org/pdf/…`, DOI pages | reading the result itself |
| MathOverflow, Math StackExchange, Theoretical CS StackExchange | "is this known?" questions; they often name the classical source |
| textbooks and lecture notes of the field | classical facts. Cite the book, with its edition and the theorem number |

Query hygiene:
- Search for the *content*, not the paper's own names: "order of 5 modulo 2^k is 2^{k-2}",
  not "Lemma 4.3 of this paper".
- Search for the *technique* under all its names (for example "phase kickback", "phase
  estimation", "Kitaev's algorithm").
- Use `--before <paper date>` to separate prior work from later work. Search once without
  it as well, for concurrent work and follow-ups.

## 6. Exact citations

Every work a novelty note relies on names a **precise place** in that work: "Theorem 3.2",
"Lemma 4.1 and its proof", "Proposition 2.7", "§5.3", "Exercise 4.12", "eq. (3.4)",
"Ch. 7, Thm 7.4". Never cite a bare paper as the precedent for a statement or a technique.

- **Read the number in the work itself.** For arXiv, `ref-index` lists its numbered
  results. Otherwise open the PDF or HTML with your fetch tool, or use `pages` on a
  downloaded PDF. Then set `verified: true`.
- **Versions differ.** arXiv versions and the journal version can be numbered
  differently. Say which one you read when it matters: "Theorem 3 (arXiv v2)", "Theorem 4.1
  (journal version)". `ref-index` reports the version it read.
- **Secondary sources.** Sometimes you only know a number from another paper ("[Kit95,
  Thm 2]" as cited elsewhere), or from a book's table of contents or index. Write it as
  "Theorem 2 (as cited in Mosca–Zalka 2004)" and set `verified: false`.
- **No access.** If the full text is not openly available (paywalled book or journal, no
  preprint), cite the work without a number, or with the secondary-source number, and
  set `verified: false`. The page then marks that inline link "(locator not verified)".
- **Never give a theorem number from memory.** Remembered numbers are often wrong, and a
  wrong number is worse than none. Never cite a work you have not found in this session:
  every entry carries the `url` you opened.
- **The paper's own citations** ("by [12, Thm 3.1]") are leads too. Check them in the
  cited work, because papers do mis-cite. If the cited work disagrees with the paper,
  say so in the note.

## 7. Writing `novelty_note` and `novelty_refs`

The note is read by someone who wants the **verdict** and **the closest prior work**, not
the evidence trail. The evidence stays in `novelty-log.md`.

**Shape.** Exactly two short paragraphs, separated by a blank line. Inline LaTeX is
allowed.
1. `Statement: …`: is the result new, known, or a variant? Name the closest precedent(s)
   and the one difference that matters. Aim for 2–3 sentences, about 50 words.
2. `Technique: …`: is the key argument standard (by its standard name), a modification
   (of what, changed how), or new? Aim for 1–2 sentences, about 30 words.

`check` rejects a note that is not shaped this way. It also rejects a Statement paragraph
over 70 words, a Technique paragraph over 50 words, and a paragraph citing more than 3
works.

**Citations are inline links.** Write each citation as `\href{url}{Author Year,
locator}`, at the place where the work is mentioned: "the closest is
`\href{https://arxiv.org/abs/<id>}{Smith 2019, Thm 1.2}`, which …". The page shows no
reference list, so every cited work must be linked where it is cited. Do not use `\cite{}`:
a bare "[12]" means nothing to the reader.

**Keep it short:**
- **Few works.** When many results are related, cite only the one to three most relevant:
  the closest precedent for the statement and the standard source for the technique. Do
  not walk through every precedent, or through how each component of the result has
  appeared before.
- **No technical details.** Leave out proof steps, constants, case lists, and accounts of
  how the paper uses each ingredient. The node's statement and proof sketch already show
  the mathematics.
- **No search reports.** Write "we found no earlier …", not the list of queries, which
  belongs in the log.

Too long. This Statement paragraph enumerates every precedent and how each is used (the
names are placeholders):

> Statement: new as a package, though each part has a precedent. Reducing X to Y goes back
> to Smith (1976, Lemma 5 and Theorem 3), randomized in Jones (2008, §10.4) and from a
> single sample in Lee (2021, Theorem 1); the auxiliary tree is a Kim tree (Kim 1975, as
> described in Park 2010, §1.3) with a test instead of witnesses; and its uses are known:
> computing Z from it (Jones 2008, Exercise 11.3; Lee 2021, App. A.2) and the exact count
> (Wu 2025, Theorems 5.2 and 6.2). We found no earlier process that …

Right length. Verdict, the closest works, and the one point that is new. This is the source
as written in `annotations.yaml`:

```yaml
    novelty_note: |
      Statement: new as a package. Reducing X to Y is classical
      (\href{https://doi.org/<doi>}{Smith 1976, Thm 3}; \href{https://arxiv.org/abs/<id>}{Lee
      2021, Thm 1}), and the auxiliary tree is a Kim tree; what we found no precedent for is a
      process that generates, during its own run, the data that later evaluate it.

      Technique: standard: the criterion of \href{https://doi.org/<doi>}{Smith 1976, §5}
      turned into an exact count, $K$-fold repetition, and Kim-style size bounds.
```

Useful openings, with placeholder names and numbers:
- "Statement: classical. This is Hensel's lemma, in the form of `\href{…}{Jones 1999, Ch.
  II, Lemma 4.6}`."
- "Statement: equivalent to a known result in coding theory, `\href{…}{Lee 2003, Thm
  6.3.2}`, under the translation codeword ↔ …"
- "Technique: standard, a direct calculus argument."
- "Technique: the hybrid argument of `\href{…}{Kim et al. 1997, Thm 3.3}`, applied to … instead
  of …"
- "Technique: new as far as we found: the key step, …, has no precedent."

Rules that still apply:
- **Be specific about the one difference that matters**: "only for prime moduli", "with
  an extra log factor", "needs gates that depend on the input".
- **Claims of absence are claims about your search.** Write "we found no earlier …", not
  "this is new". Say so when the evidence is thin.
- **Name techniques by their standard names**, so a reader can look them up.

`novelty_refs` is the record behind the links, and the page does not show it. It has one
entry per linked work, with the same `url`. Each entry gives the exact locator and whether
you checked it. Other works you consulted go in `novelty-log.md`, not here:

```yaml
    novelty_refs:                    # (placeholders)
      - cite: "A. Smith, Exact circuits for X, J. Quantum Y 2 (2019)"
        where: "Theorem 1.2"         # theorem / lemma / section / equation in the cited work
        url: "https://arxiv.org/abs/<id>"
        verified: true               # you read `where` in the work itself
      - cite: "B. Jones, Algebraic Number Theory, Springer 1999"
        where: "Ch. II, Lemma 4.6 (as cited in Smith 2019)"
        url: "https://doi.org/<doi>"
        verified: false              # full text not accessible: the page marks the link
```

`check` enforces the following:
- every `\href` in the note has an entry here;
- every entry has `cite` and an explicit `verified`;
- every entry with `verified: true` has `where`.

It suggests removing entries that the note does not link. The page marks every link whose
entry has `verified: false` "(locator not verified)".

## 8. Calibration and honesty rules

- **Compare across nodes at the end.** Sort the key results by novelty and re-read the
  notes together. Does the order match the evidence and, where the evidence agrees, the
  authors' own account of what is new? Adjust inconsistent ratings.
- **Evidence beats claims.** If the authors call something new and you find a precedent,
  the precedent wins. State it precisely and politely, with the locator. If the authors
  call something standard, that is usually right. Still, find and cite the standard
  source.
- **Do not inflate.** A recent, important or hard paper is not automatically new in every
  step. Being the paper's main result is not evidence of novelty.
- **Do not deflate on surface similarity.** "Uses the quantum Fourier transform" does not
  make an argument standard. What matters is whether the *key step* has a precedent.
- **Concurrent work** (independent, within about six months) is mentioned and does not
  lower the rating. Later work that builds on the paper does not lower it either.
- **Inconclusive search.** Rate by the evidence you have, say in the note that the search
  was inconclusive, and log what you tried. Do not round up to look generous, or down to
  look sceptical.
- **No invented sources, no guessed numbers** (§6). This rule has no exceptions.

## 9. Several nodes in parallel

The research for each node is independent. If you can launch subagents with web access,
give each one a node, or a few closely related nodes. Run them in the foreground and wait
for their reports. Give each subagent:
- the path of the paper, and its node's section of `novelty-brief.md`;
- the path of this file, to follow §§2 and 4–7;
- the paper's date;
- the instruction to return YAML (`novelty`, `novelty_note`, `novelty_refs`) plus its
  search log, with the note shaped and sized as in §7.

Then merge their outputs into `annotations.yaml` and `novelty-log.md`, and **calibrate
globally** yourself (§8). Ratings from different subagents drift, and the scale must mean
the same thing across the page. Spot-check at least one `verified: true` locator per
subagent against the source. Subagents also tend to write long notes. Trim them to §7's
shape and length: keep the verdict and the most relevant one to three works per
paragraph, and move the rest into the log. Use only works the subagent verified. Without
subagents, do the nodes one by one.

## 10. Worked example

The hypothetical combinatorics paper of importance.md §6. The works cited here are
placeholders; in a real assessment every entry is a work you found and opened.

```yaml
novelty_date: 2026-10-26            # top level: the date of the search, shown in the legend and the modals
nodes:
  thm:main:                          # importance 5
    novelty: 4
    novelty_note: |
      Statement: new. The best earlier bound for planar graphs with property X is
      $O(n^{2/3})$ (\href{https://arxiv.org/abs/<id>}{Smith 2019, Thm 1.2}); we found no
      earlier $f(n)$ bound.

      Technique: the standard decomposition-plus-discharging scheme
      (\href{https://doi.org/<doi>}{Jones 2015, §3}); what is new is the decomposition itself.
    novelty_refs:
      - cite: "A. Smith, Bounds for Y in planar graphs, J. Graph Theory 90 (2019)"
        where: "Theorem 1.2"
        url: "https://arxiv.org/abs/<id>"
        verified: true
      - cite: "B. Jones, Decomposition and discharging, Combinatorica 35 (2015)"
        where: "§3"
        url: "https://doi.org/<doi>"
        verified: true
  lem:discharging:                   # importance 4
    novelty: 2
    novelty_note: |
      Statement: a new list of rules, but of a familiar kind.

      Technique: standard discharging (\href{https://arxiv.org/abs/<id>}{Lee 2017, §2}), with
      a case analysis tailored to property X; long, but without a new idea.
    novelty_refs:
      - cite: "C. Lee, An introduction to discharging, Discrete Math. 340 (2017)"
        where: "§2"
        url: "https://arxiv.org/abs/<id>"
        verified: true
  prop:separator:                    # importance 2: not assessed
```
