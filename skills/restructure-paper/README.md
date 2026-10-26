# restructure-paper

Rewrites a proof-based mathematics or theoretical CS paper (LaTeX) so that researchers in its field can read and check it as easily as the best human-written papers on neighbouring problems. Two model families divide the work:

- **GPT** (Codex CLI) retrieves the literature, writes the baseline revision, keeps the terminology in order, and does the well-defined checking.
- **Claude** (Claude Code CLI) judges: it calibrates against comparable papers, reviews each version against a written editorial standard, votes against regressions, and compiles the repair sheets.
- **Both** write each round's revision in the cross review (`cross_review/`): each reviews the writing against the paper's literature and judges the other's findings, and GPT applies the accepted fixes.

**Statements keep their exact strength.** Arguments are completed and independently checked. What the reader does not need is cut. Gaps that need new mathematics go to the author in the report, never into the paper.

`SKILL.md` is the operating manual, `docs/DESIGN.md` explains why each part exists, and `docs/TESTS.md` records the tests.

## Quick start

```bash
python3 scripts/duo.py run    --src path/to/paper_source --out path/to/run.nosync --config my.json
python3 scripts/duo.py status --out path/to/run.nosync
python3 scripts/duo.py resume --out path/to/run.nosync --config my.json
```

`my.json` names the models, for example `{"claude": {"model": "claude-opus-5-5", "effort": "xhigh"}, "gpt": {"model": "gpt-6-astra", "effort": "max"}}`. Neither the run directory nor this package may sit in a folder that iCloud, Dropbox, OneDrive or Google Drive syncs; with iCloud, a folder name ending in `.nosync` is safe. Results land in `run.nosync/deliverable/` and `run.nosync/report.md`.

## Legend

```mermaid
flowchart LR
    C["Claude step"]:::claude
    G["GPT step"]:::gpt
    B["Claude and GPT,<br/>separately"]:::both
    S["Script step"]:::script
    D[/"Input, output<br/>or outcome"/]:::data
    classDef claude fill:#fbe3d3,stroke:#c2410c,color:#111
    classDef gpt fill:#d6f2df,stroke:#15803d,color:#111
    classDef script fill:#e7e9ee,stroke:#6b7280,color:#111
    classDef both fill:#e9e2fb,stroke:#6d28d9,color:#111
    classDef data fill:#ffffff,stroke:#6b7280,stroke-dasharray:4 3,color:#111
```

## 1. The run, end to end

```mermaid
flowchart TD
    IN[/"Paper source (LaTeX)"/]:::data --> RET["Literature retrieval<br/>comparable papers, sources of imported results"]:::gpt
    RET --> CAL["Calibration<br/>how comparable papers are arranged and written"]:::claude
    RET --> TERMS["Terminology verification<br/>quotations checked by script"]:::gpt
    CAL --> GAPS{"Gaps in the<br/>reference bundle?"}:::script
    TERMS --> GAPS
    GAPS -- "yes" --> SUP["One supplementary retrieval<br/>and recalibration"]:::gpt
    GAPS -- "no" --> B1
    SUP --> B1
    B1["Baseline, pass 1<br/>statements, arrangement<br/>(standard, parts 02–03)"]:::gpt --> B2["Baseline, pass 2<br/>local proofs<br/>(standard, part 04)"]:::gpt
    B2 --> SK["Proof sketch<br/>(standard, part 05)"]:::gpt
    SK --> ROUNDS[["Rounds: panel, gate, cross review<br/>(diagram 2)"]]
    ROUNDS -- "round limit, all conditions pass, a round<br/>that changes nothing, or two rejections" --> REG
    REG["Registrar, once, after the last structural change<br/>one rule for every name and symbol;<br/>light gate"]:::gpt
    REG --> CONF["Confirmation check<br/>fresh proof check of every rewritten passage"]:::gpt
    CONF --> FA["Final acceptance review<br/>against every condition"]:::both
    FA --> FC["Final blind comparison<br/>with the original"]:::both
    FC --> DEF["Defensive-sentence pass<br/>deletions only, checked by script"]:::gpt
    DEF --> OUT[/"deliverable/ and report.md<br/>last accepted version without soundness debt"/]:::data

    classDef claude fill:#fbe3d3,stroke:#c2410c,color:#111
    classDef gpt fill:#d6f2df,stroke:#15803d,color:#111
    classDef script fill:#e7e9ee,stroke:#6b7280,color:#111
    classDef both fill:#e9e2fb,stroke:#6d28d9,color:#111
    classDef data fill:#ffffff,stroke:#6b7280,stroke-dasharray:4 3,color:#111
```

