"""Literature helpers for the novelty assessment (references/novelty.md).

* net_check()            which literature services this machine can reach
* search_arxiv / search_openalex   prior-work search (titles, years, ids, abstracts)
* fetch_text(source)     a cited work as plain text: arXiv id (arXiv HTML / ar5iv), URL, or local file
* numbered_results(text) "Theorem 3.2 (Title). statement …" entries, for exact citations

Only the standard library is used (pymupdf optionally, for PDFs).
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "Mozilla/5.0 paper-blueprint (novelty assessment)"}

NET_PROBES = [
    ("arXiv API", "https://export.arxiv.org/api/query?search_query=all:quantum&max_results=1"),
    ("OpenAlex", "https://api.openalex.org/works?search=quantum&per-page=1&select=id"),
    ("arXiv pages", "https://arxiv.org/abs/quant-ph/9508027"),
]

ARXIV_ID = re.compile(r"^(?:arxiv:)?((?:\d{4}\.\d{4,5}|[a-z][a-z.\-]*/\d{7})(?:v\d+)?)$", re.I)


def _get(url: str, timeout: int = 30) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.geturl()


def net_check() -> list[tuple[str, bool, str]]:
    out = []
    for name, url in NET_PROBES:
        try:
            data, _ = _get(url, timeout=15)
            out.append((name, True, f"{len(data)} bytes"))
        except Exception as exc:  # any failure means "not reachable from here"
            out.append((name, False, str(exc).splitlines()[0][:120]))
    return out


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def _date_digits(before: str | None) -> str | None:
    if not before:
        return None
    d = re.sub(r"\D", "", before)
    return (d + "1231")[:8] if len(d) == 4 else (d + "31")[:8] if len(d) == 6 else d[:8]


def search_arxiv(query: str, n: int = 8, before: str | None = None) -> list[dict]:
    terms = re.findall(r'"[^"]+"|\S+', query)
    q = " AND ".join(f"all:{t}" for t in terms)
    end = _date_digits(before)
    if end:
        q += f" AND submittedDate:[199101010000 TO {end}2359]"
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": q, "start": 0, "max_results": n, "sortBy": "relevance"})
    data, _ = _get(url)
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(data)
    out = []
    for e in root.findall("a:entry", ns):
        aid = (e.findtext("a:id", "", ns) or "").rsplit("/abs/", 1)[-1]
        jref = " ".join((e.findtext("arxiv:journal_ref", "", ns) or "").split())
        cat = e.find("arxiv:primary_category", ns)
        doi = e.findtext("arxiv:doi", "", ns)
        out.append({
            "title": " ".join((e.findtext("a:title", "", ns) or "").split()),
            "authors": _authors([a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)]),
            "year": (e.findtext("a:published", "", ns) or "")[:4],
            "venue": jref or ("arXiv " + cat.get("term") if cat is not None else "arXiv"),
            "url": f"https://arxiv.org/abs/{aid}",
            "ids": f"arXiv:{aid}" + (f" · doi:{doi}" if doi else ""),
            "abstract": " ".join((e.findtext("a:summary", "", ns) or "").split()),
        })
    return out


def search_openalex(query: str, n: int = 8, before: str | None = None) -> list[dict]:
    params = {"search": query, "per-page": n,
              "select": "id,doi,display_name,publication_year,authorships,primary_location,"
                        "abstract_inverted_index,cited_by_count,type"}
    end = _date_digits(before)
    if end:
        params["filter"] = f"to_publication_date:{end[:4]}-{end[4:6]}-{end[6:8]}"
    data, _ = _get("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
    out = []
    for w in json.loads(data).get("results", []):
        src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        inv = w.get("abstract_inverted_index") or {}
        words = sorted(((p, wd) for wd, ps in inv.items() for p in ps))
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        out.append({
            "title": w.get("display_name") or "",
            "authors": _authors([(a.get("author") or {}).get("display_name") or "" for a in w.get("authorships") or []]),
            "year": str(w.get("publication_year") or ""),
            "venue": " · ".join(x for x in (src, w.get("type") or "", f"cited by {w.get('cited_by_count', 0)}") if x),
            "url": w.get("doi") or w.get("id") or "",
            "ids": f"doi:{doi}" if doi else (w.get("id") or ""),
            "abstract": " ".join(wd for _, wd in words),
        })
    return out


def _authors(names: list[str]) -> str:
    names = [x for x in names if x]
    return ", ".join(names[:3]) + (" et al." if len(names) > 3 else "")


# ---------------------------------------------------------------------------
# full text and numbered results
# ---------------------------------------------------------------------------

def html_to_text(page: str) -> str:
    """Plain text of an HTML page; MathML is replaced by its LaTeX `alttext` (arXiv HTML, ar5iv)."""
    page = re.sub(r"(?is)<(script|style|head|nav|footer|header)\b.*?</\1>", " ", page)
    page = re.sub(r'(?is)<math\b[^>]*?alttext="([^"]*)"[^>]*>.*?</math>',
                  lambda mm: " $" + html.unescape(mm.group(1)) + "$ ", page)
    page = re.sub(r"(?i)<br\s*/?>|</?(?:p|div|h[1-6]|li|tr|section|article|blockquote|figcaption|table|dt|dd)\b[^>]*>",
                  "\n", page)
    page = html.unescape(re.sub(r"<[^>]+>", "", page))
    page = re.sub(r"[ \t\r\f\v ]+", " ", page)
    lines = [ln.strip() for ln in page.split("\n")]
    out, blank = [], False
    for ln in lines:
        if ln:
            out.append(ln)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    # LaTeXML puts the closing "." of a theorem head on its own line: "Theorem 2.1" / "." -> one line
    return re.sub(r"\n([.:])\n", r"\1\n", "\n".join(out))


def fetch_text(source: str) -> tuple[str, str]:
    """(plain text, where it came from).  SOURCE: arXiv id, http(s) URL, or a local .pdf/.html/.txt."""
    m = ARXIV_ID.match(source.strip())
    if m:
        aid = m.group(1)
        errors = []
        for url in (f"https://arxiv.org/html/{aid}", f"https://ar5iv.labs.arxiv.org/html/{aid}"):
            try:
                data, final = _get(url, timeout=60)
            except Exception as exc:
                errors.append(f"{url}: {str(exc).splitlines()[0][:100]}")
                continue
            page = data.decode("utf-8", errors="replace")
            if "ltx_document" not in page and "ltx_page" not in page:
                errors.append(f"{url}: no LaTeXML HTML (not converted)")
                continue
            text = html_to_text(page)
            # the version: in the URL after a redirect, else in the "arXiv:…vN [cat] date" stamp at the top
            ver = re.search(r"(\d{4}\.\d{4,5}v\d+|[a-z.\-]+/\d{7}v\d+)", final) or \
                re.search(r"arXiv:(\d{4}\.\d{4,5}v\d+|[a-z.\-]+/\d{7}v\d+)", text[:6000])
            via = "ar5iv" if "ar5iv" in final else "arXiv HTML"
            origin = f"{final} ({via}; {'arXiv:' + ver.group(1) if ver else 'latest arXiv version'})"
            return text, origin
        try:
            data, final = _get(f"https://arxiv.org/pdf/{aid}", timeout=90)
            return _pdf_text(data), f"{final} (arXiv PDF)"
        except Exception as exc:
            errors.append(f"pdf: {str(exc).splitlines()[0][:100]}")
        raise SystemExit("could not get a text version of arXiv:" + aid + "\n  " + "\n  ".join(errors) +
                         "\n  Read the PDF with your own tools instead (https://arxiv.org/pdf/" + aid + ").")
    if re.match(r"https?://", source):
        data, final = _get(source, timeout=60)
        if data[:4] == b"%PDF":
            return _pdf_text(data), final
        return html_to_text(data.decode("utf-8", errors="replace")), final
    with open(source, "rb") as fh:
        data = fh.read()
    if data[:4] == b"%PDF":
        return _pdf_text(data), source
    text = data.decode("utf-8", errors="replace")
    return (html_to_text(text) if re.search(r"(?i)<html|<body|<div", text[:5000]) else text), source


def _pdf_text(data: bytes) -> str:
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError:
            raise SystemExit("this source is a PDF and pymupdf is not installed (pip install pymupdf), "
                             "or read the PDF with your own tools")
    doc = pymupdf.open(stream=data, filetype="pdf")
    return "\n".join(f"[page {i + 1}]\n" + p.get_text() for i, p in enumerate(doc))


RESULT_HEAD = re.compile(
    r"^(Theorem|Lemma|Proposition|Corollary|Definition|Claim|Conjecture|Fact|Observation|Remark|Example|"
    r"Assumption|Hypothesis|Problem|Question|Algorithm|Construction|Exercise|Main Theorem)\s+"
    r"([A-Z]?\d+(?:\.\d+)*[a-z]?|[A-Z](?:\.\d+)?|[IVX]+)"
    r"(?:\s*(\([^()\n]{1,120}(?:\([^()\n]*\)[^()\n]*)*\)))?\s*(?:[.:](?=\s|$)|$)", re.M)


def numbered_results(text: str) -> list[dict]:
    """Numbered theorem-like heads at line starts, with the text that follows (up to the next head)."""
    heads = list(RESULT_HEAD.finditer(text))
    pages = [(mm.start(), int(mm.group(1))) for mm in re.finditer(r"^\[page (\d+)\]$", text, re.M)]
    out, seen = [], set()
    for k, mm in enumerate(heads):
        key = (mm.group(1), mm.group(2))
        end = heads[k + 1].start() if k + 1 < len(heads) else len(text)
        body = text[mm.end():min(end, mm.end() + 3000)]
        if key in seen:
            continue
        seen.add(key)
        page = next((p for pos, p in reversed(pages) if pos < mm.start()), None)
        out.append({"kind": mm.group(1), "number": mm.group(2), "title": (mm.group(3) or "").strip("() "),
                    "page": page, "text": " ".join(body.split())})
    return out
