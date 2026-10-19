#!/usr/bin/env python3
"""Render the exact, self-contained editor prompt used in production and trials."""
import argparse
from pathlib import Path

STAGES = {
    '01': '01-terminology', '02': '02-statements', '03': '03-architecture',
    '04': '04-local-proofs', '05': '05-contribution', '06': '06-complete-repair',
}

def render(stage, root):
    names = ['06'] + list(STAGES)[:5] if stage == '06' else [stage]
    parts = [(root / 'stages/common.md').read_text()]
    for key in names:
        parts.append((root / 'stages' / (STAGES[key] + '.md')).read_text())
        example = root / 'examples' / (STAGES[key] + '.md')
        if example.exists():
            parts.append(example.read_text())
    return '\n\n---\n\n'.join(parts).rstrip() + '\n'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=STAGES)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    content = render(args.stage, Path(__file__).resolve().parents[1])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    else:
        print(content, end='')
