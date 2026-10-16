<div align="center">

# Readable Intelligence Skills & Demo Papers

**From AI-generated mathematics to human understanding.**

[![Website](https://img.shields.io/badge/website-readable--intelligence.com-1f6feb)](https://readable-intelligence.com)
[![Skill](https://img.shields.io/badge/skill-restructure--paper-8250df)](skills/restructure-paper/SKILL.md)
[![Demos](https://img.shields.io/badge/demo%20papers-5-2da44e)](#demo-papers)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)

[Website](https://readable-intelligence.com) ·
[Skill](skills/restructure-paper/SKILL.md) ·
[Download](downloads/readable-v4.zip) ·
[Demos](#demo-papers) ·
[Contributing](CONTRIBUTING.md) ·
[Licensing](LICENSES.md)

</div>

---

This is the public contribution repository for [Readable Intelligence](https://readable-intelligence.com). It holds our paper-rewriting skill and the five demo papers featured on the site.

## Current skill

**Readable Intelligence Skill (Current Version)** reorganizes proof-based mathematics and theoretical computer science papers for research readers. Statements and complete arguments are kept intact.

| | |
| --- | --- |
| 📖 **Read** | [`SKILL.md`](skills/restructure-paper/SKILL.md) and its [reference files](skills/restructure-paper/references/) |
| 📦 **Download** | [`readable-v4.zip`](downloads/readable-v4.zip), the same file offered on the website |
| ⚙️ **Install** | Unzip to get `restructure-paper/`, then install it as a skill in your AI tool |
| 📝 **Input** | A manuscript |

```bash
unzip downloads/readable-v4.zip   # → restructure-paper/
```

## Demo papers

Each pair below is the original manuscript next to its Readable Version, exactly as deployed on the site.

| Family | Paper | Original | Readable Version |
| :---: | --- | :---: | :---: |
| 003 | The Quasi-Riemann Hypothesis: A Zero-Free Half-Plane ℜs > 7/8 | [PDF](demos/003/original.pdf) | [PDF](demos/003/readable.pdf) |
| 102 | The Unique Games Theorem | [PDF](demos/102/original.pdf) | [PDF](demos/102/readable.pdf) |
| 074 | Every four-dimensional Kakeya set has full Hausdorff dimension | [PDF](demos/074/original.pdf) | [PDF](demos/074/readable.pdf) |
| 107 | An Upper Bound of 9/4 for the Matrix Multiplication Exponent | [PDF](demos/107/original.pdf) | [PDF](demos/107/readable.pdf) |
| 260 | The spacetime Penrose inequality and enclosing area | [PDF](demos/260/original.pdf) | [PDF](demos/260/readable.pdf) |

Source revisions and SHA-256 checksums are listed in [`demos/manifest.json`](demos/manifest.json). The full upstream collection of 722 manuscripts lives at [openai/math](https://github.com/openai/math).

## Contributing

You can propose a new skill, improve an existing one, or correct a demo by opening a pull request; [CONTRIBUTING.md](CONTRIBUTING.md) walks through the process. Maintainers review and merge accepted changes, then publish them to the website in a separate release step.

## Attribution and licensing

- **Demo manuscripts** are under [Apache-2.0](demos/LICENSE), with [attribution](demos/NOTICE) retained. Readable PDFs are modified editions, and each demo README says so.
- **The skill** was supplied without a separate license. [LICENSES.md](LICENSES.md) explains what that means for reuse and covers the full scope.