The original is delivered instead only if both final judges prefer it.

## 2. One round

```mermaid
flowchart TD
    CAND[/"Candidate: the baseline (round 1),<br/>or the last round's revision"/]:::data --> PANEL

    subgraph PANEL ["Panel on the candidate (parallel, fresh sessions)"]
        ACC["Acceptance review<br/>reading.json first, then PASS / FAIL / UNVERIFIED<br/>on all 23 conditions of parts 02–06"]:::claude
        FID["Fidelity check<br/>statements, steps, qualifications, assumptions<br/>against the original"]:::gpt
        CHK["Proof check<br/>a verdict on every rewritten proof passage"]:::gpt
        VOTE["Blind vote<br/>regression guard against the predecessor"]:::claude
    end

    PANEL --> DEC{"Decision (script)"}:::script
    DEC -- "builds, no soundness debt,<br/>vote does not find it worse" --> ACCEPT[/"Accepted: the new base"/]:::data
    DEC -- "only debt blocks it" --> REPAIR[["Repair loop (diagram 3)"]]
    REPAIR -- "debt cleared, or a strong vote" --> ACCEPT
    DEC -- "otherwise" --> REJ[/"Rejected: the base stays<br/>the last accepted version"/]:::data
    ACCEPT --> PROB
    REJ --> PROB
    PROB[/"Problems the checks found in the base<br/>fidelity H and M · unconfirmed added steps and gaps · failed proof conditions (P04)<br/>math issues · false or unsupported claims in the vote · copied text · unknown references · reader reports"/]:::data
    PROB --> CR
    subgraph CR ["Cross review of the base (cross_review/, its own process; the vault is locked)"]
        REV["Review: each reviews the writing against<br/>the paper's literature and decides every reported problem"]:::both
        JUD["Cross review: each judges<br/>every item of the other's list"]:::both
        MER["Merge of the accepted fixes,<br/>then the revision"]:::gpt
        REV --> JUD --> MER
    end
    CR --> NEXT[/"Revised version: the next round's candidate"/]:::data

    classDef claude fill:#fbe3d3,stroke:#c2410c,color:#111
    classDef gpt fill:#d6f2df,stroke:#15803d,color:#111
    classDef script fill:#e7e9ee,stroke:#6b7280,color:#111
    classDef both fill:#e9e2fb,stroke:#6d28d9,color:#111
    classDef data fill:#ffffff,stroke:#6b7280,stroke-dasharray:4 3,color:#111
```

