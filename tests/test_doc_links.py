"""Every link and anchor in the project's markdown points somewhere.

A link that points nowhere is a promise the reader cannot keep.
"""

import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]

LINK = re.compile(r'\[[^\]]*\]\(([^)]+)\)')


def slug(heading):
    text = heading.strip().lower()
    text = re.sub(r'[^a-z0-9 _\-]', '', text)
    text = re.sub(r'[ \-]+', '-', text)
    return text.strip('-')


def anchors_of(path):
    found = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        match = re.match(r'^#{1,6}\s+(.*)', line)
        if match:
            found.add(slug(match.group(1)))
    return found


def broken_links():
    broken = []
    for file in sorted(PROJECT.glob('**/*.md')):
        if '.git' in file.parts or '.pytest_cache' in file.parts:
            continue
        for number, line in enumerate(
                file.read_text(encoding='utf-8').splitlines(), start=1):
            for target in LINK.findall(line):
                if target.startswith(('http://', 'https://')):
                    continue
                path_part, _, anchor = target.partition('#')
                target_file = ((file.parent / path_part).resolve()
                               if path_part else file)
                if not target_file.exists():
                    broken.append(f'{file.name}:{number} missing file {target}')
                elif anchor and target_file.suffix == '.md' \
                        and anchor not in anchors_of(target_file):
                    broken.append(f'{file.name}:{number} missing anchor {target}')
    return broken


def test_no_link_in_the_docs_is_broken():
    assert broken_links() == []
