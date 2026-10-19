#!/usr/bin/env python3
"""Check package integrity only. This does not certify editorial quality."""
from pathlib import Path
import re
import render_prompt

root = Path(__file__).resolve().parents[1]
failures = []
skill = (root/'SKILL.md').read_text()
if not skill.startswith('---\nname: restructure-paper\n'):
    failures.append('Missing or incorrect skill front matter')
for number, name in render_prompt.STAGES.items():
    path = root/'stages'/(name+'.md')
    text = path.read_text()
    if '## Acceptance' not in text or '## Procedure' not in text:
        failures.append(f'{name}: missing procedure/acceptance')
    prompt = render_prompt.render(number, root)
    if prompt.count('# Contract shared by every editing stage') != 1:
        failures.append(f'{name}: shared contract count')
    if number != '06' and ('## Abstract example' not in prompt):
        failures.append(f'{name}: examples absent from operational prompt')
complete = render_prompt.render('06', root)
positions = [complete.index('# Stage ' + number + ' —') for number in ['06','01','02','03','04','05']]
if positions != sorted(positions):
    failures.append('Complete prompt composition order')
for path in root.rglob('*.md'):
    for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if '://' in link or link.startswith('#'):
            continue
        target = link.split('#')[0]
        if target and not (path.parent/target).exists():
            failures.append(f'Broken local link: {path.name}: {link}')
if failures:
    raise SystemExit('\n'.join(failures))
print('Package integrity checks passed. Editorial qualification requires the actual experiments and independent reviews.')
