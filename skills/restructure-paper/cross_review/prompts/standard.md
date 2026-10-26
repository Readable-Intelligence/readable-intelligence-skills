## What counts as an issue
The standard is how the paper's literature presents its mathematics, as found in the reviewers' notes, applied for the reader the paper is written for. An issue is a place where that reader would be better served if the draft did what the literature does: the works share a way of handling the situation, the draft does not follow it, and so its reader understands, checks, finds or uses what the paper says with more trouble, or misreads it. Judge each passage as the reader meets it, with what the paper has given them by that point. A reader who could work a point out later, or from elsewhere, still pays for it at this place: the question is how much work the draft asks of its reader here, not whether the point can be recovered. An issue need not be an error, an ambiguity or a gap the reader cannot fill, and its fix need not be necessary: it is enough that the fix saves the reader work here, however little, and costs them no more elsewhere. Time is part of that work: a passage that takes this reader longer to read than its content requires costs them that time, even when every sentence in it is clear. Saying something about another work that the work does not say is an issue too, and so is an error in the mathematics, or a step the paper does not justify, when a correct fix can be given.

A pattern shows what serves readers; it is not a rule. A departure is not an issue when it serves the reader as well or better where they meet it: for instance, where the draft does the same job there in another way, or where the pattern does not fit what this paper does. A choice between equally clear wordings is not an issue either.

## What a fix must be
A fix is a list of exact edits to the files in `paper/`. Each edit has:
- `file`: the path of the file within `paper/`;
- `old`: a passage copied exactly from that file, character for character with its line breaks, long enough to occur in the file exactly once;
- `new`: the complete text that replaces it, or nothing to delete it. To insert text, include the neighbouring text in `old` and repeat it in `new`. To move text, delete it with one edit and insert it with another.

The fix must:
- resolve the issue fully, at every place where the reader meets it, with no more change than that takes, following the pattern it relies on. Some issues need a word changed; others need a passage rewritten or moved;
- keep the mathematics: the results, their hypotheses and the arguments stay what they are, unless they are wrong, and then change only as far as the evidence supports. Presenting them better is what a fix is for: it may define, explain, restate, cite, add or move text, as long as what the paper claims and proves stays the same;
- consist of the actual text, with nothing left for the editor to decide. New mathematics in it is correct, with the exact hypotheses, normalizations and scope of what it describes, and is either a standard fact given with its source or argued in full. A new citation is to a work you have checked, at the location that says what the paper uses it for, and comes with its bibliography entry;
- fit the rest of the paper: commands and labels that exist, references that still resolve, and every other passage that states, restates or relies on what the fix changes still correct with it. Look for these passages in the whole paper, and change them in the same fix where they need it.

No two edits may change the same text, within one issue or across issues. When two issues need the same passage, they are one issue.
