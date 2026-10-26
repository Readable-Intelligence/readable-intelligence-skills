"""The editorial standard, rendered from `standard/` (the previous restructure-paper's specifications, examples and reviewer protocol,
kept verbatim except part 05, which is this skill's own, part 06's two references to it, and the renaming of the old skill's
"stages" to parts; the single source). Its six parts are areas of the standard, not steps of the workflow: a step
carries out or reviews some of them. Prompts quote it through placeholders `{{STANDARD:<spec>}}`:

  common                      the contract shared by every editing pass
  part:NN                     a whole part file (01-06)
  part:NN:procedure           its "## Procedure" section           part:NN:acceptance   its acceptance section
  part:06:composition         the composition of part scopes       part:06:views        the reading views (step 3)
  examples:NN                 a part's examples (part 05 has none)
  review:independent|application|checklist

`conditions()` numbers the acceptance conditions `PNN.i`; `criteria_md()` is the standard given to an acceptance
reviewer. Part 01 (terminology and notation) is in neither: names and symbols are the registrar's, under its own rule
(`prompts/registrar.md`).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "standard"
PARTS = {"01": "01-terminology", "02": "02-statements", "03": "03-architecture",
         "04": "04-local-proofs", "05": "05-proof-sketch", "06": "06-complete-repair"}
REVIEW = {"independent": "independent", "application": "application", "checklist": "general-checklist"}
# Part 06 bullets that are not properties of a manuscript: "all of 01-05 hold" (covered by those conditions) and
# "the final reviewer is a different agent" (a property of the process, which the pipeline guarantees).
NOT_MANUSCRIPT = {("06", 1), ("06", 5)}
REVIEWED = ("02", "03", "04", "05", "06")     # part 01 is the registrar's


def _read(rel):
    return (ROOT / rel).read_text()


def _section(text, heading):
    """The body of the first `## <heading...>` section, up to the next `## ` heading."""
    m = re.search(rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        raise KeyError(heading)
    return m.group(0).strip()


def raw(spec):
    s = spec.split(":")
    if s[0] == "common":
        return _read("parts/common.md").strip()
    if s[0] == "part":
        text = _read(f"parts/{PARTS[s[1]]}.md")
        if len(s) == 2:
            return text.strip()
        sub = s[2]
        if sub == "procedure":
            return _section(text, "Procedure")
        if sub == "acceptance":
            return _section(text, "Acceptance")
        if sub == "composition":
            return _section(text, "Composition of part scopes")
        if sub == "views":
            step = re.search(r"^3\. Recheck the introduction without the body.*?(?=^4\. )", text, re.S | re.M)
            return step.group(0).strip()
    if s[0] == "examples":
        return _read(f"examples/{PARTS[s[1]]}.md").strip()
    if s[0] == "review":
        return _read(f"review/{REVIEW[s[1]]}.md").strip()
    raise KeyError(spec)


def quote(spec):
    return f"--- begin quoted editing standard: {spec} ---\n\n{raw(spec)}\n\n--- end quoted editing standard ---"


def render(text):
    """Replace every `{{STANDARD:<spec>}}` placeholder with the quoted section."""
    return re.sub(r"\{\{STANDARD:([a-z0-9:]+)\}\}", lambda m: quote(m.group(1)), text)


def conditions():
    """Every acceptance condition of the reviewed parts that is a property of the manuscript, numbered `PNN.i`."""
    out = []
    for nn in REVIEWED:
        body = raw(f"part:{nn}:acceptance")
        bullets = re.findall(r"^- (.+?)(?=^- |\Z)", body, re.S | re.M)
        for i, b in enumerate(bullets, 1):
            if (nn, i) in NOT_MANUSCRIPT:
                continue
            out.append({"id": f"P{nn}.{i}", "part": PARTS[nn], "text": re.sub(r"\s+", " ", b).strip()})
    return out


ADAPTER = """# How this standard is applied in this pipeline

The texts below were written for a workflow of editors, a coordinator and reviewers; read their roles through this
mapping. You are the independent acceptance reviewer. Your discovery record is `reading.json`, written before you
opened this file; your verdict is `acceptance.json`. No editor notes, earlier reviews or change records exist for you:
judge the manuscript alone. The author original is `original.txt`. There is no separate input for each part: apply
every condition of parts 02-06 to the whole paper, as part 06 does. Part 01 (terminology and notation) is not given to
you: another role puts names and symbols in order, and you rule on no condition about them. You do not edit the
manuscript and you do not coordinate repairs; a FAIL goes to the editors with its required repair.
"""


def criteria_md():
    out = [ADAPTER, quote("review:independent"), quote("review:application"), quote("review:checklist"),
           quote("common")]
    for nn in ("06", "02", "03", "04", "05"):
        out.append(quote(f"part:{nn}"))
        if nn != "06" and (ROOT / f"examples/{PARTS[nn]}.md").exists():
            out.append(quote(f"examples:{nn}"))
    listing = "\n".join(f"- `{c['id']}` ({c['part']}): {c['text']}" for c in conditions())
    out.append("# The acceptance conditions you must rule on, with their ids\n\n" + listing)
    return "\n\n".join(out) + "\n"


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) > 1 and sys.argv[1] == "conditions":
        print(json.dumps(conditions(), indent=1))
    else:
        print(criteria_md())