- **The cross review** is described in `cross_review/README.md`. Each round runs it once on the base, with fresh reviewers, the reference bundle (without GPT's descriptions), and the works that earlier rounds' reviewers obtained online. The reported problems go to both reviewers: each decides every one, as a fix, a problem for the author, or not an issue with a reason, and the other judges that decision. A fix of a reported problem is the shortest correct one. The reviewers must not open the paper itself online.
- **Round 1** also plants three defects in a copy for the fidelity and proof checks. If they miss one, every later panel adds Claude instances of both checks.
- **Coverage is enforced by script.** An output is rejected and retried if any condition, rewritten proof passage, script-flagged place or labelled result lacks its verdict.

## 3. Soundness debt and the repair loop

**Soundness debt.** A blocking finding is a fidelity item of severity H, or an added step the proof check rates `unsupported` or `false`. The debt of a version is every blocking finding of any check so far whose quoted text it still contains unchanged. Only a version without debt is delivered.

```mermaid
flowchart TD
    C[/"Candidate rejected only for debt"/]:::data --> RS["Repair sheet<br/>exactly the blocking findings"]:::claude
    RS --> RX["Executor"]:::gpt
    RX --> LC["Local check<br/>fidelity, proof check of the changed passages,<br/>vote against the current deliverable"]:::script
    LC --> PROG{"Debt strictly lower and<br/>the vote does not find it worse?"}:::script
    PROG -- "yes, debt reaches 0" --> OK[/"Accepted"/]:::data
    PROG -- "yes, debt remains,<br/>attempts left" --> RS
    PROG -- "no, or attempts used up" --> RV["Revert sheet<br/>restore the original's wording<br/>where the findings sit"]:::claude
    RV --> ZERO{"Debt 0?"}:::script
    ZERO -- "yes" --> OK
    ZERO -- "no" --> STRONG{"Round's vote preferred<br/>the candidate strongly?"}:::script
    STRONG -- "yes" --> OPEN[/"Working base with open debt<br/>(never delivered as such)"/]:::data
    STRONG -- "no" --> REJ[/"Rejected"/]:::data

    classDef claude fill:#fbe3d3,stroke:#c2410c,color:#111
    classDef gpt fill:#d6f2df,stroke:#15803d,color:#111
    classDef script fill:#e7e9ee,stroke:#6b7280,color:#111
    classDef both fill:#e9e2fb,stroke:#6d28d9,color:#111
    classDef data fill:#ffffff,stroke:#6b7280,stroke-dasharray:4 3,color:#111
```

**Termination.**
- **Repair loop:** the debt is a non-negative integer that every accepted attempt lowers, and the revert sheet restores text the original is taken to state correctly.
- **The run:** it stops when every condition passes with clean checks, when a cross-review round changes nothing, after two rejections in a row, or at the round limit (`rounds`, default 3: three cross-review rounds, and a panel on the last one's revision).

## 4. Keeping the two models independent

```mermaid
flowchart LR
    subgraph GPTF ["GPT: codex exec, its own Codex home, sandboxed, network off except retrieval"]
        GR["Retrieval"]:::gpt
        GW["Writers<br/>baseline, executor, registrar"]:::gpt
        GC["Checkers<br/>fidelity, proof check"]:::gpt
    end
    subgraph CLF ["Claude: claude -p --restricted --safe-mode, file tools only"]
        CC["Calibration"]:::claude
        CJ["Acceptance review, vote"]:::claude
        CP["Repair compiler"]:::claude
    end
    subgraph CRF ["Cross review: its own process and records; both models, network on for literature"]
        XR["Reviewers, judges,<br/>merge, revision"]:::both
    end
    GR -- "reference texts<br/>(GPT commentary stripped)" --> CC
    GR -- "reference texts<br/>(GPT commentary stripped)" --> XR
    CC -- "architecture, style card" --> GW
    GW -- "manuscript versions<br/>(blind, comments stripped)" --> CJ
    XR -- "revised version" --> CJ
    GC -- "check results" --> CP
    CJ -- "review and vote" --> CP
    GC -- "problems found" --> XR
    CJ -- "failed proof conditions,<br/>math issues, vote findings" --> XR
    CP -- "repair sheets" --> GW

    classDef claude fill:#fbe3d3,stroke:#c2410c,color:#111
    classDef gpt fill:#d6f2df,stroke:#15803d,color:#111
```

Every step is a fresh process in a freshly staged workspace with an opaque name and only its listed inputs. The models meet only through typed files, as drawn.
- **Locks:** while steps run, the vault and the other CLI's session stores are unreadable. A watcher stops the run if a lock is undone, and every step's tool calls are audited.
- **GPT's Codex home:** GPT steps run with their own Codex home, which shares only the login. The user's global Codex instructions, skills and memories never reach them.
- **The cross review** reads only copies staged for it in `run/cross/` and runs while the vault is locked. Its own steps lock its records and audit every tool call, flagging any read of this run directory or package and any search or download of the paper itself. While the skill's own steps run, `run/cross/` is locked as well.

## Who decides what

| Question | Decided by |
|---|---|
| Is the version good enough? | The acceptance review (Claude), against the 23 numbered conditions of parts 02–06 in `standard/` |
| Is it sound? | GPT's fidelity check and proof check, through the soundness debt (script) |
| Is it worse than before? | The blind vote (Claude); it can only reject |
| What changes next? | The cross review: its two reviewers, each checked by the other; it also decides every problem the checks found |
| How is soundness debt paid? | The repair compiler (Claude) and the executor (GPT), checked locally |
| Terminology and notation | The registrar (GPT), which applies one rule and fixes the source itself |
| Accept, repair, stop, deliver | The script, from the recorded verdicts |

## Files

```
README.md               this overview
SKILL.md                how to run it, roles, decisions, report
config.default.json     models, per-role overrides (the registrar runs at max effort), rounds, limits, isolation
standard/               the editorial standard (single source; rendered into prompts)
prompts/                one prompt per role, plus hard_rules.md (R1–R9)
schemas/                JSON schemas for every structured output
scripts/duo.py          the orchestrator (standard library only)
scripts/standard.py     renders the standard; numbers its acceptance conditions
scripts/texutil.py      LaTeX build, statement extraction, diffs, anchors, detectors
scripts/mock_agent.py   stub agents for --mock
cross_review/           the cross review that writes each round's revision (its own README, prompts, schemas, stub)
docs/DESIGN.md          why it is built this way, with the evidence
docs/TESTS.md           the tests and their results
```
