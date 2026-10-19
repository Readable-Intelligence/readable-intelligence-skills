#!/usr/bin/env python3
"""Look at a built blueprint page in headless Chromium (optional helper).

Needs `pip install playwright && python3 -m playwright install chromium`.

  screenshot.py INDEX_HTML OUT.png [NODE_ID ...] [--expand] [--check-math]

* OUT.png             the whole graph
* OUT-<node>.png      for each NODE_ID: that node's modal, shown in full
                      (--expand also opens the Proof / Proof sketch sections)
* --check-math        open every node's modal, typeset it, and list MathJax errors
                      (undefined macros, unbalanced braces …) — run it after writing
                      LaTeX statements; nothing else will tell you about red formulas.

Pages built without --offline load d3 / MathJax from a CDN, so this needs network.
"""
import argparse
import asyncio
import os
import re
import sys

OPEN_NODE = """(id) => { const g = [...document.querySelectorAll('#graph .node')]
    .find(n => n.querySelector('title').textContent.trim() === id);
  if (!g) return false;
  g.dispatchEvent(new MouseEvent('click', {bubbles: true})); return true; }"""

TYPESET = r"""async (expand) => {
  if (expand) document.querySelectorAll('#modal-body details').forEach(d => d.open = true);
  const errs = [];
  const body = document.getElementById('modal-body');
  if (window.MathJax && MathJax.startup) {
    await MathJax.startup.promise;
    for (let attempt = 0; attempt < 3; attempt++) {
      try { await new Promise(r => setTimeout(r, 150)); await MathJax.typesetPromise([body]); break; }
      catch (e) { if (attempt === 2) errs.push('typeset exception: ' + e.message); }
    }
  }
  document.querySelectorAll('#modal-body [data-mml-node="merror"], #modal-body mjx-merror').forEach(e => {
    errs.push(e.getAttribute('data-mjx-error') || e.getAttribute('title') || e.textContent);
  });
  document.querySelectorAll('#modal-body [data-mml-node="mtext"][fill="red"]').forEach(e => {
    const txt = [...e.querySelectorAll('[data-c]')].map(u => String.fromCodePoint(parseInt(u.getAttribute('data-c'), 16))).join('');
    errs.push('undefined macro: ' + (txt || e.textContent || '?'));
  });
  const raw = document.getElementById('modal-body').innerText;
  const m = raw.match(/\\\(|\\\[|\\begin\{/);
  if (m) errs.push('math left untypeset (unbalanced braces or $?) near: ' + raw.slice(Math.max(0, m.index - 30), m.index + 50).replace(/\s+/g, ' '));
  return errs;
}"""

UNCLIP = """() => { for (const s of ['.dep-modal-container', '.dep-modal-content']) {
  const e = document.querySelector(s); e.style.maxHeight = 'none'; e.style.overflow = 'visible'; }
  return document.querySelector('.dep-modal-content').getBoundingClientRect().bottom; }"""


async def main(a):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": a.width, "height": a.height})
        console = []
        page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console.append(f"page error: {e}"))
        await page.goto("file://" + os.path.abspath(a.html))
        await page.wait_for_selector("#graph .node", timeout=90000)
        await page.wait_for_timeout(1200)
        await page.screenshot(path=a.out)
        print(f"wrote {a.out}")
        root, ext = os.path.splitext(a.out)
        for nid in a.nodes:
            if not await page.evaluate(OPEN_NODE, nid):
                print(f"node {nid} not found in graph", file=sys.stderr)
                continue
            await page.wait_for_timeout(400)
            errs = await page.evaluate(TYPESET, a.expand)
            bottom = await page.evaluate(UNCLIP)
            await page.set_viewport_size({"width": a.width, "height": max(a.height, int(bottom) + 40)})
            await page.wait_for_timeout(300)
            fn = f"{root}-{re.sub(r'[^A-Za-z0-9.]+', '_', nid)}{ext}"
            await page.locator(".dep-modal-content").screenshot(path=fn)
            await page.set_viewport_size({"width": a.width, "height": a.height})
            print(f"wrote {fn}" + (f"   MathJax errors: {errs}" if errs else ""))
            await page.keyboard.press("Escape")
        if a.check_math:
            ids = await page.evaluate("() => JSON.parse(document.getElementById('bp-data').textContent).order")
            bad = 0
            for nid in ids:
                await page.evaluate("() => { location.hash = ''; }")
                if not await page.evaluate(OPEN_NODE, nid):
                    continue
                try:
                    errs = await page.evaluate(TYPESET, True)
                except Exception as exc:  # keep going; report the node
                    errs = [f"check failed: {str(exc).splitlines()[0]}"]
                if errs:
                    bad += 1
                    print(f"MathJax errors in {nid}: {errs}")
                await page.keyboard.press("Escape")
            if await page.evaluate("() => !!document.getElementById('glossary-btn') && "
                                   "document.getElementById('glossary-btn').style.display !== 'none'"):
                await page.click("#glossary-btn")
                errs = await page.evaluate(TYPESET, False)
                if errs:
                    bad += 1
                    print(f"MathJax errors in the notation table: {errs}")
                await page.keyboard.press("Escape")
            print(f"math check: {len(ids) - bad}/{len(ids)} nodes typeset cleanly (and the notation table)")
        for e in console[:20]:
            print("console:", e)
        await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html")
    ap.add_argument("out")
    ap.add_argument("nodes", nargs="*")
    ap.add_argument("--expand", action="store_true", help="open Proof / Proof sketch in modal shots")
    ap.add_argument("--check-math", action="store_true", help="typeset every modal and report MathJax errors")
    ap.add_argument("--width", type=int, default=1400)
    ap.add_argument("--height", type=int, default=900)
    asyncio.run(main(ap.parse_args()))
